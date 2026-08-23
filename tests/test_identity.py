# SPDX-License-Identifier: GPL-3.0-or-later
"""The known-good identity layer: what a match adds, and what it must never do.

The properties under test here are the ones that make this layer defensible
rather than dangerous:

* a match **adds** identity context and never removes, hides or downgrades a
  finding;
* a **byte** match may keep a block out of the "needs a human" branch, and only
  when the entry describes a shared release rather than a per-file generated
  script;
* a **structural** match never stands anything down, and must name the string
  literals that differ -- an injected URL has to end up on screen, not be
  absorbed by the match that recognised the surrounding code;
* a missing, corrupt or half-broken database costs identity context and
  nothing else. The scan still runs and the report still renders.
"""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from blend_xray import identity, report, scanner, strings
from blend_xray.structure import STRUCTURE_SCHEME, structure_of

from .blend_builder import BlendBuilder
from .conftest import BANNED_WORDS_BY_LANG

# A stand-in for CloudRig: legitimate, published, and it really does call eval()
# on data stored in the file. This is the shape the whole layer exists for.
RELEASE_SCRIPT = """
import bpy


class RIG_PT_panel(bpy.types.Panel):
    bl_label = "Rig"

    def draw(self, context):
        info = context.object.data["op_info"]
        if isinstance(info, str):
            info = eval(info)
        self.layout.operator(info["bl_idname"])
"""

# A stand-in for Rigify's rig_ui.py: identical in every copy except the per-rig
# identifier baked into the string literals, which is what defeats a byte hash.
GENERATED_TEMPLATE = '''
import bpy

rig_id = "{rig_id}"
HOME = "{home}"


class RIG_PT_ui(bpy.types.Panel):
    bl_idname = "VIEW3D_PT_rig_ui_" + rig_id

    def draw(self, context):
        names = context.object.data["bone_names"]
        self.layout.label(text=eval(names)[0])
'''

REFERENCE_RIG_ID = "v3sz3700a4d33376"
REFERENCE_HOME = "//textures/"

ORDINARY_SCRIPT = """
import bpy

bpy.context.scene.frame_start = 1
"""


def as_extracted(body: str) -> str:
    """The body as the scanner will read it back out of a .blend -- unchanged.

    This used to strip blank lines, because ``scanner._read_text_lines`` did.
    That was the defect: the tool hashed a reconstruction rather than the
    file's real content, so nobody re-hashing the extracted block could
    reproduce a recorded digest. The round trip is lossless now, and
    ``tests/test_extraction.py`` is what holds it that way, so this is
    deliberately the identity function rather than a deleted call -- it names
    the guarantee at every site that depends on it.
    """
    return body


def _entry(source: str, name: str, **overrides: object) -> dict:
    body = as_extracted(source)
    entry = {
        "sha256": identity.sha256_of(body),
        "script_name": name,
        "byte_size": len(body.encode("utf-8")),
        "origin": "Example Rig, Example Studio, release 2.1",
        "source_url": "https://example.invalid/rigs/example-2.1.zip",
        "fetched_on": "2026-08-23",
        "attested_by": "test fixture (single attester)",
        "attested_on": "2026-08-23",
        "notes": "Draws a rig panel; calls eval() on a custom property to pick an operator.",
        "generated": False,
    }
    entry.update(overrides)
    return entry


def _structural_entry(source: str, name: str) -> dict:
    shape = structure_of(as_extracted(source))
    assert shape is not None
    return _entry(
        source,
        name,
        generated=True,
        structure={
            "scheme": STRUCTURE_SCHEME,
            "sha256": shape.sha256,
            "literals": list(shape.literals),
        },
    )


def _reference_generated() -> str:
    return GENERATED_TEMPLATE.format(rig_id=REFERENCE_RIG_ID, home=REFERENCE_HOME)


