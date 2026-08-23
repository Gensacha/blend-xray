# SPDX-License-Identifier: GPL-3.0-or-later
"""``--max-seconds`` has to bound the whole scan, and say so when it bites.

The bug these cover: the :class:`~blend_xray.guards.Deadline` was created inside
``preflight()`` and handed only to ``walk_block_table()``. Everything after the
structural walk -- the BAT parse, text reconstruction, ``ast.parse``, the
literal sweeps and library classification -- ran with no time limit at all,
while the flag in the command line said otherwise. A file with eight text
blocks just under the parse cap took 7.95 seconds against ``--max-seconds 1``.

The second half of the fix matters as much as the first: a scan that stops
early must not be able to render as an uneventful one. A truncated inventory
that says nothing about being truncated is indistinguishable from a file with
nothing in it, which is the one reading this tool exists to prevent.

Nothing here asserts on wall-clock timing except
:func:`test_the_documented_budget_bounds_the_whole_scan`, and that one measures
the same file unbounded first and compares, rather than hard-coding a duration
that would mean something different on another machine. Everything else drives
an already-expired deadline, which is exact.
"""

from __future__ import annotations

import gzip
import io
import json
import tempfile
import time
from pathlib import Path
from typing import Any, ClassVar

import pytest

from blend_xray import banner, cli, guards, report, scanner, strings, truncation
from blend_xray.banner import Tier
from blend_xray.models import Category, ScanResult

from .blend_builder import BlendBuilder, minimal_blend

#: Bodies of quoted tokens: cheap to build, expensive to sweep for literals,
#: which is where the unbounded time actually went.
HEAVY_BLOCK_COUNT = 8
HEAVY_TOKENS = 12_000

#: Comfortably longer than preflight on the fixture below (a millisecond) and
#: comfortably shorter than one block's analysis (a tenth of a second), so the
#: budget always runs out during the text stage and never during preflight.
MID_SCAN_BUDGET = 0.05


def _heavy_body(seed: int) -> str:
    tokens = ",".join(f"'{seed}-{n}'" for n in range(HEAVY_TOKENS))
    return f"x = [{tokens}]"


@pytest.fixture
def heavy_blend(tmp_path: Path) -> Path:
    builder = BlendBuilder()
    for i in range(HEAVY_BLOCK_COUNT):
        builder.add_text(f"s{i}.py", _heavy_body(i), flags=4)
    path = tmp_path / "heavy.blend"
    path.write_bytes(builder.to_bytes())
    return path


@pytest.fixture
def mixed_blend(tmp_path: Path) -> Path:
    """One datablock of every category, so each stage has something to reach."""
    builder = BlendBuilder()
    builder.add_text("s.py", "import bpy\n", flags=4)
    builder.add_driver("frame * 2")
    builder.add_script_node(1, filepath="//s.osl")
    builder.add_library("//lib/a.blend")
    path = tmp_path / "mixed.blend"
    path.write_bytes(builder.to_bytes())
    return path


def _expired() -> guards.Deadline:
    return guards.Deadline(-1.0)


def _timed_out_result(stage: Category = Category.TEXT) -> ScanResult:
    """A result that stopped with nothing collected -- the dangerous shape."""
    result = ScanResult(path=Path("partial.blend"))
    scanner._mark_timeout(result, stage, guards.Deadline(1.0))
    return result


# -- the budget is actually honoured ---------------------------------------
def test_the_documented_budget_bounds_the_whole_scan(heavy_blend: Path) -> None:
    unbounded_start = time.monotonic()
    full = scanner.scan_file(heavy_blend, guards.Limits(max_seconds=600.0))
    unbounded = time.monotonic() - unbounded_start
    assert full.timed_out is False
    assert len(full.texts) == HEAVY_BLOCK_COUNT

    budget = unbounded / 3
    bounded_start = time.monotonic()
    partial = scanner.scan_file(heavy_blend, guards.Limits(max_seconds=budget))
    bounded = time.monotonic() - bounded_start

    assert partial.timed_out is True
    assert len(partial.texts) < HEAVY_BLOCK_COUNT
    assert bounded < unbounded
    # The margin is one block's analysis: the deadline is polled between blocks
    # and between the stages of a block, so the overshoot is bounded by
    # whichever single stage was in flight when the budget ran out.
    assert bounded < budget + (unbounded / HEAVY_BLOCK_COUNT) + 0.5


