# SPDX-License-Identifier: GPL-3.0-or-later
"""Library-path classification: every disguise, and no filesystem access at all.

The bug these cover: ``classify_library_path`` used to strip Blender's ``//``
marker and hand the rest to ``Path.resolve()``. A *doubled* separator survived
the strip, ``Path.__truediv__`` reset the join to a UNC root, and ``resolve()``
on Windows opened an SMB connection to a host the scanned file had chosen --
which authenticates automatically with the user's NTLM credentials. Scanning a
hostile file therefore leaked a credential hash before the reader had seen a
single line of the report.

Two things are asserted here and both matter. First that every spelling of the
disguise is *classified* as UNC. Second, and independently, that classification
performs no filesystem operation whatsoever -- because a classifier that gets
the answer right but still calls ``resolve()`` has the same bug waiting for the
next spelling nobody thought of.
"""

from __future__ import annotations

import io
import json
import os
from pathlib import Path, PurePath, PurePosixPath, PureWindowsPath

import pytest

from blend_xray import banner, libpath, report, scanner, strings
from blend_xray.banner import Tier
from blend_xray.scanner import classify_library_path

from .blend_builder import BlendBuilder

BASE = PureWindowsPath(r"C:\proj\shot")

#: Every spelling that must land on a UNC root, with the host it names.
#: ``//`` is Blender's "next to this .blend"; anything after it that has a root
#: of its own is a disguise, however it is punctuated.
UNC_SPELLINGS: list[tuple[str, str]] = [
    (r"\\fileserver\share\rig.blend", "fileserver"),
    ("////host/share/x.blend", "host"),
    ("//\\\\host\\share\\x.blend", "host"),
    ("//\\/host/share/x.blend", "host"),
    ("//////host/share/x.blend", "host"),
    (r"//\\host/share/x.blend", "host"),
    (r"\\?\UNC\host\share\x.blend", "host"),
    (r"\\.\UNC\host\share\x.blend", "host"),
    (r"//\\?\UNC\host\share\x.blend", "host"),
    ("//" + r"\\.\unc\host\share", "host"),
    (r"\/host/share/x.blend", "host"),
    (r"/\host\share\x.blend", "host"),
]


@pytest.mark.parametrize(("raw", "host"), UNC_SPELLINGS)
def test_every_unc_spelling_is_detected_after_normalisation(raw: str, host: str) -> None:
    finding = classify_library_path(raw, BASE)
    assert finding.is_unc is True, raw
    assert finding.unc_host == host, raw
    assert finding.is_absolute is True
    assert finding.is_relative is False
    assert finding.notable is True


def test_the_smuggled_form_is_reported_as_a_disguise() -> None:
    """The banner-driving flags AND the wording have to change, not just one."""
    finding = classify_library_path("////host/share/evil.blend", BASE)
    assert finding.disguised is True
    assert finding.is_unc is True
    # It contains no "..", so the report must not claim it escapes via "..".
    assert finding.escapes_folder is False


def test_a_plain_blend_relative_path_is_not_a_disguise() -> None:
    finding = classify_library_path("//textures/wood.blend", BASE)
    assert finding.disguised is False
    assert finding.is_relative is True
    assert finding.is_unc is False
    assert finding.notable is False


def test_escaping_is_reported_only_when_the_path_actually_climbs() -> None:
    assert classify_library_path("//../../lib/x.blend", BASE).escapes_folder is True
    assert classify_library_path("//a/../b/x.blend", BASE).escapes_folder is False
    assert classify_library_path("//./x.blend", BASE).escapes_folder is False


def test_a_drive_letter_smuggled_behind_the_marker_is_still_a_drive_letter() -> None:
    finding = classify_library_path(r"//C:\Users\victim\x.blend", BASE)
    assert finding.has_drive_letter is True
    assert finding.is_unc is False
    assert finding.disguised is True


def test_the_windows_device_prefix_on_a_drive_is_not_a_share() -> None:
    """``\\\\?\\C:\\x`` has two leading slashes but names a drive, not a host."""
    finding = classify_library_path(r"\\?\C:\Users\victim\x.blend", BASE)
    assert finding.has_drive_letter is True
    assert finding.is_unc is False
    assert finding.unc_host is None


def test_root_relative_smuggling_is_absolute_not_relative() -> None:
    finding = classify_library_path("///etc/passwd", BASE)
    assert finding.is_absolute is True
    assert finding.is_relative is False
    assert finding.is_unc is False