@pytest.fixture
def database(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A two-entry database: one shared release, one generated script."""
    path = tmp_path / "known_scripts.json"
    payload = {
        "schema": identity.SCHEMA_VERSION,
        "entries": [
            _entry(RELEASE_SCRIPT, "rig_panel.py"),
            _structural_entry(_reference_generated(), "rig_ui.py"),
        ],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(identity, "DATABASE_PATH", path)
    identity.clear_cache()
    yield path
    identity.clear_cache()


def _blend_with(tmp_path: Path, name: str, body: str) -> Path:
    builder = BlendBuilder()
    builder.add_text(name, body, flags=1 | 4 | 16)  # TXT_ISSCRIPT
    path = tmp_path / f"{name}.blend"
    path.write_bytes(builder.to_bytes())
    return path


def _render(path: Path) -> str:
    pal = report.make_palette(io.StringIO(), force=False)
    return report.format_text_report(scanner.scan_file(path), pal)


# -- byte-identical match -----------------------------------------------------
def test_byte_match_names_the_script_and_its_origin(tmp_path: Path, database: Path) -> None:
    result = scanner.scan_file(_blend_with(tmp_path, "rig_panel.py", RELEASE_SCRIPT))
    match = result.texts[0].identity
    assert match is not None
    assert match.evidence == identity.EVIDENCE_BYTE
    assert match.entry.origin == "Example Rig, Example Studio, release 2.1"

    text = _render(tmp_path / "rig_panel.py.blend")
    assert "Example Rig, Example Studio, release 2.1" in text
    assert "https://example.invalid/rigs/example-2.1.zip" in text
    assert "test fixture (single attester)" in text


def test_byte_match_keeps_every_finding_at_its_own_severity(
    tmp_path: Path, database: Path
) -> None:
    """The point of the layer: context is added, nothing is taken away."""
    blend = _blend_with(tmp_path, "rig_panel.py", RELEASE_SCRIPT)
    with_db = scanner.scan_file(blend).texts[0]

    identity.clear_cache()
    monkey = pytest.MonkeyPatch()
    monkey.setattr(identity, "DATABASE_PATH", tmp_path / "absent.json")
    identity.clear_cache()
    without_db = scanner.scan_file(blend).texts[0]
    monkey.undo()
    identity.clear_cache()

    assert without_db.identity is None
    assert with_db.explanation is not None
    assert without_db.explanation is not None
    assert with_db.explanation.max_severity == without_db.explanation.max_severity
    assert [s.key for s in with_db.explanation.statements] == [
        s.key for s in without_db.explanation.statements
    ]
    # Still alarming, still says so on screen.
    assert with_db.explanation.alarming
    assert strings.t("x_dynamic_code") in _render(blend)


def test_byte_match_of_a_release_stands_down_the_escalation(
    tmp_path: Path, database: Path
) -> None:
    text = _render(_blend_with(tmp_path, "rig_panel.py", RELEASE_SCRIPT))
    assert strings.t("recommend_needs_human") not in text
    assert strings.t("recommend_known_release") in text


def test_byte_match_of_a_generated_script_keeps_escalating(
    tmp_path: Path, database: Path
) -> None:
    """One generated copy is not a release many people have read between them."""
    text = _render(_blend_with(tmp_path, "rig_ui.py", _reference_generated()))
    assert strings.t("identity_generated_byte") in text
    assert strings.t("recommend_needs_human") in text


# -- structural match ---------------------------------------------------------
def test_structural_match_reports_which_literals_differ(tmp_path: Path, database: Path) -> None:
    body = GENERATED_TEMPLATE.format(rig_id="c0ffee0123456789", home=REFERENCE_HOME)
    result = scanner.scan_file(_blend_with(tmp_path, "rig_ui.py", body))
    match = result.texts[0].identity
    assert match is not None
    assert match.evidence == identity.EVIDENCE_STRUCTURE
    assert [(d.reference, d.actual) for d in match.differences] == [
        (REFERENCE_RIG_ID, "c0ffee0123456789")
    ]

    text = _render(tmp_path / "rig_ui.py.blend")
    assert "c0ffee0123456789" in text
    assert REFERENCE_RIG_ID in text


def test_structural_match_never_stands_down_the_escalation(
    tmp_path: Path, database: Path
) -> None:
    body = GENERATED_TEMPLATE.format(rig_id="c0ffee0123456789", home=REFERENCE_HOME)
    text = _render(_blend_with(tmp_path, "rig_ui.py", body))
    assert strings.t("recommend_needs_human") in text
    assert strings.t("recommend_known_release") not in text


def test_structural_match_surfaces_an_injected_url_and_still_escalates(
    tmp_path: Path, database: Path
) -> None:
    """The security crux, stated as a test.

    An attacker who keeps a known script's structure and edits only its strings
    gets recognised -- and the edit is the one thing highlighted, rather than
    the recognition being used to quieten the file down.
    """
    payload = "http://drop.example-host.top/stage2"
    body = GENERATED_TEMPLATE.format(rig_id=REFERENCE_RIG_ID, home=payload)
    result = scanner.scan_file(_blend_with(tmp_path, "rig_ui.py", body))
    match = result.texts[0].identity
    assert match is not None
    assert match.evidence == identity.EVIDENCE_STRUCTURE
    assert [d.actual for d in match.differences] == [payload]

    text = _render(tmp_path / "rig_ui.py.blend")
    assert payload in text
    assert strings.t("identity_diff_header", count=1) in text
    assert strings.t("recommend_needs_human") in text


def test_structure_ignores_comments_and_blank_lines() -> None:
    """Reformatting is not tampering; changing a string is."""
    reference = structure_of(_reference_generated())
    reformatted = structure_of("# a note\n" + _reference_generated().replace("\n", "\n\n"))
    assert reference is not None and reformatted is not None
    assert reformatted.sha256 == reference.sha256
    assert reformatted.literals == reference.literals


def test_structure_of_unparseable_source_is_none() -> None:
    assert structure_of("def broken(:\n") is None


def test_structure_changes_when_the_code_changes_but_not_when_a_literal_does() -> None:
    base = structure_of('def f():\n    return "a"\n')
    literal_only = structure_of('def f():\n    return "zzz"\n')
    different_code = structure_of('def f():\n    return len("a")\n')
    assert base is not None and literal_only is not None and different_code is not None
    assert literal_only.sha256 == base.sha256
    assert different_code.sha256 != base.sha256


@pytest.mark.parametrize(
    ("left", "right"),
    [
        ('x = "AB"', 'x = b"AB"'),  # a str and a bytes literal must not collide
        ("x = None", "x = ..."),  # the hand-written serialiser skips empty fields;
        ("x = None", "x = 0"),  # `None` is a real value and must survive that
    ],
)
def test_structure_distinguishes_values_the_serialiser_could_have_flattened(
    left: str, right: str
) -> None:
    a, b = structure_of(left), structure_of(right)
    assert a is not None and b is not None
    assert a.sha256 != b.sha256


def test_a_deep_expression_degrades_instead_of_crashing() -> None:
    """No bracket nesting, so the depth cap does not see it -- it must still be safe."""
    assert structure_of("x = " + "+".join(["1"] * 4000)) is None


# -- no match -----------------------------------------------------------------
def test_unrecognised_script_says_nothing_about_identity(
    tmp_path: Path, database: Path
) -> None:
    result = scanner.scan_file(_blend_with(tmp_path, "ordinary.py", ORDINARY_SCRIPT))
    assert result.texts[0].identity is None
    assert strings.t("identity_header") not in _render(tmp_path / "ordinary.py.blend")


def test_a_changed_release_body_no_longer_matches(tmp_path: Path, database: Path) -> None:
    """One injected line is a different hash, and the file escalates again."""
    tampered = RELEASE_SCRIPT + "\nimport urllib.request\nurllib.request.urlopen('http://x.top/a')\n"
    result = scanner.scan_file(_blend_with(tmp_path, "rig_panel.py", tampered))
    assert result.texts[0].identity is None
    assert strings.t("recommend_needs_human") in _render(tmp_path / "rig_panel.py.blend")


# -- a database that is missing or damaged ------------------------------------
def test_absent_database_degrades_to_normal_operation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(identity, "DATABASE_PATH", tmp_path / "nowhere.json")
    identity.clear_cache()
    try:
        blend = _blend_with(tmp_path, "rig_panel.py", RELEASE_SCRIPT)
        result = scanner.scan_file(blend)
        assert result.texts[0].identity is None
        assert result.texts[0].explanation is not None
        assert result.texts[0].explanation.alarming
        text = _render(blend)
        assert strings.t("recommend_needs_human") in text
        assert "nowhere.json" in text  # the gap is stated, not swallowed
    finally:
        identity.clear_cache()


#: Broken database files, by short name. The last two are the ones a precise
#: `except` tuple got wrong: an integer past CPython's 4300-digit conversion
#: limit raises a bare ValueError out of ``json.loads``, and deeply nested JSON
#: raises RecursionError -- neither is a ``JSONDecodeError``. Both used to
#: escape and abort an entire batch scan. Built lazily by name because a
#: 200 KB parametrisation id overflows pytest's own environment variable.
CORRUPT_DATABASES: dict[str, str] = {
    "not-json": "{ this is not json",
    "top-level-list": "[]",
    "unknown-schema": '{"schema": 999, "entries": []}',
    "entries-not-a-list": '{"schema": 1, "entries": "not a list"}',
    "empty-file": "",
    "oversized-integer": '{"schema": 1, "entries": [], "n": ' + "9" * 5000 + "}",
    "deeply-nested": '{"schema": 1, "entries": ' + "[" * 100000 + "]" * 100000 + "}",
}


@pytest.mark.parametrize("case", sorted(CORRUPT_DATABASES))
def test_corrupt_database_never_crashes_a_scan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, case: str
) -> None:
    path = tmp_path / "known_scripts.json"
    path.write_text(CORRUPT_DATABASES[case], encoding="utf-8")
    monkeypatch.setattr(identity, "DATABASE_PATH", path)
    identity.clear_cache()
    try:
        database = identity.load_database()
        assert not database.usable
        assert database.problems, "a database that loaded nothing must say why"
        blend = _blend_with(tmp_path, "rig_panel.py", RELEASE_SCRIPT)
        result = scanner.scan_file(blend)
        assert result.texts[0].identity is None
        assert _render(blend)  # renders rather than raising
    finally:
        identity.clear_cache()


def test_one_broken_entry_is_skipped_and_the_rest_still_load(tmp_path: Path) -> None:
    path = tmp_path / "known_scripts.json"
    path.write_text(
        json.dumps(
            {
                "schema": identity.SCHEMA_VERSION,
                "entries": [
                    {"sha256": "abc", "script_name": "half.py"},
                    "not an object",
                    _entry(RELEASE_SCRIPT, "rig_panel.py"),
                ],
            }
        ),
        encoding="utf-8",
    )
    database = identity.load_database(path)
    assert len(database.entries) == 1
    assert len(database.problems) == 2
    assert database.match(as_extracted(RELEASE_SCRIPT)) is not None


@pytest.mark.parametrize("bad", ["", "abc", 12345, "z" * 64, None])
def test_an_entry_whose_hash_is_not_a_digest_is_reported_not_quietly_kept(
    tmp_path: Path, bad: object
) -> None:
    """An entry that can never match must say so rather than pass for coverage."""
    entry = _entry(RELEASE_SCRIPT, "rig_panel.py", sha256=bad)
    path = tmp_path / "known_scripts.json"
    path.write_text(
        json.dumps({"schema": identity.SCHEMA_VERSION, "entries": [entry]}), encoding="utf-8"
    )
    database = identity.load_database(path)
    assert database.entries == ()
    assert database.problems


def test_a_structural_entry_with_a_blank_structure_hash_is_reported(tmp_path: Path) -> None:
    entry = _structural_entry(_reference_generated(), "rig_ui.py")
    entry["structure"]["sha256"] = ""
    path = tmp_path / "known_scripts.json"
    path.write_text(
        json.dumps({"schema": identity.SCHEMA_VERSION, "entries": [entry]}), encoding="utf-8"
    )
    database = identity.load_database(path)
    assert database.entries == ()
    assert database.problems


def test_entry_with_an_unknown_structure_scheme_is_skipped(tmp_path: Path) -> None:
    """A hash computed by a scheme we no longer speak must not silently never match."""
    entry = _structural_entry(_reference_generated(), "rig_ui.py")
    entry["structure"]["scheme"] = STRUCTURE_SCHEME + 99
    path = tmp_path / "known_scripts.json"
    path.write_text(
        json.dumps({"schema": identity.SCHEMA_VERSION, "entries": [entry]}), encoding="utf-8"
    )
    database = identity.load_database(path)
    assert database.entries == ()
    assert database.problems


# -- "generated" is declared data, never derived -------------------------------
# The defect: KnownScript.is_generated returned ``structure_sha256 is not
# None``. Entry 5 of the shipped database, cloudrig.py.001, is a per-file
# generated body -- ``script_id = "gabby"`` is baked into it -- recorded with no
# structural form, so the derivation called it a shared release and let it stand
# down the "needs a human" branch. The report would then have said a body
# exactly one person has ever downloaded "is one many people have already
# downloaded and read".
def _write_db(tmp_path: Path, *entries: dict) -> Path:
    """A database file on disk. Read it with ``load_database(path)``."""
    path = tmp_path / "known_scripts.json"
    path.write_text(
        json.dumps({"schema": identity.SCHEMA_VERSION, "entries": list(entries)}),
        encoding="utf-8",
    )
    return path


def _install(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *entries: dict) -> Path:
    """As :func:`_write_db`, but registered as *the* database for a scan.

    ``monkeypatch`` must be the fixture, never a hand-built ``MonkeyPatch``: an
    un-torn-down patch of ``DATABASE_PATH`` leaks a test's fixture database into
    every test that runs after it, including the ones that check the database
    this repository actually ships.
    """
    path = _write_db(tmp_path, *entries)
    monkeypatch.setattr(identity, "DATABASE_PATH", path)
    identity.clear_cache()
    return path


def test_a_generated_entry_needs_no_structural_form_to_be_believed(tmp_path: Path) -> None:
    """The shipped cloudrig.py.001 shape: one per-file copy, recorded verbatim."""
    entry = _entry(RELEASE_SCRIPT, "cloudrig.py.001", generated=True)
    assert "structure" not in entry
    loaded = identity.load_database(_write_db(tmp_path, entry)).entries
    assert len(loaded) == 1
    assert loaded[0].is_generated is True


def test_a_byte_match_on_a_generated_entry_does_not_stand_the_file_down(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """End to end. This is the sentence the defect would have printed."""
    _install(tmp_path, monkeypatch, _entry(RELEASE_SCRIPT, "cloudrig.py.001", generated=True))
    try:
        blend = _blend_with(tmp_path, "cloudrig.py.001", RELEASE_SCRIPT)
        match = scanner.scan_file(blend).texts[0].identity
        assert match is not None
        assert match.evidence == identity.EVIDENCE_BYTE
        assert match.suppresses_escalation is False
        text = _render(blend)
        assert strings.t("recommend_needs_human") in text
        assert strings.t("recommend_known_release") not in text
        # The identity is still reported in full -- nothing is hidden.
        assert "cloudrig.py.001" in text
    finally:
        identity.clear_cache()


def test_the_same_body_declared_a_shared_release_does_stand_the_file_down(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The control: only the declaration differs between this and the test above."""
    _install(tmp_path, monkeypatch, _entry(RELEASE_SCRIPT, "cloudrig.py", generated=False))
    try:
        blend = _blend_with(tmp_path, "cloudrig.py", RELEASE_SCRIPT)
        match = scanner.scan_file(blend).texts[0].identity
        assert match is not None and match.suppresses_escalation is True
        assert strings.t("recommend_needs_human") not in _render(blend)
    finally:
        identity.clear_cache()


def test_an_entry_that_omits_the_declaration_is_reported_not_assumed(tmp_path: Path) -> None:
    entry = _entry(RELEASE_SCRIPT, "rig_panel.py")
    del entry["generated"]
    database = identity.load_database(_write_db(tmp_path, entry))
    assert database.entries == ()
    assert any("generated" in problem for problem in database.problems)


@pytest.mark.parametrize("bad", ["true", "false", "yes", 1, 0, None, [], {}])
def test_a_declaration_that_is_not_a_boolean_is_reported(tmp_path: Path, bad: object) -> None:
    """``"true"``, ``1`` and ``0`` are truthy or falsy; none of them is a claim."""
    entry = _entry(RELEASE_SCRIPT, "rig_panel.py", generated=bad)
    database = identity.load_database(_write_db(tmp_path, entry))
    assert database.entries == ()
    assert database.problems


def test_a_structural_entry_that_denies_being_generated_is_malformed(tmp_path: Path) -> None:
    """The two halves disagree, so neither half is believed."""
    entry = _structural_entry(_reference_generated(), "rig_ui.py")
    entry["generated"] = False
    database = identity.load_database(_write_db(tmp_path, entry))
    assert database.entries == ()
    assert any("structural form" in problem for problem in database.problems)


def test_the_declaration_reaches_the_machine_readable_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install(tmp_path, monkeypatch, _entry(RELEASE_SCRIPT, "cloudrig.py.001", generated=True))
    try:
        result = scanner.scan_file(_blend_with(tmp_path, "cloudrig.py.001", RELEASE_SCRIPT))
        payload = json.loads(report.format_json([result], []))
        block = payload["files"][0]["texts"][0]["identity"]
        assert block["entry"]["generated"] is True
        assert block["suppresses_escalation"] is False
    finally:
        identity.clear_cache()


# -- the database this repository actually ships ------------------------------
def test_shipped_database_loads_with_no_problems() -> None:
    database = identity.load_database(identity.DATABASE_PATH)
    assert database.usable, "the shipped known-script database must load"
    assert database.problems == ()


def test_shipped_entries_are_well_formed() -> None:
    for entry in identity.load_database(identity.DATABASE_PATH).entries:
        assert len(entry.sha256) == 64
        assert entry.sha256 == entry.sha256.lower()
        int(entry.sha256, 16)  # raises if it is not hexadecimal
        assert entry.byte_size > 0
        assert entry.source_url.startswith("https://")
        assert entry.attested_by and entry.attested_on
        assert entry.notes.strip(), f"{entry.sha256[:12]} has no notes"
        assert isinstance(entry.is_generated, bool)
        if entry.structure_sha256 is not None:
            assert len(entry.structure_sha256) == 64
            assert entry.structure_literals
            assert entry.is_generated, f"{entry.sha256[:12]} has a shape but denies being generated"


def test_the_shipped_generated_entries_are_the_audited_ones() -> None:
    """Audited by reading all twenty sets of notes, not by deriving anything.

    ``rig_ui.py`` carries Rigify's per-rig ``rig_id``; ``cloudrig.py.001``
    carries ``script_id = "gabby"``. Every other entry ships byte-identical in
    several published files, which is exactly what makes suppressing escalation
    defensible for them and not for these two.
    """
    entries = identity.load_database(identity.DATABASE_PATH).entries
    generated = sorted(entry.script_name for entry in entries if entry.is_generated)
    assert generated == ["cloudrig.py.001", "rig_ui.py"]


def test_no_shipped_entry_claims_to_be_a_release_while_carrying_a_shape() -> None:
    """The contradiction the loader refuses must not exist in the shipped file."""
    payload = json.loads(identity.DATABASE_PATH.read_text(encoding="utf-8"))
    for position, raw in enumerate(payload["entries"]):
        assert isinstance(raw["generated"], bool), position
        if "structure" in raw:
            assert raw["generated"] is True, position


def test_shipped_database_prose_never_says_safe() -> None:
    """The banned words apply to the database file too, not only the catalogue."""
    text = identity.DATABASE_PATH.read_text(encoding="utf-8").lower()
    for banned in BANNED_WORDS_BY_LANG["en"]:
        assert banned not in text, f"the known-script database must never say {banned!r}"


# -- doctrine -----------------------------------------------------------------
def test_identity_report_never_says_safe_in_any_language(
    tmp_path: Path, database: Path
) -> None:
    blend = _blend_with(tmp_path, "rig_panel.py", RELEASE_SCRIPT)
    variant = GENERATED_TEMPLATE.format(rig_id="c0ffee0123456789", home=REFERENCE_HOME)
    structural = _blend_with(tmp_path, "rig_ui.py", variant)
    for lang, banned_words in BANNED_WORDS_BY_LANG.items():
        strings.set_language(lang)
        for path in (blend, structural):
            text = _render(path).lower().replace(str(tmp_path).lower(), "<tmp>")
            for banned in banned_words:
                assert banned not in text, f"[{lang}] identity output must never say {banned!r}"
    strings.set_language(strings.DEFAULT_LANGUAGE)


def test_json_output_carries_the_match_and_its_evidence_class(
    tmp_path: Path, database: Path
) -> None:
    result = scanner.scan_file(_blend_with(tmp_path, "rig_panel.py", RELEASE_SCRIPT))
    payload = json.loads(report.format_json([result], []))
    block = payload["files"][0]["texts"][0]
    assert block["identity"]["evidence"] == identity.EVIDENCE_BYTE
    assert block["identity"]["suppresses_escalation"] is True
    assert block["identity"]["entry"]["source_url"].startswith("https://")
    # The finding itself is untouched in the machine-readable output too.
    assert block["explanation"]["max_severity"] == "ALARMING"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("line1\nline2", "'line1\\\\nline2'"),  # no newline breaks the difference line
        ("\x1b[31mred", "'\\x1b[31mred'"),  # no raw escape reaches the terminal
    ],
)
def test_a_differing_literal_is_printed_without_letting_it_drive_the_terminal(
    value: str, expected: str
) -> None:
    """These values come out of a hostile file, so they are shown, never obeyed."""
    assert report.clip_literal(value) == expected