def test_the_deadline_can_be_polled_without_raising() -> None:
    """Pre-parse expiry is a refusal; mid-scan expiry is a partial result.

    Both readings come off one object, so it has to offer both a raising check
    and a silent one.
    """
    assert guards.Deadline(600.0).expired is False
    assert _expired().expired is True
    with pytest.raises(guards.MalformedBlendError):
        _expired().check()
    assert guards.Deadline(5.0).limit == 5.0


# -- every stage consults the budget, not just the first -------------------
@pytest.fixture
def opened_blend(mixed_blend: Path) -> Any:
    from blender_asset_tracer.blendfile import BlendFile

    with tempfile.TemporaryDirectory() as tmp:
        pre = guards.preflight(mixed_blend, guards.Limits(), Path(tmp))
        bfile = BlendFile(pre.data_path)
        try:
            yield bfile
        finally:
            bfile.close()


def test_every_stage_stops_on_an_expired_budget_and_names_itself(
    opened_blend: Any, mixed_blend: Path
) -> None:
    """Each stage is checked in isolation, so none can be silently unwired."""
    limits = guards.Limits()
    stages = {
        Category.TEXT: lambda r: scanner._scan_texts(opened_blend, limits, r, _expired()),
        Category.DRIVER: lambda r: scanner._scan_drivers(opened_blend, r, _expired()),
        Category.OSL: lambda r: scanner._scan_osl(opened_blend, r, _expired()),
        Category.LIBRARY: lambda r: scanner._scan_libraries(
            opened_blend, mixed_blend.parent, r, _expired()
        ),
        Category.FILEPATH: lambda r: scanner._scan_filepaths(opened_blend, r, _expired()),
    }
    for category, run in stages.items():
        result = ScanResult(path=mixed_blend)
        assert run(result) is False, category
        assert result.timed_out is True, category
        assert result.timed_out_at == str(category)


def test_a_stage_that_finishes_reports_success(opened_blend: Any, mixed_blend: Path) -> None:
    result = ScanResult(path=mixed_blend)
    assert scanner._scan_texts(opened_blend, guards.Limits(), result, guards.Deadline(600)) is True
    assert result.timed_out is False


def test_a_block_cut_short_mid_analysis_is_dropped_not_reported_as_empty(
    heavy_blend: Path,
) -> None:
    """A TextFinding with no explanation is this tool's spelling of "empty"."""
    result = scanner.scan_file(heavy_blend, guards.Limits(max_seconds=MID_SCAN_BUDGET))
    assert result.timed_out is True
    assert all(t.explanation is not None for t in result.texts)


# -- a stopped scan says so, everywhere ------------------------------------
def test_a_timed_out_scan_records_where_it_stopped(heavy_blend: Path) -> None:
    result = scanner.scan_file(heavy_blend, guards.Limits(max_seconds=MID_SCAN_BUDGET))
    assert result.timed_out is True
    assert result.timed_out_at == "text"
    assert result.time_budget == MID_SCAN_BUDGET
    assert len(result.texts) < HEAVY_BLOCK_COUNT
    assert result.needs_attention is True


def test_a_timed_out_scan_can_never_render_a_neutral_banner() -> None:
    result = _timed_out_result()
    assert result.has_findings is False  # nothing at all was collected
    info = banner.for_result(result)
    assert info.tier is not Tier.NEUTRAL
    assert banner.REASON_TIMEOUT in info.reasons
    assert info.to_dict()["timed_out"] is True
    assert info.headline() == strings.t("banner_timeout_headline")


