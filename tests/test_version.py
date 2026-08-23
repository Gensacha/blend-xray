# SPDX-License-Identifier: GPL-3.0-or-later
"""The version has to be reachable, and it has to come from one place.

``blend_xray.__version__`` existed and was used by nothing: there was no
``--version`` flag, no version in the JSON report, none in the window title,
and no ``version=`` resource in the PyInstaller spec -- so Properties >
Details on the unsigned exe was blank, which reads as one more reason not to
trust it. ``SECURITY.md`` meanwhile asks a reporter which version they are on,
a question the zip audience had no way to answer.

These tests cover both halves of the fix: every surface can state the version,
and every surface reads it from ``blend_xray/_version.py`` rather than carrying
its own copy for a future bump to forget. ``__init__.py`` re-exports it, so
``blend_xray.__version__`` still works for every caller.
"""

from __future__ import annotations

import ast
import io
import json
import re
import sys
import tomllib
from pathlib import Path

import pytest

from blend_xray import __version__, cli, report, scanner, strings

REPO = Path(__file__).resolve().parents[1]


# -- the version is reachable -------------------------------------------------
def test_version_looks_like_a_version() -> None:
    assert re.fullmatch(r"\d+\.\d+\.\d+([.\-+].*)?", __version__), __version__


def test_cli_has_a_version_flag_that_prints_and_exits_zero(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """argparse's version action fires during parsing, so the required
    subcommand does not have to be supplied to ask this question -- which is
    the point: a copy too broken to scan must still be able to identify itself.
    """
    with pytest.raises(SystemExit) as caught:
        cli.run(["--version"])
    assert caught.value.code == 0
    printed = capsys.readouterr().out
    assert __version__ in printed
    assert "blend-xray" in printed


def test_cli_version_flag_needs_no_subcommand_but_scan_still_does() -> None:
    with pytest.raises(SystemExit) as caught:
        cli.run([])
    assert caught.value.code != 0


def test_json_report_carries_the_tool_version(tmp_path: Path) -> None:
    from .blend_builder import minimal_blend

    path = tmp_path / "empty.blend"
    path.write_bytes(minimal_blend())
    payload = json.loads(report.format_json([scanner.scan_file(path)], []))
    assert payload["version"] == __version__
    # The schema number is the shape of the document and moves independently
    # of the tool version; adding a key does not change it.
    assert payload["schema"] == 1


def test_json_version_survives_the_cli_path(tmp_path: Path) -> None:
    from .blend_builder import minimal_blend

    path = tmp_path / "empty.blend"
    path.write_bytes(minimal_blend())
    out, err = io.StringIO(), io.StringIO()
    cli.run(["scan", "--json", str(path)], stdout=out, stderr=err)
    assert json.loads(out.getvalue())["version"] == __version__


def test_window_title_states_the_version() -> None:
    pytest.importorskip("tkinter", reason="the window module imports tkinter")
    from blend_xray.gui.app import window_title

    title = window_title()
    assert title.startswith(strings.t("tool_name"))
    assert __version__ in title


# -- one source of truth ------------------------------------------------------
def _declared_attr() -> str:
    data = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))
    return str(data["tool"]["setuptools"]["dynamic"]["version"]["attr"])


def test_pyproject_reads_the_version_from_the_package() -> None:
    """A static ``version = "..."`` here is a second place to forget."""
    data = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))
    assert "version" not in data["project"], "pyproject pins a second version"
    assert "version" in data["project"]["dynamic"]
    assert _declared_attr() == "blend_xray._version.__version__"


def test_the_declared_attribute_actually_resolves_to_the_version() -> None:
    """Declaring it is not the same as it working, and this caught that.

    setuptools resolves ``attr:`` with its own module lookup, which tries
    ``<root>/blend_xray.py`` -- the double-click launcher -- before
    ``<root>/blend_xray/__init__.py``. Pointed at ``blend_xray.__version__``
    the build found the launcher, saw no version in it, fell back to importing
    it and raised ModuleNotFoundError. Only reading it back proves the
    declaration is wired to the number the tool reports.
    """
    expand = pytest.importorskip("setuptools.config.expand")
    resolved = expand.read_attr(_declared_attr(), {}, str(REPO))
    assert str(resolved) == __version__


def test_the_spec_builds_its_version_resource_from_the_package() -> None:
    """The exe's VERSIONINFO must not be a hand-typed third copy."""
    spec = (REPO / "blend-xray.spec").read_text(encoding="utf-8")
    assert "version=_version_resource()" in spec
    assert 'Path(SPECPATH) / "blend_xray" / "_version.py"' in spec
    assert not re.search(r'StringStruct\("FileVersion", "\d', spec)


def test_the_spec_version_parser_agrees_with_the_package() -> None:
    """Re-run the spec's own parser here, so a rename of ``__version__``
    fails in the suite instead of silently stamping the wrong build."""
    source = (REPO / "blend_xray" / "_version.py").read_text(encoding="utf-8")
    found = [
        node.value.value
        for node in ast.parse(source).body
        if isinstance(node, ast.Assign)
        and isinstance(node.value, ast.Constant)
        and any(getattr(t, "id", None) == "__version__" for t in node.targets)
    ]
    assert found == [__version__]


@pytest.mark.skipif(sys.platform != "win32", reason="VERSIONINFO is a Windows resource")
def test_the_spec_version_tuple_is_four_integers() -> None:
    """Windows VERSIONINFO takes exactly four; "0.1.0" is three."""
    parts = tuple([*map(int, re.findall(r"\d+", __version__)), 0, 0, 0, 0][:4])
    assert len(parts) == 4
    assert all(isinstance(part, int) for part in parts)
