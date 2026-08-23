# SPDX-License-Identifier: GPL-3.0-or-later
"""Classify a library path out of a .blend file, touching nothing.

Why this is its own module
--------------------------
This used to live in :mod:`blend_xray.scanner` and used ``Path.resolve()``. On
Windows that is a **network operation**: ``resolve()`` on ``\\\\host\\share``
asks the OS for that share, the OS opens an SMB connection, and SMB
authenticates automatically with the logged-in user's NTLM credentials. So
merely *classifying* a path handed to us by a hostile file leaked the user's
credential hash to a host that file chose -- before the human had read a single
line of the report, in a tool whose README promises it makes no network calls.

A doubled separator was all it took. Blender writes blend-relative paths as
``//name``; the old code stripped those two characters and joined the rest onto
the .blend's folder. ``////host/share/x.blend`` survives that strip as
``//host/share/x.blend``, and ``Path.__truediv__`` **discards the left operand**
when the right one has its own root -- so the join landed on a UNC root, and
``resolve()`` went to the network. The path was reported as an ordinary
blend-relative one, and the file came out neutral.

The rule now
------------
Classification is pure string and :class:`~pathlib.PurePath` computation.
Nothing here calls ``resolve``, ``stat``, ``exists``, ``is_dir`` or
``realpath``, and nothing here may ever start: the input is attacker-controlled,
so every filesystem call on it is a capability handed to the attacker. ``..``
segments are collapsed lexically, which is what a reader means by "where does
this point" anyway -- symlink-accurate resolution is not worth a network round
trip to a host named by the file being inspected.

Detection happens **after** normalisation, never before. ``////host/share``,
``//\\\\host\\share``, ``\\\\?\\UNC\\host\\share`` and every mixed-separator
spelling of those normalise to the same UNC root and are all reported as UNC.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import PurePath, PureWindowsPath
from typing import Final

from .models import LibraryFinding

#: Blender's marker for "relative to this .blend file's own folder".
BLEND_RELATIVE_PREFIX: Final = "//"

#: Segments Windows accepts as the device-namespace prefix in ``\\?\...`` and
#: ``\\.\...``. They are skipped when looking for the real host name.
_DEVICE_PREFIXES: Final = frozenset({"?", "."})

#: The segment that marks a device-namespace path as a UNC one:
#: ``\\?\UNC\server\share`` is ``\\server\share`` written the long way.
_UNC_MARKER: Final = "UNC"


def _segments(normalised: str) -> list[str]:
    """Non-empty path segments of an already-slash-normalised path."""
    return [part for part in normalised.split("/") if part]


def root_kind(normalised: str) -> tuple[str, str | None]:
    """What root, if any, a slash-normalised path stands on.

    Returns one of ``("unc", host)``, ``("drive", letter)``, ``("root", None)``
    or ``("relative", None)``. This is the whole security decision of the
    module, and it is made on the normalised text alone -- no filesystem, no
    platform dependence, so a Windows-only hazard is still classified
    identically when the tests run on Linux.
    """
    if normalised.startswith("//"):
        parts = _segments(normalised)
        if parts and parts[0] in _DEVICE_PREFIXES:
            parts = parts[1:]
            # \\?\C:\x is a drive, not a share, despite the two leading slashes.
            if parts and _is_drive(parts[0]):
                return "drive", parts[0][0]
            if parts and parts[0].upper() == _UNC_MARKER:
                parts = parts[1:]
        return "unc", (parts[0] if parts else None)
    if _is_drive(normalised):
        return "drive", normalised[0]
    if normalised.startswith("/"):
        return "root", None
    return "relative", None


def _is_drive(text: str) -> bool:
    """``C:`` or ``C:/anything`` -- a Windows drive-qualified path."""
    return len(text) >= 2 and text[1] == ":" and text[0].isalpha()


def escapes_upward(normalised: str) -> bool:
    """Whether a relative path ever climbs above its starting folder.

    Counts depth across the segments instead of asking the filesystem. This
    also fixes a wording bug: the report used to announce "PATH ESCAPES the
    file's folder via '..'" for paths containing no ``..`` at all, because the
    old check was "did resolve() land outside" rather than "did it climb".
    """
    depth = 0
    for segment in normalised.split("/"):
        if segment in ("", "."):
            continue
        if segment == "..":
            depth -= 1
            if depth < 0:
                return True
            continue
        depth += 1
    return False


def _rooted(normalised: str) -> tuple[str, tuple[str, ...]] | None:
    """Split an absolute slash-normalised path into ``(root token, segments)``.

    ``None`` means "this cannot be compared to anything with confidence", and
    the callers must then make no containment claim at all. That covers the
    relative case and the drive-relative one (``C:work/x.blend``), which names
    a per-drive working directory this tool has no way to know.

    Every spelling of a root collapses to one token here, so
    ``\\\\?\\UNC\\host\\share`` and ``//host/share`` compare equal, and a drive
    letter compares equal to itself however it was punctuated.
    """
    kind, host = root_kind(normalised)
    parts = _segments(normalised)
    if kind == "unc":
        if parts and parts[0] in _DEVICE_PREFIXES:
            parts = parts[1:]
            if parts and parts[0].upper() == _UNC_MARKER:
                parts = parts[1:]
        if not host or not parts:
            return None
        return "//" + host.lower(), tuple(parts[1:])
    if kind == "drive":
        if parts and parts[0] in _DEVICE_PREFIXES:
            parts = parts[1:]
        if not parts or len(parts[0]) != 2:
            return None  # drive-relative: C:work/x.blend is not a fixed place
        return parts[0].lower(), tuple(parts[1:])
    if kind == "root":
        return "/", tuple(parts)
    return None


def _collapse(segments: Sequence[str]) -> tuple[str, ...]:
    """``.`` and ``..`` removed in memory, with a root's floor respected."""
    out: list[str] = []
    for segment in segments:
        if segment in ("", "."):
            continue
        if segment == "..":
            if out:
                out.pop()
            continue
        out.append(segment)
    return tuple(out)


