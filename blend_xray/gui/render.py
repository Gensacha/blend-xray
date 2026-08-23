# SPDX-License-Identifier: GPL-3.0-or-later
"""Turn a :class:`~blend_xray.models.ScanResult` into drawable elements.

Same content, same wording and the same per-block order as the CLI report in
:mod:`blend_xray.report`: **plain-language explanation first, then the
extracted literals, then the raw source last**. Source that nobody in the room
can read is the least useful thing on screen, so it never leads -- and in the
window it starts collapsed on top of that.

Two differences from the CLI, both deliberate:

* The closing **Recommendation** is drawn near the top rather than at the
  bottom. It is the part that turns a finding into an action, and in a
  scrollable window the bottom of a long report is where things go to be
  ignored. Nothing else is reordered.
* The raw source is not previewed-and-cut at 1500 characters, because the
  reader can collapse it instead. The scanner's own byte budget still applies.

This module deliberately imports nothing from tkinter: it produces plain data,
which is what makes both the copy-to-clipboard text and the tests possible.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from .. import banner, report, strings, truncation
from ..banner import Tier
from ..explain import Explanation, Severity
from ..identity import IdentityMatch
from ..models import (
    CATEGORY_STRING_KEYS,
    ERROR_STRING_KEYS,
    DriverFinding,
    LibraryFinding,
    OSLFinding,
    ScanResult,
    TextFinding,
)
from ..sanitise import printable_block, printable_line
from .theme import (
    TAG_ALARM,
    TAG_BODY,
    TAG_DIM,
    TAG_HEADING,
    TAG_NOTABLE,
    TAG_STRONG,
    TAG_TITLE,
)

#: Two spaces per indent level, matching the CLI's shape.
INDENT = "  "


@dataclasses.dataclass(frozen=True)
class Line:
    """One line of prose, drawn with the colour its tag names."""

    text: str
    tag: str = TAG_BODY
    indent: int = 0

    def rendered(self) -> str:
        return INDENT * self.indent + self.text


@dataclasses.dataclass(frozen=True)
class Source:
    """A raw script body. Drawn collapsed behind a toggle, always last."""

    body: str
    indent: int = 1


@dataclasses.dataclass(frozen=True)
class Separator:
    """A section break the *widget* draws, carrying no text of its own.

    The window used to rule its sections with a fixed run of dashes, which is
    what a terminal does and what a proportional font makes a mess of: the
    line stops somewhere in the middle of the window and moves when the font
    or the window size changes. That is the same reason the CLI's ASCII box is
    not drawn here (see the module docstring); the rule had simply outlived
    the reasoning.

    It carries no text so that the clipboard copy stays prose: the bold
    heading above it already names the section.
    """


Element = Line | Source | Separator

_SEVERITY_TAGS = {
    Severity.ALARMING: TAG_ALARM,
    Severity.NOTABLE: TAG_NOTABLE,
    Severity.BENIGN: TAG_DIM,
}


def plain_text(elements: list[Element]) -> str:
    """Flatten to plain text for the clipboard, with every source expanded.

    Someone pasting this into a message to a friend who reads Python wants the
    code, not a note saying it was collapsed.
    """
    out: list[str] = []
    for element in elements:
        if isinstance(element, Source):
            prefix = INDENT * element.indent
            out.extend(prefix + line for line in element.body.splitlines())
            continue
        if isinstance(element, Separator):
            continue
        out.append(element.rendered())
    return "\n".join(out)


def _rule(title: str) -> list[Element]:
    """A blank line, the section name, and a rule the widget sizes itself."""
    return [Line(""), Line(title, TAG_HEADING), Separator()]


def render_error(path: Path | str, kind: str, message: str) -> list[Element]:
    """One file that could not be read at all.

    The title carries the path through the sanitiser for the same reason
    :func:`render_result` does, and this is the surface that needs it more: a
    file that fails to parse is exactly the file whose *name* an attacker
    controls and whose contents never got far enough to be shown. A filename
    is allowed to contain U+202E on every filesystem this tool runs on, and
    without this the window and its clipboard would render a reversed name as
    a plain title.
    """
    key = ERROR_STRING_KEYS.get(kind, "err_unreadable")
    return [
        Line(printable_line(path), TAG_TITLE),
        Line(strings.t("gui_error_header"), TAG_ALARM, indent=1),
        Line(strings.t(key, path=str(path), reason=message), TAG_ALARM, indent=1),
        Line(""),
    ]


def _banner(result: ScanResult) -> list[Element]:
    """The at-a-glance header, drawn before anything else in the window.

    The CLI draws this in an ASCII box because a terminal has one font; here
    the tier is carried by the marker and the colour instead, since a box
    ruled in a proportional font lines up with nothing. The words, the tier
    and the reasons are the same object either way --
    :func:`blend_xray.banner.for_result` -- so the two surfaces cannot
    disagree about what a file is showing.

    The neutral tier is TAG_DIM. It is never green and never a tick: see the
    reasoning at the top of :mod:`blend_xray.banner`.
    """
    info = banner.for_result(result)
    tag = _SEVERITY_TAGS[info.severity]
    out: list[Element] = [Line(f"{report.tier_marker(info.tier)} {info.headline()}", tag)]
    detail = info.detail()
    if detail:
        out.append(Line(detail, tag, indent=1))
    note_tag = TAG_DIM if info.tier is Tier.NEUTRAL else TAG_NOTABLE
    out.extend(Line(note, note_tag, indent=1) for note in info.notes())
    out.append(Line(""))
    return out


def render_result(result: ScanResult) -> list[Element]:
    """The whole inventory for one file."""
    out: list[Element] = [
        *_banner(result),
        Line(f"{strings.t('tool_name')} -- {printable_line(result.path)}", TAG_TITLE),
        Line(report.file_meta_line(result), TAG_DIM),
        Line(strings.t("never_runs"), TAG_DIM),
        Line(""),
    ]
    # Directly under the banner and above the recommendation: the window is
    # scrollable, and a caveat about how much of the file was read is worth
    # nothing further down than the thing it qualifies.
    if result.timed_out:
        out.append(Line(truncation.notice(result), TAG_ALARM))
        out.append(Line(""))
    out.extend(_recommendation(result))
    out.append(Line(""))
    out.append(
        Line(strings.t("categories_checked_header", count=len(result.categories_checked)))
    )
    out.extend(
        Line("- " + strings.t(CATEGORY_STRING_KEYS[cat]), TAG_BODY, indent=1)
        for cat in result.categories_checked
    )
    out.append(Line(""))

    if not result.has_findings:
        # No "nothing found" paragraph here: _recommendation() drew it a few
        # lines above, under the same condition. See the reasoning in
        # tests/test_gui.py::test_nothing_found_is_said_exactly_once_in_the_window.
        out.extend(_paths(result))
        out.append(Line(""))
        out.append(Line(strings.t("not_a_verdict"), TAG_DIM))
        return out

    out.extend(_summary(result))
    out.extend(_section("cat_text", result.texts, _text_finding))
    out.extend(_section("cat_driver", result.drivers, _driver))
    out.extend(_section("cat_osl", result.osl_nodes, _osl))
    out.extend(_section("cat_library", result.libraries, _library))
    out.extend(_paths(result))
    out.extend(_warnings(result))
    out.append(Line(""))
    out.append(Line(strings.t("not_a_verdict"), TAG_DIM))
    return out


def _recommendation(result: ScanResult) -> list[Element]:
    """The block that turns a finding into a next action. Never a clearance.

    The decision itself lives in :func:`blend_xray.report.recommendation_lines`
    and is shared with the CLI. It used to be reimplemented here, and the two
    copies had already drifted; a window that escalates a file the command line
    does not is a bug the user cannot even see, so there is now one branch.
    """
    out = _rule(strings.t("recommend_header"))
    if not result.has_findings and not result.timed_out:
        out.append(Line(strings.t("nothing_found"), TAG_STRONG, indent=1))
        return out
    out.extend(
        Line(text, _SEVERITY_TAGS[severity], indent=1)
        for text, severity in report.recommendation_lines(result)
    )
    return out


def _summary(result: ScanResult) -> list[Element]:
    """Group code blocks by what they do, spotlighting the ones that matter."""
    if not result.texts:
        return []
    groups: dict[tuple[str, bool], int] = {}
    for finding in result.texts:
        key = report.headline_for(finding.explanation)
        groups[key] = groups.get(key, 0) + 1

    out: list[Element] = [Line(strings.t("summary_blocks_found", count=len(result.texts)), TAG_STRONG)]
    for (description, spotlight), count in sorted(
        groups.items(), key=lambda kv: (not kv[0][1], -kv[1])
    ):
        marker = strings.t("summary_look_at_this") if spotlight else ""
        text = strings.t("summary_line", count=count, description=description, marker=marker)
        out.append(Line(text.rstrip(), TAG_ALARM if spotlight else TAG_BODY))
    return out


def _section(
    title_key: str, items: Sequence[Any], renderer: Callable[[Any], list[Element]]
) -> list[Element]:
    if not items:
        return []
    out = _rule(strings.t(title_key))
    for item in items:
        out.extend(renderer(item))
        out.append(Line(""))
    return out


def _text_finding(finding: TextFinding) -> list[Element]:
    out: list[Element] = [Line(strings.t("text_block_title", name=finding.name), TAG_STRONG)]
    if finding.is_autorun:
        out.append(Line(strings.t("text_autorun_flag"), TAG_ALARM, indent=1))
    else:
        out.append(Line(strings.t("text_not_autorun"), TAG_DIM, indent=1))
    flags = ", ".join(finding.flag_names) or "-"
    out.append(Line(strings.t("text_flags", flags=flags), TAG_DIM, indent=1))
    if finding.filepath:
        out.append(Line(strings.t("text_filepath", path=finding.filepath), TAG_BODY, indent=1))
    if finding.is_memory:
        out.append(Line(strings.t("text_is_mem"), TAG_DIM, indent=1))
    if finding.is_external:
        out.append(Line(strings.t("text_is_ext"), TAG_DIM, indent=1))

    if finding.identity is not None:
        out.extend(_identity(finding.identity))

    if finding.explanation is not None:
        out.extend(_explanation(finding.explanation))

    out.append(Line(strings.t("text_source_header"), TAG_STRONG, indent=1))
    out.append(Line(strings.t("gui_source_hint"), TAG_DIM, indent=1))
    if finding.truncated:
        out.append(Line(strings.t("gui_source_capped"), TAG_NOTABLE, indent=1))
    # Sanitised here for the same reason the CLI sanitises it: the window
    # copies to the clipboard, and a clipboard paste lands in somebody's
    # terminal. See blend_xray/sanitise.py.
    body = printable_block(finding.source) if finding.source.strip() else strings.t("text_empty")
    out.append(Source(body))
    return out


def _identity(match: IdentityMatch) -> list[Element]:
    """What the block was recognised as. Same wording as the CLI, same order."""
    out: list[Element] = [Line(strings.t("identity_header"), TAG_STRONG, indent=1)]
    out.extend(
        Line(text, _SEVERITY_TAGS[severity], indent=2)
        for text, severity in report.identity_lines(match)
    )
    return out


def _explanation(exp: Explanation) -> list[Element]:
    out: list[Element] = []
    if exp.note:
        out.append(Line(printable_line(exp.note), TAG_NOTABLE, indent=1))
    if not exp.parsed and exp.parse_error:
        out.append(
            Line(strings.t("explain_unparseable", reason=exp.parse_error), TAG_NOTABLE, indent=1)
        )
    if exp.obfuscated and not exp.statements:
        out.append(Line(strings.t("explain_obfuscated_honest"), TAG_ALARM, indent=1))

    if exp.statements:
        out.append(Line(strings.t("explain_header"), TAG_STRONG, indent=1))
        for st in exp.statements:
            out.append(Line(f"* {printable_line(st.text)}", _SEVERITY_TAGS[st.severity], indent=2))
            if st.evidence:
                evidence = strings.t("explain_evidence", evidence=", ".join(st.evidence))
                out.append(Line(evidence, TAG_DIM, indent=3))
    elif exp.parsed:
        out.append(Line(strings.t("explain_nothing_notable"), TAG_DIM, indent=1))

    if exp.obfuscated and exp.statements:
        out.append(Line(strings.t("explain_obfuscated_partial"), TAG_ALARM, indent=1))
    out.extend(_literals(exp))
    out.append(Line(strings.t("explain_baseline"), TAG_DIM, indent=1))
    return out


def _literals(exp: Explanation) -> list[Element]:
    if not exp.literals:
        return [Line(strings.t("explain_no_literals"), TAG_DIM, indent=1)]
    out: list[Element] = [Line(strings.t("explain_literals_header"), TAG_STRONG, indent=1)]
    for lit in exp.literals:
        label = strings.t(f"lit_{lit.kind}")
        out.append(Line(f"[{label}] {report.show_literal(lit.value)}", TAG_NOTABLE, indent=2))
    return out


def _driver(finding: DriverFinding) -> list[Element]:
    out: list[Element] = [Line(strings.t("driver_title", owner=finding.owner), TAG_STRONG)]
    out.append(Line(strings.t("driver_type", type_name=finding.driver_type_name), indent=1))
    out.append(Line(strings.t("driver_expression", expr=finding.expression), indent=1))
    if not finding.expression_is_evaluated:
        # Blender never reads this field for this driver type, so neither
        # "runs without Python" nor "needs full Python" is true of it.
        key = "driver_expression_unused"
        out.append(Line(strings.t(key, type_name=finding.driver_type_name), TAG_DIM, indent=1))
        return _driver_flags(finding, out)
    if finding.is_simple:
        out.append(Line(strings.t("driver_simple"), TAG_DIM, indent=1))
    else:
        out.append(Line(strings.t("driver_suspicious"), TAG_NOTABLE, indent=1))
    out.append(Line(printable_line(f"({finding.classification_reason})"), TAG_DIM, indent=1))
    exp = finding.explanation
    if exp is not None and exp.statements:
        out.append(Line(strings.t("explain_header"), TAG_STRONG, indent=1))
        for st in exp.statements:
            out.append(Line(printable_line(st.text), _SEVERITY_TAGS[st.severity], indent=2))
    return _driver_flags(finding, out)


def _driver_flags(finding: DriverFinding, out: list[Element]) -> list[Element]:
    if finding.flag_names:
        flags = ", ".join(finding.flag_names)
        out.append(Line(strings.t("driver_flags", flags=flags), TAG_DIM, indent=1))
    return out


def _osl(finding: OSLFinding) -> list[Element]:
    out: list[Element] = [Line(strings.t("osl_title", owner=finding.owner), TAG_STRONG)]
    out.append(Line(strings.t("osl_external" if finding.mode else "osl_internal"), indent=1))
    if finding.filepath:
        out.append(Line(strings.t("osl_filepath", path=finding.filepath), indent=1))
    if finding.bytecode_bytes:
        out.append(
            Line(strings.t("osl_has_bytecode", size=finding.bytecode_bytes), TAG_NOTABLE, indent=1)
        )
    if finding.bytecode_hash:
        out.append(
            Line(strings.t("osl_bytecode_hash", hash=finding.bytecode_hash), TAG_DIM, indent=1)
        )
    out.append(Line(strings.t("osl_lower_severity"), TAG_DIM, indent=1))
    return out


def _library(finding: LibraryFinding) -> list[Element]:
    out: list[Element] = [Line(strings.t("library_title", path=finding.raw_path), TAG_STRONG)]
    if finding.disguised:
        out.append(Line(strings.t("library_disguised"), TAG_ALARM, indent=1))
    if finding.is_unc:
        out.append(Line(strings.t("library_unc", host=finding.unc_host or "?"), TAG_ALARM, indent=1))
    if finding.has_drive_letter:
        out.append(Line(strings.t("library_drive"), TAG_ALARM, indent=1))
    resolved = finding.resolved_path or "?"
    if finding.escapes_folder:
        out.append(Line(strings.t("library_escapes", resolved=resolved), TAG_ALARM, indent=1))
    elif finding.is_absolute:
        key = "library_absolute_inside" if finding.absolute_inside_blend_dir else "library_absolute"
        out.append(Line(strings.t(key), TAG_ALARM, indent=1))
    elif finding.is_relative:
        out.append(Line(strings.t("library_relative", resolved=resolved), TAG_DIM, indent=1))
        out.append(Line(strings.t("library_ok_relative"), TAG_DIM, indent=1))
    return out


def _paths(result: ScanResult) -> list[Element]:
    if not result.filepaths:
        return []
    out = _rule(strings.t("cat_filepath"))
    out.append(Line(strings.t("filepath_informational"), TAG_DIM, indent=1))
    for item in result.filepaths:
        out.append(Line(strings.t("filepath_title", kind=item.kind, name=item.name), indent=1))
        out.append(Line(strings.t("filepath_value", path=item.path), TAG_DIM, indent=1))
    return out


def _warnings(result: ScanResult) -> list[Element]:
    if not result.warnings:
        return []
    out = _rule(strings.t("warnings_header"))
    out.extend(Line(printable_line(w), TAG_NOTABLE, indent=1) for w in result.warnings)
    return out
