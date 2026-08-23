# SPDX-License-Identifier: GPL-3.0-or-later
"""Render a :class:`~blend_xray.models.ScanResult` for humans or for machines.

Two rules shape everything in this module:

1. The output is an **inventory, never a verdict**. There is no "SAFE", no
   "clean", no score. We report what is in the file and what we looked at; the
   reader decides. Note there is deliberately no green in the palette either --
   green reads as "all clear" at a glance, which is the false confidence this
   tool exists to avoid.
2. Per code block, the order is: plain-language explanation, then the extracted
   literals, then the raw source **last**. Source that nobody can read is the
   least useful thing on screen, so it does not go first.
"""

from __future__ import annotations

import json
import os
import sys
import textwrap
from collections.abc import Iterable
from typing import Any, Final, TextIO

from . import __version__, banner, guards, strings, truncation
from .banner import Tier
from .explain import OBFUSCATION_KEYS, Explanation, Severity
from .identity import EVIDENCE_BYTE, IdentityMatch, KnownScript
from .models import (
    CATEGORY_STRING_KEYS,
    DriverFinding,
    LibraryFinding,
    OSLFinding,
    ScanResult,
    TextFinding,
)
from .recommend import recommendation_lines
from .sanitise import printable_block, printable_line

__all__ = [
    "Palette",
    "format_json",
    "format_text_report",
    "make_palette",
    # Re-exported: the decision lives in blend_xray.recommend, but both
    # surfaces import it from here and moving the module must not move the
    # import in every caller.
    "recommendation_lines",
]

#: How much of a script body to show without ``--full``.
DEFAULT_SOURCE_PREVIEW = 1500

#: How many differing string literals a structural match prints before it says
#: how many more there are. A wall of 800 lines hides the one that matters.
MAX_LITERAL_DIFFS_SHOWN = 12

#: Longest literal value printed in a difference line, before ellipsis.
MAX_LITERAL_WIDTH = 120

#: Longest extracted literal printed in the literals list, before ellipsis.
#: Measured on the sanitised text, so the cut can never split an escape.
MAX_LITERAL_VALUE_WIDTH = 200

#: Total width of the banner box, borders included.
BANNER_WIDTH: Final = 78

# Box drawing and tier markers, in two charsets. A stock ``cmd.exe`` runs in
# cp1252, which cannot encode U+2500 box drawing or U+2716; printing them
# there raises UnicodeEncodeError and takes the whole report down, which is
# how a non-ASCII output bug got into this tool once already. So the charset
# is chosen from what the output stream says it can encode, and the fallback
# is plain ASCII rather than mojibake or a crash.
_BOX_UNICODE: Final[dict[str, str]] = {
    "tl": "┌", "tr": "┐", "bl": "└", "br": "┘", "h": "─", "v": "│",
}
_BOX_ASCII: Final[dict[str, str]] = {
    "tl": "+", "tr": "+", "bl": "+", "br": "+", "h": "-", "v": "|",
}

# No tick, no check mark, and nothing green -- not even for NEUTRAL. See the
# reasoning at the top of blend_xray/banner.py. Both sets are three columns
# wide so the box lines up identically either way.
_MARK_UNICODE: Final[dict[Tier, str]] = {Tier.RED: "[✖]", Tier.AMBER: "[▲]", Tier.NEUTRAL: "[·]"}
_MARK_ASCII: Final[dict[Tier, str]] = {Tier.RED: "[X]", Tier.AMBER: "[!]", Tier.NEUTRAL: "[-]"}

_UNICODE_PROBE: Final = "".join(_BOX_UNICODE.values()) + "".join(_MARK_UNICODE.values())


def stream_can_encode(stream: TextIO, probe: str) -> bool:
    """Whether ``probe`` survives ``stream``'s encoding.

    A stream with no declared encoding (an in-memory ``StringIO``, a test
    buffer) holds text rather than bytes and can carry anything, so it is
    treated as capable. An unknown encoding name is treated as incapable: the
    ASCII fallback is always readable, a traceback never is.
    """
    encoding = getattr(stream, "encoding", None)
    if not encoding:
        return True
    try:
        probe.encode(encoding)
    except (UnicodeEncodeError, LookupError, TypeError):
        return False
    return True


