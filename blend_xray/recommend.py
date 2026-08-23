# SPDX-License-Identifier: GPL-3.0-or-later
"""Turn a scan result into a next action, without ever clearing the file.

Split out of :mod:`blend_xray.report` so the decision has one home and the two
surfaces that draw it -- the CLI report and the window -- cannot drift apart.
Nothing here changes a severity or a finding; it reads what the scanner
produced and says what to do about it.

Re-exported from :mod:`blend_xray.report`, which remains the module both
surfaces import.
"""

from __future__ import annotations

from . import strings, truncation
from .explain import Severity
from .models import DriverFinding, ScanResult, TextFinding


def split_alarming_texts(result: ScanResult) -> tuple[list[TextFinding], list[TextFinding]]:
    """Alarming blocks, split into the ones that escalate and the ones that do not.

    A block that is byte-for-byte a published release lands in the second list.
    Not because the code is harmless -- it is not, cloudrig.py really does call
    eval() and that finding is still printed in red above -- but because "ask
    someone who reads Python to look at this" is the wrong next action for a
    script that thousands of people have already downloaded and read. Asking
    for that review twenty times over one rig collection is how a true positive
    gets trained into background noise. The hash is what makes it defensible:
    it pins the exact body, so a CloudRig with one injected line is a different
    hash and escalates like anything else. A *structural* match never lands
    here -- its whole weakness is that the strings can be swapped while the
    shape holds -- and nor does a byte match on a per-file generated script,
    which identifies one generated copy rather than a shared release.

    scanner.py leaves ``explanation`` as None for an empty text datablock, so
    this must not dereference it blindly: an empty block used to crash the
    whole human-readable report while --json survived, which is how it stayed
    hidden.
    """
    alarming = [t for t in result.texts if t.explanation is not None and t.explanation.alarming]
    unexplained = [t for t in alarming if not t.identity_clears_escalation]
    explained = [t for t in alarming if t.identity_clears_escalation]
    return unexplained, explained


def alarming_drivers(result: ScanResult) -> list[DriverFinding]:
    """Drivers whose expression the explanation engine found alarming.

    Drivers reached neither this function nor the banner before: the closing
    recommendation consulted texts and libraries only, so a driver holding
    ``__import__('os').system('calc.exe')`` was answered with "nothing here
    matched the patterns Blend X-Ray treats as alarming". A driver outside the
    restricted evaluator runs through ``BPY_driver_exec`` under the same
    auto-execution gate as a text datablock, so it escalates like one.

    The known-script identity layer has no counterpart here on purpose: it
    pins whole published *bodies* by hash, and a 256-character expression
    field is not a body anyone publishes.
    """
    return [
        driver
        for driver in result.drivers
        if driver.expression_is_evaluated
        and driver.explanation is not None
        and driver.explanation.alarming
    ]


def unreadable_texts(result: ScanResult) -> list[TextFinding]:
    """Blocks that had NO rule applied to them, and are a real blind spot.

    The predicate itself is :attr:`blend_xray.models.TextFinding.is_blind_spot`,
    shared with the banner so the header and the closing recommendation cannot
    disagree about what counts as unexamined.
    """
    return [t for t in result.texts if t.is_blind_spot]


def recommendation_lines(result: ScanResult) -> list[tuple[str, Severity]]:
    """Turn the findings into a next action, without ever clearing the file.

    Returns already-formatted text with the severity to colour it by, so the
    CLI report and the window draw the same decision from one implementation
    instead of two that can drift apart.

    Severity is never softened to keep this block calm -- an alarming pattern
    stays alarming, and the wording here is what changes. A legitimate rig that
    genuinely calls eval() should read as "needs a human", not as "malware".
    """
    unexplained, explained = split_alarming_texts(result)
    # Only paths that reach outside the user's own machine escalate. Absolute
    # paths and "//../.." fired on every linked library across a ~100-file
    # corpus, so they carry no signal at all -- "//../../lib/x.blend" is the
    # standard production layout. They stay in the inventory; they just no
    # longer spend an alarm. UNC and drive letters do discriminate, and a UNC
    # path can make Blender reach for a network share on its own.
    escalating_lib = any(lib.is_unc or lib.has_drive_letter for lib in result.libraries)
    unreadable = unreadable_texts(result)
    drivers = alarming_drivers(result)

    out: list[tuple[str, Severity]] = []
    # Leads, and suppresses "looks ordinary" below. "Nothing here matched the
    # patterns Blend X-Ray treats as alarming" is a sentence about a file that
    # was read to the end; after a timeout it would be describing the part
    # nobody looked at, which is exactly the false clearance this tool exists
    # to avoid handing anyone.
    if result.timed_out:
        out.append((truncation.recommendation(result), Severity.ALARMING))
    if unexplained or escalating_lib or drivers:
        out.append((strings.t("recommend_needs_human"), Severity.ALARMING))
    elif explained:
        out.append((strings.t("recommend_known_release"), Severity.NOTABLE))
    elif not unreadable and not result.timed_out:
        out.append((strings.t("recommend_looks_ordinary"), Severity.BENIGN))
    if unreadable:
        out.append((strings.t("recommend_unreadable", count=len(unreadable)), Severity.ALARMING))
    if result.autorun_texts:
        out.append((strings.t("recommend_autorun_present"), Severity.NOTABLE))
    return out
