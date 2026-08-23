# SPDX-License-Identifier: GPL-3.0-or-later
"""Gather the facts :mod:`blend_xray.explain` needs. Collection only, no judgement.

Split out of :mod:`blend_xray.explain` when the collector grew past the point
where "what did we see" and "what do we say about it" could share a screen.
Nothing here decides a severity or writes a sentence; every attribute below is
raw observation, and the rule tables in :mod:`blend_xray.explain_rules` decide
what it means.

Pure :mod:`ast`. Nothing is imported, executed or evaluated.

On the limits of the shapes collected here
------------------------------------------
Four of them (:attr:`Collector.builtins_indirection`,
:attr:`Collector.indirect_calls`, :attr:`Collector.assembled_names`,
:attr:`Collector.split_literals`) do not describe what a script *does*. They
describe a script arranging for a reader like this one not to be able to tell.
Recording the shape of the obfuscation is the only move available once the
names are gone, and it is a partial one: it raises the cost of hiding, it does
not close the door. The README says so in the author's own words rather than
leaving a reader to discover it.
"""

from __future__ import annotations

import ast

from .astutil import dotted_name
from .explain_rules import (
    BUILTINS_NAMES,
    DYNAMIC_CODE_CALLS,
    INDIRECTION_CALLS,
    NAME_TAKING_CALLS,
    RUNTIME_IMPORT_CALLS,
)
from .resolve import (
    decoded_bindings,
    find_decode_source,
    import_bindings,
    resolve_alias,
    resolve_call_name,
    table_hit,
)

#: Spellings of the ``@persistent`` decorator that need no import tracking.
#: ``from bpy.app.handlers import persistent as keep_me`` is picked up
#: separately, in :meth:`Collector.visit_ImportFrom`.
PERSISTENT_SPELLINGS: frozenset[str] = frozenset(
    {"persistent", "handlers.persistent", "app.handlers.persistent", "bpy.app.handlers.persistent"}
)

#: The handler-list methods that *install* a callback. ``remove`` is excluded
#: on purpose: unregister code calls it, and an uninstall is not an install.
HANDLER_INSTALL_METHODS: frozenset[str] = frozenset({"append", "insert"})

_HANDLERS_PREFIX = "bpy.app.handlers."


def _string_concat(node: ast.AST) -> str | None:
    """Return the text of a ``+`` chain of string literals, else ``None``.

    ``"__imp" + "ort__"`` reduces to ``"__import__"``. Adjacent literals
    (``"a" "b"``) are folded by the parser into one constant long before this
    sees them, so a wrapped long string in ordinary code cannot reach here --
    only an explicit ``+`` between two literals can, and across the 100
    parseable script bodies in both corpora that happens zero times.
    """
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left = _string_concat(node.left)
        right = _string_concat(node.right)
        if left is not None and right is not None:
            return left + right
    return None


def _is_literal_concat(node: ast.AST) -> bool:
    """True for a ``+`` of string literals, false for a lone literal."""
    return isinstance(node, ast.BinOp) and _string_concat(node) is not None