class Palette:
    """ANSI colours that turn themselves off when output is not a terminal."""

    def __init__(
        self, stream: TextIO, force: bool | None = None, ascii_only: bool | None = None
    ) -> None:
        if force is None:
            enabled = stream.isatty() and os.environ.get("NO_COLOR") is None
            if os.environ.get("FORCE_COLOR"):
                enabled = True
        else:
            enabled = force
        self.enabled = bool(enabled)
        if ascii_only is None:
            ascii_only = not stream_can_encode(stream, _UNICODE_PROBE)
        self.ascii_only = bool(ascii_only)

    def _wrap(self, code: str, text: str) -> str:
        return f"\033[{code}m{text}\033[0m" if self.enabled else text

    def alarm(self, text: str) -> str:
        return self._wrap("1;31", text)

    def notable(self, text: str) -> str:
        return self._wrap("33", text)

    def header(self, text: str) -> str:
        return self._wrap("1;36", text)

    def dim(self, text: str) -> str:
        return self._wrap("2", text)

    def bold(self, text: str) -> str:
        return self._wrap("1", text)

    def for_severity(self, severity: Severity, text: str) -> str:
        if severity is Severity.ALARMING:
            return self.alarm(text)
        if severity is Severity.NOTABLE:
            return self.notable(text)
        return self.dim(text)


def _rule(pal: Palette, title: str) -> str:
    return pal.header(f"\n--- {title} " + "-" * max(4, 60 - len(title)))


def headline_for(exp: Explanation | None) -> tuple[str, bool]:
    """A short phrase describing one code block, plus whether to spotlight it.

    Concrete behaviour leads. An obfuscated block that also opens a socket is
    summarised as "connects to the internet ... and hides part of what it
    does", not just "hidden" -- the visible half is the actionable half. Only
    when nothing else is visible does hiding become the headline itself.

    When it does, the sentence comes from the statement that actually fired
    rather than from a fixed key. There are now several ways to be hiding --
    decode-then-execute, a ``__builtins__`` lookup, calling the value another
    call returned, a name assembled from fragments -- and printing "has to be
    decoded" over a block that decodes nothing would be the same class of
    false sentence this headline is meant to summarise.
    """
    if exp is None:
        return strings.t("text_empty"), False

    alarming = [
        s.text
        for s in exp.statements
        if s.severity is Severity.ALARMING and s.key not in OBFUSCATION_KEYS
    ]
    if alarming:
        text = ", ".join(alarming[:2])
        if exp.obfuscated:
            text += " " + strings.t("summary_and_hidden")
        return text, True
    # Statements are sorted by descending severity, so the first hiding
    # statement is the loudest one that matched.
    hidden = [s.text for s in exp.statements if s.key in OBFUSCATION_KEYS]
    if hidden:
        return hidden[0], True
    if exp.obfuscated:
        # An unparseable body with a blob in it: no statement survived, but
        # the fallback sweep still found something encoded.
        return strings.t("x_obfuscation"), True

    notable = [s.text for s in exp.statements if s.severity is Severity.NOTABLE]
    if notable:
        return ", ".join(notable[:2]), False
    benign = [s.text for s in exp.statements if s.severity is Severity.BENIGN]
    if benign:
        return benign[0], False
    return strings.t("explain_nothing_notable"), False


_COMPRESSION_KEYS = {
    "none": "compression_none",
    "gzip": "compression_gzip",
    "zstd": "compression_zstd",
    "unrecognised": "compression_unrecognised",
}


def compression_label(compression: str) -> str:
    """Human wording for the header. The raw value stays in the JSON output.

    An unrecognised value is echoed back verbatim rather than guessed at.
    """
    key = _COMPRESSION_KEYS.get(compression.strip().lower())
    return strings.t(key) if key else compression


def file_meta_line(result: ScanResult) -> str:
    """The one-line "what this file structurally is" header, shared by both UIs.

    The version is rendered the way Blender writes it rather than as the raw
    header integer -- see :func:`blend_xray.guards.format_version`. The raw
    value is untouched in ``ScanResult.blender_version`` and therefore in
    ``--json``, so machine consumers see exactly what they saw before.
    """
    return strings.t(
        "file_meta",
        version=guards.format_version(result.blender_version),
        pointers=result.pointer_size,
        compression=compression_label(result.compression),
        blocks=result.block_count,
    )


