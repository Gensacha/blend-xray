# SPDX-License-Identifier: GPL-3.0-or-later
"""Canonical *shape* of a Python script, with the text inside quotes removed.

Some legitimate scripts are generated per-file and therefore have a different
byte hash in every single .blend that contains them. Rigify's ``rig_ui.py`` is
the standard example: the generator writes a per-rig ``rig_id`` string into it,
so a byte-keyed database can never match it, no matter how many copies exist.

This module answers a narrower question than "is this the same file?": it
answers "is this the same *code*, with possibly different text inside the
quotes?". It replaces every string and bytes literal **value** with a typed
placeholder, keeps everything else -- statements, calls, names, numbers,
operators -- and hashes the result. The replaced values are returned alongside,
in visit order, so a caller can say exactly which ones differ from a reference.

That distinction is the whole security point, and it cuts both ways: an
attacker can keep a well-known script's structure and change only what is
inside the quotes, which is exactly where a payload URL would live. So a
structural match is deliberately *weaker* evidence than a byte match, and the
differing values are the thing worth putting on screen.

Nothing here executes the analysed code. ``ast.parse`` builds a syntax tree and
runs none of it.

Version stability
-----------------
The serialisation below is written by hand rather than taken from
``ast.dump``. A stored structural hash has to keep matching across Python
releases, and ``ast.dump`` output changes when a release adds a field to a node
(3.12 added ``type_params`` to ``FunctionDef``). Fields that are absent,
``None`` or an empty list are skipped, so a field that a newer Python adds and
leaves empty serialises to nothing at all -- the same bytes an older Python
produced.
"""

from __future__ import annotations

import ast
import dataclasses
import hashlib
from typing import Final

from .astutil import MAX_NESTING_DEPTH, max_nesting

#: Same budget as the explainer: do not attempt to parse anything larger.
MAX_STRUCTURE_BYTES: Final = 2 * 1024 * 1024

#: Stand-ins for the removed literal values. The NUL bytes make an accidental
#: collision with a real source string effectively impossible.
STR_PLACEHOLDER: Final = "\x00<str>\x00"
BYTES_PLACEHOLDER: Final = "\x00<bytes>\x00"

#: Bumped when the serialisation below changes in a way that alters hashes.
#: Stored entries record the version they were computed with, so an entry from
#: an older scheme is skipped instead of silently never matching.
STRUCTURE_SCHEME: Final = 1


@dataclasses.dataclass(frozen=True)
class Structure:
    """The shape of one script, plus the literal values taken out of it."""

    sha256: str
    #: Every string/bytes literal value, in the order the walk found them.
    #: Two scripts with the same ``sha256`` always have lists of equal length,
    #: which is what makes a position-by-position comparison meaningful.
    literals: tuple[str, ...]
    scheme: int = STRUCTURE_SCHEME


class _Canonicaliser(ast.NodeTransformer):
    """Replace literal *values* with typed placeholders, keeping the structure."""

    def __init__(self) -> None:
        self.literals: list[str] = []

    def visit_Constant(self, node: ast.Constant) -> ast.Constant:
        if isinstance(node.value, str):
            self.literals.append(node.value)
            return ast.Constant(value=STR_PLACEHOLDER)
        if isinstance(node.value, bytes):
            # latin-1 round-trips every byte, so nothing is lost or guessed at.
            self.literals.append(node.value.decode("latin-1"))
            return ast.Constant(value=BYTES_PLACEHOLDER)
        return node


def _serialise(node: object, out: list[str]) -> None:
    """Append a deterministic rendering of ``node`` to ``out``.

    See the module docstring for why empty fields are skipped rather than
    rendered. ``Constant.value`` is the one field always written: the literal
    ``None`` is a real value there, not an absent field.
    """
    if isinstance(node, ast.AST):
        out.append("(" + type(node).__name__)
        for field in node._fields:
            value = getattr(node, field, None)
            keep_empty = isinstance(node, ast.Constant) and field == "value"
            if (value is None or value == []) and not keep_empty:
                continue
            out.append("," + field + "=")
            _serialise(value, out)
        out.append(")")
        return
    if isinstance(node, list):
        out.append("[")
        for item in node:
            _serialise(item, out)
            out.append(",")
        out.append("]")
        return
    out.append(repr(node))


def structure_of(source: str) -> Structure | None:
    """Canonical structure of ``source``, or ``None`` when it cannot be parsed.

    Returning ``None`` is the honest answer for anything this cannot read:
    unparseable text, a body over the size budget, or nesting deep enough to
    threaten the parser's own C stack. A caller must treat ``None`` as "no
    identity information", never as "no match found".

    Note what the nesting pre-check does and does not cover.
    :func:`astutil.max_nesting` counts bracket characters, so it catches deeply
    nested literals before ``ast.parse`` ever sees them. It does **not** see
    constructs that nest just as deeply without brackets -- a four-thousand-term
    ``1 + 1 + 1 + ...`` chain, or a stack of unary operators. Those are handled
    one layer down, by catching ``RecursionError`` around both the parse and
    the walk, which is the interpreter's own guard rather than a limit this
    module enforces. Measured behaviour on such input is a clean ``None``, not
    a crash, but the guarantee is CPython's and depends on its stack margin.
    """
    if len(source.encode("utf-8", errors="replace")) > MAX_STRUCTURE_BYTES:
        return None
    if max_nesting(source) > MAX_NESTING_DEPTH:
        return None
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError, RecursionError, MemoryError):
        return None

    canonicaliser = _Canonicaliser()
    try:
        canonical = canonicaliser.visit(tree)
        parts: list[str] = []
        _serialise(canonical, parts)
    except (RecursionError, MemoryError):
        return None

    digest = hashlib.sha256("".join(parts).encode("utf-8", errors="replace")).hexdigest()
    return Structure(sha256=digest, literals=tuple(canonicaliser.literals))
