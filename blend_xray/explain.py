# SPDX-License-Identifier: GPL-3.0-or-later
"""Explain, in plain language, what an extracted script actually does.

The audience is 3D artists who do not read Python. Printing raw source at them
reproduces the failure of Blender's own warning dialog: told "this is
dangerous" with no explanation, people conclude it must be a false alarm and
click through. So this module maps concrete Python constructs to sentences a
non-programmer can act on.

This is pure static analysis via :mod:`ast`. ``ast.parse`` builds a syntax tree
and does **not** execute the code. Nothing in this module runs, imports, or
evaluates anything found in a scanned file.

Every statement we emit carries the concrete evidence (the function called, the
literal found) so a technical friend can verify our claim.

One sentence per construct
--------------------------
The rule this module is now held to: a statement's sentence must be true of
*every* construct that can produce it. Where one key used to cover several
constructs -- ``compile()`` under "builds and runs code", a bare
``zlib.decompress`` under "deliberately hidden", a plain handler registration
under "keeps running on every file you open afterwards" -- the key has been
split so that each sentence is true of what actually matched it. Splitting the
key rather than softening the sentence keeps the loud cases loud.
"""

from __future__ import annotations

import ast
import dataclasses
import enum
import re
from typing import Final

from . import strings
from .astutil import MAX_NESTING_DEPTH, max_nesting
from .collect import Collector
from .explain_rules import (
    BENIGN_IMPORT_OPS,
    BROWSER_CALLS,
    CODE_BUILD_CALLS,
    CREDENTIAL_MARKERS,
    DECODE_CALLS,
    DELETE_CALLS,
    DESERIALISE_CALLS,
    DYNAMIC_CODE_CALLS,
    LIVING_OFF_LAND,
    LOWLEVEL_MODULES,
    MAKEDIR_CALLS,
    NETWORK_LISTEN_MODULES,
    NETWORK_MODULES,
    PERSISTENCE_MARKERS,
    SUBPROCESS_CALLS,
    UI_BASES,
    WRITE_CALLS,
)
from .literals import Budget, Literal, extract_literals
from .resolve import table_hit

__all__ = [
    "Budget",
    "Explanation",
    "Literal",
    "Severity",
    "Statement",
    "explain_source",
    "extract_literals",
]

#: Do not attempt to parse anything larger than this (2 MiB of source).
MAX_PARSE_BYTES: Final = 2 * 1024 * 1024


class Severity(enum.IntEnum):
    BENIGN = 0
    NOTABLE = 1
    ALARMING = 2


@dataclasses.dataclass(frozen=True)
class Statement:
    severity: Severity
    #: Stable catalogue key (e.g. ``x_network``). Machine-readable and
    #: translation-independent -- match on this, never on ``text``.
    key: str
    text: str
    evidence: tuple[str, ...] = ()


@dataclasses.dataclass(frozen=True)
class Explanation:
    parsed: bool
    statements: tuple[Statement, ...]
    literals: tuple[Literal, ...]
    obfuscated: bool
    parse_error: str | None = None
    note: str | None = None

    @property
    def max_severity(self) -> Severity:
        if not self.statements:
            return Severity.BENIGN
        return max(s.severity for s in self.statements)

    @property
    def alarming(self) -> bool:
        return self.max_severity is Severity.ALARMING


def _matches(names: set[str], table: frozenset[str]) -> list[str]:
    """Return the collected names that hit ``table`` exactly or by prefix.

    For sets that are already module names by construction: ``col.imports``,
    ``col.class_bases``, ``col.attributes``. **Not** for ``col.calls`` -- see
    :func:`_matches_calls`, which is what every call-name rule uses now.
    """
    return [name for name in sorted(names) if table_hit(name, table)]


