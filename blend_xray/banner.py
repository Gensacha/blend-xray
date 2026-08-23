# SPDX-License-Identifier: GPL-3.0-or-later
"""The one-glance banner: three tiers, decided by what was found.

Why this exists
---------------
The report below it is correct and complete, and that is exactly its problem:
it is a wall of text, and an artist cannot tell in one second what they are
looking at. That is the same failure as Blender's own warning dialog, which
says "this file contains scripts" and nothing an artist can act on. This
module turns the findings into one line at the top that can be read at a
glance, and it does it without ever rating the file.

The three tiers
---------------
``RED``     something in the file reaches *outside Blender* -- the network, a
            process, the registry, credential stores, the operating system's
            own low-level interfaces, or code that hides itself.
``AMBER``   everything else that was found: dynamic code, an auto-run script
            that is not recognised, a script that could not be parsed, and
            behaviour worth a second reader.
``NEUTRAL`` neither of the above fired.

There is no green tier, no tick, no "OK" symbol, and there must never be one.
------------------------------------------------------------------------------
This tool's own public argument is that antivirus does not inspect ``.blend``
internals -- that is the whole reason it exists. A green tick on a file that
later turns out to be malicious is therefore the single screenshot that would
destroy the project's credibility, because we would have made exactly the
promise we tell people not to trust from anyone else. The neutral tier is grey
and dim, it is worded as "nothing found in the N categories checked", and it
carries "this is not a clearance" plus the list of what was actually looked
at. That reads just as fast as a tick and promises nothing. The rule is
machine-checked: ``tests/test_banner.py`` asserts no tier maps to a green
colour role and that no banner string ever uses a tick or "OK" marker.

Why RED is allowed to be loud
-----------------------------
Measured, not assumed: across **578 parsable real legitimate** ``.blend`` files,
the rules listed in :data:`REACHES_OUTSIDE_KEYS` fire on exactly **one**, a game
engine example that imports ``ctypes``. A tier that fires once in five hundred
legitimate files can afford to shout. AMBER cannot, which is why the known-good
identity layer is allowed to suppress it (below).

That figure was three before the 677-file campaign, and the two it lost were
both false: a local variable named ``socket`` read as the ``socket`` module, and
an unrelated ``zlib`` call paired with an unrelated ``exec``. Both are fixed
above their own rules and both have regression tests. The number matters here
because it is the only thing licensing RED to be loud, so it has to be a
measurement of the current code and not of an older one.

Nothing in this module changes a severity or a finding. It reads what the
scanner already produced and adds a header. The inventory underneath is
untouched, and this is presentation only.
"""

from __future__ import annotations

import dataclasses
import enum
from typing import Final

from . import strings
from .explain import Explanation, Severity
from .models import CATEGORY_STRING_KEYS, ScanResult, TextFinding

#: How many published-release names the recognition line prints before it
#: stops. A banner is one glance; a list of thirty rig scripts is not.
MAX_RECOGNISED_NAMES: Final = 3


class Tier(enum.StrEnum):
    """The banner tier. The value is the stable key used in ``--json``."""

    RED = "red"
    AMBER = "amber"
    NEUTRAL = "neutral"


