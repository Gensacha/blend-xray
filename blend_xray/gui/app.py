# SPDX-License-Identifier: GPL-3.0-or-later
"""The Blend X-Ray window: a portable, double-click front end for the scanner.

Built on tkinter alone so the packaged executable stays small and needs no
third-party runtime. Drag-and-drop is a *bonus*: if ``tkinterdnd2`` imports we
register a drop target, and if it does not the window says so once and the
"Choose a file..." buttons do the same job. Nothing else changes.

Scanning happens on a worker thread (:mod:`blend_xray.gui.scan_worker`); this
module only drains its queue from the Tk event loop, so the window keeps
repainting through a long folder scan and the Cancel button stays live.

There are no network calls, no telemetry and no auto-update here either. The
only thing this window touches is the file you point it at -- plus, and only
after you have read the exact key and agreed to it, one HKEY_CURRENT_USER
registry entry (:mod:`blend_xray.gui.shell_integration`).
"""

from __future__ import annotations

import contextlib
import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .. import __version__, cli, scanner, strings
from ..models import ScanResult
from . import render, shell_integration
from .report_view import ReportView
from .scan_worker import Failed, Finished, Progress, Scanned, ScanWorker, Started
from .theme import COLOURS, TAG_ALARM, TAG_DIM, UI_FAMILY, UI_SIZE

#: How often the Tk loop drains the worker queue, in milliseconds.
POLL_MS = 80

Entry = ScanResult | Failed

#: Registry state -> the catalogue key labelling the right-click button. Three
#: states, not two: an entry that exists but no longer works is not the same
#: thing as an entry that is installed.
SHELL_BUTTON_KEYS: dict[str, str] = {
    shell_integration.ABSENT: "gui_shell_add",
    shell_integration.CURRENT: "gui_shell_remove",
    shell_integration.STALE: "gui_shell_repair",
}


def window_title() -> str:
    """Title bar text: the tool, then the version.

    The exe is unsigned and arrives in a zip, so the title bar is the one
    place a user can always read the build back without hunting for a menu --
    which is exactly what SECURITY.md asks a reporter to quote.
    """
    return f"{strings.t('tool_name')} {__version__}"


def _make_root() -> tuple[tk.Tk, bool]:
    """Return a Tk root and whether drag-and-drop is available on it.

    ``tkinterdnd2`` needs both the Python package and the bundled ``tkdnd``
    Tcl library; either can be missing, and neither is worth an error message
    beyond the one line the window already shows.
    """
    try:
        from tkinterdnd2 import TkinterDnD

        return TkinterDnD.Tk(), True
    except Exception:  # noqa: BLE001 - optional dependency, any failure degrades
        return tk.Tk(), False