def contains_lexically(base: PurePath, normalised: str) -> bool:
    """Whether an absolute path lands inside ``base``, by text comparison alone.

    The report used to print "ABSOLUTE PATH -- this points outside the file's
    own folder" for every absolute path without ever asking the question.
    ``C:\\proj\\shot\\lib.blend`` sitting beside ``C:\\proj\\shot\\scene.blend``
    is absolute *and* inside its own folder, and the report said the opposite
    in both languages.

    Same rule as the rest of the module: pure text and :class:`PurePath`, no
    ``resolve``, ``stat``, ``exists`` or any other filesystem call, because the
    input is chosen by the file being inspected. Two paths on different roots
    are simply not comparable and the answer is ``False``.

    Case is folded for the roots and segments of UNC and drive paths, which are
    Windows-only spellings and case-insensitive there, and kept for anything
    standing on a POSIX root. That decision is made from the path's own
    spelling rather than from the host platform, so the answer does not change
    with the machine running the scan.

    A ``False`` here means "not established", never "proven outside" -- which
    is why the wording it selects claims containment only in the ``True``
    branch. Nothing about a path written on somebody else's machine can be
    checked against a folder on this one.
    """
    theirs = _rooted(normalised)
    ours = _rooted(str(base).replace("\\", "/"))
    if theirs is None or ours is None:
        return False

    fold = theirs[0] != "/"
    if theirs[0] != ours[0]:
        return False
    mine = _collapse(theirs[1])
    yours = _collapse(ours[1])
    if fold:
        mine = tuple(part.lower() for part in mine)
        yours = tuple(part.lower() for part in yours)
    return len(mine) > len(yours) and mine[: len(yours)] == yours


def lexical_join(base: PurePath, segments: Sequence[str]) -> str:
    """``base`` plus ``segments``, with ``.`` and ``..`` collapsed in memory.

    A pure-text stand-in for ``resolve()``. ``..`` at an absolute root is
    dropped rather than kept, which is how every OS treats ``/..``.

    The result is assembled as text rather than by handing the parts back to
    ``PurePath``, because that constructor re-parses what it is given: a
    segment spelled ``C:`` is read as a drive and quietly absorbed, so
    ``//textures/C:/evil.blend`` used to display as
    ``C:\\proj\\textures\\evil.blend`` with the odd component missing. The
    classification is unaffected either way, but a displayed path that has
    silently lost a piece of itself is the same small dishonesty as the ``..``
    message this module was written to fix.
    """
    parts = list(base.parts)
    floor = 1 if base.anchor else 0
    for segment in segments:
        if segment in ("", "."):
            continue
        if segment == "..":
            if len(parts) > floor and parts[-1] != "..":
                parts.pop()
            elif not base.anchor:
                parts.append("..")
            continue
        parts.append(segment)

    if not parts:
        return "."
    separator = "\\" if isinstance(base, PureWindowsPath) else "/"
    if base.anchor:
        # parts[0] is the anchor and already ends in a separator.
        return parts[0] + separator.join(parts[1:])
    return separator.join(parts)


def classify_library_path(raw: str, blend_dir: PurePath) -> LibraryFinding:
    """Describe one library path and every way it can point somewhere else.

    Never touches the filesystem or the network. ``blend_dir`` is used as text.
    """
    marker = raw.startswith(BLEND_RELATIVE_PREFIX)
    body = raw[len(BLEND_RELATIVE_PREFIX) :] if marker else raw
    normalised = body.replace("\\", "/")

    kind, host = root_kind(normalised)
    is_unc = kind == "unc"
    has_drive = kind == "drive"
    is_absolute = kind != "relative"
    # A path is only relative if it is *spelled* relative AND stays relative
    # once normalised. "//" followed by another root is a disguise, not a
    # blend-relative path, and calling it relative is how the smuggled form
    # used to reach the report as an ordinary link.
    is_relative = marker and not is_absolute
    disguised = marker and is_absolute

    resolved: str | None = None
    escapes = False
    inside = False
    if is_absolute:
        inside = contains_lexically(blend_dir, normalised)
    else:
        resolved = lexical_join(blend_dir, normalised.split("/"))
        escapes = escapes_upward(normalised)

    return LibraryFinding(
        raw_path=raw,
        resolved_path=resolved,
        is_relative=is_relative,
        is_absolute=is_absolute,
        escapes_folder=escapes,
        is_unc=is_unc,
        unc_host=host if is_unc else None,
        has_drive_letter=has_drive,
        disguised=disguised,
        absolute_inside_blend_dir=inside,
    )
