# SPDX-License-Identifier: GPL-3.0-or-later
"""Data shapes for a scan result.

Kept free of parsing and formatting logic so that :mod:`blend_xray.report` can
render them and the JSON output can serialise them without importing
blender-asset-tracer.
"""

from __future__ import annotations

import dataclasses
import enum
from pathlib import Path
from typing import Any

from .explain import Explanation
from .identity import IdentityMatch


class Category(enum.StrEnum):
    """The categories Blend X-Ray inspects. Always reported, even when empty.

    Listing what was checked is the point: a user must be able to see the tool
    actually looked, and see the edges of what it knows about.
    """

    TEXT = "text"
    DRIVER = "driver"
    OSL = "osl"
    LIBRARY = "library"
    FILEPATH = "filepath"


CATEGORY_STRING_KEYS: dict[Category, str] = {
    Category.TEXT: "cat_text",
    Category.DRIVER: "cat_driver",
    Category.OSL: "cat_osl",
    Category.LIBRARY: "cat_library",
    Category.FILEPATH: "cat_filepath",
}

#: Why one file could not be scanned -> the catalogue key that says so.
#: Shared by the CLI and the window so the two cannot describe the same
#: failure differently. Every one of these templates tolerates being handed
#: both ``path`` and ``reason``; ``str.format`` ignores the one it does not use.
ERROR_STRING_KEYS: dict[str, str] = {
    "not_a_blend": "err_not_blend",
    "malformed": "err_malformed",
    "tool_error": "err_tool",
    "unreadable": "err_unreadable",
}


@dataclasses.dataclass(frozen=True)
class TextFinding:
    """A ``struct Text`` datablock (DNA_text_types.h)."""

    name: str
    filepath: str | None
    flags: int
    flag_names: tuple[str, ...]
    is_autorun: bool
    is_memory: bool
    is_external: bool
    source: str
    source_bytes: int
    truncated: bool
    explanation: Explanation | None
    #: What the known-script database recognised this body as, if anything.
    #: ``None`` means "nothing to say about where this came from" -- never
    #: "this is unknown-bad" and never "this is unrecognised-therefore-fine".
    identity: IdentityMatch | None = None

    @property
    def identity_clears_escalation(self) -> bool:
        """True when this block's alarming findings are explained by a byte match.

        Only meaningful together with the findings themselves, which stay
        exactly as they were: this changes which closing recommendation the
        report prints, nothing about what it lists.
        """
        return self.identity is not None and self.identity.suppresses_escalation

    @property
    def is_blind_spot(self) -> bool:
        """True when this block had NO rule applied to it and that matters.

        Reporting a file as ordinary on the strength of a script we could not
        parse would present a blind spot as a result. But Blender text
        datablocks hold arbitrary text -- READMEs, credits, GLSL -- and across
        a ~100-file corpus most unparseable blocks were exactly that. Warning
        about a README is the noise this tool exists to avoid. Only two cases
        are real blind spots: a block Blender will execute (auto-run), and one
        whose author named it Python.

        Lives here rather than in one renderer because the closing
        recommendation and the banner must agree about what counts as
        unexamined; two copies of this predicate would eventually disagree.
        """
        if self.explanation is None or self.explanation.parsed:
            return False
        return self.is_autorun or self.name.lower().endswith(".py")

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "filepath": self.filepath,
            "flags": self.flags,
            "flag_names": list(self.flag_names),
            "is_autorun": self.is_autorun,
            "is_memory": self.is_memory,
            "is_external": self.is_external,
            "source_bytes": self.source_bytes,
            "truncated": self.truncated,
            "source": self.source,
            "explanation": _explanation_dict(self.explanation),
            "identity": None if self.identity is None else self.identity.to_dict(),
        }