def _matches_calls(col: Collector, table: frozenset[str]) -> list[str]:
    """Return the calls that hit ``table``, once grounded in a real import.

    The tables are tables of modules, and a dotted call name is only a module
    reference if its root was bound to a module in this body. Without that
    check, ``socket.default_value_set()`` on a local variable named ``socket``
    -- which is what Blender's own node-socket type is called, and so is
    ordinary add-on code -- matched the ``socket`` entry of
    :data:`~blend_xray.explain_rules.NETWORK_MODULES` and produced the RED
    "reaches outside Blender" banner. See :mod:`blend_xray.resolve`.

    Evidence quotes the call as written, so a reader can find the line; where
    an alias made the written form different from what it stands for, the
    resolved name is shown next to it rather than instead of it.
    """
    hits: list[str] = []
    for resolved, written in col.resolved_calls():
        if not table_hit(resolved, table):
            continue
        hits.append(written if written == resolved else f"{written} ({resolved})")
    return hits


#: Keys whose presence means "the code hides what it does", so the report can
#: say the list of statements is incomplete rather than implying it is whole.
OBFUSCATION_KEYS: Final = frozenset(
    {
        "x_obfuscation",
        "x_opaque_blob",
        "x_builtins_indirection",
        "x_indirect_call",
        "x_assembled_name",
    }
)


def _add(out: list[Statement], sev: Severity, key: str, evidence: list[str], **fmt: object) -> None:
    if not evidence:
        return
    out.append(Statement(sev, key, strings.t(key, **fmt), tuple(sorted(set(evidence))[:8])))


def _benign_statements(col: Collector, out: list[Statement]) -> None:
    _add(out, Severity.BENIGN, "x_import_geometry", _matches_calls(col, BENIGN_IMPORT_OPS))
    _add(out, Severity.BENIGN, "x_ui_panel", _matches(col.class_bases, UI_BASES))
    _add(
        out,
        Severity.BENIGN,
        "x_register",
        _matches_calls(col, frozenset({"bpy.utils.register_class", "bpy.utils.unregister_class"})),
    )
    _add(
        out,
        Severity.BENIGN,
        "x_driver_namespace",
        [a for a in sorted(col.attributes) if a.startswith("bpy.app.driver_namespace")],
    )


def _handler_statements(col: Collector, out: list[Statement]) -> None:
    """Two handler findings, because Blender treats the two cases differently.

    A callback appended to a ``bpy.app.handlers`` list survives the rest of
    this session and runs on Blender's own events. It does **not** survive the
    next file load unless it carries ``@persistent``: loading a file runs
    ``BPY_python_reset`` (``bpy_interface.cc:721``), which calls
    ``BPY_app_handlers_reset(false)`` and then ``BPY_modules_load_user`` -- so
    the strip happens *before* the incoming file's own scripts run.
    ``BPY_app_handlers_reset(false)`` keeps an entry only when the callback
    function's ``__dict__`` holds ``_bpy_persistent``
    (``bpy_app_handlers.cc:376-423``), which is exactly what the decorator sets
    (``:209-246``); the decorator's own docstring is "Function decorator for
    callback functions **not to be removed when loading new files**".

    Claiming persistence for an undecorated handler was therefore false, and
    it was false on real files: ``cloudrig.py`` and ``rigged_particle_hair.py``
    both register handlers without ``@persistent``, so ~27 findings across the
    institutional corpus told an artist that an ordinary Blender Studio rig had
    permanently infected their session.

    https://raw.githubusercontent.com/blender/blender/e6d1620ad53feed4a83e3b168f0a2ea74f4de6ce/source/blender/python/intern/bpy_app_handlers.cc
    https://raw.githubusercontent.com/blender/blender/e6d1620ad53feed4a83e3b168f0a2ea74f4de6ce/source/blender/python/intern/bpy_interface.cc
    """
    persistent = col.persistent_handler_evidence()
    _add(out, Severity.NOTABLE, "x_handler_persist", persistent)
    if not persistent:
        _add(out, Severity.NOTABLE, "x_handler_register", col.handler_attributes())


def _notable_statements(col: Collector, out: list[Statement]) -> None:
    writes = _matches_calls(col, WRITE_CALLS)
    if col.write_modes:
        writes += [f"open(mode={m!r})" for m in sorted(col.write_modes)]
    _add(out, Severity.NOTABLE, "x_file_write", writes)
    _add(out, Severity.NOTABLE, "x_file_delete", _matches_calls(col, DELETE_CALLS))
    _add(out, Severity.NOTABLE, "x_makedirs", _matches_calls(col, MAKEDIR_CALLS))
    _add(out, Severity.NOTABLE, "x_compile_code", _matches_calls(col, CODE_BUILD_CALLS))
    _add(out, Severity.NOTABLE, "x_deserialise", _matches_calls(col, DESERIALISE_CALLS))
    _add(out, Severity.NOTABLE, "x_runtime_import", sorted(col.dynamic_import_literal))
    _add(
        out,
        Severity.NOTABLE,
        "x_opens_browser",
        _matches(col.imports, BROWSER_CALLS) + _matches_calls(col, BROWSER_CALLS),
    )
    _handler_statements(col, out)


