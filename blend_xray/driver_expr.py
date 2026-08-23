# SPDX-License-Identifier: GPL-3.0-or-later
"""Classify a driver expression as simple-looking or worth reading.

Why classify instead of flagging every driver
---------------------------------------------
Blender compiles driver expressions built only from arithmetic and a small set
of known names into a restricted C evaluator (``BLI_expr_pylike_eval``). Those
run **even when Python auto-execution is disabled**. An expression needing
anything outside that set falls back to full Python, and therefore only runs if
the user enabled script auto-execution.

That distinction is the useful one for a reader, so flagging every driver
equally would be noise. A rig with two hundred ``frame * 2`` drivers is normal;
one driver reaching into ``bpy.data`` is not.

Being wrong here is expensive in both directions, so the tables below are
transcribed from the evaluator itself rather than from its documentation --
including Blender's own header comment, which is stale and omits ``round``,
``lerp``, ``clamp`` and ``smoothstep``. Say an expression is simple when it is
not, and the tool promises "no Python needed" about something that needs
auto-run. Say it is not simple when it is, and the tool asks an artist to
review ``smoothstep(0, 1, frame)``.

Upstream, all quoted below at their line numbers:
``source/blender/blenlib/intern/expr_pylike_eval.cc``
https://raw.githubusercontent.com/blender/blender/e6d1620ad53feed4a83e3b168f0a2ea74f4de6ce/source/blender/blenlib/intern/expr_pylike_eval.cc

Nothing here executes the expression. ``ast.parse`` builds a syntax tree only.
"""

from __future__ import annotations

import ast
from typing import Final

from .astutil import MAX_NESTING_DEPTH, dotted_name, max_nesting

#: Function name -> the argument counts the evaluator accepts for it.
#:
#: Transcribed from ``builtin_ops[]`` (expr_pylike_eval.cc:414-442), where the
#: arity is carried by which of ``UnaryOpFunc``/``BinaryOpFunc``/
#: ``TernaryOpFunc`` the entry holds (``BuiltinOpDef::arg_count``, :391-408).
#: ``log`` and ``clamp`` appear twice in the table, at two arities, which is
#: why the values are sets::
#:
#:     {"log", UnaryOpFunc(log)},
#:     {"log", BinaryOpFunc(op_log2)},
#:     {"clamp", UnaryOpFunc(op_clamp)},
#:     {"clamp", TernaryOpFunc(op_clamp3)},
#:     {"smoothstep", TernaryOpFunc(op_smoothstep)},
#:
#: ``min`` and ``max`` are not in that table at all. They are special-cased in
#: ``parse_unary`` (:815-828) with ``CHECK_ERROR(count > 0)``, so they take any
#: number of arguments from one upwards -- spelled here as ``None``.
#:
#: **``sign`` is not in the evaluator.** It was in this tool's table and does
#: not exist upstream: ``grep -n sign expr_pylike_eval.cc`` returns nothing in
#: all 1072 lines. ``sign(frame)`` fails to parse, so Blender falls back to
#: ``BPY_driver_exec`` and the expression needs script auto-execution -- the
#: opposite of what this tool used to say about it.
SIMPLE_EXPR_FUNCTIONS: Final[dict[str, frozenset[int] | None]] = {
    "radians": frozenset({1}),
    "degrees": frozenset({1}),
    "abs": frozenset({1}),
    "fabs": frozenset({1}),
    "floor": frozenset({1}),
    "ceil": frozenset({1}),
    "trunc": frozenset({1}),
    "round": frozenset({1}),
    "int": frozenset({1}),
    "sin": frozenset({1}),
    "cos": frozenset({1}),
    "tan": frozenset({1}),
    "asin": frozenset({1}),
    "acos": frozenset({1}),
    "atan": frozenset({1}),
    "atan2": frozenset({2}),
    "exp": frozenset({1}),
    "log": frozenset({1, 2}),
    "sqrt": frozenset({1}),
    "pow": frozenset({2}),
    "fmod": frozenset({2}),
    "lerp": frozenset({3}),
    "clamp": frozenset({1, 3}),
    "smoothstep": frozenset({3}),
    # Variadic, one argument minimum. Not in builtin_ops[]; parse_unary:815.
    "min": None,
    "max": None,
}

#: Names the evaluator resolves without a call.
#:
#: ``builtin_consts[]`` (expr_pylike_eval.cc:382-383) is exactly
#: ``{"pi", M_PI}, {"True", 1.0}, {"False", 0.0}`` -- no ``e``, no ``tau``.
#: ``frame`` is not known to that file at all; the driver layer injects it as
#: parameter 0 (``fcurve_driver.cc:1105-1128``, ``names[VAR_INDEX_FRAME] =
#: "frame"``), alongside the user's own driver variables. Since those variable
#: names are arbitrary, a bare identifier is accepted below regardless, and
#: this set exists to document the boundary rather than to enforce it.
SIMPLE_EXPR_CONSTANTS: Final[frozenset[str]] = frozenset({"pi", "True", "False", "frame"})

#: Kept as a flat name set for callers that only want "is this name known".
SIMPLE_EXPR_NAMES: Final[frozenset[str]] = frozenset(SIMPLE_EXPR_FUNCTIONS) | SIMPLE_EXPR_CONSTANTS