def test_a_very_long_differing_literal_is_cut(tmp_path: Path) -> None:
    clipped = report.clip_literal("a" * 4000)
    assert clipped.endswith("...'")
    assert len(clipped) < report.MAX_LITERAL_WIDTH + 20


def test_the_window_shows_the_same_identity_and_the_same_recommendation(
    tmp_path: Path, database: Path
) -> None:
    """The two front ends must not describe one match differently."""
    from blend_xray.gui import render

    result = scanner.scan_file(_blend_with(tmp_path, "rig_panel.py", RELEASE_SCRIPT))
    drawn = render.plain_text(render.render_result(result))
    for line, _severity in report.identity_lines(result.texts[0].identity):
        assert line in drawn
    assert strings.t("recommend_known_release") in drawn
    assert strings.t("recommend_needs_human") not in drawn


def test_the_window_escalates_a_structural_match_like_the_command_line(
    tmp_path: Path, database: Path
) -> None:
    from blend_xray.gui import render

    body = GENERATED_TEMPLATE.format(rig_id=REFERENCE_RIG_ID, home="http://drop.example.top/s")
    result = scanner.scan_file(_blend_with(tmp_path, "rig_ui.py", body))
    drawn = render.plain_text(render.render_result(result))
    assert "http://drop.example.top/s" in drawn
    assert strings.t("recommend_needs_human") in drawn


