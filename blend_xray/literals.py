# SPDX-License-Identifier: GPL-3.0-or-later
"""Classify the string literals a script carries, so a reader can judge them.

Split out of :mod:`blend_xray.explain` to keep the rule-application module to
one job. This one answers a narrower question: given a piece of text that
appeared as a literal, is it a URL, a host name, a shell command, a file path
or an opaque blob -- and nothing about what the surrounding code does with it.

Re-exported from :mod:`blend_xray.explain`, which stays the public face of the
analysis layer.
"""

from __future__ import annotations

import dataclasses
import re
from typing import Final, Protocol

from .explain_rules import FILE_EXTENSION_BLOCKLIST, KNOWN_TLDS, LIVING_OFF_LAND

#: How often the literal sweep polls the caller's wall-clock budget. The
#: sweep is a Python-level loop over every string in a script and is by far
#: the most expensive thing the analysis does on a hostile body: 2 MiB of
#: quoted tokens is a quarter of a million candidates and most of a second.
#: Leaving it unbounded is what let a file overrun --max-seconds many times
#: over even once every other stage was bounded.
LITERAL_SWEEP_POLL: Final = 4096
#: A run of encoded-looking characters at least this long is called out.
OPAQUE_BLOB_MIN: Final = 200

_URL_RE: Final = re.compile(r"(?:https?|ftps?|file)://[^\s'\"<>|]{3,}", re.IGNORECASE)
_HOST_RE: Final = re.compile(r"^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?(?:\.[a-z0-9-]+)+$", re.IGNORECASE)
_BASE64ISH_RE: Final = re.compile(r"^[A-Za-z0-9+/=_-]+$")
_HEXISH_RE: Final = re.compile(r"^(?:0x)?[0-9a-fA-F]+$")
_WINDOWS_ABS_RE: Final = re.compile(r"^[a-zA-Z]:[\\/]")


class Budget(Protocol):
    """The one thing this needs from a deadline: has it run out.

    A structural type rather than an import of
    :class:`blend_xray.guards.Deadline`, so the analysis layer stays
    independent of the parser-hardening layer and a test can pass a two-line
    stub.
    """

    @property
    def expired(self) -> bool: ...


@dataclasses.dataclass(frozen=True)
class Literal:
    kind: str
    value: str


def looks_like_path(text: str) -> bool:
    if len(text) > 400 or "\n" in text:
        return False
    if _WINDOWS_ABS_RE.match(text) or text.startswith(("\\\\", "~/", "~\\", "//")):
        return True
    if "%" in text and re.search(r"%[A-Za-z_]+%", text):
        return True
    # A bare "$", or a "$" sitting in prose, is not a path -- require a variable name.
    if re.match(r"\$\{?\w", text) or "$HOME" in text or "$env:" in text.lower():
        return True
    if ("/" in text or "\\" in text) and not text.startswith(("http", "ftp")):
        if not re.search(r"[\w.-]+[\\/][\w.-]", text):
            return False
        # UI prose trips the pattern above ("bones selected/assigned"). When the
        # candidate contains whitespace, demand a real path anchor: a leading
        # separator, or an extension on the final segment.
        if " " in text or "\t" in text:
            return bool(
                text.startswith(("/", "\\", "./", ".\\"))
                or re.search(r"[\\/][\w -]+\.[A-Za-z0-9]{1,8}$", text)
            )
        return True
    return False


def looks_like_host(text: str) -> bool:
    """Bare dotted strings are only hosts when the last label is a real TLD.

    Without the allow-list, literals like ``rig.snap`` or ``out.bin`` get
    reported as network hosts. Hosts inside full URLs are matched by
    :data:`_URL_RE` and do not depend on this check.
    """
    if not _HOST_RE.match(text) or len(text) > 253:
        return False
    suffix = text.rsplit(".", 1)[-1].lower()
    if suffix in FILE_EXTENSION_BLOCKLIST or not suffix.isalpha():
        return False
    return suffix in KNOWN_TLDS


def looks_like_command(text: str) -> bool:
    low = text.lower()
    return any(tool in low for tool in LIVING_OFF_LAND)


def is_opaque_blob(text: str) -> bool:
    if len(text) < OPAQUE_BLOB_MIN or any(c.isspace() for c in text):
        return False
    return bool(_BASE64ISH_RE.match(text) or _HEXISH_RE.match(text))


def extract_literals(
    candidates: list[str], *, bare_tokens: bool = False, deadline: Budget | None = None
) -> tuple[list[Literal], list[str]]:
    """Classify every string literal the user could plausibly judge for themselves.

    ``bare_tokens`` marks the unparsed path, where the candidates are raw source
    fragments rather than real string literals and some classifications cannot
    be trusted -- see the hostname note below.

    ``deadline`` stops the sweep when the caller's budget is spent. The result
    is then incomplete by construction, which is why the scanner checks the
    same deadline afterwards and discards the block rather than reporting a
    half-swept body as though the sweep had finished -- see
    :func:`blend_xray.scanner._read_text_block`.
    """
    found: list[Literal] = []
    blobs: list[str] = []
    seen: set[tuple[str, str]] = set()

    def push(kind: str, value: str) -> None:
        key = (kind, value)
        if key not in seen:
            seen.add(key)
            found.append(Literal(kind, value))

    for index, text in enumerate(candidates):
        if deadline is not None and index % LITERAL_SWEEP_POLL == 0 and deadline.expired:
            break
        if not text or len(text) > 4096:
            continue
        for url in _URL_RE.findall(text):
            push("url", url)
        stripped = text.strip()
        if is_opaque_blob(stripped):
            blobs.append(stripped)
            push("blob", stripped)
            continue
        if looks_like_command(stripped):
            push("command", stripped)
        # Without an AST we are looking at raw source tokens, where `self.co` is
        # an attribute access that looks exactly like a hostname (`.co` is a real
        # TLD). Only a parse can tell the two apart, so bare-token mode does not
        # guess: a wrong claim costs more here than a missed one, because the
        # user cannot check it.
        if not bare_tokens and looks_like_host(stripped):
            push("host", stripped)
        elif looks_like_path(stripped):
            push("path", stripped)

    order = {"url": 0, "host": 1, "command": 2, "path": 3, "blob": 4}
    found.sort(key=lambda lit: (order.get(lit.kind, 9), lit.value))
    return found, blobs