#: Rule keys that mean "this code reaches beyond Blender". An explicit
#: allow-list, never "everything ALARMING": ``x_dynamic_code`` (eval/exec) is
#: ALARMING and deliberately absent, because an ``eval`` in a rig UI is a
#: second-reader problem, not a machine-reaches-the-internet problem.
#:
#: Three edits, each with its reason:
#:
#: * ``x_network_listen`` **added**. A file that opens a port on the artist's
#:   machine reaches outside Blender at least as far as one that dials out.
#:   The construct used to be inside ``x_network``, wearing the sentence
#:   "connects to the internet", which had the direction backwards.
#: * ``x_obfuscation`` **kept**, but narrowed twice. It first stopped firing on
#:   a lone ``zlib.decompress``, which conceals nothing and is not code. It
#:   then stopped firing on a decode and an ``exec`` that merely share a file:
#:   ``Sandman13sq/DmrVBM-blender-to-gms2`` compresses mesh and image data and,
#:   elsewhere, execs something that never touched it, and that co-occurrence
#:   was enough to escalate the whole file to RED. The key now requires the
#:   decoded value to reach the call that runs it, so it means exactly what the
#:   RED headline says.
#: * ``x_opaque_blob`` **removed**. Its sentence is "carries a
#:   {size}-character block of encoded text". That is data sitting in the file:
#:   it opens no socket, starts no process and touches nothing in the operating
#:   system, and it is not necessarily code at all -- an embedded icon looks
#:   the same. Under the RED headline "this file contains code that reaches
#:   outside Blender" it was a claim the finding does not support. It keeps its
#:   ALARMING severity, so it still drives "ask someone who reads Python", and
#:   it still spends an AMBER banner. The shape that makes a blob dangerous --
#:   a blob that is decoded and then executed -- is what ``x_obfuscation`` now
#:   detects, and that stays RED.
#:
#: The three evasion keys are new rather than moved, and all three are RED
#: under the "or code that hides itself" clause of the tier definition above.
#: Measured over the 100 parseable script bodies in both corpora, each fires on
#: zero of them; the RED tier's licence to be loud is that it does not fire on
#: legitimate work, and these do not.
REACHES_OUTSIDE_KEYS: Final[frozenset[str]] = frozenset(
    {
        "x_network",
        "x_network_listen",
        "x_subprocess",
        "x_living_off_land",
        "x_obfuscation",
        "x_builtins_indirection",
        "x_indirect_call",
        "x_assembled_name",
        "x_persistence",
        "x_credentials",
        "x_lowlevel",
    }
)

#: Reason keys that are not rule keys, in the order the sentence uses them.
REASON_UNC_LIBRARY: Final = "library_unc"
REASON_DRIVE_LIBRARY: Final = "library_drive_letter"
REASON_DRIVER: Final = "driver_not_simple"
REASON_OSL_BYTECODE: Final = "osl_bytecode"
REASON_AUTORUN: Final = "autorun_unrecognised"
REASON_UNREADABLE: Final = "unreadable_script"
#: The scan itself ran out of wall-clock budget and stopped part-way. Not a
#: property of the file -- a property of how much of it was looked at -- but
#: it belongs in the banner precisely because the banner is what a reader
#: takes away, and "nothing found" over an unfinished scan is a lie.
REASON_TIMEOUT: Final = "scan_timed_out"

#: Reading order for the plain sentence: the thing a reader most needs to hear
#: comes first, and the order is fixed so two runs of the same file read the
#: same way.
REASON_ORDER: Final[tuple[str, ...]] = (
    REASON_TIMEOUT,
    "x_network",
    "x_network_listen",
    "x_subprocess",
    "x_living_off_land",
    "x_persistence",
    "x_credentials",
    "x_lowlevel",
    "x_obfuscation",
    "x_builtins_indirection",
    "x_indirect_call",
    "x_assembled_name",
    "x_opaque_blob",
    REASON_UNC_LIBRARY,
    "x_dynamic_code",
    REASON_AUTORUN,
    REASON_UNREADABLE,
    "x_deserialise",
    "x_compile_code",
    "x_runtime_import",
    "x_decodes_data",
    "x_split_literal",
    "x_file_delete",
    "x_file_write",
    "x_makedirs",
    "x_opens_browser",
    "x_handler_persist",
    "x_handler_register",
    REASON_DRIVER,
    REASON_OSL_BYTECODE,
    REASON_DRIVE_LIBRARY,
)

#: Tier -> the severity that colours it. NEUTRAL maps to BENIGN, which every
#: surface draws dim/grey. No entry maps to anything green, anywhere.
TIER_SEVERITY: Final[dict[Tier, Severity]] = {
    Tier.RED: Severity.ALARMING,
    Tier.AMBER: Severity.NOTABLE,
    Tier.NEUTRAL: Severity.BENIGN,
}