# -- containment of absolute paths --------------------------------------------
# The defect: "ABSOLUTE PATH -- this points outside the file's own folder" was
# asserted for every absolute path and never checked. A library sitting beside
# the .blend that links it is absolute *and* inside, and the report said the
# opposite -- identically in French, so the same wrong claim twice.
POSIX_BASE = PurePosixPath("/proj/shot")

#: (raw path, base, is it demonstrably inside that base?)
CONTAINMENT: list[tuple[str, PurePath, bool]] = [
    (r"C:\proj\shot\lib.blend", BASE, True),
    (r"C:\proj\shot\sub\lib.blend", BASE, True),
    (r"c:/PROJ/Shot/lib.blend", BASE, True),  # drive paths are case-insensitive
    (r"C:\proj\shot\a\..\b.blend", BASE, True),
    (r"C:\proj\other\lib.blend", BASE, False),
    (r"C:\proj\shot", BASE, False),  # the folder itself is not inside itself
    (r"C:\proj\shot\..\other\x.blend", BASE, False),
    (r"D:\proj\shot\lib.blend", BASE, False),
    (r"\\host\share\proj\x.blend", BASE, False),
    ("C:work/x.blend", BASE, False),  # drive-relative: no fixed place to compare
    ("/proj/shot/lib.blend", BASE, False),  # different root entirely
    ("/proj/shot/lib.blend", POSIX_BASE, True),
    ("/proj/Shot/lib.blend", POSIX_BASE, False),  # POSIX roots stay case-sensitive
    ("/proj/shot/../other/x.blend", POSIX_BASE, False),
    ("//textures/wood.blend", BASE, False),  # relative: the question does not arise
]


@pytest.mark.parametrize(("raw", "base", "inside"), CONTAINMENT)
def test_containment_is_computed_not_assumed(raw: str, base: PurePath, inside: bool) -> None:
    assert classify_library_path(raw, base).absolute_inside_blend_dir is inside, raw


@pytest.mark.parametrize(("raw", "base", "_inside"), CONTAINMENT)
def test_containment_never_touches_the_filesystem(
    raw: str, base: PurePath, _inside: bool, no_filesystem: None
) -> None:
    """The restriction that made this module exist must not regress."""
    classify_library_path(raw, base)


def test_an_absolute_path_beside_the_blend_is_not_called_outside(tmp_path: Path) -> None:
    """End to end, in both languages: the false claim is gone."""
    builder = BlendBuilder()
    builder.add_library(str(tmp_path / "lib.blend"))
    path = tmp_path / "scene.blend"
    path.write_bytes(builder.to_bytes())

    result = scanner.scan_file(path)
    assert result.libraries[0].is_absolute is True
    assert result.libraries[0].absolute_inside_blend_dir is True

    for lang in ("en", "fr"):
        strings.set_language(lang)
        rendered = report.format_text_report(
            result, report.make_palette(io.StringIO(), force=False)
        )
        assert strings.t("library_absolute_inside") in rendered
        assert strings.t("library_absolute") not in rendered
    strings.set_language(strings.DEFAULT_LANGUAGE)


def test_an_absolute_path_from_another_machine_claims_no_position(tmp_path: Path) -> None:
    """Nothing about it can be checked here, so nothing about it is claimed."""
    builder = BlendBuilder()
    builder.add_library("/home/someone-else/studio/rig.blend")
    path = tmp_path / "scene.blend"
    path.write_bytes(builder.to_bytes())

    result = scanner.scan_file(path)
    assert result.libraries[0].absolute_inside_blend_dir is False

    for lang in ("en", "fr"):
        strings.set_language(lang)
        rendered = report.format_text_report(
            result, report.make_palette(io.StringIO(), force=False)
        )
        assert strings.t("library_absolute") in rendered
        assert strings.t("library_absolute_inside") not in rendered
    strings.set_language(strings.DEFAULT_LANGUAGE)


@pytest.mark.parametrize("lang", ["en", "fr"])
def test_neither_wording_claims_a_position_it_did_not_check(lang: str) -> None:
    strings.set_language(lang)
    outside_claims = ("outside", "hors du dossier", "en dehors")
    for claim in outside_claims:
        assert claim not in strings.t("library_absolute").lower()
        assert claim not in strings.t("library_absolute_inside").lower()
    strings.set_language(strings.DEFAULT_LANGUAGE)