def _dynamic_code_evidence(col: Collector) -> list[str]:
    """Constructs that really do build code at run time and then run it."""
    dynamic = _matches_calls(col, DYNAMIC_CODE_CALLS)
    if col.dynamic_import_nonliteral:
        dynamic.append("__import__(<computed name>)")
    return dynamic


def _decode_statements(col: Collector, out: list[Statement]) -> None:
    """Decoding alone says what it does; a decode that is *run* is hiding.

    Requiring both halves in the same body was already an improvement on the
    bare ``zlib.decompress`` that used to print "deliberately hidden", but it
    still treated co-occurrence as a link, and on real files the two halves
    are routinely unrelated: ``Sandman13sq/DmrVBM-blender-to-gms2`` compresses
    mesh and image data with ``zlib`` and, elsewhere, calls ``exec`` on
    something that never touched it. So the link is now established by
    :meth:`blend_xray.collect.Collector._record_decode_link` -- the decoded
    value has to reach the call that runs it -- and the sentence says that,
    rather than asserting a conclusion two unrelated calls do not support.
    """
    decode = _matches_calls(col, DECODE_CALLS)
    if not decode:
        return
    if col.decoded_then_run:
        _add(out, Severity.ALARMING, "x_obfuscation", decode + col.decoded_then_run)
    else:
        _add(out, Severity.NOTABLE, "x_decodes_data", decode)


def _evasion_statements(col: Collector, out: list[Statement]) -> None:
    """The shape of the hiding, when the names it would have used are gone.

    None of these describes a capability. They describe a script routing round
    the name tables: reaching a builtin through ``getattr`` so ``__import__``
    never appears as a call, calling the value another call returned so the
    callee has no name at all, gluing a module name out of fragments so it
    matches no search. Static analysis cannot follow any of that -- but it can
    say that it is happening, which is the honest half of the answer.

    Loud because measured: across the 100 parseable script bodies in both
    corpora, every one of these shapes occurs zero times.
    """
    _add(out, Severity.ALARMING, "x_builtins_indirection", col.builtins_indirection)
    _add(out, Severity.ALARMING, "x_indirect_call", col.indirect_calls)
    _add(out, Severity.ALARMING, "x_assembled_name", col.assembled_names)
    plain = [s for s in col.split_literals if not any(s in ev for ev in col.assembled_names)]
    _add(out, Severity.NOTABLE, "x_split_literal", plain)


def _alarming_statements(col: Collector, out: list[Statement], blobs: list[str]) -> None:
    net = _matches(col.imports, NETWORK_MODULES) + _matches_calls(col, NETWORK_MODULES)
    _add(out, Severity.ALARMING, "x_network", net)
    listen = _matches(col.imports, NETWORK_LISTEN_MODULES) + _matches_calls(
        col, NETWORK_LISTEN_MODULES
    )
    _add(out, Severity.ALARMING, "x_network_listen", listen)

    _add(out, Severity.ALARMING, "x_subprocess", _matches_calls(col, SUBPROCESS_CALLS))

    lol = sorted({tool for s in col.strings for tool in LIVING_OFF_LAND if tool in s.lower()})
    if lol:
        _add(out, Severity.ALARMING, "x_living_off_land", lol, tools=", ".join(lol))

    dynamic = _dynamic_code_evidence(col)
    _add(out, Severity.ALARMING, "x_dynamic_code", dynamic)
    _decode_statements(col, out)
    _evasion_statements(col, out)

    if blobs:
        _add(
            out,
            Severity.ALARMING,
            "x_opaque_blob",
            [f"{b[:24]}... ({len(b)} chars)" for b in blobs],
            size=max(len(b) for b in blobs),
        )

    lower = [s.lower() for s in col.strings]
    persist = [m for m in PERSISTENCE_MARKERS if any(m in s for s in lower)]
    persist += _matches(col.imports, frozenset({"winreg", "_winreg"}))
    _add(out, Severity.ALARMING, "x_persistence", persist)

    _add(out, Severity.ALARMING, "x_lowlevel", _matches(col.imports, LOWLEVEL_MODULES))

    creds = [m for m in CREDENTIAL_MARKERS if any(m in s for s in lower)]
    _add(out, Severity.ALARMING, "x_credentials", creds)