def scan_bindings(tree: ast.AST) -> tuple[dict[str, str], list[tuple[str, ast.Call]]]:
    """Read every simple binding in one walk.

    Returns ``({local name: the name it was bound to}, [(name, call)])``: plain
    rebindings, and the names bound to the result of a call.

    ``g = getattr`` is one statement and it takes every name-keyed rule in this
    file out of play, because from then on the call reads ``g(...)`` and
    ``getattr`` never appears as a callee again. The evasion PoC opens with
    exactly that line. Read in a pass of its own so that a rebinding is
    honoured wherever it sits relative to the uses -- a collector that learned
    as it walked would miss ``f()`` on the line above ``f = exec``.

    One walk, not two: the second fact (which names hold a call's result)
    cannot be classified until the alias map is complete, but it can be
    *collected* alongside it, and a second ``ast.walk`` over a 10,000-node
    body costs about as much as the whole visit that follows.

    The two halves have deliberately different reach.

    *Rebindings* stay narrow -- only a lone ``name = <name>`` or
    ``name = <a.b.c>`` -- because :func:`~blend_xray.resolve.resolve_alias`
    keys on a bare root name and has nothing to do with a dotted target.

    *Call results* are recorded for every simple target of the assignment,
    including an attribute and including each target of ``a = b = f()``.
    Restricting this half to a bare local name cost the ``x_obfuscation``
    link its most ordinary shape -- ``self.payload = b64decode(BLOB)`` in one
    method and ``exec(self.payload)`` in the next is how a class writes it,
    and one attribute was enough to drop the finding from RED to AMBER.

    Still shallow, and it makes no attempt at real dataflow, which static
    analysis of a hostile file does not win: a target this cannot name --
    ``d['payload']``, or a tuple unpack -- is not recorded at all. The README
    says so in the author's own words.
    """
    aliases: dict[str, str] = {}
    calls: list[tuple[str, ast.Call]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            targets: list[ast.expr] = list(node.targets)
            value = node.value
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            targets, value = [node.target], node.value
        else:
            continue
        if isinstance(value, (ast.Name, ast.Attribute)):
            if len(targets) == 1 and isinstance(targets[0], ast.Name):
                source = dotted_name(value)
                if source:
                    aliases[targets[0].id] = source
        elif isinstance(value, ast.Call):
            for target in targets:
                bound = dotted_name(target)
                if bound:
                    calls.append((bound, value))
    return aliases, calls


def _builtins_target(node: ast.AST, aliases: dict[str, str]) -> str | None:
    """Return the name if ``node`` is the builtins namespace, else ``None``."""
    if isinstance(node, ast.Name):
        resolved = resolve_alias(node.id, aliases)
        return node.id if resolved in BUILTINS_NAMES else None
    if isinstance(node, ast.Attribute) and node.attr in BUILTINS_NAMES:
        return node.attr
    return None


def _indirection_base(func: ast.AST, aliases: dict[str, str], tainted: set[str]) -> str | None:
    """Name of the indirection call whose *result* ``func`` is reaching into.

    ``getattr(m, "system")(...)`` gives ``getattr``;
    ``__import__("os").system(...)`` gives ``__import__`` -- the second is the
    shape that makes :func:`blend_xray.astutil.dotted_name` return ``""`` and
    so hides ``os.system`` from every name table in the tool. Walking the
    attribute chain down to its base is what recovers it.

    Restricted to :data:`~blend_xray.explain_rules.INDIRECTION_CALLS` on
    purpose. "A call whose callee is any call" is not rare: CloudRig writes
    ``type(frames)(...)`` and that shape appears in 20 of the 100 parseable
    corpus bodies. Keyed on the inner callee it appears in none.

    ``tainted`` extends this by exactly one binding: a name that was assigned
    the result of reaching into the builtins namespace, or of a runtime
    import, is treated as that result when it is later called. ``i =
    getattr(__builtins__, "__import__")`` followed by ``i("urllib.request")``
    is the PoC's own shape.
    """
    node = func
    while isinstance(node, ast.Attribute):
        node = node.value
    if isinstance(node, ast.Name) and node.id in tainted:
        return node.id
    if not isinstance(node, ast.Call):
        return None
    name = resolve_alias(dotted_name(node.func), aliases)
    return name if name in INDIRECTION_CALLS else None


class Collector(ast.NodeVisitor):
    """Every fact the rule tables consult, and nothing else."""

    def __init__(self, *, ambient_names: bool = False) -> None:
        #: The body was handed a namespace it did not build, so a dotted name
        #: whose root has no import here is still read as a module reference.
        #: True only for driver expressions -- see
        #: :func:`blend_xray.resolve.resolve_call_name`.
        self.ambient_names = ambient_names
        self.imports: set[str] = set()
        self.calls: set[str] = set()
        self.attributes: set[str] = set()
        self.strings: list[str] = []
        self.class_bases: set[str] = set()
        self.decorators: set[str] = set()
        self.write_modes: set[str] = set()
        #: Runtime imports whose target name is computed rather than written.
        self.dynamic_import_nonliteral = False
        #: Runtime imports naming their target with a plain string literal.
        self.dynamic_import_literal: set[str] = set()
        #: Functions carrying ``@persistent``, by name.
        self.persistent_functions: set[str] = set()
        #: Local spellings of the decorator, extended by aliased imports.
        self.persistent_aliases: set[str] = set(PERSISTENT_SPELLINGS)
        #: ``(handler list, callback name)`` for each install we could read.
        self.handler_installs: list[tuple[str, str]] = []
        self.builtins_indirection: list[str] = []
        self.indirect_calls: list[str] = []
        self.assembled_names: list[str] = []
        self.split_literals: list[str] = []
        #: ``{local name: what it was rebound to}``; see :func:`build_alias_map`.
        self.aliases: dict[str, str] = {}
        #: ``{local name: the module path it was imported from}``. What lets
        #: the rule layer tell ``socket.socket()`` from a method call on a
        #: local variable that happens to be named ``socket``.
        self.import_bindings: dict[str, str] = {}
        #: Names holding the result of reaching into the builtins namespace.
        self.tainted: set[str] = set()
        #: ``{local name: the decode call that produced it}``, one hop.
        self.decode_bindings: dict[str, str] = {}
        #: Evidence that a decoded value reached a call that runs code.
        self.decoded_then_run: list[str] = []
        #: ``id()`` of concat nodes already covered by an enclosing chain.
        self._covered_concats: set[int] = set()

    def analyse(self, tree: ast.AST) -> None:
        """Read the bindings, then walk. Use this instead of :meth:`visit`.

        A preparatory pass rather than learning as we go, because every fact
        it establishes can be written *after* the line that uses them, and a
        single-pass collector would read the file in the attacker's preferred
        order. The import bindings in particular have to be whole before the
        first call is judged: ``import socket`` at the bottom of a file still
        governs a ``socket.socket()`` at the top.
        """
        self.aliases, assigned_calls = scan_bindings(tree)
        self.import_bindings = import_bindings(tree)
        # Resolved after the alias map is whole: `g = getattr` may sit below
        # `i = g(__builtins__, ...)`.
        self.tainted = {
            name for name, call in assigned_calls if self._is_tainting_call(call)
        }
        self.decode_bindings = decoded_bindings(
            assigned_calls, self.import_bindings, self.aliases, self.ambient_names
        )
        self.visit(tree)

    def resolve(self, name: str) -> str | None:
        """The module-qualified form of ``name``, or ``None`` if it is not one."""
        return resolve_call_name(
            name, self.import_bindings, self.aliases, self.ambient_names
        )

    def resolved_calls(self) -> list[tuple[str, str]]:
        """``(resolved name, name as written)`` for every call we could ground.

        Calls whose root was never bound to a module here are dropped, because
        the rule tables are tables of *modules* and a name that stands for a
        local variable is not one of them. Sorted so evidence is stable.
        """
        pairs = []
        for written in sorted(self.calls):
            resolved = self.resolve(written)
            if resolved is not None:
                pairs.append((resolved, written))
        return pairs

    def _is_tainting_call(self, call: ast.Call) -> bool:
        """True when this call hands back a capability reached indirectly.

        Narrow on purpose. ``func = getattr(bone, name)`` followed by
        ``func()`` is ordinary rig code, so an ordinary ``getattr`` result is
        not tainted; only a lookup against ``__builtins__``/``builtins``, or
        an import performed at run time, is. Both are zero-occurrence shapes
        across the two corpora, which is what lets the statements they feed be
        loud.
        """
        callee = resolve_alias(dotted_name(call.func), self.aliases)
        if callee in RUNTIME_IMPORT_CALLS:
            return True
        if callee not in INDIRECTION_CALLS or not call.args:
            return False
        return _builtins_target(call.args[0], self.aliases) is not None

    # -- imports, names, literals ------------------------------------------
    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self.imports.add(alias.name)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        """Absolute imports only. ``from .socket import connect`` is a sibling.

        ``node.level`` counts the leading dots. A relative import names a
        module inside the add-on's own package, so recording ``socket`` for it
        handed an add-on that ships its own ``socket.py`` the RED "connects to
        the internet" banner on the strength of a file name. A relative import
        can never reach the stdlib modules these tables are about.
        """
        if node.module and not node.level:
            self.imports.add(node.module)
            for alias in node.names:
                self.imports.add(f"{node.module}.{alias.name}")
                if alias.name == "persistent" and node.module.endswith("app.handlers"):
                    self.persistent_aliases.add(alias.asname or alias.name)
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        name = dotted_name(node)
        if name:
            self.attributes.add(name)
        base = _builtins_target(node.value, self.aliases)
        if base is not None and node.attr.startswith("__"):
            self.builtins_indirection.append(f"{base}.{node.attr}")
        self.generic_visit(node)

    def visit_Subscript(self, node: ast.Subscript) -> None:
        base = _builtins_target(node.value, self.aliases)
        if base is not None:
            self.builtins_indirection.append(f"{base}[...]")
        self.generic_visit(node)

    def visit_Constant(self, node: ast.Constant) -> None:
        if isinstance(node.value, str):
            self.strings.append(node.value)
        elif isinstance(node.value, bytes):
            self.strings.append(node.value.decode("latin-1", errors="replace"))
        self.generic_visit(node)

    def visit_BinOp(self, node: ast.BinOp) -> None:
        """Record the finished text of a literal concatenation, once.

        The visitor descends parents first, so the outermost ``+`` chain is
        seen before its parts. Marking its inner nodes as covered keeps the
        evidence to ``http://x.example.com/p`` instead of that plus every one
        of the eight prefixes it was built from.
        """
        joined = _string_concat(node) if isinstance(node.op, ast.Add) else None
        if joined is not None and id(node) not in self._covered_concats:
            self.split_literals.append(joined[:60])
            for child in ast.walk(node):
                if isinstance(child, ast.BinOp) and child is not node:
                    self._covered_concats.add(id(child))
        self.generic_visit(node)

    # -- definitions -------------------------------------------------------
    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        for base in node.bases:
            name = dotted_name(base)
            if name:
                self.class_bases.add(name)
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        for dec in node.decorator_list:
            target = dec.func if isinstance(dec, ast.Call) else dec
            name = dotted_name(target)
            if name:
                self.decorators.add(name)
            if name in self.persistent_aliases:
                self.persistent_functions.add(node.name)
        self.generic_visit(node)

    visit_AsyncFunctionDef = visit_FunctionDef  # type: ignore[assignment]

    # -- calls -------------------------------------------------------------
    def visit_Call(self, node: ast.Call) -> None:
        name = dotted_name(node.func)
        if name:
            self.calls.add(name)
        if name in {"open", "io.open", "codecs.open"}:
            self._record_open_mode(node)
        self._record_runtime_import(name, node)
        self._record_handler_install(name, node)
        self._record_evasion(name, node)
        self._record_decode_link(name, node)
        self.generic_visit(node)

    def _record_decode_link(self, name: str, node: ast.Call) -> None:
        """Record only a decode whose result actually reaches this execution.

        Co-occurrence is not a link. ``Sandman13sq/DmrVBM-blender-to-gms2``
        has a real ``exec()`` and real ``zlib`` calls in the same file, and the
        ``zlib`` calls compress mesh and image data that never goes near it --
        yet the file was escalated to RED and told an artist its content was
        "deliberately hidden", on the strength of two calls that have nothing
        to do with each other.

        So the link is established rather than assumed: the decode has to be
        written inside an argument of the call that runs code, or be one
        binding away from it (``payload = b64decode(BLOB)`` then
        ``exec(payload)``). Deliberately one hop and no more -- real dataflow
        analysis of a hostile file is not a fight static analysis wins, and a
        deeper chase would only move the line at which we start guessing.

        Nothing is silenced by failing to find a link. ``exec`` remains
        ALARMING under ``x_dynamic_code`` on its own, and the decode remains
        NOTABLE under ``x_decodes_data``; what the file no longer gets is the
        claim that the two are one hidden payload. The other half of the
        "hidden" reading -- an opaque blob sitting in the file -- is evidence
        in itself and keeps its own key.
        """
        resolved = self.resolve(name)
        if resolved is None or not table_hit(resolved, DYNAMIC_CODE_CALLS):
            return
        arguments = [*node.args, *(kw.value for kw in node.keywords)]
        for arg in arguments:
            source = find_decode_source(
                arg,
                self.import_bindings,
                self.aliases,
                self.decode_bindings,
                self.ambient_names,
            )
            if source is not None:
                self.decoded_then_run.append(f"{source} then {name or resolved}(...)")
                return

    def _record_runtime_import(self, name: str, node: ast.Call) -> None:
        if name not in RUNTIME_IMPORT_CALLS:
            return
        first = node.args[0] if node.args else None
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            self.dynamic_import_literal.add(f"{name}({first.value!r})")
        elif first is not None:
            self.dynamic_import_nonliteral = True

    def _record_handler_install(self, name: str, node: ast.Call) -> None:
        if not name.startswith(_HANDLERS_PREFIX):
            return
        head, _, method = name.rpartition(".")
        if method not in HANDLER_INSTALL_METHODS or not node.args:
            return
        callback = dotted_name(node.args[-1])
        self.handler_installs.append((head, callback))

    def _record_evasion(self, name: str, node: ast.Call) -> None:
        """The three hiding shapes, read through any local rebinding.

        ``name`` is what the call is written as; ``callee`` is what it stands
        for once ``g = getattr`` has been followed. The rules key on the
        second, the evidence quotes the first, so a reader sees the line as it
        appears in the file.
        """
        callee = resolve_alias(name, self.aliases) if name else ""
        if callee in {"getattr", "setattr", "vars", "hasattr"} and node.args:
            base = _builtins_target(node.args[0], self.aliases)
            if base is not None:
                self.builtins_indirection.append(f"{name or callee}({base}, ...)")
        inner = _indirection_base(node.func, self.aliases, self.tainted)
        if inner is not None:
            self.indirect_calls.append(f"{inner}(...) result is called")
        if callee in NAME_TAKING_CALLS:
            for arg in node.args:
                if _is_literal_concat(arg):
                    joined = _string_concat(arg) or ""
                    self.assembled_names.append(f"{name or callee}(... {joined[:40]!r} ...)")

    def _record_open_mode(self, node: ast.Call) -> None:
        mode = ""
        if (
            len(node.args) > 1
            and isinstance(node.args[1], ast.Constant)
            and isinstance(node.args[1].value, str)
        ):
            mode = node.args[1].value
        for kw in node.keywords:
            if (
                kw.arg == "mode"
                and isinstance(kw.value, ast.Constant)
                and isinstance(kw.value.value, str)
            ):
                mode = kw.value.value
        if any(ch in mode for ch in ("w", "a", "x", "+")):
            self.write_modes.add(mode)

    # -- derived views the rule layer asks for -----------------------------
    def persistent_handler_evidence(self) -> list[str]:
        """Installs this file marked ``@persistent``, in Blender's own terms.

        Blender keeps a handler across a file load only when the callback
        object carries ``_bpy_persistent`` in its ``__dict__``, which is what
        the decorator sets and the only thing
        ``BPY_app_handlers_reset(false)`` looks at. An install whose callback
        we cannot resolve to a decorated function in this body is therefore
        *not* claimed as persistent -- the honest failure here is to say less.
        """
        hits = [
            f"{head}.append({callback}) with @persistent"
            for head, callback in self.handler_installs
            if callback in self.persistent_functions
        ]
        if not hits and self.persistent_functions and self.handler_attributes():
            hits = [f"@persistent on {name}()" for name in sorted(self.persistent_functions)]
        return hits

    def handler_attributes(self) -> list[str]:
        """Every ``bpy.app.handlers.*`` name touched, sorted."""
        return [a for a in sorted(self.attributes) if a.startswith(_HANDLERS_PREFIX)]
