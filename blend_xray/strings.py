# SPDX-License-Identifier: GPL-3.0-or-later
"""Language selection and lookup for every user-facing string in Blend X-Ray.

Rationale: the tool targets the international Blender community, so all prose
is centralised behind :func:`t` to make a French (or any other) translation a
data change rather than a code change.

The prose itself lives one module per language -- :mod:`blend_xray.strings_en`
and :mod:`blend_xray.strings_fr` -- because two full catalogues plus this
machinery in a single file had grown past this project's file-size ceiling.
Add a language by adding a module and one entry to :data:`CATALOGUE`; no other
module needs to change, and the per-language style rules are documented in
each catalogue module's docstring.

Style rules enforced in every language (see README):
  * We describe what code *does*, never whether it is safe.
  * There is deliberately no "SAFE", no "clean", no risk score, no percentage.
    In French: no "sûr", "sain", "propre" or "sans danger" either -- not even
    inside a negation, because a skimming reader picks up the word and drops
    the "not". Asserted by tests/test_scanner.py::test_report_never_says_safe.
  * When something is obfuscated we say we cannot tell, instead of guessing.
  * Blender's own on-screen UI labels ("Auto Run Python Scripts", "Register",
    "Preferences > Save & Load", ...) and code-level identifiers (TXT_ISSCRIPT,
    struct/flag/function names) are never translated: that is what the reader
    sees on screen or in their own script, so translating it would make the
    report harder to act on, not easier.

Language selection
-------------------
:func:`set_language` sets the active language for the process (unknown codes
fall back to English). :func:`detect_language` makes a best-effort guess from
the OS locale (``locale.getlocale()``, then the POSIX ``LANG`` environment
variable), landing on English when neither yields a language we ship. The CLI
calls :func:`detect_language` first and then lets an explicit ``--lang``
always override it -- see :mod:`blend_xray.cli`.
"""

from __future__ import annotations

import locale
import os
import re
from typing import Final

from .sanitise import printable_line
from .strings_en import EN as _EN
from .strings_fr import FR as _FR

DEFAULT_LANGUAGE: Final = "en"

CATALOGUE: Final[dict[str, dict[str, str]]] = {"en": _EN, "fr": _FR}

#: Language codes the CLI's ``--lang`` flag accepts, in catalogue order.
SUPPORTED_LANGUAGES: Final[tuple[str, ...]] = tuple(CATALOGUE)

_current_language = DEFAULT_LANGUAGE

#: OS-locale spellings that do not match an ISO 639-1 code by simple
#: truncation (chiefly Windows' verbose locale names, e.g. "French_France").
_LANGUAGE_ALIASES: Final[dict[str, str]] = {
    "french": "fr",
    "francais": "fr",
    "english": "en",
}


def set_language(language: str) -> None:
    """Select the active language; unknown languages fall back to English."""
    global _current_language
    _current_language = language if language in CATALOGUE else DEFAULT_LANGUAGE


def current_language() -> str:
    return _current_language


def _normalise_locale(value: str | None) -> str | None:
    """Turn 'fr_FR.UTF-8', 'fr-FR' or the Windows-style 'French_France' into 'fr'."""
    if not value:
        return None
    token = re.split(r"[._-]", value.strip().lower())[0]
    return _LANGUAGE_ALIASES.get(token, token) or None


def detect_language() -> str:
    """Best-effort language guess from the OS locale; English is the final fallback.

    Tries :func:`locale.getlocale` first (what a correctly configured OS
    reports), then the POSIX ``LANG`` environment variable, then gives up and
    returns English. Never raises. A command-line ``--lang`` always wins over
    whatever this returns -- see :func:`blend_xray.cli.run`.
    """
    try:
        candidate = locale.getlocale()[0]
    except (ValueError, TypeError):
        candidate = None
    for raw in (candidate, os.environ.get("LANG")):
        code = _normalise_locale(raw)
        if code in CATALOGUE:
            return code
    return DEFAULT_LANGUAGE


def t(key: str, **kwargs: object) -> str:
    """Look up ``key`` in the active catalogue and format it.

    A missing key returns ``![key]`` rather than raising: a translation gap
    must never crash a security tool mid-report.

    **Every interpolated string value is sanitised here**, and this is the
    reason it happens here rather than at each call site. The templates are
    ours and are trusted; the values filled into them are the part that came
    out of a hostile .blend file -- a datablock name, a library path, a driver
    expression, a parser's account of what went wrong. Doing it at the one
    place where untrusted data meets trusted prose means a field added to the
    report next year is covered without anyone remembering to cover it. See
    :mod:`blend_xray.sanitise` for what is escaped and why nothing is deleted.

    Non-string values (counts, sizes, limits) pass through untouched so that
    ``{count}`` and ``{limit:.1f}`` still format as numbers.
    """
    table = CATALOGUE.get(_current_language, _EN)
    template = table.get(key) or _EN.get(key)
    if template is None:
        return f"![{key}]"
    if not kwargs:
        return template
    safe = {
        name: printable_line(value) if isinstance(value, str) else value
        for name, value in kwargs.items()
    }
    try:
        return template.format(**safe)
    except (KeyError, IndexError, ValueError):
        return template