def tier_marker(tier: Tier, ascii_only: bool = False) -> str:
    """The three-column marker for a tier, shared by the CLI and the window.

    Never a tick and never an "OK" symbol, in either charset. The neutral
    marker is a placeholder, not a pass.
    """
    return (_MARK_ASCII if ascii_only else _MARK_UNICODE)[tier]


def _banner_body(info: banner.Banner, mark: str) -> list[str]:
    """The banner's text, wrapped to the box, marker first."""
    width = BANNER_WIDTH - 4
    indent = " " * (len(mark) + 1)
    lines = textwrap.wrap(f"{mark} {info.headline()}", width, subsequent_indent=indent)
    detail = info.detail()
    if detail:
        lines += textwrap.wrap(detail, width, initial_indent=indent, subsequent_indent=indent)
    notes = info.notes()
    if notes and detail:
        lines.append("")
    for note in notes:
        lines += textwrap.wrap(note, width, initial_indent=indent, subsequent_indent=indent)
    return lines or [mark]


def banner_lines(result: ScanResult, pal: Palette) -> list[str]:
    """The at-a-glance box that opens the report.

    Drawn in one colour for the whole box -- red, amber or dim -- because the
    point is a shape the reader recognises before reading a word. There is no
    green branch here and there must never be one; :mod:`blend_xray.banner`
    carries the reasoning.
    """
    info = banner.for_result(result)
    box = _BOX_ASCII if pal.ascii_only else _BOX_UNICODE
    mark = tier_marker(info.tier, pal.ascii_only)
    inner = BANNER_WIDTH - 2
    rule = box["h"] * inner

    out = [box["tl"] + rule + box["tr"]]
    out += [f"{box['v']} {text:<{BANNER_WIDTH - 4}} {box['v']}" for text in _banner_body(info, mark)]
    out.append(box["bl"] + rule + box["br"])
    return [pal.for_severity(info.severity, line) for line in out]


def _summary_lines(result: ScanResult, pal: Palette) -> list[str]:
    """Group code blocks by what they do, spotlighting the ones that matter."""
    if not result.texts:
        return []

    groups: dict[tuple[str, bool], int] = {}
    for finding in result.texts:
        key = headline_for(finding.explanation)
        groups[key] = groups.get(key, 0) + 1

    out = [pal.bold(strings.t("summary_blocks_found", count=len(result.texts)))]
    for (description, spotlight), count in sorted(
        groups.items(), key=lambda kv: (not kv[0][1], -kv[1])
    ):
        marker = pal.alarm(strings.t("summary_look_at_this")) if spotlight else ""
        line = strings.t("summary_line", count=count, description=description, marker=marker)
        out.append(pal.alarm(line) if spotlight else line)
    return out


def _render_explanation(exp: Explanation, pal: Palette, indent: str) -> list[str]:
    lines: list[str] = []
    if exp.note:
        lines.append(indent + pal.notable(printable_line(exp.note)))
    if not exp.parsed and exp.parse_error:
        lines.append(indent + pal.notable(strings.t("explain_unparseable", reason=exp.parse_error)))

    # When nothing else could be read, the concealment IS the whole finding and leads.
    # When behaviour was also found, saying "I can't tell you what this does" straight
    # before a list of what it does reads as a contradiction, so it becomes a caveat
    # printed after the list instead.
    if exp.obfuscated and not exp.statements:
        lines.append(indent + pal.alarm(strings.t("explain_obfuscated_honest")))

    if exp.statements:
        lines.append(indent + pal.bold(strings.t("explain_header")))
        for st in exp.statements:
            # st.text normally arrives from strings.t and is already clean.
            # Sanitised again anyway: this is the one rendered field that does
            # not have to pass through the catalogue, so it is the one place a
            # future code path could route file text straight to the terminal.
            bullet = pal.for_severity(st.severity, f"  * {printable_line(st.text)}")
            lines.append(indent + bullet)
            if st.evidence:
                lines.append(
                    indent
                    + pal.dim(
                        "      " + strings.t("explain_evidence", evidence=", ".join(st.evidence))
                    )
                )
    elif exp.parsed:
        lines.append(indent + pal.dim(strings.t("explain_nothing_notable")))

    if exp.obfuscated and exp.statements:
        lines.append(indent + pal.alarm(strings.t("explain_obfuscated_partial")))

    if exp.literals:
        lines.append(indent + pal.bold(strings.t("explain_literals_header")))
        for lit in exp.literals:
            label = strings.t(f"lit_{lit.kind}")
            lines.append(indent + pal.notable(f"  [{label}] {show_literal(lit.value)}"))
    else:
        lines.append(indent + pal.dim(strings.t("explain_no_literals")))

    lines.append(indent + pal.dim(strings.t("explain_baseline")))
    return lines