def test_containment_is_reported_in_the_machine_readable_output(tmp_path: Path) -> None:
    builder = BlendBuilder()
    builder.add_library(str(tmp_path / "lib.blend"))
    path = tmp_path / "scene.blend"
    path.write_bytes(builder.to_bytes())
    payload = json.loads(report.format_json([scanner.scan_file(path)], []))
    assert payload["files"][0]["libraries"][0]["absolute_inside_blend_dir"] is True


def test_resolution_is_lexical_and_collapses_dot_dot() -> None:
    resolved = libpath.lexical_join(PurePath("/proj/shot"), ["..", "lib", "x.blend"])
    assert resolved.replace("\\", "/").endswith("proj/lib/x.blend")
    # ".." at an absolute root is a no-op, exactly as the OS treats "/..".
    assert libpath.lexical_join(PurePath("/"), ["..", "x"]).replace("\\", "/").endswith("x")


# -- the real guarantee: no filesystem, no network -------------------------
FS_ATTRS = ("resolve", "stat", "exists", "is_dir", "is_file", "lstat", "iterdir")


@pytest.fixture
def no_filesystem(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make every filesystem entry point on Path explode."""

    def forbidden(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("classification touched the filesystem")

    for attr in FS_ATTRS:
        monkeypatch.setattr(Path, attr, forbidden, raising=False)
        monkeypatch.setattr(PurePath, attr, forbidden, raising=False)
    monkeypatch.setattr(os.path, "realpath", forbidden)
    monkeypatch.setattr(os, "stat", forbidden)


@pytest.mark.parametrize(("raw", "_host"), UNC_SPELLINGS)
def test_classification_never_touches_the_filesystem(
    raw: str, _host: str, no_filesystem: None
) -> None:
    assert classify_library_path(raw, BASE).is_unc is True


def test_scanning_a_smuggled_unc_file_never_touches_the_filesystem_to_classify(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """End to end: the whole scan of the proof-of-concept completes with
    ``Path.resolve`` poisoned.

    ``resolve`` is the one that reached the network, so it is the one pinned
    here. The rest of the scan legitimately reads the file it was pointed at,
    which is why only ``resolve`` and ``realpath`` are forbidden rather than
    all of :data:`FS_ATTRS`.
    """
    builder = BlendBuilder()
    builder.add_library("////blend-xray-test-nonexistent-host/share/evil.blend")
    path = tmp_path / "smuggled.blend"
    path.write_bytes(builder.to_bytes())

    def forbidden(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("the scan called resolve() on file-controlled data")

    monkeypatch.setattr(Path, "resolve", forbidden)
    monkeypatch.setattr(os.path, "realpath", forbidden)

    result = scanner.scan_file(path)
    assert len(result.libraries) == 1
    assert result.libraries[0].is_unc is True
    assert result.libraries[0].unc_host == "blend-xray-test-nonexistent-host"


@pytest.mark.parametrize(("raw", "_host"), UNC_SPELLINGS)
def test_every_unc_spelling_drives_the_red_banner(tmp_path: Path, raw: str, _host: str) -> None:
    """Classification is only half of it: the reader has to be told.

    The smuggled form used to reach the report as ``is_unc=False`` and the file
    came out neutral, which is the failure that matters -- the disguise worked
    on the banner, not just on the classifier.
    """
    builder = BlendBuilder()
    builder.add_library(raw)
    path = tmp_path / "unc.blend"
    path.write_bytes(builder.to_bytes())

    result = scanner.scan_file(path)
    info = banner.for_result(result)
    assert info.tier is Tier.RED, raw
    assert banner.REASON_UNC_LIBRARY in info.reasons


def test_the_report_no_longer_claims_a_dot_dot_escape_that_is_not_there(
    tmp_path: Path,
) -> None:
    """The old wording said "PATH ESCAPES ... via '..'" for a path with no ".."."""
    builder = BlendBuilder()
    builder.add_library("////host/share/evil.blend")
    path = tmp_path / "unc.blend"
    path.write_bytes(builder.to_bytes())

    result = scanner.scan_file(path)
    rendered = report.format_text_report(result, report.make_palette(io.StringIO(), force=False))
    assert strings.t("library_escapes", resolved="?") not in rendered
    assert "PATH ESCAPES" not in rendered
    assert strings.t("library_disguised") in rendered
    assert strings.t("library_unc", host="host") in rendered
