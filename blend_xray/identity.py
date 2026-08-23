# SPDX-License-Identifier: GPL-3.0-or-later
"""Recognise a script body as a published one, and say where it came from.

**Entries record identity, never safety.** An entry says "this block is
byte-identical to ``cloudrig.py`` as shipped in <this published file>, fetched
from <this URL> on <this date>". It must never say, or let a reader infer,
"this script is harmless". The first claim is verifiable by anyone, forever:
re-download the file, re-extract the block, re-compute the hash. The second
would become false the day somebody finds a bug in CloudRig, and we would have
signed it.

Why this layer exists: on a 55-file corpus of first-party Blender content the
tool raised its top-level alarm on 20 files, and 19 of those were the *same*
script -- Blender Studio's ``cloudrig.py``, which genuinely calls ``eval()`` on
a property stored in the file. Every alarm was a true positive. That is exactly
the problem: twenty true positives an artist cannot act on teach the artist to
ignore the tool.

What a match changes, and what it never changes
-----------------------------------------------
A match **adds a line of context**. It never removes a finding, never hides
one, and never lowers a severity. The block still lists ``eval()`` in red.

* **Byte-identical** -- strong evidence. Every byte matches a recorded copy.
  This is the one thing that suppresses *escalation*: see
  :attr:`IdentityMatch.suppresses_escalation`.
* **Same structure, different text in the quotes** -- medium evidence, and it
  does **not** suppress anything. An attacker can keep a well-known script's
  structure and change only its string literals, which is precisely where a
  payload URL would go. So the match reports every literal that differs from
  the reference and the file keeps escalating.

Nothing here reaches the network, at scan time or ever. The database is a
plain JSON file shipped in the package; see ``known_scripts.json`` and the
README section "The known-good identity layer".
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Final

from . import strings
from .structure import STRUCTURE_SCHEME, structure_of

#: The database file, shipped inside the package next to this module.
DATABASE_PATH: Final = Path(__file__).with_name("known_scripts.json")

#: Bumped when the on-disk shape changes incompatibly. Version 2 made
#: ``generated`` a required field on every entry: it used to be *derived* from
#: the presence of a structural form, and that derivation was wrong for any
#: per-file generated script recorded without one. See
#: :attr:`KnownScript.is_generated`.
SCHEMA_VERSION: Final = 2

#: Refuse to read a database file larger than this (8 MiB). The shipped one is
#: about 55 KB. Without a ceiling, ``json.loads`` on a huge file raises
#: MemoryError from inside a module whose whole contract is that it degrades.
MAX_DATABASE_BYTES: Final = 8 * 1024 * 1024
#: Ceilings on what one file may declare, for the same reason.
MAX_ENTRIES: Final = 20000
MAX_LITERALS_PER_ENTRY: Final = 200000

#: Evidence classes. Machine-readable and translation-independent.
EVIDENCE_BYTE: Final = "byte"
EVIDENCE_STRUCTURE: Final = "structure"

_REQUIRED_FIELDS: Final = (
    "sha256",
    "script_name",
    "byte_size",
    "origin",
    "source_url",
    "fetched_on",
    "attested_by",
    "attested_on",
    "notes",
    "generated",
)


@dataclasses.dataclass(frozen=True)
class KnownScript:
    """One attested script body. Identity only -- no claim about behaviour."""

    sha256: str
    script_name: str
    byte_size: int
    origin: str
    source_url: str
    fetched_on: str
    attested_by: str
    attested_on: str
    notes: str
    #: Whether this records a script written afresh for each .blend, so that a
    #: byte match identifies one generated copy rather than a shared release.
    #:
    #: **Declared by the entry, never inferred.** It used to be derived from
    #: ``structure_sha256 is not None``, on the reasoning that a structural
    #: form is only needed when the bytes differ in every copy. That is true
    #: one way round and false the other: entry 5 of the shipped database is an
    #: older, per-file generated CloudRig UI script with ``script_id =
    #: "gabby"`` baked into it and *no* structural form -- one copy was
    #: recorded, nothing was generalised -- so the derivation called it a
    #: shared release and let it suppress escalation. The report would then
    #: have told an artist that a body exactly one person has ever downloaded
    #: "is one many people have already downloaded and read". A derived
    #: property silently encoding an assumption the data does not carry is the
    #: same shape as the driver-owner defect that survived 94 green tests, so
    #: this is data now, and :func:`_entry_from` refuses an entry whose
    #: declaration contradicts what it carries.
    is_generated: bool
    #: Present only on entries that also support structural matching.
    structure_sha256: str | None = None
    #: The reference body's string literals, in canonical visit order. Compared
    #: position by position against a candidate's, which is what lets a
    #: structural match name the values that differ.
    structure_literals: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "sha256": self.sha256,
            "script_name": self.script_name,
            "byte_size": self.byte_size,
            "origin": self.origin,
            "source_url": self.source_url,
            "fetched_on": self.fetched_on,
            "attested_by": self.attested_by,
            "attested_on": self.attested_on,
            "notes": self.notes,
            "generated": self.is_generated,
        }


@dataclasses.dataclass(frozen=True)
class LiteralDifference:
    """One string literal whose value differs from the recorded reference."""

    index: int
    reference: str
    actual: str

    def to_dict(self) -> dict[str, Any]:
        return {"index": self.index, "reference": self.reference, "actual": self.actual}


@dataclasses.dataclass(frozen=True)
class IdentityMatch:
    """What the database recognised, and how strong the evidence is."""

    entry: KnownScript
    evidence: str
    differences: tuple[LiteralDifference, ...] = ()

    @property
    def suppresses_escalation(self) -> bool:
        """Whether this match may keep the block out of the "needs a human" branch.

        Two conditions, and the second one matters as much as the first.

        The match must be **byte-identical**. A structural match never
        qualifies: its whole failure mode is an attacker keeping the structure
        and editing the strings, so answering it with a suppressed alarm would
        hand an attacker the suppression.

        The entry must also describe a **shared release** rather than a
        per-file generated script -- see :attr:`KnownScript.is_generated`. The
        justification for suppressing at all is about readership: a release
        that thousands of people have downloaded and read is not something one
        artist alone can usefully be asked to review at midnight. A generated
        script does not inherit that. Matching one Rigify ``rig_ui.py`` byte
        for byte identifies *that one rig's* generated copy, which precisely
        one person has ever downloaded, so the argument that justifies
        suppression is simply not available and the block keeps escalating.

        Either way the findings stay on screen at full severity, and the
        identity is reported in full: this decides one line of closing advice,
        not what the report contains.
        """
        return self.evidence == EVIDENCE_BYTE and not self.entry.is_generated

    def to_dict(self) -> dict[str, Any]:
        return {
            "evidence": self.evidence,
            "suppresses_escalation": self.suppresses_escalation,
            "entry": self.entry.to_dict(),
            "differing_literals": [d.to_dict() for d in self.differences],
        }


@dataclasses.dataclass(frozen=True)
class Database:
    """Loaded entries, plus every reason an entry or the file was rejected."""

    entries: tuple[KnownScript, ...] = ()
    by_sha256: dict[str, KnownScript] = dataclasses.field(default_factory=dict)
    by_structure: dict[str, KnownScript] = dataclasses.field(default_factory=dict)
    #: Non-fatal load problems, surfaced to the user rather than logged away.
    problems: tuple[str, ...] = ()

    @property
    def usable(self) -> bool:
        return bool(self.entries)

    def match(self, source: str) -> IdentityMatch | None:
        """Recognise ``source``, byte-first. ``None`` means "nothing to say"."""
        entry = self.by_sha256.get(sha256_of(source))
        if entry is not None:
            return IdentityMatch(entry, EVIDENCE_BYTE)
        if not self.by_structure:
            return None
        shape = structure_of(source)
        if shape is None:
            return None
        entry = self.by_structure.get(shape.sha256)
        if entry is None:
            return None
        return IdentityMatch(
            entry,
            EVIDENCE_STRUCTURE,
            _differences(entry.structure_literals, shape.literals),
        )


def sha256_of(source: str) -> str:
    """Hash a script body the way the database keys it: SHA-256 of its UTF-8."""
    return hashlib.sha256(source.encode("utf-8", errors="replace")).hexdigest()


def _differences(
    reference: Sequence[str], actual: Sequence[str]
) -> tuple[LiteralDifference, ...]:
    """Position-by-position comparison of two literal sequences.

    Equal structure hashes imply equal lengths, so positions line up.
    ``strict=False`` is deliberate: if that ever failed we would rather report
    the differences we can line up than raise inside a scan and lose the file's
    whole inventory over a database defect.
    """
    return tuple(
        LiteralDifference(index, ref, act)
        for index, (ref, act) in enumerate(zip(reference, actual, strict=False))
        if ref != act
    )


def _is_sha256(value: Any) -> bool:
    """A 64-character hexadecimal digest, and nothing else."""
    if not isinstance(value, str) or len(value.strip()) != 64:
        return False
    return all(char in "0123456789abcdef" for char in value.strip().lower())


def _printable(value: object) -> str:
    """Text with terminal control characters removed, ready to be displayed.

    Everything in an entry ends up printed to a terminal or drawn in a window.
    Control characters there can hide, overwrite or spoof the lines around them
    -- the worst possible failure in a tool whose whole job is showing an
    accurate report. The literal-difference values get the same treatment via
    ``report.clip_literal``; this covers the provenance fields.

    None of these fields has any legitimate use for a control character, so
    they are dropped rather than escaped. The SHA-256 is unaffected, so
    re-verifying an entry against its source still works.
    """
    return "".join(ch for ch in str(value) if not _is_control(ch))


def _is_control(ch: str) -> bool:
    """C0 controls, DEL, C1 controls, and the Unicode line/paragraph separators."""
    point = ord(ch)
    return point < 0x20 or 0x7F <= point <= 0x9F or point in (0x2028, 0x2029)


def _structure_from(
    shape: Any, position: int
) -> tuple[tuple[str | None, tuple[str, ...]], str | None]:
    """Read an entry's optional ``structure`` block, or explain why it is unusable.

    An entry with no structure block is normal and returns empty values. A
    structure block that is present but broken is an error rather than
    something to skip past: it would be dropped from the structure index and
    then never match anything, leaving no trace that it was ever meant to.
    """
    empty: tuple[str | None, tuple[str, ...]] = (None, ())
    if not isinstance(shape, dict):
        return empty, None

    def rejected(reason: str) -> tuple[tuple[str | None, tuple[str, ...]], str]:
        return empty, strings.t("identity_bad_entry", index=position, reason=reason)

    if shape.get("scheme") != STRUCTURE_SCHEME:
        return rejected(f"structure scheme {shape.get('scheme')!r} is not {STRUCTURE_SCHEME}")
    shape_hash = shape.get("sha256")
    raw_literals = shape.get("literals")
    if not _is_sha256(shape_hash) or not isinstance(raw_literals, list):
        return rejected("structure block is malformed")
    if len(raw_literals) > MAX_LITERALS_PER_ENTRY:
        return rejected(f"structure declares {len(raw_literals)} literals")
    return (shape_hash.strip().lower(), tuple(str(value) for value in raw_literals)), None


def _generated_from(
    raw: dict[str, Any], shape_hash: str | None, position: int
) -> tuple[bool, str | None]:
    """Read the declared ``generated`` flag, or explain why it cannot be believed.

    Two refusals, both because a wrong answer here decides whether a block is
    allowed to stand down the "ask someone who reads Python" branch.

    The value must be a real JSON boolean. ``"true"``, ``1`` and ``"no"`` are
    all truthy or falsy in Python and none of them is a declaration; accepting
    them would put the whole point of moving this out of a derived property --
    that the entry says what it means -- back in the hands of whatever the
    contributor happened to type.

    And it must not contradict the entry's structural form. A structural form
    exists precisely because a script's bytes differ in every copy, so
    ``"generated": false`` alongside one is a self-contradicting entry.
    Reported as malformed rather than resolved in either direction: an entry
    whose two halves disagree is not evidence for either half.

    The converse is *not* an error. An entry may declare itself generated and
    carry no structural form -- that is the shipped ``cloudrig.py.001``, a
    single per-file copy recorded verbatim without generalising a shape from
    it -- and refusing that would be refusing the very case this field exists
    to record.
    """
    value = raw.get("generated")
    if not isinstance(value, bool):
        reason = f"generated {value!r} is not true or false"
        return False, strings.t("identity_bad_entry", index=position, reason=reason)
    if shape_hash is not None and not value:
        reason = "generated is false but the entry carries a structural form"
        return False, strings.t("identity_bad_entry", index=position, reason=reason)
    return value, None


def _entry_from(raw: Any, position: int) -> tuple[KnownScript | None, str | None]:
    """Build one entry, or explain why it was skipped. Never raises."""
    if not isinstance(raw, dict):
        return None, strings.t("identity_bad_entry", index=position, reason="not an object")
    missing = [field for field in _REQUIRED_FIELDS if field not in raw]
    if missing:
        reason = "missing " + ", ".join(missing)
        return None, strings.t("identity_bad_entry", index=position, reason=reason)
    # An entry keyed on something that is not a digest can never match. Saying
    # so beats loading it and looking like coverage that is not there.
    if not _is_sha256(raw["sha256"]):
        reason = f"sha256 {raw['sha256']!r} is not a 64-character hexadecimal digest"
        return None, strings.t("identity_bad_entry", index=position, reason=reason)

    (shape_hash, literals), problem = _structure_from(raw.get("structure"), position)
    if problem is not None:
        return None, problem

    generated, problem = _generated_from(raw, shape_hash, position)
    if problem is not None:
        return None, problem

    try:
        entry = KnownScript(
            sha256=str(raw["sha256"]).strip().lower(),
            script_name=_printable(raw["script_name"]),
            byte_size=int(raw["byte_size"]),
            origin=_printable(raw["origin"]),
            source_url=_printable(raw["source_url"]),
            fetched_on=_printable(raw["fetched_on"]),
            attested_by=_printable(raw["attested_by"]),
            attested_on=_printable(raw["attested_on"]),
            notes=_printable(raw["notes"]),
            is_generated=generated,
            structure_sha256=shape_hash,
            structure_literals=literals,
        )
    except (TypeError, ValueError) as exc:
        return None, strings.t("identity_bad_entry", index=position, reason=str(exc))
    return entry, None


def _read_payload(target: Path) -> tuple[Any, str | None]:
    """Read and decode the database file, or say why it could not be.

    The except clause is deliberately broad. Naming the expected exception
    types looked complete and was not: a JSON number with more than 4300
    digits makes ``json.loads`` raise a bare ``ValueError`` (CPython's integer
    conversion limit, not wrapped in ``JSONDecodeError``), and deeply nested
    JSON raises ``RecursionError``. Both escaped a precise tuple, propagated
    past ``scan_file``, and aborted an entire batch run in ``cli.main`` --
    exactly the outcome this module promises cannot happen. The rule here is
    the outcome, not a list of failure modes somebody enumerated correctly on
    the day.
    """
    try:
        size = target.stat().st_size
        if size > MAX_DATABASE_BYTES:
            reason = f"{size} bytes exceeds the {MAX_DATABASE_BYTES}-byte limit"
            return None, strings.t("identity_db_unreadable", reason=reason)
        return json.loads(target.read_text(encoding="utf-8")), None
    except FileNotFoundError:
        return None, strings.t("identity_db_missing", path=str(target))
    except Exception as exc:
        detail = str(exc) or type(exc).__name__
        return None, strings.t("identity_db_unreadable", reason=detail)


def load_database(path: Path | None = None) -> Database:
    """Read the database. A missing or damaged file degrades, never crashes.

    An identity layer that can take the whole tool down with it is worse than
    no identity layer: the file is data, and bad data must cost context, not
    the scan. Every rejection is recorded in :attr:`Database.problems` so a
    silently empty database cannot pass for an empty result.
    """
    target = path or DATABASE_PATH
    payload, problem = _read_payload(target)
    if problem is not None:
        return Database(problems=(problem,))

    if not isinstance(payload, dict) or payload.get("schema") != SCHEMA_VERSION:
        found = payload.get("schema") if isinstance(payload, dict) else "none"
        return Database(problems=(strings.t("identity_db_schema", found=str(found)),))

    raw_entries = payload.get("entries")
    if not isinstance(raw_entries, list):
        return Database(problems=(strings.t("identity_db_schema", found="entries"),))
    if len(raw_entries) > MAX_ENTRIES:
        reason = f"{len(raw_entries)} entries exceeds the {MAX_ENTRIES} limit"
        return Database(problems=(strings.t("identity_db_unreadable", reason=reason),))

    entries: list[KnownScript] = []
    problems: list[str] = []
    for position, raw in enumerate(raw_entries):
        entry, problem = _entry_from(raw, position)
        if entry is None:
            problems.append(problem or "")
            continue
        entries.append(entry)

    return Database(
        entries=tuple(entries),
        by_sha256={e.sha256: e for e in entries},
        by_structure={e.structure_sha256: e for e in entries if e.structure_sha256},
        problems=tuple(problems),
    )


_cached: Database | None = None


def default_database() -> Database:
    """The shipped database, read once per process -- including when it fails.

    A failed load is cached like any other result. Leaving the cache empty on
    failure meant a damaged database was re-read, and re-failed, once per file
    in a batch scan: the slowest possible way to learn the same thing.
    """
    global _cached
    if _cached is None:
        _cached = load_database(DATABASE_PATH)
    return _cached


def clear_cache() -> None:
    """Forget the memoised database. For tests and for reloading after an edit."""
    global _cached
    _cached = None
