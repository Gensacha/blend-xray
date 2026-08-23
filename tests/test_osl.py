# SPDX-License-Identifier: GPL-3.0-or-later
"""OSL script nodes, end to end, against synthetic files.

Why this module exists as its own file: across the 101 real ``.blend`` files in
the two corpora there are **zero** ``NodeShaderScript`` datablocks. Every
sentence this category prints therefore ships unexercised against real data,
and the only way to exercise it at all is to build the datablock ourselves.
:mod:`tests.blend_builder` does that, and these tests drive the whole path --
scanner, banner, human report in both languages, and ``--json`` -- for the
three shapes a script node comes in: internal mode, external mode, and
compiled bytecode present.

The specific defect they close: ``osl_internal`` used to say the code came
from "the text block named below" (``nommé ci-dessous`` in French).
``OSLFinding.text_name`` was hardcoded ``None`` at its only construction site
and no surface ever printed it, so the reader was sent looking for a line that
did not exist. The name is not on ``NodeShaderScript`` -- an internal script
node reaches its Text through the owning ``bNode``'s ``id`` pointer -- so the
promise was removed rather than answered with a guess that no real file could
contradict.
"""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from blend_xray import banner, report, scanner, strings
from blend_xray import dna_constants as dna
from blend_xray.banner import Tier

from .blend_builder import BlendBuilder
from .conftest import BANNED_WORDS_BY_LANG

BYTECODE = b"\x00\x01\x02\x03" * 16  # 64 bytes of "compiled" shader
BYTECODE_HASH = "6f1ed002ab5595859014ebf0951522d9"


def _blend(tmp_path: Path, name: str, **node: object) -> Path:
    builder = BlendBuilder()
    builder.add_script_node(**node)  # type: ignore[arg-type]
    path = tmp_path / name
    path.write_bytes(builder.to_bytes())
    return path


def _render(path: Path) -> str:
    result = scanner.scan_file(path)
    return report.format_text_report(result, report.make_palette(io.StringIO(), force=False))


# -- internal mode ------------------------------------------------------------
def test_internal_mode_is_inventoried(tmp_path: Path) -> None:
    result = scanner.scan_file(_blend(tmp_path, "internal.blend", mode=dna.NODE_SCRIPT_INTERNAL))
    assert len(result.osl_nodes) == 1
    node = result.osl_nodes[0]
    assert node.mode == dna.NODE_SCRIPT_INTERNAL
    assert node.mode_name == "NODE_SCRIPT_INTERNAL"
    assert node.filepath is None
    assert node.bytecode_bytes == 0


@pytest.mark.parametrize("lang", ["en", "fr"])
def test_internal_mode_promises_no_name_it_cannot_show(tmp_path: Path, lang: str) -> None:
    """The defect itself: a name was announced and never printed."""
    strings.set_language(lang)
    rendered = _render(_blend(tmp_path, "internal.blend", mode=dna.NODE_SCRIPT_INTERNAL))
    assert strings.t("osl_internal") in rendered
    assert strings.t("osl_external") not in rendered
    for promise in ("named below", "nommé ci-dessous", "nomme ci-dessous"):
        assert promise not in rendered.lower(), promise
    for banned in BANNED_WORDS_BY_LANG[lang]:
        assert banned not in rendered.lower()


def test_internal_mode_ignores_a_filepath_it_would_not_use(tmp_path: Path) -> None:
    """``filepath`` is only meaningful in external mode; internal must not print it."""
    path = _blend(
        tmp_path, "internal.blend", mode=dna.NODE_SCRIPT_INTERNAL, filepath="//unused.osl"
    )
    result = scanner.scan_file(path)
    assert result.osl_nodes[0].filepath is None
    assert "//unused.osl" not in _render(path)


# -- external mode ------------------------------------------------------------
def test_external_mode_reports_the_path_and_never_reads_it(tmp_path: Path) -> None:
    path = _blend(
        tmp_path, "external.blend", mode=dna.NODE_SCRIPT_EXTERNAL, filepath="//shaders/glow.osl"
    )
    result = scanner.scan_file(path)
    node = result.osl_nodes[0]
    assert node.mode_name == "NODE_SCRIPT_EXTERNAL"
    assert node.filepath == "//shaders/glow.osl"

    rendered = _render(path)
    assert strings.t("osl_external") in rendered
    assert strings.t("osl_filepath", path="//shaders/glow.osl") in rendered
    assert strings.t("osl_internal") not in rendered


