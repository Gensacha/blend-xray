# SPDX-License-Identifier: GPL-3.0-or-later
"""Shared fixtures.

``blend_xray.strings`` keeps the active language as module-global state, and
``strings.detect_language()`` reads the real OS locale. Both would otherwise
leak between tests and make results depend on the machine running them --
this development machine's OS locale is French (``locale.getlocale()``
returns ``fr_FR`` even with no explicit ``setlocale()`` call), which would
silently flip every existing English-language assertion in the suite. This
fixture pins the language to English and neutralises OS-locale detection
before and after every test; tests that specifically exercise French or
detection set their own state explicitly within the test.
"""

from __future__ import annotations

import locale

import pytest

from blend_xray import strings

#: Words that must never reach a user, in any language and any surface --
#: not even inside a negation, because a skimming reader picks up the word and
#: drops the "not". Lives here rather than in one test module so the report
#: assertion and the GUI assertion cannot drift apart. French list: "sûr",
#: "sain", "propre" and "sans danger" are the direct equivalents of "safe";
#: "clean" is covered by "propre" too.
BANNED_WORDS_BY_LANG: dict[str, tuple[str, ...]] = {
    "en": ("safe", "clean", "no threat", "verdict:", "100%"),
    "fr": ("sûr", "sain", "propre", "sans danger"),
}


@pytest.fixture(autouse=True)
def _english_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LANG", raising=False)
    monkeypatch.delenv("LC_ALL", raising=False)
    monkeypatch.setattr(locale, "getlocale", lambda: (None, None))
    strings.set_language(strings.DEFAULT_LANGUAGE)
    yield
    strings.set_language(strings.DEFAULT_LANGUAGE)