#: AST nodes the restricted evaluator can represent.
#:
#: The operator set follows the precedence chain exactly, loosest first:
#: ``parse_or`` (``or``) -> ``parse_and`` (``and``) -> ``parse_not`` (``not``)
#: -> ``parse_cmp`` (``== != > >= < <=``, chained) -> ``parse_add`` (``+ -``)
#: -> ``parse_mul`` -> ``parse_unary`` (prefix ``+ -``, parentheses, numbers,
#: identifiers). ``parse_expr`` adds the ``if``/``else`` ternary.
#:
#: ``ast.Pow``, ``ast.Mod`` and ``ast.FloorDiv`` used to be in this tuple and
#: are gone, because the multiplicative level accepts two operators and only
#: two (``parse_mul``, expr_pylike_eval.cc:840-860)::
#:
#:     for (;;) {
#:       switch (state->token) {
#:         case '*':  ... parse_add_func(state, op_mul);  break;
#:         case '/':  ... parse_add_func(state, op_div);  break;
#:         default:   return true;
#:       }
#:     }
#:
#: There is no power level anywhere in the file -- no ``parse_pow``, and no
#: case for ``'^'`` or ``'%'`` at any level. ``%`` does lex (it is in
#: ``token_characters``, :473) but no level consumes it, so it survives to the
#: whole-expression check ``state.token == 0`` (:1057) and fails the parse.
#: ``**`` and ``//`` lex as two single-character tokens: ``parse_mul`` takes
#: the first, then ``parse_unary`` meets the second and falls through its
#: ``default: return false``. All three therefore fall back to
#: ``BPY_driver_exec``, which means ``frame ** 2`` **does** require script
#: auto-execution. Calling it simple was an under-warning.
_SIMPLE_NODES: Final = (
    ast.Expression,
    ast.BinOp,
    ast.UnaryOp,
    ast.BoolOp,
    ast.Compare,
    ast.IfExp,
    ast.Constant,
    ast.Name,
    ast.Load,
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.USub,
    ast.UAdd,
    ast.Not,
    ast.And,
    ast.Or,
    ast.Eq,
    ast.NotEq,
    ast.Lt,
    ast.LtE,
    ast.Gt,
    ast.GtE,
)

#: Python spellings of the operators the evaluator has no level for, so the
#: reason string can name the operator rather than the AST class.
_REJECTED_OPERATORS: Final[dict[type, str]] = {
    ast.Pow: "**",
    ast.Mod: "%",
    ast.FloorDiv: "//",
}

#: ``char expression[256]`` in struct ChannelDriver, but we accept a little
#: slack before refusing outright so a corrupt field still gets classified.
_MAX_EXPRESSION_CHARS: Final = 4096


def _call_reason(node: ast.Call) -> str | None:
    """Why this call is outside the simple evaluator, or ``None`` if it is not."""
    name = dotted_name(node.func)
    if name not in SIMPLE_EXPR_FUNCTIONS:
        return f"calls {name or '<dynamic>'}(), which is not a simple-expression function"
    if node.keywords or any(isinstance(arg, ast.Starred) for arg in node.args):
        return f"calls {name}() with arguments the simple evaluator cannot parse"
    arities = SIMPLE_EXPR_FUNCTIONS[name]
    count = len(node.args)
    if arities is None:
        # min/max: parse_unary:817-828 requires CHECK_ERROR(count > 0).
        return None if count > 0 else f"calls {name}() with no arguments"
    if count not in arities:
        wanted = " or ".join(str(n) for n in sorted(arities))
        return f"calls {name}() with {count} arguments; the simple evaluator takes {wanted}"
    return None


def _node_reason(node: ast.AST) -> str | None:
    """Why this node is outside the simple evaluator, or ``None`` if it is not."""
    if isinstance(node, ast.Attribute):
        return f"uses attribute access ({dotted_name(node) or node.attr})"
    if isinstance(node, ast.Name) and node.id.startswith("__"):
        return f"uses the dunder name {node.id}"
    spelling = _REJECTED_OPERATORS.get(type(node))
    if spelling is not None:
        return f"uses the {spelling} operator, which the simple evaluator does not support"
    if not isinstance(node, _SIMPLE_NODES):
        return f"uses {type(node).__name__}, which the simple evaluator does not support"
    return None


def classify_expression(expression: str) -> tuple[bool, str]:
    """Return ``(is_simple_looking, reason)`` for a driver expression.

    Driver *variable* names are user-defined and arbitrary, so a bare
    identifier is allowed. Attribute access, subscripting, lambdas,
    comprehensions, the three operators the evaluator has no level for, and
    calls outside :data:`SIMPLE_EXPR_FUNCTIONS` -- or to one of them at the
    wrong arity -- are not, and each returns the concrete reason so the report
    can show it.

    The caller is responsible for only asking about drivers whose expression
    Blender evaluates at all; see
    :func:`blend_xray.scanner._driver_evaluates_expression`.
    """
    text = expression.strip()
    if not text:
        return True, "empty"
    if len(text) > _MAX_EXPRESSION_CHARS or max_nesting(text) > MAX_NESTING_DEPTH:
        return False, "expression is too large or too deeply nested to analyse"

    try:
        tree = ast.parse(text, mode="eval")
    except (SyntaxError, ValueError, RecursionError, MemoryError) as exc:
        return False, f"does not parse as a Python expression ({exc.__class__.__name__})"

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            reason = _call_reason(node)
            if reason:
                return False, reason
            continue
        reason = _node_reason(node)
        if reason:
            return False, reason
    return True, "arithmetic and driver variables only"