def clip_literal(value: str) -> str:
    """One literal value, made printable on a single line.

    ``repr`` is the sanitiser here and is sufficient on its own: it escapes
    every character ``str.isprintable`` rejects, which covers the C0 and C1
    controls, DEL, U+2028/U+2029 and the bidi overrides -- the whole set
    :mod:`blend_xray.sanitise` lists. The newline/tab folding above it is only
    so the escape reads as ``\\n`` rather than ``\\x0a``.
    """
    flat = value.replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t")
    if len(flat) > MAX_LITERAL_WIDTH:
        flat = flat[:MAX_LITERAL_WIDTH] + "..."
    return repr(flat)


def show_literal(value: str) -> str:
    """An extracted literal as the report prints it, in either UI.

    Sanitised *before* clipping, never after: escaping ESC into ``\\x1b``
    lengthens the text, and cutting first would leave the cut landing in the
    middle of an escape sequence with the rest of it still live. Shared with
    the window so the two surfaces cannot disagree about what a literal looks
    like -- or about whether it is safe to print.
    """
    shown = printable_line(value)
    if len(shown) > MAX_LITERAL_VALUE_WIDTH:
        shown = shown[:MAX_LITERAL_VALUE_WIDTH] + "..."
    return shown


def identity_lines(match: IdentityMatch) -> list[tuple[str, Severity]]:
    """The identity block as (text, severity-for-colour) pairs, UI-independent.

    Shared by the CLI report and the window so the two cannot describe the same
    match differently. Severity here drives colour only; it is never mixed into
    a finding's own severity, which this layer does not touch.
    """
    entry = match.entry
    byte_match = match.evidence == EVIDENCE_BYTE
    name = strings.t("identity_line", script_name=entry.script_name, origin=entry.origin)
    evidence_key = "identity_evidence_byte" if byte_match else "identity_evidence_structure"

    out: list[tuple[str, Severity]] = [
        (name, Severity.BENIGN),
        (strings.t(evidence_key), Severity.BENIGN if byte_match else Severity.NOTABLE),
    ]
    if byte_match and entry.is_generated:
        out.append((strings.t("identity_generated_byte"), Severity.NOTABLE))
    out.extend(_provenance_lines(entry))
    if not byte_match:
        out.extend(_literal_difference_lines(match))
    out.append((strings.t("identity_scope"), Severity.BENIGN))
    return out


def _provenance_lines(entry: KnownScript) -> list[tuple[str, Severity]]:
    """Where the record came from, who vouched for it, and what the script is."""
    attested = strings.t(
        "identity_attested",
        attested_by=entry.attested_by,
        attested_on=entry.attested_on,
    )
    source = strings.t("identity_source", url=entry.source_url, fetched_on=entry.fetched_on)
    return [
        (source, Severity.BENIGN),
        (attested, Severity.BENIGN),
        (strings.t("identity_notes", notes=entry.notes), Severity.BENIGN),
    ]


def _literal_difference_lines(match: IdentityMatch) -> list[tuple[str, Severity]]:
    """Which quoted values differ from the reference -- the security payload.

    These are printed as NOTABLE rather than dimmed on purpose: on a structural
    match this list is the only place an injected address can show up, so it
    must not read as a footnote.
    """
    if not match.differences:
        return [(strings.t("identity_diff_none"), Severity.NOTABLE)]
    out = [
        (strings.t("identity_diff_header", count=len(match.differences)), Severity.NOTABLE)
    ]
    for diff in match.differences[:MAX_LITERAL_DIFFS_SHOWN]:
        out.append(
            (
                strings.t(
                    "identity_diff_line",
                    index=diff.index,
                    reference=clip_literal(diff.reference),
                    actual=clip_literal(diff.actual),
                ),
                Severity.NOTABLE,
            )
        )
    remaining = len(match.differences) - MAX_LITERAL_DIFFS_SHOWN
    if remaining > 0:
        out.append((strings.t("identity_diff_more", count=remaining), Severity.NOTABLE))
    return out