def test_a_red_finding_still_outranks_the_timeout_headline(heavy_blend: Path) -> None:
    """RED means something was already found reaching outside Blender."""
    result = _timed_out_result()
    result.libraries.append(
        scanner.classify_library_path(r"\\host\share\x.blend", heavy_blend.parent)
    )
    info = banner.for_result(result)
    assert info.tier is Tier.RED
    assert info.headline() == strings.t("banner_red_headline")
    assert banner.REASON_TIMEOUT in info.reasons  # still stated, just not the headline


def test_the_report_leads_with_the_truncation_and_drops_looks_ordinary() -> None:
    result = _timed_out_result()
    pal = report.make_palette(io.StringIO(), force=False)
    rendered = report.format_text_report(result, pal)

    assert truncation.notice(result) in rendered
    assert "PARTIAL INSPECTION" in rendered
    # The two sentences that would otherwise read as "we looked and found nothing".
    assert strings.t("nothing_found") not in rendered
    assert strings.t("recommend_looks_ordinary") not in rendered
    assert (
        truncation.recommendation(result) in rendered
    )


def test_quiet_output_still_carries_the_truncation() -> None:
    """--quiet drops every context section; it must not drop this one."""
    result = _timed_out_result()
    pal = report.make_palette(io.StringIO(), force=False)
    assert "PARTIAL INSPECTION" in report.format_text_report(result, pal, quiet=True)


def test_the_window_carries_the_same_truncation_notice() -> None:
    from blend_xray.gui import render as gui_render

    result = _timed_out_result()
    flattened = gui_render.plain_text(gui_render.render_result(result))
    assert truncation.notice(result) in flattened
    assert strings.t("nothing_found") not in flattened


def test_the_french_report_says_it_too() -> None:
    strings.set_language("fr")
    try:
        result = _timed_out_result()
        pal = report.make_palette(io.StringIO(), force=False)
        rendered = report.format_text_report(result, pal)
        assert "INSPECTION PARTIELLE" in rendered
        assert strings.t("recommend_looks_ordinary") not in rendered
    finally:
        strings.set_language(strings.DEFAULT_LANGUAGE)


def test_the_exit_code_is_not_ok_for_a_scan_that_gave_up(heavy_blend: Path) -> None:
    out, err = io.StringIO(), io.StringIO()
    code = cli.run(
        ["scan", "--max-seconds", str(MID_SCAN_BUDGET), str(heavy_blend)],
        stdout=out,
        stderr=err,
    )
    assert code == cli.EXIT_FINDINGS
    assert "PARTIAL INSPECTION" in out.getvalue()


def test_the_json_payload_names_the_truncation(heavy_blend: Path) -> None:
    out = io.StringIO()
    cli.run(
        ["scan", "--json", "--max-seconds", str(MID_SCAN_BUDGET), str(heavy_blend)],
        stdout=out,
        stderr=io.StringIO(),
    )
    payload = json.loads(out.getvalue())["files"][0]
    assert payload["timed_out"] is True
    assert payload["timed_out_at"] == "text"
    assert payload["banner"]["tier"] != "neutral"


def test_every_stage_name_has_a_string() -> None:
    """A stage added later must not render as a blank in somebody's report."""
    for stage in truncation.STAGE_STRING_KEYS:
        assert not truncation.stage_label(stage).startswith("![")
    for category in Category:
        assert str(category) in truncation.STAGE_STRING_KEYS


# -- one datablock cannot outrun the budget on its own ---------------------
class _StubPointer:
    """The shape ``_read_path_field`` accepts for a ``char *`` field."""

    def __init__(self, raw: bytes) -> None:
        self._raw = raw

    def as_bytes_string(self) -> bytes:
        return self._raw


class _StubBlock:
    def __init__(self, raw: bytes) -> None:
        self._raw = raw

    def has_field(self, _name: bytes) -> bool:
        return True

    def get_pointer(self, _name: bytes, default: object = None) -> _StubPointer:
        return _StubPointer(self._raw)