@dataclasses.dataclass(frozen=True)
class Banner:
    """What the banner says, before any surface decides how to draw it.

    Holds keys, not prose: the language can be switched between a scan and a
    render, so every string is looked up at render time.
    """

    tier: Tier
    #: Stable, language-independent reason keys, in reading order.
    reasons: tuple[str, ...]
    #: ``"script name (origin)"`` for each published release recognised
    #: byte-for-byte among the blocks that put this file in RED.
    recognised: tuple[str, ...] = ()
    #: Category string keys, for the neutral tier's "what was looked at".
    categories: tuple[str, ...] = ()
    #: Whether the file contains anything at all in the checked categories.
    has_findings: bool = False
    #: Whether the scan stopped before it had read the whole file.
    timed_out: bool = False

    @property
    def severity(self) -> Severity:
        return TIER_SEVERITY[self.tier]

    def headline(self) -> str:
        if self.tier is Tier.RED:
            return strings.t("banner_red_headline")
        # An unfinished scan outranks "needs a second pair of eyes" and it
        # certainly outranks "nothing found": both of those are claims about
        # a whole file, and this one was not read to the end. RED keeps its
        # own headline above, because something was already found reaching
        # outside Blender and that is the more urgent fact.
        if self.timed_out:
            return strings.t("banner_timeout_headline")
        if self.tier is Tier.AMBER:
            return strings.t("banner_amber_headline")
        key = "banner_neutral_headline_accounted" if self.has_findings else "banner_neutral_headline"
        return strings.t(key, count=len(self.categories))

    def detail(self) -> str | None:
        """The one plain sentence naming what was found, or None on NEUTRAL."""
        phrases = [strings.t("banner_what_" + reason) for reason in self.reasons]
        if not phrases:
            return None
        return strings.t("banner_sentence", actions=_join(phrases))

    def notes(self) -> tuple[str, ...]:
        """Lines printed under the headline, after :meth:`detail`."""
        if self.tier is Tier.NEUTRAL:
            labels = [strings.t(key) for key in self.categories]
            return (
                strings.t("banner_neutral_not_clearance"),
                strings.t("banner_neutral_checked", categories=", ".join(labels)),
            )
        if self.recognised:
            return (strings.t("banner_recognised", names="; ".join(self.recognised)),)
        return ()

    def to_dict(self) -> dict[str, object]:
        """The ``--json`` payload. Every value here is language-independent."""
        return {
            "tier": str(self.tier),
            "reasons": list(self.reasons),
            "recognised": list(self.recognised),
            "timed_out": self.timed_out,
        }


def _join(phrases: list[str]) -> str:
    """``a``, ``a and b``, ``a, b and c`` -- with a translatable conjunction."""
    if len(phrases) == 1:
        return phrases[0]
    conjunction = strings.t("banner_join_and")
    return f"{', '.join(phrases[:-1])} {conjunction} {phrases[-1]}"


def _explanation_reasons(exp: Explanation | None) -> tuple[set[str], set[str]]:
    """The (red, amber) reason keys one explanation contributes.

    Shared by text datablocks and driver expressions so that the same finding
    cannot mean two different things depending on where it was found.
    """
    red: set[str] = set()
    amber: set[str] = set()
    if exp is None:
        return red, amber
    for statement in exp.statements:
        if statement.key in REACHES_OUTSIDE_KEYS:
            red.add(statement.key)
        elif statement.severity >= Severity.NOTABLE:
            amber.add(statement.key)
    return red, amber


def _text_reasons(finding: TextFinding) -> tuple[set[str], set[str]]:
    """The (red, amber) reason keys one code block contributes.

    A byte-identical match to a published release removes this block's AMBER
    reasons and *never* its RED ones. That asymmetry is a security decision,
    not a style choice:

    * Suppressing AMBER is defensible. "Thousands of people have downloaded
      and read this exact script" is a real answer to an ``eval()`` in a rig
      UI, and asking one artist to review CloudRig twenty times over one rig
      collection is how a true positive gets trained into background noise.
    * Suppressing RED is not. Popularity is not an argument for hiding from a
      user that a file talks to the internet, launches a program, or conceals
      its own code -- a compromised release, a typosquatted copy or a stale
      database entry all look exactly like a match, and the cost of being
      wrong is the machine. When a recognised script does trigger RED, the
      banner stays RED and *names* the recognition beside it, so the reader
      gets both facts instead of one.

    The match must also be byte-identical for either effect: a structural
    match's whole weakness is that the string literals can be swapped while
    the shape holds, which is precisely where a payload URL would go.
    """
    red, amber = _explanation_reasons(finding.explanation)
    if finding.is_blind_spot:
        amber.add(REASON_UNREADABLE)
    if finding.is_autorun:
        amber.add(REASON_AUTORUN)

    if finding.identity_clears_escalation:
        amber.clear()
    return red, amber