def _render_identity(match: IdentityMatch, pal: Palette, indent: str) -> list[str]:
    lines = [indent + pal.bold(strings.t("identity_header"))]
    for text, severity in identity_lines(match):
        lines.append(indent + pal.for_severity(severity, "  " + text))
    return lines


def _render_text(finding: TextFinding, pal: Palette, full: bool) -> list[str]:
    lines = [pal.bold(strings.t("text_block_title", name=finding.name))]
    if finding.is_autorun:
        lines.append("  " + pal.alarm(strings.t("text_autorun_flag")))
    else:
        lines.append("  " + pal.dim(strings.t("text_not_autorun")))

    lines.append(
        "  " + pal.dim(strings.t("text_flags", flags=", ".join(finding.flag_names) or "none"))
    )
    if finding.filepath:
        lines.append("  " + strings.t("text_filepath", path=finding.filepath))
    if finding.is_memory:
        lines.append("  " + pal.dim(strings.t("text_is_mem")))
    if finding.is_external:
        lines.append("  " + pal.dim(strings.t("text_is_ext")))

    # Identity comes before the explanation: knowing the block is a published
    # release changes how a reader weighs the list that follows, so it has to
    # arrive before the list, not after it.
    if finding.identity is not None:
        lines.extend(_render_identity(finding.identity, pal, "  "))

    if finding.explanation is not None:
        lines.extend(_render_explanation(finding.explanation, pal, "  "))

    lines.append("  " + pal.bold(strings.t("text_source_header")))
    if not finding.source.strip():
        lines.append("    " + pal.dim(strings.t("text_empty")))
        return lines

    # Sanitised before it is cut and before it is split. ``str.splitlines()``
    # does not treat ESC as a line break, so an escape sequence in the file
    # used to survive indentation and reach the terminal intact -- with
    # --color never as well, because that flag only governs what *we* emit.
    body = printable_block(finding.source)
    if not full and len(body) > DEFAULT_SOURCE_PREVIEW:
        shown = body[:DEFAULT_SOURCE_PREVIEW]
        lines.extend("    " + ln for ln in shown.splitlines())
        lines.append(
            "    "
            + pal.notable(
                strings.t("text_truncated", shown=DEFAULT_SOURCE_PREVIEW, total=len(body))
            )
        )
    else:
        lines.extend("    " + ln for ln in body.splitlines())
    return lines


def _driver_classification_lines(finding: DriverFinding, pal: Palette) -> list[str]:
    """The three states a driver expression can be in, said plainly.

    An expression Blender never reads gets neither "runs without Python" nor
    "needs full Python": both describe an evaluation that does not happen for
    this driver type, and 3,527 of the corpus's 22,520 drivers were being
    given one of those sentences about a dead field.
    """
    if not finding.expression_is_evaluated:
        return [
            "  "
            + pal.dim(
                strings.t("driver_expression_unused", type_name=finding.driver_type_name)
            )
        ]
    lines = [
        "  " + pal.dim(strings.t("driver_simple"))
        if finding.is_simple
        else "  " + pal.notable(strings.t("driver_suspicious"))
    ]
    lines.append("  " + pal.dim(printable_line(f"({finding.classification_reason})")))
    return lines


def _render_driver(finding: DriverFinding, pal: Palette) -> list[str]:
    lines = [pal.bold(strings.t("driver_title", owner=finding.owner))]
    lines.append("  " + strings.t("driver_type", type_name=finding.driver_type_name))
    lines.append("  " + strings.t("driver_expression", expr=finding.expression))
    lines.extend(_driver_classification_lines(finding, pal))
    exp = finding.explanation
    if exp is not None and exp.statements:
        lines.append("  " + pal.bold(strings.t("explain_header")))
        for st in exp.statements:
            lines.append("  " + pal.for_severity(st.severity, f"  * {printable_line(st.text)}"))
            if st.evidence:
                lines.append(
                    "      "
                    + pal.dim(strings.t("explain_evidence", evidence=", ".join(st.evidence)))
                )
    if finding.flag_names:
        lines.append("  " + pal.dim(strings.t("driver_flags", flags=", ".join(finding.flag_names))))
    return lines