@dataclasses.dataclass(frozen=True)
class DriverFinding:
    """A ``struct ChannelDriver`` (DNA_anim_types.h).

    A driver is a code path under the same auto-execution gate as a text
    datablock, so this carries an :class:`~blend_xray.explain.Explanation` like
    :class:`TextFinding` does, and the banner and the closing recommendation
    read it the same way.
    """

    owner: str
    expression: str
    driver_type: int
    driver_type_name: str
    flags: int
    flag_names: tuple[str, ...]
    #: ``None`` when :attr:`expression_is_evaluated` is false: an expression
    #: Blender never reads is neither simple nor complex, and answering the
    #: question at all would imply it runs.
    is_simple: bool | None
    classification_reason: str
    #: Whether Blender evaluates the ``expression`` field for this driver type.
    #: ``evaluate_driver`` dispatches AVERAGE/SUM to ``evaluate_driver_sum``
    #: and MIN/MAX to ``evaluate_driver_min_max``, neither of which reads the
    #: expression, and ``driver_compile_simple_expr`` refuses outright unless
    #: the type is ``DRIVER_TYPE_PYTHON`` (fcurve_driver.cc:1182-1190,
    #: :1406-1437). For those types the field is stored, inert data.
    expression_is_evaluated: bool = True
    #: Present only for expressions Blender actually evaluates.
    explanation: Explanation | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "owner": self.owner,
            "expression": self.expression,
            "driver_type": self.driver_type,
            "driver_type_name": self.driver_type_name,
            "flags": self.flags,
            "flag_names": list(self.flag_names),
            "is_simple": self.is_simple,
            "classification_reason": self.classification_reason,
            "expression_is_evaluated": self.expression_is_evaluated,
            "explanation": _explanation_dict(self.explanation),
        }


@dataclasses.dataclass(frozen=True)
class OSLFinding:
    """A ``struct NodeShaderScript`` (DNA_node_types.h).

    There is deliberately no ``text_name`` field. There used to be one, it was
    hardcoded ``None`` at every construction site and no surface ever printed
    it, while the string for ``NODE_SCRIPT_INTERNAL`` told the reader the text
    block was "named below". The name is not on this struct at all -- an
    internal script node points at its Text through the owning ``bNode``'s
    ``id`` pointer -- and with zero script nodes across the 101-file corpora,
    code to walk back to it would ship printing a positive claim no real file
    has ever exercised. So the promise was removed instead of the field being
    filled with a guess.
    """

    owner: str
    mode: int
    mode_name: str
    filepath: str | None
    bytecode_bytes: int
    bytecode_hash: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "owner": self.owner,
            "mode": self.mode,
            "mode_name": self.mode_name,
            "filepath": self.filepath,
            "bytecode_bytes": self.bytecode_bytes,
            "bytecode_hash": self.bytecode_hash,
        }


@dataclasses.dataclass(frozen=True)
class LibraryFinding:
    """A ``struct Library`` (DNA_ID.h)."""

    raw_path: str
    resolved_path: str | None
    is_relative: bool
    is_absolute: bool
    escapes_folder: bool
    is_unc: bool
    unc_host: str | None
    has_drive_letter: bool
    #: True when the path is *written* with Blender's blend-relative ``//``
    #: marker but normalises to a root of its own -- a UNC share, a drive, or
    #: the filesystem root. The marker is then a disguise, and saying so is the
    #: finding: ``////host/share/x.blend`` reads as an ordinary relative link
    #: to a human and to Blender's own path code is a network share.
    disguised: bool = False
    #: True only when an absolute path can be *shown*, by text comparison
    #: alone, to land inside the folder the .blend sits in. False means the
    #: question was not settled -- never that the path was shown to be
    #: outside. Nothing about an absolute path written on another machine can
    #: be checked against a folder on this one, so the wording it selects makes
    #: a claim in the True branch only. See
    #: :func:`blend_xray.libpath.contains_lexically`.
    absolute_inside_blend_dir: bool = False

    @property
    def notable(self) -> bool:
        return self.is_absolute or self.escapes_folder or self.is_unc or self.has_drive_letter

    def to_dict(self) -> dict[str, Any]:
        return {
            "raw_path": self.raw_path,
            "resolved_path": self.resolved_path,
            "is_relative": self.is_relative,
            "is_absolute": self.is_absolute,
            "escapes_folder": self.escapes_folder,
            "is_unc": self.is_unc,
            "unc_host": self.unc_host,
            "has_drive_letter": self.has_drive_letter,
            "disguised": self.disguised,
            "absolute_inside_blend_dir": self.absolute_inside_blend_dir,
            "notable": self.notable,
        }