def _library_reasons(result: ScanResult) -> tuple[set[str], set[str]]:
    """UNC escalates; a drive letter asks for a second reader.

    Absolute paths and ``//../..`` are deliberately absent from both sets:
    they fired on essentially every linked library across a ~100-file corpus,
    because ``//../../lib/x.blend`` is the standard production layout. They
    stay in the inventory below; they just do not spend a banner.
    """
    red = {REASON_UNC_LIBRARY} if any(lib.is_unc for lib in result.libraries) else set()
    amber = (
        {REASON_DRIVE_LIBRARY} if any(lib.has_drive_letter for lib in result.libraries) else set()
    )
    return red, amber


def _driver_reasons(result: ScanResult) -> tuple[set[str], set[str]]:
    """Drivers escalate like any other code, because Blender runs them like any other code.

    A driver expression outside the restricted evaluator is handed to
    ``BPY_driver_exec`` under the same auto-execution gate as a text
    datablock, so a payload there is a payload. Until this existed, drivers
    could not reach the banner at all: a driver holding
    ``__import__('os').system('calc.exe')`` produced an AMBER "has a driver
    expression that needs full Python" and a closing line saying nothing
    matched the alarming patterns.

    Drivers whose type means Blender never reads the expression contribute
    nothing here. The field is inert for them, and an inert string cannot
    ask for a second reader.
    """
    red: set[str] = set()
    amber: set[str] = set()
    for driver in result.drivers:
        if not driver.expression_is_evaluated:
            continue
        if driver.is_simple is False:
            amber.add(REASON_DRIVER)
        driver_red, driver_amber = _explanation_reasons(driver.explanation)
        red |= driver_red
        amber |= driver_amber
    return red, amber


def _other_reasons(result: ScanResult) -> set[str]:
    """Non-Python findings that ask for a second reader but never escalate."""
    amber: set[str] = set()
    if any(node.bytecode_bytes for node in result.osl_nodes):
        amber.add(REASON_OSL_BYTECODE)
    return amber


def _recognised_names(red_blocks: list[TextFinding]) -> tuple[str, ...]:
    """Published releases recognised among the blocks that caused RED."""
    names: list[str] = []
    for finding in red_blocks:
        match = finding.identity
        if match is None or not match.suppresses_escalation:
            continue
        # Dash, not nested brackets: the recognition line already sits inside
        # parentheses, and "(x.py (Studio, release 2.1))" is unreadable.
        label = f"{match.entry.script_name} -- {match.entry.origin}"
        if label not in names:
            names.append(label)
    return tuple(names[:MAX_RECOGNISED_NAMES])


def for_result(result: ScanResult) -> Banner:
    """Decide the banner for one scanned file. Reads only; changes nothing."""
    red: set[str] = set()
    amber: set[str] = set()
    red_blocks: list[TextFinding] = []

    for finding in result.texts:
        block_red, block_amber = _text_reasons(finding)
        if block_red:
            red_blocks.append(finding)
        red |= block_red
        amber |= block_amber

    lib_red, lib_amber = _library_reasons(result)
    red |= lib_red
    amber |= lib_amber
    driver_red, driver_amber = _driver_reasons(result)
    red |= driver_red
    amber |= driver_amber
    amber |= _other_reasons(result)
    # Added last and never suppressed by the identity layer: a known-good
    # script explains a finding, it does not explain a scan that stopped.
    if result.timed_out:
        amber.add(REASON_TIMEOUT)

    categories = tuple(CATEGORY_STRING_KEYS[cat] for cat in result.categories_checked)
    # A RED banner names only what put it in RED. The amber reasons are still
    # in the inventory below; padding the one-glance sentence with "writes
    # files" after "contacts the internet" is how the first half stops being
    # read.
    if red:
        tier, reasons = Tier.RED, red
    elif amber:
        tier, reasons = Tier.AMBER, amber
    else:
        tier, reasons = Tier.NEUTRAL, set()

    # Survives the RED narrowing above, unlike every other amber reason. Those
    # are competing findings and padding the sentence with them is how the
    # first half stops being read; this one is not a finding at all, it is the
    # statement that the sentence describes only part of the file. Dropping it
    # would let a RED banner claim completeness it does not have. It sorts
    # first in REASON_ORDER, so it leads the sentence rather than trailing it.
    if result.timed_out:
        reasons = reasons | {REASON_TIMEOUT}

    return Banner(
        tier=tier,
        reasons=tuple(key for key in REASON_ORDER if key in reasons),
        recognised=_recognised_names(red_blocks) if tier is Tier.RED else (),
        categories=categories,
        has_findings=result.has_findings,
        timed_out=result.timed_out,
    )