def _render_osl(finding: OSLFinding, pal: Palette) -> list[str]:
    lines = [pal.bold(strings.t("osl_title", owner=finding.owner))]
    key = "osl_external" if finding.mode else "osl_internal"
    lines.append("  " + strings.t(key))
    if finding.filepath:
        lines.append("  " + strings.t("osl_filepath", path=finding.filepath))
    if finding.bytecode_bytes:
        lines.append("  " + pal.notable(strings.t("osl_has_bytecode", size=finding.bytecode_bytes)))
    if finding.bytecode_hash:
        lines.append("  " + pal.dim(strings.t("osl_bytecode_hash", hash=finding.bytecode_hash)))
    lines.append("  " + pal.dim(strings.t("osl_lower_severity")))
    return lines


def _render_library(finding: LibraryFinding, pal: Palette) -> list[str]:
    lines = [pal.bold(strings.t("library_title", path=finding.raw_path))]
    # Said before the rest: a reader who has seen "//" a thousand times will
    # read the next line as routine unless they are told first that this "//"
    # is not the "//" they know.
    if finding.disguised:
        lines.append("  " + pal.alarm(strings.t("library_disguised")))
    if finding.is_unc:
        lines.append("  " + pal.alarm(strings.t("library_unc", host=finding.unc_host or "?")))
    if finding.has_drive_letter:
        lines.append("  " + pal.alarm(strings.t("library_drive")))
    if finding.escapes_folder:
        lines.append(
            "  " + pal.alarm(strings.t("library_escapes", resolved=finding.resolved_path or "?"))
        )
    elif finding.is_absolute:
        key = "library_absolute_inside" if finding.absolute_inside_blend_dir else "library_absolute"
        lines.append("  " + pal.alarm(strings.t(key)))
    elif finding.is_relative:
        lines.append(
            "  " + pal.dim(strings.t("library_relative", resolved=finding.resolved_path or "?"))
        )
        lines.append("  " + pal.dim(strings.t("library_ok_relative")))
    return lines


def _render_section(
    pal: Palette, title_key: str, items: Iterable[Any], renderer: Any, *args: Any
) -> list[str]:
    items = list(items)
    if not items:
        return []
    out = [_rule(pal, strings.t(title_key))]
    for item in items:
        out.extend(renderer(item, pal, *args))
        out.append("")
    return out


def _report_header(result: ScanResult, pal: Palette, quiet: bool) -> list[str]:
    """The banner, the file's identity, and what was looked at."""
    lines: list[str] = banner_lines(result, pal)
    if quiet:
        # --quiet suppresses every context section, but the banner survives it:
        # it is the one thing worth keeping when everything else is gone. It
        # then has to carry the path itself, because nothing else in quiet
        # output names the file the banner is talking about.
        lines.append(pal.dim(printable_line(result.path)))
    else:
        lines.append(pal.header(f"{strings.t('tool_name')} -- {printable_line(result.path)}"))
        lines.append(pal.dim(file_meta_line(result)))
        lines.append(pal.dim(strings.t("never_runs")))
        lines.append("")
        lines.append(strings.t("categories_checked_header", count=len(result.categories_checked)))
        lines.extend(
            "  - " + strings.t(CATEGORY_STRING_KEYS[cat]) for cat in result.categories_checked
        )
        lines.append("")

    # Before anything a reader could mistake for a conclusion, in quiet mode as
    # well as full: everything below it, "nothing found" included, describes
    # only the part of the file that was read, and this says where that stopped.
    if result.timed_out:
        lines.append(pal.alarm(truncation.notice(result)))
        lines.append("")
    return lines


