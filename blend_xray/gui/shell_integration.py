# SPDX-License-Identifier: GPL-3.0-or-later
"""Optional Windows Explorer right-click entry. Never an install step.

Design constraints, all of them deliberate:

* **HKEY_CURRENT_USER only.** Nothing is ever written to HKEY_LOCAL_MACHINE, so
  the toggle never triggers a UAC prompt and never changes anything for another
  account on the machine.
* **``SystemFileAssociations`` rather than a ProgID.** This adds a verb to the
  context menu of ``.blend`` files without touching which application owns the
  extension: double-clicking a .blend still opens Blender, exactly as before.
* **Two keys, and that is the whole footprint.** The verb key and its
  ``command`` sub-key. :func:`uninstall` removes both and nothing else.
* **Nothing here runs on import, and nothing here writes without being called.**
  The window shows the user :func:`plan` -- the literal key and the literal
  command -- and only calls :func:`install` after they agree. A tool whose whole
  message is "do not run what you have not looked at" does not get to make
  silent system changes.

On a non-Windows platform :func:`is_supported` returns False and the window
hides the button rather than offering something that cannot work.
"""

from __future__ import annotations

import dataclasses
import sys
from pathlib import Path

if sys.platform == "win32":  # pragma: no cover - exercised only on Windows
    import winreg
else:  # pragma: no cover - exercised only off Windows
    winreg = None  # type: ignore[assignment]

#: Sub-key name for our verb. Not shown to anyone; the visible label is the
#: default value stored *in* the key.
VERB: str = "BlendXRay"

#: Path under HKEY_CURRENT_USER. Kept as a module constant so the confirmation
#: dialog and the writer cannot disagree about what is being created.
KEY_PATH: str = rf"Software\Classes\SystemFileAssociations\.blend\shell\{VERB}"

#: The same path as the user would see it in regedit.
DISPLAY_KEY: str = rf"HKEY_CURRENT_USER\{KEY_PATH}"

_COMMAND_PATH: str = rf"{KEY_PATH}\command"


class ShellIntegrationError(RuntimeError):
    """The registry could not be read or written. Carries the OS reason."""


@dataclasses.dataclass(frozen=True)
class Plan:
    """Exactly what a confirmed toggle would write, for showing to the user."""

    key: str
    command: str
    label: str


def is_supported() -> bool:
    """True only on Windows. Everywhere else the feature does not exist."""
    return sys.platform == "win32" and winreg is not None


def _launcher_script() -> Path | None:
    """The double-click launcher at the repository root, when running from source."""
    candidate = Path(__file__).resolve().parents[2] / "blend_xray_gui.py"
    return candidate if candidate.is_file() else None


def _interpreter() -> str:
    """Prefer ``pythonw.exe`` so the right-click entry opens no console window."""
    executable = Path(sys.executable)
    windowed = executable.with_name("pythonw.exe")
    return str(windowed if windowed.is_file() else executable)


def launch_command() -> str:
    """The command Explorer would run, with ``%1`` standing for the clicked file.

    Frozen (PyInstaller) builds are a single executable and need no interpreter.
    Running from a source checkout points at the repository's launcher script,
    falling back to ``-m blend_xray.gui`` when that file is not where expected
    (an installed wheel, for instance).
    """
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}" "%1"'
    script = _launcher_script()
    if script is not None:
        return f'"{_interpreter()}" "{script}" "%1"'
    return f'"{_interpreter()}" -m blend_xray.gui "%1"'


def plan(label: str) -> Plan:
    """What :func:`install` would write. Reads nothing and writes nothing."""
    return Plan(key=DISPLAY_KEY, command=launch_command(), label=label)


def current_command() -> str | None:
    """The command currently registered, or None when the entry is absent.

    A missing key is a normal state, not an error, and reports as None. Any
    other registry failure is raised rather than reported as "not installed":
    telling someone the entry is absent when we simply could not look would be
    the same class of lie this tool exists to avoid.
    """
    if not is_supported():
        return None
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _COMMAND_PATH) as key:
            value, _kind = winreg.QueryValueEx(key, "")
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise ShellIntegrationError(str(exc)) from exc
    return str(value)


#: No entry at all.
ABSENT: str = "absent"
#: An entry that runs this copy of the tool.
CURRENT: str = "current"
#: An entry that exists but runs a path this copy no longer occupies.
STALE: str = "stale"


def state() -> str:
    """Which of :data:`ABSENT`, :data:`CURRENT`, :data:`STALE` describes the entry.

    Key existence is not the question the window is really asking. The stored
    command is an absolute path baked in at install time, and two entirely
    ordinary sequences invalidate it without touching the registry:

    * Double-clicking ``BlendXRay.exe`` **from inside the downloaded zip**.
      Explorer silently extracts to ``%TEMP%\\Temp1_<zipname>\\``, so that is
      the path recorded -- and Windows deletes that folder later.
    * Moving, renaming or re-extracting the folder after installing.

    In both cases the Explorer menu item still appears and does nothing at
    all, while a button reading "Remove from right-click menu" tells the user
    the feature is working. Comparing the two commands is what turns that into
    an offer to repair it.
    """
    current = current_command()
    if current is None:
        return ABSENT
    return CURRENT if current == launch_command() else STALE


def is_installed() -> bool:
    """True when *some* entry exists for this user, whatever it points at."""
    return state() != ABSENT


def is_current() -> bool:
    """True only when the registered entry runs *this* copy of the tool."""
    return state() == CURRENT


def install(label: str) -> Plan:
    """Create the verb and its command. Call only after the user has agreed.

    Returns the plan that was actually written, so the caller can report it.
    """
    if not is_supported():
        raise ShellIntegrationError("this is a Windows-only feature")
    written = plan(label)
    try:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, KEY_PATH) as key:
            winreg.SetValueEx(key, "", 0, winreg.REG_SZ, label)
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, _COMMAND_PATH) as key:
            winreg.SetValueEx(key, "", 0, winreg.REG_SZ, written.command)
    except OSError as exc:
        raise ShellIntegrationError(str(exc)) from exc
    return written


def uninstall() -> None:
    """Delete the command sub-key and then the verb key. Nothing else.

    Already-absent keys are not an error: the button's job is to leave the
    registry without our entry, and it already is.
    """
    if not is_supported():
        raise ShellIntegrationError("this is a Windows-only feature")
    for path in (_COMMAND_PATH, KEY_PATH):
        try:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, path)
        except FileNotFoundError:
            continue
        except OSError as exc:
            raise ShellIntegrationError(str(exc)) from exc