def _fallback(
    source: str, reason: str, note_key: str | None = None, deadline: Budget | None = None
) -> Explanation:
    """When we cannot parse, still surface the literals via plain text search."""
    literals, blobs = extract_literals(
        re.findall(r"[^\s'\"]{4,}", source), bare_tokens=True, deadline=deadline
    )
    statements: list[Statement] = []
    if blobs:
        _add(
            statements,
            Severity.ALARMING,
            "x_opaque_blob",
            [f"{b[:24]}... ({len(b)} chars)" for b in blobs],
            size=max(len(b) for b in blobs),
        )
    return Explanation(
        parsed=False,
        statements=tuple(statements),
        literals=tuple(literals),
        obfuscated=bool(blobs),
        parse_error=reason,
        note=strings.t(note_key) if note_key else None,
    )


def explain_source(
    source: str, deadline: Budget | None = None, *, ambient_names: bool = False
) -> Explanation:
    """Statically analyse ``source`` and describe it in plain language.

    Never executes the code. Bounded in size and nesting depth so that a
    hostile script cannot exhaust memory or the parser's C stack, and bounded
    in *time* by ``deadline`` so it cannot exhaust the caller's budget either.

    Size and nesting caps were not enough on their own: both are per-body,
    and a file holding eight bodies just under the 2 MiB cap spent seconds
    here while the wall-clock limit the user asked for was already gone.

    Used for text datablocks and, since drivers are executed under the same
    auto-run gate, for driver expressions too -- see
    :func:`blend_xray.scanner._explain_driver`, which is the one caller that
    passes ``ambient_names``.

    ``ambient_names`` turns off the requirement that a dotted call name's root
    be imported in this body before it may be read as a module. Set it only
    for a body Blender hands a prepared namespace to and which cannot contain
    an import statement -- a driver expression, and nothing else. A text
    datablock is a module: if it uses ``os.system`` it imports ``os``, and
    leaving the requirement on is what stops a local variable named ``socket``
    being read as the ``socket`` module. See :mod:`blend_xray.resolve`.
    """
    raw_size = len(source.encode("utf-8", errors="replace"))
    if raw_size > MAX_PARSE_BYTES:
        note = strings.t("explain_too_large", size=raw_size, limit=MAX_PARSE_BYTES)
        exp = _fallback(source[:MAX_PARSE_BYTES], note, deadline=deadline)
        return dataclasses.replace(exp, note=note)

    if max_nesting(source) > MAX_NESTING_DEPTH:
        return _fallback(
            source,
            strings.t("explain_parse_exhausted"),
            note_key="explain_parse_exhausted",
            deadline=deadline,
        )

    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return _fallback(source, f"{exc.msg} (line {exc.lineno})", deadline=deadline)
    except (RecursionError, MemoryError, ValueError) as exc:
        return _fallback(source, str(exc) or type(exc).__name__, deadline=deadline)

    collector = Collector(ambient_names=ambient_names)
    try:
        collector.analyse(tree)
    except RecursionError:
        return _fallback(source, strings.t("explain_parse_exhausted"), deadline=deadline)

    literals, blobs = extract_literals(collector.strings, deadline=deadline)
    statements: list[Statement] = []
    _alarming_statements(collector, statements, blobs)
    _notable_statements(collector, statements)
    _benign_statements(collector, statements)
    statements.sort(key=lambda s: -int(s.severity))

    obfuscated = any(st.key in OBFUSCATION_KEYS for st in statements)
    return Explanation(
        parsed=True,
        statements=tuple(statements),
        literals=tuple(literals),
        obfuscated=obfuscated,
    )