def _empty_inventory_lines(result: ScanResult, pal: Palette, quiet: bool) -> list[str]:
    """What to print when no category turned anything up.

    "No embedded code found in the categories checked" is a claim about the
    whole file. After a timeout it would be a claim about a file nobody
    finished reading, so the truncation notice replaces it rather than sitting
    beside it, and the closing advice says what to do instead.
    """
    lines: list[str] = []
    if result.timed_out:
        lines.append("")
        lines.extend(_recommendation_block(result, pal))
    else:
        lines.append(pal.bold(strings.t("nothing_found")))
    if result.filepaths and not quiet:
        lines.extend(_render_paths(result, pal))
    lines.append("")
    lines.append(pal.dim(strings.t("not_a_verdict")))
    return lines


def format_text_report(
    result: ScanResult, pal: Palette, full: bool = False, quiet: bool = False
) -> str:
    """Render the human-readable inventory."""
    lines = _report_header(result, pal, quiet)
    if not result.has_findings:
        return "\n".join(lines + _empty_inventory_lines(result, pal, quiet))

    lines.extend(_summary_lines(result, pal))
    lines.append("")
    lines.extend(_render_section(pal, "cat_text", result.texts, _render_text, full))
    lines.extend(_render_section(pal, "cat_driver", result.drivers, _render_driver))
    lines.extend(_render_section(pal, "cat_osl", result.osl_nodes, _render_osl))
    lines.extend(_render_section(pal, "cat_library", result.libraries, _render_library))
    if not quiet:
        lines.extend(_render_paths(result, pal))

    if result.warnings:
        lines.append(_rule(pal, "Warnings"))
        lines.extend("  " + pal.notable(printable_line(w)) for w in result.warnings)

    lines.append("")
    lines.extend(_recommendation_block(result, pal))
    lines.append("")
    lines.append(pal.dim(strings.t("not_a_verdict")))
    return "\n".join(lines)


def _recommendation_block(result: ScanResult, pal: Palette) -> list[str]:
    out = [_rule(pal, strings.t("recommend_header"))]
    out.extend("  " + pal.for_severity(sev, text) for text, sev in recommendation_lines(result))
    return out


def _render_paths(result: ScanResult, pal: Palette) -> list[str]:
    if not result.filepaths:
        return []
    out = [_rule(pal, strings.t("cat_filepath"))]
    out.append("  " + pal.dim(strings.t("filepath_informational")))
    for item in result.filepaths:
        out.append("  " + strings.t("filepath_title", kind=item.kind, name=item.name))
        out.append("  " + strings.t("filepath_value", path=item.path))
    return out


def format_json(results: list[ScanResult], errors: list[dict[str, Any]]) -> str:
    """Render the JSON output.

    ``schema``, every ``key``, every ``severity`` and every identifier stay
    stable across languages -- that is what makes this machine-parseable. The
    human-readable ``text``/``message`` fields do vary with the active
    language, so ``lang`` is included at the top level rather than leaving a
    consumer to guess which language produced them.

    ``banner`` is attached here rather than inside
    :meth:`blend_xray.models.ScanResult.to_dict` because the banner is a view
    of a result, not part of it: the models layer stays free of presentation
    decisions, and nothing in it needs to import the tier logic.

    ``version`` is the tool's, not the schema's -- the two move independently,
    which is why both are here. A stored report that cannot say which build
    produced it cannot be compared with a later one, and a bug report quoting
    JSON output should not need a separate question to establish the build.
    """
    files = []
    for result in results:
        entry = result.to_dict()
        entry["banner"] = banner.for_result(result).to_dict()
        files.append(entry)
    payload = {
        "tool": strings.t("tool_name"),
        "version": __version__,
        "schema": 1,
        "lang": strings.current_language(),
        "files": files,
        "errors": errors,
    }
    # ensure_ascii=True (the default): non-ASCII text -- French accents in
    # particular -- is escaped as \uXXXX rather than written as raw UTF-8
    # bytes. That keeps the JSON valid no matter what encoding the output
    # stream ends up using; on Windows sys.stdout defaults to the console's
    # codepage (cp1252, not UTF-8), and printing raw accented characters
    # through it silently produced a mis-encoded, unparseable payload.
    return json.dumps(payload, indent=2)


def make_palette(
    stream: TextIO | None = None, force: bool | None = None, ascii_only: bool | None = None
) -> Palette:
    return Palette(stream or sys.stdout, force, ascii_only)
