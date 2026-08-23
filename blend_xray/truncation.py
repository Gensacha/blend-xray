# SPDX-License-Identifier: GPL-3.0-or-later
"""What to say about a scan that stopped before it had read the whole file.

Split out of :mod:`blend_xray.report` because both surfaces need it and neither
owns it: the CLI report prints the notice under its banner, the window prints
it under its own, and the closing recommendation in both is built from the same
two facts. Two copies of that wording would eventually disagree about how much
of a file was actually inspected, which is the one thing they must not do.

Kept out of :mod:`blend_xray.models` on purpose. The model records *that* the
scan stopped and where; turning that into a sentence is presentation, and the
models layer stays free of it.
"""

from __future__ import annotations

from typing import Final

from . import strings
from .models import ScanResult

#: Stage identifier -> the catalogue key naming it in plain language. Keyed by
#: the stable :class:`~blend_xray.models.Category` values plus ``preflight``, so
#: a stage added later shows up as an unresolved key in testing rather than as
#: a blank in somebody's report.
STAGE_STRING_KEYS: Final[dict[str, str]] = {
    "text": "stage_text",
    "driver": "stage_driver",
    "osl": "stage_osl",
    "library": "stage_library",
    "filepath": "stage_filepath",
    "preflight": "stage_preflight",
}


def stage_label(stage: str) -> str:
    """Plain-language name for the stage a scan stopped in."""
    return strings.t(STAGE_STRING_KEYS.get(stage, "stage_preflight"))


def format_budget(seconds: float) -> str:
    """The budget as the user typed it: "1" rather than "1.0", "0.5" as is."""
    return f"{seconds:g}"


def notice(result: ScanResult) -> str:
    """The one loud line saying this inventory covers only part of the file.

    Printed above anything a reader could mistake for a conclusion, on every
    surface. A partial scan that announced itself in the terminal but not in
    the window would be worse than one that never announced itself at all,
    because it would look reliable.
    """
    return strings.t(
        "scan_timed_out_notice",
        limit=format_budget(result.time_budget),
        stage=stage_label(result.timed_out_at),
    )


def recommendation(result: ScanResult) -> str:
    """The closing advice for a scan that ran out of time.

    Separate from :func:`notice` because they answer different questions --
    "what happened" and "what do I do now" -- and the report prints them in
    different places.
    """
    return strings.t(
        "recommend_timed_out",
        limit=format_budget(result.time_budget),
        stage=stage_label(result.timed_out_at),
    )
