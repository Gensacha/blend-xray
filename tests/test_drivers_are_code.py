# SPDX-License-Identifier: GPL-3.0-or-later
"""A driver expression is code, and it must reach every surface that says so.

Two separate defects live here. A driver holding a payload used to bypass the
explanation engine entirely -- it was classified by
:mod:`blend_xray.driver_expr` alone, so no network, subprocess or dynamic-code
rule ever saw it, and neither the banner nor the closing recommendation could
be influenced by it. And a driver whose *type* means Blender never reads the
expression field was being described as though it did.

The .blend files are assembled byte by byte by :mod:`tests.blend_builder`.
Nothing here launches Blender and nothing evaluates any expression.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from blend_xray import banner, scanner
from blend_xray import dna_constants as dna
from blend_xray.recommend import alarming_drivers, recommendation_lines

from .blend_builder import BlendBuilder

#: The security review's PoC payload, in a driver.
DRIVER_PAYLOAD = "__import__('os').system('calc.exe')"


def _blend_with_drivers(tmp_path: Path, name: str, *drivers: tuple[str, int]) -> Path:
    builder = BlendBuilder()
    for expression, dtype in drivers:
        builder.add_driver(expression, dtype=dtype)
    path = tmp_path / name
    path.write_bytes(builder.to_bytes())
    return path


@pytest.fixture
def payload_driver_blend(tmp_path: Path) -> Path:
    return _blend_with_drivers(
        tmp_path, "driver_payload.blend", (DRIVER_PAYLOAD, dna.DRIVER_TYPE_PYTHON)
    )


# ==========================================================================
# 5. A payload in a driver must not bypass the explanation engine.
# ==========================================================================
def test_a_driver_payload_is_explained(payload_driver_blend: Path) -> None:
    result = scanner.scan_file(payload_driver_blend)
    driver = result.drivers[0]
    assert driver.explanation is not None
    assert driver.explanation.alarming is True
    assert "x_indirect_call" in {st.key for st in driver.explanation.statements}


def test_a_driver_payload_reaches_the_banner(payload_driver_blend: Path) -> None:
    """Was: AMBER, "has a driver expression that needs full Python"."""
    info = banner.for_result(scanner.scan_file(payload_driver_blend))
    assert info.tier is banner.Tier.RED
    assert "x_indirect_call" in info.reasons


def test_a_driver_payload_reaches_the_recommendation(payload_driver_blend: Path) -> None:
    """Was: "Nothing here matched the patterns Blend X-Ray treats as alarming"."""
    result = scanner.scan_file(payload_driver_blend)
    assert alarming_drivers(result)
    texts = [text for text, _ in recommendation_lines(result)]
    assert any("cannot judge for you" in text for text in texts)
    assert not any("Nothing here matched" in text for text in texts)


def test_an_ordinary_driver_still_says_nothing(tmp_path: Path) -> None:
    """The fix must not turn every rig's arithmetic into a finding."""
    path = _blend_with_drivers(
        tmp_path, "plain.blend", ("frame * 2", dna.DRIVER_TYPE_PYTHON)
    )
    result = scanner.scan_file(path)
    assert result.drivers[0].is_simple is True
    assert result.drivers[0].explanation is None
    assert banner.for_result(result).tier is banner.Tier.NEUTRAL


def test_a_simple_expression_is_not_parsed_twice(tmp_path: Path) -> None:
    """Cost control: 22,520 drivers across the corpora, 682 distinct.

    A simple expression is arithmetic over driver variables by construction,
    so it cannot hold a call, an attribute or a string for any rule to match.
    Skipping the explanation engine for those is what keeps a rig scan from
    growing an AST parse per driver.
    """
    path = _blend_with_drivers(
        tmp_path,
        "many.blend",
        *[("frame * 2", dna.DRIVER_TYPE_PYTHON)] * 8,
    )
    result = scanner.scan_file(path)
    assert len(result.drivers) == 8
    assert all(driver.explanation is None for driver in result.drivers)


# ==========================================================================
# 2b. Driver types whose expression field Blender never reads.
# ==========================================================================
@pytest.mark.parametrize(
    "dtype",
    [dna.DRIVER_TYPE_AVERAGE, dna.DRIVER_TYPE_SUM, dna.DRIVER_TYPE_MIN, dna.DRIVER_TYPE_MAX],
)
def test_non_python_driver_types_are_not_described_as_evaluated(
    tmp_path: Path, dtype: int
) -> None:
    """evaluate_driver() sends these to evaluate_driver_sum / _min_max.

    Neither reads ``expression``, and driver_compile_simple_expr() refuses
    outright unless the type is DRIVER_TYPE_PYTHON. 3,527 of the corpora's
    22,520 driver findings are one of these types and were being given the
    sentence about the restricted evaluator.
    """
    path = _blend_with_drivers(tmp_path, f"t{dtype}.blend", (DRIVER_PAYLOAD, dtype))
    driver = scanner.scan_file(path).drivers[0]
    assert driver.expression_is_evaluated is False
    assert driver.is_simple is None
    assert driver.explanation is None


def test_an_inert_expression_does_not_spend_a_banner(tmp_path: Path) -> None:
    path = _blend_with_drivers(
        tmp_path, "inert.blend", (DRIVER_PAYLOAD, dna.DRIVER_TYPE_AVERAGE)
    )
    result = scanner.scan_file(path)
    assert banner.for_result(result).tier is banner.Tier.NEUTRAL
    assert alarming_drivers(result) == []


def test_the_inert_expression_is_still_in_the_inventory(tmp_path: Path) -> None:
    """Not evaluated is not the same as not reported. It stays visible."""
    path = _blend_with_drivers(
        tmp_path, "inert2.blend", (DRIVER_PAYLOAD, dna.DRIVER_TYPE_SUM)
    )
    result = scanner.scan_file(path)
    assert result.drivers[0].expression == DRIVER_PAYLOAD
    assert result.drivers[0].to_dict()["expression_is_evaluated"] is False


def test_python_drivers_are_still_evaluated(tmp_path: Path) -> None:
    path = _blend_with_drivers(
        tmp_path, "py.blend", ("frame * 2", dna.DRIVER_TYPE_PYTHON)
    )
    assert scanner.scan_file(path).drivers[0].expression_is_evaluated is True


def test_repeated_payloads_are_analysed_once(tmp_path: Path) -> None:
    """Memoised per scan, so a rig with thousands of copies pays once.

    Identity, not equality: the same Explanation object must come back, which
    is only true if the cache was consulted rather than the parse repeated.
    """
    path = _blend_with_drivers(
        tmp_path,
        "repeat.blend",
        *[(DRIVER_PAYLOAD, dna.DRIVER_TYPE_PYTHON)] * 6,
    )
    explanations = [driver.explanation for driver in scanner.scan_file(path).drivers]
    assert len(explanations) == 6
    assert all(item is explanations[0] for item in explanations)


def test_an_unreadable_driver_type_is_treated_as_evaluated(tmp_path: Path) -> None:
    """A missing type field must not switch the analysis off.

    The old code read the field as ``_first_field(...) or 0``, which turned an
    unreadable field into DRIVER_TYPE_AVERAGE -- so a hostile file could have
    hidden a live expression behind a corrupt type byte once the inert-type
    rule existed.
    """
    from blend_xray.scanner import _driver_evaluates_expression

    assert _driver_evaluates_expression(None) is True
    assert _driver_evaluates_expression("garbage") is True
    assert _driver_evaluates_expression(dna.DRIVER_TYPE_PYTHON) is True
    assert _driver_evaluates_expression(dna.DRIVER_TYPE_AVERAGE) is False