class BlendXRayWindow:
    """The whole application: one window, one worker at a time."""

    def __init__(self, root: tk.Tk, dnd_available: bool) -> None:
        self.root = root
        self.dnd_available = dnd_available
        self.entries: list[Entry] = []
        self.worker: ScanWorker | None = None
        self.startup_error: str | None = None

        root.title(window_title())
        root.geometry("1000x720")
        root.minsize(720, 480)
        root.configure(background=COLOURS["background"])
        self._build()
        self._check_dependencies()
        self._refresh_idle()

    # -- construction -------------------------------------------------------
    def _build(self) -> None:
        style = ttk.Style(self.root)
        style.configure("TFrame", background=COLOURS["background"])
        style.configure(
            "TLabel", background=COLOURS["background"], foreground=COLOURS["foreground"]
        )
        style.configure("Dim.TLabel", foreground=COLOURS["dim"])
        style.configure("Alarm.TLabel", foreground=COLOURS["alarm"])

        outer = ttk.Frame(self.root, padding=10)
        outer.pack(fill="both", expand=True)
        outer.rowconfigure(3, weight=1)
        outer.columnconfigure(0, weight=1)

        self._build_toolbar(outer)
        self._build_dropzone(outer)
        self._build_status(outer)
        self.view = ReportView(outer)
        self.view.grid(row=3, column=0, sticky="nsew", pady=(8, 0))

    def _build_toolbar(self, parent: ttk.Frame) -> None:
        bar = ttk.Frame(parent)
        bar.grid(row=0, column=0, sticky="ew")
        self.btn_file = ttk.Button(bar, command=self._choose_file)
        self.btn_folder = ttk.Button(bar, command=self._choose_folder)
        self.btn_copy = ttk.Button(bar, command=self._copy_report)
        self.btn_file.pack(side="left")
        self.btn_folder.pack(side="left", padx=(6, 0))
        self.btn_copy.pack(side="left", padx=(18, 0))

        self.btn_shell: ttk.Button | None = None
        if shell_integration.is_supported():
            self.btn_shell = ttk.Button(bar, command=self._toggle_shell)
            self.btn_shell.pack(side="left", padx=(6, 0))

        self.lang_label = ttk.Label(bar, style="Dim.TLabel")
        self.lang_label.pack(side="right", padx=(0, 6))
        self.lang_box = ttk.Combobox(
            bar,
            width=5,
            state="readonly",
            values=list(strings.SUPPORTED_LANGUAGES),
        )
        self.lang_box.set(strings.current_language())
        self.lang_box.bind("<<ComboboxSelected>>", self._on_language)
        self.lang_box.pack(side="right")

    def _build_dropzone(self, parent: ttk.Frame) -> None:
        self.dropzone = tk.Label(
            parent,
            background=COLOURS["surface"],
            foreground=COLOURS["dim"],
            font=(UI_FAMILY, UI_SIZE),
            relief="solid",
            borderwidth=1,
            padx=12,
            pady=14,
            wraplength=900,
            justify="left",
        )
        self.dropzone.grid(row=1, column=0, sticky="ew", pady=(10, 0))
        if self.dnd_available:
            self._register_drop_target()

    def _register_drop_target(self) -> None:
        try:
            from tkinterdnd2 import DND_FILES

            self.dropzone.drop_target_register(DND_FILES)
            self.dropzone.dnd_bind("<<Drop>>", self._on_drop)
        except Exception:  # noqa: BLE001 - a failed registration is not fatal
            self.dnd_available = False

    def _build_status(self, parent: ttk.Frame) -> None:
        row = ttk.Frame(parent)
        row.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        row.columnconfigure(0, weight=1)
        self.status = ttk.Label(row, style="Dim.TLabel", anchor="w")
        self.status.grid(row=0, column=0, sticky="ew")
        self.progress = ttk.Progressbar(row, mode="indeterminate", length=160)
        self.btn_cancel = ttk.Button(row, command=self._cancel, state="disabled")
        self.btn_cancel.grid(row=0, column=2, padx=(8, 0))

    # -- language -----------------------------------------------------------
    def _retranslate(self) -> None:
        """Re-label every static widget from the catalogue."""
        self.root.title(window_title())
        self.btn_file.configure(text=strings.t("gui_choose_file"))
        self.btn_folder.configure(text=strings.t("gui_choose_folder"))
        self.btn_copy.configure(text=strings.t("gui_copy_report"))
        self.btn_cancel.configure(text=strings.t("gui_cancel"))
        self.lang_label.configure(text=strings.t("gui_language"))
        key = "gui_drop_prompt" if self.dnd_available else "gui_drop_unavailable"
        self.dropzone.configure(text=strings.t(key))
        self._refresh_shell_button()

    def _on_language(self, _event: object = None) -> None:
        strings.set_language(self.lang_box.get())
        self._retranslate()
        self._redraw()

    # -- dependency check ---------------------------------------------------
    def _check_dependencies(self) -> None:
        """Refuse to look usable when blender-asset-tracer is wrong or absent."""
        try:
            scanner.assert_bat_version()
        except scanner.ToolError as exc:
            self.startup_error = str(exc)

    # -- choosing targets ---------------------------------------------------
    def _choose_file(self) -> None:
        path = filedialog.askopenfilename(
            title=strings.t("gui_file_dialog_title"),
            filetypes=[
                (strings.t("gui_blend_filter"), "*.blend"),
                (strings.t("gui_all_files"), "*.*"),
            ],
        )
        if path:
            self.start_scan([path])

    def _choose_folder(self) -> None:
        path = filedialog.askdirectory(title=strings.t("gui_folder_dialog_title"))
        if path:
            self.start_scan([path])

    def _on_drop(self, event: object) -> None:
        data = getattr(event, "data", "")
        targets = [str(item) for item in self.root.tk.splitlist(data) if str(item)]
        if targets:
            self.start_scan(targets)

    # -- scanning -----------------------------------------------------------
    def start_scan(self, targets: list[str]) -> None:
        if self.worker is not None and self.worker.is_running():
            return
        paths = cli.expand_targets(targets)
        if not paths:
            self._set_status(strings.t("gui_status_no_files", target=", ".join(targets)))
            return
        self.entries = []
        self.view.clear()
        self._draw_startup_error()
        self.worker = ScanWorker(paths)
        self.worker.start()
        self._set_busy(True)
        self.root.after(POLL_MS, self._drain)

    def _cancel(self) -> None:
        if self.worker is not None and self.worker.is_running():
            self.worker.cancel()
            self._set_status(strings.t("gui_cancel_pending"))

    def _drain(self) -> None:
        """Pull everything the worker has produced, then reschedule."""
        worker = self.worker
        if worker is None:
            return
        finished = False
        while not worker.events.empty():
            event = worker.events.get_nowait()
            finished = self._handle_guarded(event) or finished
        if not finished:
            self.root.after(POLL_MS, self._drain)

    def _handle_guarded(self, event: object) -> bool:
        """:meth:`_handle`, with a failure inside it reported instead of fatal.

        This runs from the Tk event loop, and it is the only thing that ever
        reschedules itself. An exception escaping it therefore does not stop
        one file -- it stops the loop: File and Folder stay disabled, Cancel
        stays live over a worker that has already gone, and the spinner turns
        forever. There is no message to go with it either, because a windowed
        PyInstaller build has ``sys.stderr is None`` and Tk's
        ``report_callback_exception`` writes the traceback to nowhere at all.
        The user gets a hung window and no reason for it.

        The event has already been taken off the queue by the time this can
        fail, so the rest of a folder scan still draws: one unrenderable
        result costs that result, not the batch.
        """
        try:
            return self._handle(event)
        except Exception as exc:  # noqa: BLE001 - see docstring
            self._report_draw_failure(exc)
            if isinstance(event, Finished):
                # The event that would have re-enabled the toolbar is the one
                # that blew up. Do its job and let the loop stop.
                self._set_busy(False)
                return True
            return False

    def _report_draw_failure(self, exc: Exception) -> None:
        """Put the failure in the window, which is the only place it can be seen.

        The report area is tried first and the status bar always follows: if
        whatever broke the drawing also breaks appending to the view, a
        one-line status is still better than the silence this replaces.
        """
        message = strings.t("gui_draw_failed", reason=f"{type(exc).__name__}: {exc}")
        with contextlib.suppress(Exception):
            self.view.append([render.Line(message, TAG_ALARM)])
        self._set_status(message)

    def _handle(self, event: object) -> bool:
        """Apply one worker event. Returns True when the scan is over."""
        if isinstance(event, Started):
            self._set_status(strings.t("gui_status_counted", done=0, total=event.total))
        elif isinstance(event, Progress):
            self._set_status(strings.t("gui_status_reading", path=event.path))
        elif isinstance(event, Scanned):
            self.entries.append(event.result)
            self._draw_entry(event.result)
        elif isinstance(event, Failed):
            self.entries.append(event)
            self._draw_entry(event)
        elif isinstance(event, Finished):
            self._on_finished(event)
            return True
        return False

    def _on_finished(self, event: Finished) -> None:
        self._set_busy(False)
        if event.cancelled:
            self._set_status(
                strings.t("gui_status_cancelled", done=event.done, total=event.total)
            )
        else:
            self._set_status(strings.t("gui_status_done", total=event.total))

    def _set_busy(self, busy: bool) -> None:
        state = "disabled" if busy else "normal"
        self.btn_file.configure(state=state)
        self.btn_folder.configure(state=state)
        self.btn_cancel.configure(state="normal" if busy else "disabled")
        if busy:
            self.progress.grid(row=0, column=1, padx=(8, 0))
            self.progress.start(15)
        else:
            self.progress.stop()
            self.progress.grid_remove()

    def _set_status(self, text: str) -> None:
        self.status.configure(text=text)

    # -- drawing ------------------------------------------------------------
    def _refresh_idle(self) -> None:
        self._retranslate()
        self.view.clear()
        self._draw_startup_error()
        if not self.entries:
            self.view.append([render.Line(strings.t("gui_status_idle"), TAG_DIM)])
        self._set_status(strings.t("gui_status_idle"))

    def _draw_startup_error(self) -> None:
        if self.startup_error:
            self.view.append([render.Line(self.startup_error, TAG_ALARM)])

    def _redraw(self) -> None:
        """Re-render the stored entries, e.g. after a language change.

        Guarded per entry for the same reason :meth:`_handle_guarded` is: a
        result that could not be drawn once is still in ``entries``, so the
        next language switch would hit it again -- and this runs from a Tk
        callback, where an escaping exception is written to a stderr that a
        windowed build does not have. One unrenderable entry costs that entry.
        """
        if not self.entries:
            self._refresh_idle()
            return
        self.view.clear()
        self._draw_startup_error()
        for entry in self.entries:
            try:
                self._draw_entry(entry)
            except Exception as exc:  # noqa: BLE001 - see docstring
                self._report_draw_failure(exc)

    def _draw_entry(self, entry: Entry) -> None:
        """Append one stored entry to the report area."""
        if isinstance(entry, Failed):
            self.view.append(render.render_error(entry.path, entry.kind, entry.message))
        else:
            self.view.append(render.render_result(entry))

    def _copy_report(self) -> None:
        if not self.view.has_content():
            self._set_status(strings.t("gui_copy_nothing"))
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(self.view.plain_text())
        self.root.update()
        self._set_status(strings.t("gui_copied"))

    # -- Windows right-click entry -----------------------------------------
    def _refresh_shell_button(self) -> None:
        """Label the button from what the registry points at, not from key existence.

        The question is not "does the key exist" but "does the key run *this*
        copy". An entry pointing at a path this build no longer occupies --
        the zip run straight out of ``%TEMP%``, or the folder moved since --
        is a menu item that silently does nothing, and a button reading
        "Remove" would be telling the user it works. See
        :func:`blend_xray.gui.shell_integration.state`.
        """
        if self.btn_shell is None:
            return
        try:
            state = shell_integration.state()
        except shell_integration.ShellIntegrationError:
            state = shell_integration.ABSENT
        self.btn_shell.configure(text=strings.t(SHELL_BUTTON_KEYS[state]))

    def _toggle_shell(self) -> None:
        """Show the exact registry change, then apply it only if agreed."""
        label = strings.t("gui_shell_verb", tool=strings.t("tool_name"))
        title = strings.t("gui_shell_dialog_title")
        try:
            current = shell_integration.current_command()
            plan = shell_integration.plan(label)
            installed = current == plan.command
            stale = None if installed else current
            body = self._shell_dialog_text(installed, plan, stale)
            if not messagebox.askokcancel(title, body, parent=self.root):
                return
            if installed:
                shell_integration.uninstall()
                self._set_status(strings.t("gui_shell_removed"))
            else:
                # CreateKey opens the key when it already exists, so the stale
                # command is overwritten rather than duplicated: confirming a
                # repair is one write, not an uninstall/reinstall dance.
                shell_integration.install(label)
                self._set_status(strings.t("gui_shell_added", label=label))
        except shell_integration.ShellIntegrationError as exc:
            messagebox.showerror(title, strings.t("gui_shell_failed", reason=exc), parent=self.root)
        self._refresh_shell_button()

    @staticmethod
    def _shell_dialog_text(
        installed: bool, plan: shell_integration.Plan, stale: str | None = None
    ) -> str:
        if installed:
            return strings.t("gui_shell_confirm_remove", key=plan.key)
        parts = [strings.t("gui_shell_explain")]
        if stale is not None:
            parts.append(strings.t("gui_shell_stale", command=stale))
        parts.append(strings.t("gui_shell_confirm_add", key=plan.key, command=plan.command))
        return "\n\n".join(parts)


def main(argv: list[str] | None = None) -> int:
    """Open the window. A path in ``argv[1]`` is scanned straight away."""
    args = sys.argv[1:] if argv is None else argv
    strings.set_language(strings.detect_language())
    root, dnd = _make_root()
    window = BlendXRayWindow(root, dnd)
    target = args[0] if args and Path(args[0]).exists() else None
    if target:
        root.after(50, lambda: window.start_scan([target]))
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
