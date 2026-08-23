# SPDX-License-Identifier: GPL-3.0-or-later
"""Graphical front end for Blend X-Ray.

The window renders exactly the same inventory as the CLI, from the same
scanner and the same string catalogue. It adds no detection of its own, and it
softens nothing: no score, no badge, no green, and never the word "safe".

``main`` is imported lazily so that ``import blend_xray.gui`` does not pull in
tkinter on a machine that has no Tk installed -- the string catalogue and the
palette rules stay importable and testable there.
"""

from __future__ import annotations

from typing import Any

__all__ = ["main"]


def main(argv: list[str] | None = None) -> int:
    """Open the Blend X-Ray window. See :mod:`blend_xray.gui.app`."""
    from .app import main as _main

    return _main(argv)


def __getattr__(name: str) -> Any:
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