def test_an_oversized_database_is_refused_before_it_is_parsed(tmp_path: Path) -> None:
    path = tmp_path / "known_scripts.json"
    path.write_text("x" * (identity.MAX_DATABASE_BYTES + 1), encoding="utf-8")
    database = identity.load_database(path)
    assert not database.usable
    assert database.problems


def test_control_characters_in_an_entry_never_reach_the_report(tmp_path: Path) -> None:
    """Provenance text is displayed, never allowed to drive the terminal."""
    entry = _entry(
        RELEASE_SCRIPT,
        "rig_panel.py",
        origin="Real Studio\x1b[2J\x1b[HFAKE CLEARED SCREEN",
        notes="line one\nline two\x07",
    )
    path = tmp_path / "known_scripts.json"
    path.write_text(
        json.dumps({"schema": identity.SCHEMA_VERSION, "entries": [entry]}), encoding="utf-8"
    )
    loaded = identity.load_database(path).entries[0]
    assert "\x1b" not in loaded.origin
    assert "\n" not in loaded.notes
    assert "\x07" not in loaded.notes
    assert "Real Studio" in loaded.origin


def test_a_failed_load_is_cached_so_a_batch_scan_does_not_retry_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[Path] = []
    real = identity.load_database

    def counting(path: Path | None = None) -> identity.Database:
        calls.append(path)
        return real(path)

    monkeypatch.setattr(identity, "DATABASE_PATH", tmp_path / "nowhere.json")
    monkeypatch.setattr(identity, "load_database", counting)
    identity.clear_cache()
    try:
        for _ in range(3):
            assert not identity.default_database().usable
        assert len(calls) == 1
    finally:
        identity.clear_cache()


def test_a_lookup_that_explodes_becomes_a_warning_not_a_crash(
    tmp_path: Path, database: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(_source: str) -> None:
        raise RuntimeError("database went bad mid-scan")

    monkeypatch.setattr(identity.Database, "match", lambda self, source: boom(source))
    result = scanner.scan_file(_blend_with(tmp_path, "rig_panel.py", RELEASE_SCRIPT))
    assert result.texts[0].identity is None
    assert any("database went bad mid-scan" in w for w in result.warnings)
