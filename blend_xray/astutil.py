# SPDX-License-Identifier: GPL-3.0-or-later
"""Small AST helpers shared by the script explainer and the driver classifier.

Both modules statically analyse attacker-supplied Python. Neither executes it.
The nesting cap lives here because both need to apply it *before* calling
``ast.parse``: deeply nested literals can exhaust the C stack inside the parser
itself, which is a crash we must prevent rather than catch.
"""

from __future__ import annotations

import ast
from typing import Final

#: Refuse to parse source nested deeper than this many brackets.
MAX_NESTING_DEPTH: Final = 180


def dotted_name(node: ast.AST) -> str:
    """Render ``a.b.c`` from an Attribute/Name chain.

    Returns ``""`` when the chain is dynamic (e.g. ``f().attr``), which callers
    treat as "we cannot name this", never as "this is fine".
    """
    parts: list[str] = []
    cur = node
    while isinstance(cur, ast.Attribute):
        parts.append(cur.attr)
        cur = cur.value
    if isinstance(cur, ast.Name):
        parts.append(cur.id)
        return ".".join(reversed(parts))
    return ""


def max_nesting(source: str) -> int:
    """Deepest bracket nesting in ``source``, counted without parsing it."""
    depth = maximum = 0
    for ch in source:
        if ch in "([{":
            depth += 1
            maximum = max(maximum, depth)
        elif ch in ")]}":
            depth = max(0, depth - 1)
    return maximum
