# SPDX-License-Identifier: GPL-3.0-or-later
"""Run scans off the Tk main thread.

A folder of .blend files can take a while, and a frozen window is how a user
concludes a tool has crashed. So the scanning happens on a worker thread and
the only thing it ever touches is a :class:`queue.Queue`; the window drains
that queue from its own event loop and does all the drawing. No Tk object is
ever handled from the worker.

**Cancellation is checked between files, not inside one.** A single very large
file therefore finishes reading before the worker stops. That is bounded rather
than open-ended: :class:`blend_xray.guards.Limits` already caps per-file
wall-clock time, file size and decompressed size. It is stated here rather than
hidden because a Cancel button that sometimes takes a few seconds is fine, and
a Cancel button whose limits are undocumented is not.
"""

from __future__ import annotations

import dataclasses
import queue
import threading
from pathlib import Path

from .. import guards, scanner
from ..models import ScanResult


@dataclasses.dataclass(frozen=True)
class Started:
    """Emitted once, before the first file is opened."""

    total: int


@dataclasses.dataclass(frozen=True)
class Progress:
    """Emitted before each file is read."""

    done: int
    total: int
    path: Path


@dataclasses.dataclass(frozen=True)
class Scanned:
    """One file read successfully."""

    result: ScanResult


@dataclasses.dataclass(frozen=True)
class Failed:
    """One file that could not be read. ``kind`` keys into ERROR_STRING_KEYS."""

    path: Path
    kind: str
    message: str


@dataclasses.dataclass(frozen=True)
class Finished:
    """Emitted exactly once, whatever happened, including on cancellation."""

    done: int
    total: int
    cancelled: bool


Event = Started | Progress | Scanned | Failed | Finished


def classify(exc: Exception) -> str:
    """Map an exception from :func:`scanner.scan_file` to an error kind."""
    if isinstance(exc, guards.NotABlendFileError):
        return "not_a_blend"
    if isinstance(exc, guards.MalformedBlendError):
        return "malformed"
    if isinstance(exc, scanner.ToolError):
        return "tool_error"
    return "unreadable"


class ScanWorker:
    """One scan, on one background thread, cancellable between files."""

    def __init__(self, paths: list[Path], limits: guards.Limits | None = None) -> None:
        self._paths = list(paths)
        self._limits = limits or guards.Limits()
        self._cancel = threading.Event()
        self._thread: threading.Thread | None = None
        #: Drained by the window from its own event loop.
        self.events: queue.Queue[Event] = queue.Queue()

    def start(self) -> None:
        if self._thread is not None:
            raise RuntimeError("this worker has already been started")
        self._thread = threading.Thread(target=self._run, name="blend-xray-scan", daemon=True)
        self._thread.start()

    def cancel(self) -> None:
        """Ask the worker to stop after the file it is currently reading."""
        self._cancel.set()

    @property
    def cancelled(self) -> bool:
        return self._cancel.is_set()

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def _run(self) -> None:
        total = len(self._paths)
        done = 0
        self.events.put(Started(total=total))
        for path in self._paths:
            if self._cancel.is_set():
                break
            self.events.put(Progress(done=done, total=total, path=path))
            self._scan_one(path)
            done += 1
        self.events.put(Finished(done=done, total=total, cancelled=self._cancel.is_set()))

    def _scan_one(self, path: Path) -> None:
        """Read one file, turning any failure into a Failed event.

        Every exception is caught on purpose: one hostile or corrupt file must
        degrade into a reported error, never into a dead worker thread that
        leaves the window waiting for events that will not come.
        """
        try:
            self.events.put(Scanned(result=scanner.scan_file(path, self._limits)))
        except Exception as exc:  # noqa: BLE001 - see docstring
            self.events.put(Failed(path=path, kind=classify(exc), message=str(exc)))