@dataclasses.dataclass(frozen=True)
class PathFinding:
    """An informational filepath on some other datablock (image, sound, ...)."""

    kind: str
    name: str
    path: str

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "name": self.name, "path": self.path}


@dataclasses.dataclass
class ScanResult:
    """Everything Blend X-Ray found in one file, plus what it checked."""

    path: Path
    blender_version: str = ""
    pointer_size: int = 0
    compression: str = "none"
    block_count: int = 0
    categories_checked: tuple[Category, ...] = tuple(Category)
    texts: list[TextFinding] = dataclasses.field(default_factory=list)
    drivers: list[DriverFinding] = dataclasses.field(default_factory=list)
    osl_nodes: list[OSLFinding] = dataclasses.field(default_factory=list)
    libraries: list[LibraryFinding] = dataclasses.field(default_factory=list)
    filepaths: list[PathFinding] = dataclasses.field(default_factory=list)
    #: Non-fatal problems hit while reading individual datablocks.
    warnings: list[str] = dataclasses.field(default_factory=list)
    #: True when the wall-clock budget ran out mid-scan and the inventory below
    #: covers only part of the file. Every surface has to treat this as louder
    #: than any finding it did manage to collect: an inventory that stopped
    #: early and does not say so is indistinguishable from a file with nothing
    #: in it, which is the one reading this tool must never produce.
    timed_out: bool = False
    #: Which :class:`Category` was being read when the budget ran out, as its
    #: stable string value, or ``"preflight"`` for the structural walk.
    timed_out_at: str = ""
    #: The budget that was exceeded, in seconds -- carried so the report can
    #: name the number the user actually passed to ``--max-seconds``.
    time_budget: float = 0.0

    @property
    def autorun_texts(self) -> list[TextFinding]:
        return [t for t in self.texts if t.is_autorun]

    @property
    def notable_libraries(self) -> list[LibraryFinding]:
        return [lib for lib in self.libraries if lib.notable]

    @property
    def has_findings(self) -> bool:
        """True when anything at all was found in the inspected categories.

        Informational filepaths alone do not count as a finding: every normal
        .blend file with a texture would otherwise exit non-zero.

        Deliberately *not* true merely because the scan timed out. This answers
        "what is in the file", and a timeout is a fact about the inspection
        rather than about the file. :attr:`needs_attention` is the one that
        merges the two, and it is what the exit code uses.
        """
        return bool(self.texts or self.drivers or self.osl_nodes or self.libraries)

    @property
    def needs_attention(self) -> bool:
        """True when this scan must not be reported as an uneventful one.

        A timed-out scan qualifies even with an empty inventory: exiting 0 on a
        file the tool gave up on would tell a script -- and the artist reading
        its output -- that the file came back with nothing in it.
        """
        return self.has_findings or self.timed_out

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": str(self.path),
            "blender_version": self.blender_version,
            "pointer_size": self.pointer_size,
            "compression": self.compression,
            "block_count": self.block_count,
            "categories_checked": [str(c) for c in self.categories_checked],
            "texts": [t.to_dict() for t in self.texts],
            "drivers": [d.to_dict() for d in self.drivers],
            "osl_nodes": [o.to_dict() for o in self.osl_nodes],
            "libraries": [lib.to_dict() for lib in self.libraries],
            "filepaths": [f.to_dict() for f in self.filepaths],
            "warnings": list(self.warnings),
            "has_findings": self.has_findings,
            "timed_out": self.timed_out,
            "timed_out_at": self.timed_out_at,
            "time_budget": self.time_budget,
        }


def _explanation_dict(exp: Explanation | None) -> dict[str, Any] | None:
    if exp is None:
        return None
    return {
        "parsed": exp.parsed,
        "parse_error": exp.parse_error,
        "note": exp.note,
        "obfuscated": exp.obfuscated,
        "max_severity": exp.max_severity.name,
        "statements": [
            {
                "severity": st.severity.name,
                "key": st.key,
                "text": st.text,
                "evidence": list(st.evidence),
            }
            for st in exp.statements
        ],
        "literals": [{"kind": lit.kind, "value": lit.value} for lit in exp.literals],
    }
