# SPDX-License-Identifier: GPL-3.0-or-later
"""What a dotted name stands for, and whether a decoded value reaches a run.

Two questions :mod:`blend_xray.explain` used to answer by pattern-matching on
text alone, and got wrong in both directions on real add-on code. Pure
:mod:`ast` and dictionary lookups; nothing here imports, executes or evaluates
anything found in a file.

Is this dotted name a module reference?
---------------------------------------
The rule tables list module names, and the matcher treats a collected *call*
name as a module reference whenever it sits under a table entry on a dotted
boundary. That is true of ``socket.socket()`` and false of
``socket.default_value_set()`` -- and the second is what Blender add-on code
writes, because ``socket`` is the name of the node-socket type and one of the
most common local variable names in the ecosystem::

    socket = node.inputs.new('NodeSocketFloat', 'Scale')
    socket.default_value_set(1.0)

That produced ``ALARMING x_network | connects to the internet`` and the loudest
banner the tool has, on a file that opens nothing, and it was found in the wild
on ``BradyAJohnston/MolecularNodes``. Renaming the variable made it vanish,
which is the signature of a rule keyed on a name rather than on a fact.

``socket`` is not special. Every table entry that is also a plausible
identifier -- ``pickle``, ``codecs``, ``types``, ``requests``, ``mmap``,
``compile`` -- carries the same exposure. The fix is therefore general: before
a call name may be read as a module reference, its root has to be a name this
body actually bound to a module, via :func:`resolve_call_name`.

Aliasing is handled rather than left as a hole. ``import socket as sk`` binds
``sk``, ``from urllib import request`` binds ``request``, and a plain
rebinding (``s = socket``) is followed one chain further through
:func:`resolve_alias` -- otherwise the check would be defeated by the same one
line that defeats every other name-keyed rule in the tool.

Does this decode feed that exec?
--------------------------------
See :func:`find_decode_source`.
"""

from __future__ import annotations

import ast
from typing import Final

from .astutil import dotted_name
from .explain_rules import DECODE_CALLS

#: How far an alias chain is followed before we give up. Bounds a cycle
#: (``a = b`` / ``b = a``) without needing to remember where we have been.
_MAX_ALIAS_HOPS: Final = 8

#: Roots a body may dot into without an ``import`` statement of its own.
#:
#: Two kinds, and nothing else may be added without one of these two reasons:
#:
#: * Python builtins that the rule tables name or reach through -- ``exec``,
#:   ``compile``, ``bytes.fromhex``. There is no import to find for these, so
#:   requiring one would silently disable the loudest rules in the tool.
#: * ``bpy``. Blender puts it in the namespace a driver expression is evaluated
#:   in, and a driver expression cannot contain an import statement, so a
#:   driver that reads ``bpy.context.scene`` has no binding for us to find.
#:
#: Note what is *not* here: ``os``, ``socket``, ``subprocess``, ``pickle`` and
#: every other module. A body that uses one of those has to import it, and
#: that import is the fact this module makes the rules depend on.
IMPORT_FREE_ROOTS: Final[frozenset[str]] = frozenset(
    {
        "exec",
        "eval",
        "compile",
        "open",
        "getattr",
        "setattr",
        "hasattr",
        "vars",
        "globals",
        "locals",
        "__import__",
        "bytes",
        "bytearray",
        "str",
        "bpy",
    }
)


def resolve_alias(name: str, aliases: dict[str, str]) -> str:
    """Follow ``name`` through a plain-rebinding map to what it stands for."""
    seen = name
    for _ in range(_MAX_ALIAS_HOPS):
        head, dot, rest = seen.partition(".")
        target = aliases.get(head)
        if target is None:
            return seen
        seen = target + dot + rest
    return seen


def table_hit(name: str, table: frozenset[str]) -> bool:
    """True when ``name`` is in ``table`` exactly, or sits under it dotted.

    The dotted boundary is what makes ``subprocess`` match
    ``subprocess.Popen`` and not ``subprocess_helper``. It also means a bare
    package name in a table swallows every submodule beneath it, which is why
    :data:`~blend_xray.explain_rules.NETWORK_MODULES` lists ``urllib.request``
    and never ``urllib``.
    """
    return any(name == entry or name.startswith(entry + ".") for entry in table)


def import_bindings(tree: ast.AST) -> dict[str, str]:
    """``{local name: the module path it was bound to}`` for the whole body.

    ``import socket`` binds ``socket``; ``import os.path`` binds only ``os``,
    the way Python does; ``import urllib.request as ur`` binds ``ur`` to
    ``urllib.request``; ``from urllib import request`` binds ``request`` to
    ``urllib.request``; ``from socket import socket`` binds ``socket`` to
    ``socket.socket``.

    Every import in the body is read, including ones nested in a function or a
    ``try``, because "was this root ever bound to a module here" is a question
    about the file and not about one code path.

    Relative imports are skipped: ``from .socket import connect`` names a
    module *inside the add-on*, and recording it as ``socket.connect`` would
    invent a network finding out of a sibling file that happens to share a
    stdlib name. A relative import can never reach the modules these tables
    are about, so dropping it loses nothing.
    """
    bindings: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.asname:
                    bindings[alias.asname] = alias.name
                else:
                    head = alias.name.partition(".")[0]
                    bindings[head] = head
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            for alias in node.names:
                if alias.name != "*":
                    bindings[alias.asname or alias.name] = f"{node.module}.{alias.name}"
    return bindings


