# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for the multilingual string catalogue itself.

These protect the two properties the whole module exists for:

1. A translation gap must degrade gracefully to English, never to a raised
   exception or a raw ``key`` printed at the user.
2. A translated template must keep exactly the format placeholders the
   English original has. A ``{count}`` that becomes ``{nombre}`` in French
   would raise ``KeyError`` the moment a real finding tries to fill it in --
   that must fail here, in CI, not in front of a user.
"""

from __future__ import annotations

import locale
import string

import pytest

from blend_xray import strings


def _placeholders(template: str) -> set[str]:
    """Field names a ``str.format`` template consumes, ignoring literal text."""
    return {field_name for _, field_name, _, _ in string.Formatter().parse(template) if field_name}


# -- every English key resolves everywhere -----------------------------------
def test_every_english_key_resolves_in_every_language() -> None:
    en = strings.CATALOGUE[strings.DEFAULT_LANGUAGE]
    for lang, table in strings.CATALOGUE.items():
        for key in en:
            resolved = table.get(key) or en.get(key)
            assert resolved, f"{lang}:{key} does not resolve to anything"
            assert not resolved.startswith("!["), f"{lang}:{key} leaked a raw key"


def test_t_falls_back_to_english_for_a_missing_translation(monkeypatch: pytest.MonkeyPatch) -> None:
    """Simulate an incomplete translation without editing the real catalogue."""
    incomplete = {k: v for k, v in strings.CATALOGUE["fr"].items() if k != "tool_tagline"}
    monkeypatch.setitem(strings.CATALOGUE, "fr", incomplete)
    strings.set_language("fr")
    assert strings.t("tool_tagline") == strings.CATALOGUE["en"]["tool_tagline"]


def test_t_never_raises_or_prints_a_bare_key() -> None:
    strings.set_language("fr")
    assert strings.t("this_key_does_not_exist_anywhere") == "![this_key_does_not_exist_anywhere]"


def test_unknown_language_falls_back_to_english() -> None:
    strings.set_language("de")
    assert strings.current_language() == strings.DEFAULT_LANGUAGE


# -- every translation keeps the English placeholders -------------------------
def test_translation_placeholders_match_english() -> None:
    en = strings.CATALOGUE[strings.DEFAULT_LANGUAGE]
    for lang, table in strings.CATALOGUE.items():
        if lang == strings.DEFAULT_LANGUAGE:
            continue
        for key, translated in table.items():
            assert key in en, f"{lang}:{key} is not a known English key"
            expected = _placeholders(en[key])
            actual = _placeholders(translated)
            assert actual == expected, (
                f"{lang}:{key} placeholders {sorted(actual)} do not match "
                f"english placeholders {sorted(expected)}"
            )


def test_formatting_a_translation_does_not_raise() -> None:
    """A concrete regression check backing the placeholder-parity test above."""
    strings.set_language("fr")
    assert "{" not in strings.t("scanned_n_files", count=3)
    assert "3" in strings.t("scanned_n_files", count=3)
    assert "SQBFAFgA" in strings.t("driver_expression", expr="SQBFAFgA")


# -- the words that must never ship, in any language --------------------------
def test_no_catalogue_entry_uses_a_banned_word() -> None:
    """Checked over the whole catalogue, not over a rendered sample.

    ``tests/test_scanner.py::test_report_never_says_safe`` renders a handful of
    fixtures and asserts on the output, which only reaches the strings those
    fixtures happen to trigger. A string added for a state no fixture produces
    -- a scan that timed out, a disguised library path -- would slip past it
    entirely. This is the version that cannot be outrun by new prose: it reads
    the catalogues themselves, so every key present or future is covered in
    both languages, including inside a negation.
    """
    from .conftest import BANNED_WORDS_BY_LANG

    for lang, table in strings.CATALOGUE.items():
        for key, template in table.items():
            lowered = template.lower()
            for word in BANNED_WORDS_BY_LANG[lang]:
                assert word not in lowered, f"{lang}:{key} says {word!r}: {template[:80]}"


def test_no_catalogue_entry_uses_a_tick_or_an_all_clear_mark() -> None:
    """No tick, no check mark, no "OK" symbol -- see blend_xray/banner.py."""
    for lang, table in strings.CATALOGUE.items():
        for key, template in table.items():
            for mark in ("✓", "✔", "✅", "[OK]", "[ok]"):
                assert mark not in template, f"{lang}:{key} carries {mark!r}"


# -- language selection --------------------------------------------------------
def test_set_language_selects_a_known_language() -> None:
    strings.set_language("fr")
    assert strings.current_language() == "fr"


def test_detect_language_prefers_locale_getlocale(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(locale, "getlocale", lambda: ("fr_FR", "cp1252"))
    assert strings.detect_language() == "fr"


def test_detect_language_handles_windows_style_locale_names(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(locale, "getlocale", lambda: ("French_France", "1252"))
    assert strings.detect_language() == "fr"


def test_detect_language_falls_back_to_lang_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(locale, "getlocale", lambda: (None, None))
    monkeypatch.setenv("LANG", "fr_FR.UTF-8")
    assert strings.detect_language() == "fr"


def test_detect_language_defaults_to_english(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(locale, "getlocale", lambda: (None, None))
    monkeypatch.delenv("LANG", raising=False)
    assert strings.detect_language() == strings.DEFAULT_LANGUAGE


def test_detect_language_ignores_an_unsupported_locale(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(locale, "getlocale", lambda: ("ja_JP", "utf-8"))
    monkeypatch.delenv("LANG", raising=False)
    assert strings.detect_language() == strings.DEFAULT_LANGUAGE
