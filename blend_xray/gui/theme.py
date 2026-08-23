# SPDX-License-Identifier: GPL-3.0-or-later
"""Colours, fonts and tag names for the window.

**There is deliberately no green in this palette**, for exactly the reason
there is none in the CLI one (see :mod:`blend_xray.report`): green reads as
"all clear" at a glance, and a glance is all most people give a security tool.
That false confidence is the failure mode this whole project exists to prevent.
The rule is machine-checked by ``tests/test_gui.py::test_palette_has_no_green``.

This module imports nothing from tkinter on purpose, so the palette rule can be
tested on a machine with no Tk installed.
"""

from __future__ import annotations

from typing import Final

# -- tag names used by the renderer and configured on the Text widget ---------
TAG_TITLE: Final = "title"
TAG_HEADING: Final = "heading"
TAG_BODY: Final = "body"
TAG_DIM: Final = "dim"
TAG_NOTABLE: Final = "notable"
TAG_ALARM: Final = "alarm"
TAG_STRONG: Final = "strong"
TAG_SOURCE: Final = "source"

#: Every colour the window paints, by role. Neutral greys carry the structure;
#: red and amber carry the two levels of "look at this"; blue is chrome only.
#: Nothing here is green, and nothing here should become green.
COLOURS: Final[dict[str, str]] = {
    "background": "#f5f5f6",
    "surface": "#ffffff",
    "source_background": "#ebebed",
    "border": "#c8c8ce",
    "foreground": "#1b1b1d",
    "dim": "#68686e",
    "heading": "#1b4a7a",
    "title": "#12325a",
    "notable": "#8a4b00",
    "alarm": "#b3261e",
}

#: Tag -> (colour role, bold?). The renderer only ever emits these tags.
TAG_STYLES: Final[dict[str, tuple[str, bool]]] = {
    TAG_TITLE: ("title", True),
    TAG_HEADING: ("heading", True),
    TAG_BODY: ("foreground", False),
    TAG_DIM: ("dim", False),
    TAG_NOTABLE: ("notable", False),
    TAG_ALARM: ("alarm", True),
    TAG_STRONG: ("foreground", True),
    TAG_SOURCE: ("foreground", False),
}

#: Font families are given with fallbacks; Tk picks the first one it has.
UI_FAMILY: Final = "Segoe UI"
MONO_FAMILY: Final = "Consolas"
UI_SIZE: Final = 10
MONO_SIZE: Final = 9
TITLE_SIZE: Final = 13

#: Pixels of left margin per indent level of a rendered line.
#:
#: The window wraps on word boundaries, so an indent written into the text --
#: which is what the clipboard copy needs -- only ever reaches the *first*
#: visual line of a wrapped paragraph. Every continuation line falls back to
#: the left edge and the statement/evidence hierarchy flattens exactly where
#: the prose is longest. Tk expresses the fix as ``lmargin1`` (first line) and
#: ``lmargin2`` (continuations); setting both to the same value is a block
#: indent that survives wrapping. See ``ReportView._configure_tags``.
INDENT_PIXELS: Final = 22

#: Deepest indent level the renderer emits (evidence lines, under a statement,
#: under an explanation header). Tags are configured up to here at build time
#: so that drawing never has to create one mid-scan.
MAX_INDENT_LEVEL: Final = 4


def indent_tag(level: int) -> str:
    """Tag name carrying the left margin for one indent level."""
    return f"indent{max(0, min(level, MAX_INDENT_LEVEL))}"


def indent_margins(level: int) -> dict[str, int]:
    """Tk options for one indent level: first line **and** continuations.

    ``lmargin2`` is the half that was missing. Without it an indented
    paragraph that wraps drops its continuation lines back to the left edge,
    which is exactly where the hierarchy needs to hold -- the longest lines
    are the ones that wrap. Both are returned together so the pair cannot be
    separated by a later edit.
    """
    margin = max(0, min(level, MAX_INDENT_LEVEL)) * INDENT_PIXELS
    return {"lmargin1": margin, "lmargin2": margin}


def parse_hex(colour: str) -> tuple[int, int, int]:
    """Split ``#rrggbb`` into integer channels. Raises on anything else."""
    value = colour.strip()
    if not value.startswith("#") or len(value) != 7:
        raise ValueError(f"not a #rrggbb colour: {colour!r}")
    return int(value[1:3], 16), int(value[3:5], 16), int(value[5:7], 16)


def is_green(colour: str) -> bool:
    """True when green dominates the other two channels.

    Used by the test that keeps the no-green rule from eroding one palette
    tweak at a time. A grey (equal channels) is not green; a colour is only
    green when its green channel is strictly the largest.
    """
    red, green, blue = parse_hex(colour)
    return green > red and green > blue