def resolve_call_name(
    name: str, bindings: dict[str, str], aliases: dict[str, str], ambient: bool = False
) -> str | None:
    """Return the module-qualified name a call refers to, or ``None``.

    ``None`` means "the root of this name was never bound to a module in this
    body", which is the honest answer for ``socket.default_value_set`` in a
    file that never imports ``socket``. Callers must treat it as "not a module
    reference", never as "not interesting".

    A plain rebinding is followed first (``s = socket`` then ``s.socket()``),
    but only when the root is not itself an import binding -- an import wins
    over a later local assignment, so shadowing a module name cannot hide a
    real use of it.

    ``ambient`` says the body was handed a namespace it did not build, so an
    unbound root is taken at face value instead of being refused. That is a
    driver expression: Blender evaluates it against a namespace assembled
    elsewhere, and a driver *cannot* contain an import statement, so demanding
    one would silence every module rule on exactly the path a payload uses. It
    costs nothing in precision there, because a driver is one expression and
    cannot contain an assignment either -- the local variable this whole check
    exists to stop being mistaken for a module cannot be created in one.
    """
    if not name:
        return None
    head = name.partition(".")[0]
    if head not in bindings and head in aliases:
        name = resolve_alias(name, aliases)
        head = name.partition(".")[0]
    target = bindings.get(head)
    if target is not None:
        return target + name[len(head) :]
    return name if ambient or head in IMPORT_FREE_ROOTS else None


#: Nodes :func:`find_decode_source` will look at inside one argument before
#: giving up. This search runs once per ``exec``/``eval`` argument and returns
#: the moment it finds something, so the only body that reaches the cap is one
#: with no decode in it -- and a hostile file can nest those calls up to the
#: parser's own limit (``MAX_NESTING_DEPTH``, 180), which without a cap would
#: make the work depth times body size. Giving up costs a finding this analysis
#: was never promising past one hop; not giving up costs the wall-clock budget
#: the user asked for.
MAX_DATAFLOW_NODES: Final = 2_000


def find_decode_source(
    node: ast.AST,
    bindings: dict[str, str],
    aliases: dict[str, str],
    decoded: dict[str, str],
    ambient: bool = False,
) -> str | None:
    """Name the decode whose result reaches ``node``, or ``None``.

    ``node`` is an argument of a call that runs code. The answer is a decode
    call written inside that argument, or a name -- plain or dotted, so
    ``self.payload`` counts -- that was bound to an expression containing one.
    One binding hop, no further.

    ``ambient`` carries the same meaning as in :func:`resolve_call_name` and
    must be threaded through: a driver expression cannot import ``base64``, so
    leaving it off here would find no decode inside one and quietly downgrade
    ``exec(base64.b64decode(BLOB))`` in a driver.
    """
    for seen, child in enumerate(ast.walk(node)):
        if seen >= MAX_DATAFLOW_NODES:
            return None
        if isinstance(child, ast.Call):
            callee = resolve_call_name(dotted_name(child.func), bindings, aliases, ambient)
            if callee is not None and table_hit(callee, DECODE_CALLS):
                return f"{callee}(...)"
        elif isinstance(child, (ast.Attribute, ast.Name)):
            # Attribute first, because ``ast.walk`` reaches ``self.payload``
            # before the ``self`` inside it, and the binding was recorded
            # under the whole dotted target.
            held = dotted_name(child)
            bound = decoded.get(held) if held else None
            if bound is not None:
                return f"{held} = {bound}(...)"
    return None


def decoded_bindings(
    assigned: list[tuple[str, ast.Call]],
    bindings: dict[str, str],
    aliases: dict[str, str],
    ambient: bool = False,
) -> dict[str, str]:
    """``{local name: the decode that produced it}`` for one hop of dataflow.

    The decode is looked for anywhere inside the expression that produced the
    bound value, not only as its outermost callee, because the shape that
    matters most writes the decode inside another call::

        code = zlib.decompress(base64.b64decode(BLOB)).decode('utf-8')

    Here the outermost callee is an attribute of a call, which
    :func:`blend_xray.astutil.dotted_name` cannot name at all.
    """
    out: dict[str, str] = {}
    for name, call in assigned:
        for child in ast.walk(call):
            if not isinstance(child, ast.Call):
                continue
            callee = resolve_call_name(dotted_name(child.func), bindings, aliases, ambient)
            if callee is not None and table_hit(callee, DECODE_CALLS):
                out[name] = callee
                break
    return out