def test_an_oversized_path_field_is_refused_at_the_read() -> None:
    """The deadline is polled between items; this makes one item bounded.

    A ``char *`` path is limited only by the block's declared length, which is
    checked against the size of the *file*, not against anything path-shaped.
    Without this cap a small file could declare a path of tens of megabytes and
    spend the whole budget inside a single classification, with the next
    ``deadline.expired`` check never reached.
    """
    ok = scanner._read_path_field(_StubBlock(b"//lib/x.blend"), (b"filepath",))
    assert ok == "//lib/x.blend"

    huge = b"//" + b"a/" * scanner.MAX_PATH_FIELD_BYTES
    with pytest.raises(guards.MalformedBlendError) as exc:
        scanner._read_path_field(_StubBlock(huge), (b"filepath",))
    assert str(scanner.MAX_PATH_FIELD_BYTES) in str(exc.value)


def test_classifying_the_longest_permitted_path_is_still_cheap() -> None:
    """The cap is only worth having if what fits under it is fast."""
    worst = "//" + "a/" * (scanner.MAX_PATH_FIELD_BYTES // 2)
    start = time.monotonic()
    scanner.classify_library_path(worst, Path("C:/proj/shot"))
    assert time.monotonic() - start < 0.5


class _StubFile:
    """Enough of a BlendFile for a stage to reach its first field read."""

    sdna_index_from_id: ClassVar[dict[bytes, int]] = {
        b"ChannelDriver": 0,
        b"NodeShaderScript": 0,
    }

    def __init__(self) -> None:
        self.blocks = [_StubDataBlock()]

    def find_blocks_from_code(self, _code: bytes) -> list[_StubDataBlock]:
        return [_StubDataBlock()]


class _StubDataBlock(_StubBlock):
    sdna_index = 0
    addr_old = 1
    id_name = b"IMtexture.png"

    def __init__(self) -> None:
        super().__init__(b"//tex.png")


@pytest.mark.parametrize(
    "stage",
    [
        "_scan_texts",
        "_scan_drivers",
        "_scan_osl",
        "_scan_libraries",
        "_scan_filepaths",
    ],
)
def test_a_malformed_field_refuses_the_file_from_every_stage(
    stage: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every stage treats "not a .blend we keep parsing" the same way.

    ``_scan_texts`` re-raised ``MalformedBlendError`` and the other four
    downgraded it to a warning, so the same hostile field meant "refuse this
    file" in one category and "note it and carry on" in the next -- and the
    oversized-path refusal added above would have been silently absorbed in
    four of the five places it can fire.
    """

    def boom(*_args: object, **_kwargs: object) -> None:
        raise guards.MalformedBlendError("field is not a path")

    monkeypatch.setattr(scanner, "_read_path_field", boom)
    monkeypatch.setattr(scanner, "_first_field", boom)
    monkeypatch.setattr(scanner, "_read_text_lines", boom)

    limits = guards.Limits()
    deadline = guards.Deadline(600)
    calls = {
        "_scan_texts": lambda b, r: scanner._scan_texts(b, limits, r, deadline),
        "_scan_drivers": lambda b, r: scanner._scan_drivers(b, r, deadline),
        "_scan_osl": lambda b, r: scanner._scan_osl(b, r, deadline),
        "_scan_libraries": lambda b, r: scanner._scan_libraries(b, Path("."), r, deadline),
        "_scan_filepaths": lambda b, r: scanner._scan_filepaths(b, r, deadline),
    }
    with pytest.raises(guards.MalformedBlendError):
        calls[stage](_StubFile(), ScanResult(path=Path("x.blend")))


# -- the decompression path is bounded too ---------------------------------
def test_the_decompression_copy_honours_the_deadline() -> None:
    """A small bomb could force a 4 GiB temp write with no time bound at all."""
    src = io.BytesIO(b"x" * (4 << 20))
    dst = io.BytesIO()
    with pytest.raises(guards.MalformedBlendError) as exc:
        guards._copy_capped(src, dst, 1 << 30, _expired())
    assert "longer than" in str(exc.value)


def test_a_compressed_file_cannot_outlast_the_budget(tmp_path: Path) -> None:
    path = tmp_path / "packed.blend"
    path.write_bytes(gzip.compress(minimal_blend()))
    with pytest.raises(guards.MalformedBlendError):
        scanner.scan_file(path, guards.Limits(max_seconds=-1.0))