@pytest.mark.parametrize("lang", ["en", "fr"])
def test_external_mode_renders_in_both_languages(tmp_path: Path, lang: str) -> None:
    strings.set_language(lang)
    rendered = _render(
        _blend(tmp_path, "external.blend", mode=dna.NODE_SCRIPT_EXTERNAL, filepath="//s.osl")
    )
    assert strings.t("osl_external") in rendered
    assert strings.t("osl_lower_severity") in rendered
    for banned in BANNED_WORDS_BY_LANG[lang]:
        assert banned not in rendered.lower()


# -- bytecode present ---------------------------------------------------------
def test_bytecode_is_measured_and_reported(tmp_path: Path) -> None:
    path = _blend(
        tmp_path,
        "bytecode.blend",
        mode=dna.NODE_SCRIPT_INTERNAL,
        bytecode_hash=BYTECODE_HASH,
        bytecode=BYTECODE,
    )
    result = scanner.scan_file(path)
    node = result.osl_nodes[0]
    assert node.bytecode_bytes == len(BYTECODE)
    assert node.bytecode_hash == BYTECODE_HASH

    rendered = _render(path)
    assert strings.t("osl_has_bytecode", size=len(BYTECODE)) in rendered
    assert strings.t("osl_bytecode_hash", hash=BYTECODE_HASH) in rendered


def test_bytecode_drives_amber_and_nothing_louder(tmp_path: Path) -> None:
    """Bytecode asks for a second reader; it does not reach outside Blender."""
    path = _blend(
        tmp_path, "bytecode.blend", mode=dna.NODE_SCRIPT_INTERNAL, bytecode=BYTECODE
    )
    info = banner.for_result(scanner.scan_file(path))
    assert info.tier is Tier.AMBER
    assert banner.REASON_OSL_BYTECODE in info.reasons


def test_a_script_node_without_bytecode_does_not_claim_any(tmp_path: Path) -> None:
    path = _blend(tmp_path, "plain.blend", mode=dna.NODE_SCRIPT_EXTERNAL, filepath="//s.osl")
    result = scanner.scan_file(path)
    assert result.osl_nodes[0].bytecode_bytes == 0
    assert banner.REASON_OSL_BYTECODE not in banner.for_result(result).reasons
    assert strings.t("osl_has_bytecode", size=0) not in _render(path)


# -- the severity framing this category depends on ----------------------------
@pytest.mark.parametrize(
    "node",
    [
        {"mode": dna.NODE_SCRIPT_INTERNAL},
        {"mode": dna.NODE_SCRIPT_EXTERNAL, "filepath": "//s.osl"},
        {"mode": dna.NODE_SCRIPT_INTERNAL, "bytecode": BYTECODE},
    ],
)
def test_every_shape_says_this_is_not_an_auto_run_vector(
    tmp_path: Path, node: dict[str, object]
) -> None:
    rendered = _render(_blend(tmp_path, "n.blend", **node))
    assert strings.t("cat_osl") in rendered
    assert strings.t("osl_lower_severity") in rendered


# -- machine surface ----------------------------------------------------------
def test_json_carries_the_node_and_no_field_that_is_never_filled(tmp_path: Path) -> None:
    path = _blend(
        tmp_path,
        "bytecode.blend",
        mode=dna.NODE_SCRIPT_EXTERNAL,
        filepath="//s.osl",
        bytecode_hash=BYTECODE_HASH,
        bytecode=BYTECODE,
    )
    payload = json.loads(report.format_json([scanner.scan_file(path)], []))
    nodes = payload["files"][0]["osl_nodes"]
    assert len(nodes) == 1
    assert set(nodes[0]) == {
        "owner",
        "mode",
        "mode_name",
        "filepath",
        "bytecode_bytes",
        "bytecode_hash",
    }
    assert nodes[0]["bytecode_bytes"] == len(BYTECODE)
    assert nodes[0]["mode_name"] == "NODE_SCRIPT_EXTERNAL"
