# SPDX-License-Identifier: GPL-3.0-or-later
"""Parity with Blender's restricted driver evaluator, in both directions.

Getting this wrong is expensive either way. Call an expression simple when
Blender cannot parse it, and the tool promises "no Python needed" about
something that in fact falls through to ``BPY_driver_exec`` and therefore
needs script auto-execution. Call it complex when Blender handles it, and the
tool asks an artist to review ``smoothstep(0, 1, frame)``.

Everything asserted here was transcribed from
``source/blender/blenlib/intern/expr_pylike_eval.cc`` at commit
``e6d1620ad53feed4a83e3b168f0a2ea74f4de6ce``; the line numbers are in
:mod:`blend_xray.driver_expr`.

Nothing here evaluates an expression. ``ast.parse`` builds a tree only.
"""

from __future__ import annotations

import pytest

from blend_xray import driver_expr

# -- functions the evaluator really has (builtin_ops[], :414-442) ----------
UPSTREAM_FUNCTIONS = (
    "radians",
    "degrees",
    "abs",
    "fabs",
    "floor",
    "ceil",
    "trunc",
    "round",
    "int",
    "sin",
    "cos",
    "tan",
    "asin",
    "acos",
    "atan",
    "exp",
    "log",
    "sqrt",
)


@pytest.mark.parametrize("name", UPSTREAM_FUNCTIONS)
def test_every_unary_builtin_is_simple(name: str) -> None:
    is_simple, reason = driver_expr.classify_expression(f"{name}(frame)")
    assert is_simple is True, reason


@pytest.mark.parametrize(
    "expression",
    [
        "atan2(frame, 2)",
        "pow(frame, 2)",
        "fmod(frame, 2)",
        "log(frame, 2)",
        "lerp(0, 1, frame)",
        "clamp(frame)",
        "clamp(frame, 0, 1)",
        "smoothstep(0, 1, frame)",
        "min(a, b, c)",
        "max(a)",
        "pi * frame",
        "frame if frame > 1 else 0",
        "not frame",
        "a and b or not c",
        "-frame + +2",
        "1 < frame <= 10",
    ],
)
def test_expressions_the_restricted_evaluator_accepts(expression: str) -> None:
    is_simple, reason = driver_expr.classify_expression(expression)
    assert is_simple is True, reason


def test_smoothstep_is_no_longer_reported_as_needing_python() -> None:
    """It is in builtin_ops[] at line 440 and was missing from our table."""
    is_simple, _ = driver_expr.classify_expression("smoothstep(0, 1, frame)")
    assert is_simple is True


def test_sign_does_not_exist_upstream_and_is_not_simple() -> None:
    """`grep -n sign expr_pylike_eval.cc` returns nothing in all 1072 lines.

    So Blender fails to parse it, falls back to BPY_driver_exec, and the
    expression needs script auto-execution -- the opposite of what this tool
    said about it.
    """
    is_simple, reason = driver_expr.classify_expression("sign(frame)")
    assert is_simple is False
    assert "sign" in reason
    assert "sign" not in driver_expr.SIMPLE_EXPR_FUNCTIONS


@pytest.mark.parametrize(
    ("expression", "operator"),
    [("frame ** 2", "**"), ("frame % 4", "%"), ("frame // 4", "//")],
)
def test_operators_with_no_parse_level_are_not_simple(expression: str, operator: str) -> None:
    """parse_mul() has a case for '*' and '/' and a default that returns.

    There is no power level anywhere in the file, and '%' is never a case at
    any level, so it survives to the ``state.token == 0`` check and fails the
    parse. All three fall back to Python and need auto-run.
    """
    is_simple, reason = driver_expr.classify_expression(expression)
    assert is_simple is False
    assert operator in reason


@pytest.mark.parametrize(
    "expression",
    ["sqrt(frame, 2)", "atan2(frame)", "lerp(0, 1)", "clamp(0, 1)", "min()"],
)
def test_wrong_arity_is_not_simple(expression: str) -> None:
    """A call at an arity the table does not hold fails CHECK_ERROR."""
    is_simple, reason = driver_expr.classify_expression(expression)
    assert is_simple is False
    assert reason


def test_keyword_arguments_are_not_simple() -> None:
    """The evaluator's parse_function_args() reads positional args only."""
    is_simple, _ = driver_expr.classify_expression("clamp(frame, mn=0, mx=1)")
    assert is_simple is False


def test_constants_match_builtin_consts() -> None:
    """builtin_consts[] is exactly pi, True, False; `frame` is parameter 0."""
    assert set(driver_expr.SIMPLE_EXPR_CONSTANTS) == {"pi", "True", "False", "frame"}
