# Contributing to Blend X-Ray

Thank you for looking at this. Blend X-Ray is a small tool with a narrow job,
and the most useful contributions are usually small too: a rule that misreads a
real script, a language string that overclaims, a `.blend` file it refuses to
parse, or one more entry in the known-good database.

Before anything else, please read the two rules in the README. They are not
style preferences, and a change that breaks either one will be declined however
good the code is:

1. **Blend X-Ray never runs anything it finds.** No `eval`, no `exec`, no
   `import` of scanned content, no launching Blender, no following a path out
   of the scanned file. It parses bytes.
2. **Blend X-Ray never issues a verdict.** No "safe", no "clean", no score, no
   percentage, no green colour, no tick. Not in English, not in French, not
   inside a negation. There is a test that enforces this over the whole string
   catalogue in every language, and it has already caught a real slip.

## Setting up

Python 3.11 or 3.12. Not 3.13 or newer — `blender-asset-tracer` is pinned to
1.23, which predates them, and the dependency set does not resolve on 3.14.

```bash
py -3.12 -m venv .venv            # Windows; python3.12 -m venv .venv elsewhere
.venv\Scripts\activate            # Windows; source .venv/bin/activate elsewhere
pip install -e ".[dev]"
```

The `dev` extra brings `pytest` and `ruff`. Add `gui` if you are touching the
window and want drag-and-drop, and `build` only if you are working on the
PyInstaller spec.

**Do not upgrade `blender-asset-tracer`.** BAT 2.x removed standalone parsing
and requires a Blender 5.1+ installation to do its work, which would turn a
tool whose entire premise is "never open the file in Blender" into one that
needs Blender. `blend_xray/scanner.py` asserts the version at runtime and
refuses to run against anything else. Also do not switch to the
`blender-asset-tracer[zstandard]` extra: it resolves to a 2021 `zstandard`
with no wheels for current Python, so it fails to install on any machine
without a C compiler.

## Running the tests

```bash
python -m pytest                  # the whole suite
python -m pytest tests/test_identity.py -v      # one file
python -m ruff check .
```

On a clean clone the suite is **798 passed, 6 skipped**. One skip asserts
off-Windows behaviour of the registry toggle and is expected to skip on Windows.
The other five need Blender demo files from blender.org, which are third-party
downloads and are not in this repository: point `BLEND_XRAY_CORPUS` at a
directory holding them and the suite reports **803 passed, 1 skipped**. Both
numbers are correct — they just describe different machines. `ruff check` must report no findings; the configuration lives in
`pyproject.toml`, including the per-file ignores that let the scanner catch
broad exceptions on purpose.

No test fetches anything from the network, and no test needs a real `.blend`
file on disk. `tests/blend_builder.py` constructs valid `.blend` files from
scratch, including a hand-written SDNA (DNA1) block, so the suite runs
offline and deterministically. **No real malware sample is used, fetched or
required by any test** — the hostile scripts in `tests/test_explain.py` are
written by hand to trigger specific rules, and none of them is ever executed.

If you send a fixture, send a builder call that generates it, not a binary
`.blend` in the repository.

## Code conventions

- **Python 3.11+**, `from __future__ import annotations` at the top of every
  module, type hints on public functions.
- **`ruff` decides formatting disputes.** Line length 100. Run
  `ruff check .` before you push; the selected rule set is in `pyproject.toml`.
- **Small files.** 200–400 lines is normal, 800 is the ceiling. If a module is
  growing past that it usually wants splitting along a real seam.
- **Small functions**, early returns rather than deep nesting.
- **Immutability.** Findings are frozen dataclasses. Build a new object rather
  than mutating one in place.
- **No debug prints.** The CLI writes the report; nothing else writes to
  stdout.
- **Every user-facing string goes in the catalogue**, never in a module.
  `blend_xray/strings_en.py` and `blend_xray/strings_fr.py` hold them, and code
  looks them up through `strings.t("key")`. That includes every label, button
  and dialog in the window. A string hardcoded in a GUI module is a bug even if
  it reads correctly, because it cannot be translated and it escapes the
  never-say-safe test.
- **Comments explain *why*.** The existing code comments are long on purpose:
  several of them record a decision that looks wrong until you know what it
  cost. Keep that habit. A comment restating what the line does is noise.
- **Errors are handled explicitly.** The scanner deliberately catches broad
  exceptions because it parses hostile input and one corrupt datablock must not
  abort a whole batch — but a swallowed failure has to surface in
  `ScanResult.warnings`, never disappear.

### If you add or change a detection rule

- The rule's sentence must name the concrete evidence — the function called,
  the literal found — so a reader can check the claim instead of trusting it.
- The rule must describe what the code *arranges*, never predict what it *will
  do*. Guessing is the failure this tool exists to avoid.
- Both languages, or the catalogue test fails.
- If you put a rule key in `banner.REACHES_OUTSIDE_KEYS` (the red tier), its
  own sentence has to support the red headline, *"This file contains code that
  reaches outside Blender"*. That is machine-checked in
  `tests/test_banner.py`, not left to review.

## Contributing a known-good database entry

`blend_xray/known_scripts.json` records the identity of scripts that legitimately
appear inside real `.blend` files — Blender Studio's `cloudrig.py`, Rigify's
`rig_ui.py`, and so on — so that an artist is not asked to review the same
benign rig script twenty times and taught to ignore the tool.

**A database entry is a security-relevant change.** It is the one place where
adding data changes what the tool tells a user about a file, and a wrong entry
is worse than a missing one because it looks checkable. Treat a pull request
that touches this file as a security review, and expect it to be read that way.

### The rule the whole layer rests on

An entry records **identity, and never safety**. It says:

> this block is byte-identical to `<name>` as shipped in *this* published file,
> fetched from *this* URL on *this* date, attested by *this* person.

It never says, and may never be reworded to say, "this script is harmless".
The first claim is verifiable by anyone, forever — re-download, re-extract,
re-hash. The second would become false the day somebody finds a bug in
CloudRig, and we would have signed it. Several scripts already in the database
really do call `eval()` or `exec()`, and Blend X-Ray still reports that at full
severity for every one of them.

A match never removes, hides or downgrades a finding. It adds provenance, and —
for byte matches on shared releases only — changes which closing recommendation
is printed.

### Where the body must come from

**From a published `.blend` file that you fetched yourself, at a URL other
people can fetch too.**

- Not from a copy of the script pasted out of a text editor. Line endings will
  differ and the hash will be wrong.
- Not from a file somebody sent you privately. If a third party cannot
  re-download it, the entry is not checkable and is worse than no entry.
- Not from a paywalled or account-gated source, for the same reason.
- Not guessed, and not derived from a file you have only read about.

Get the hash by extracting the block from the `.blend` with Blend X-Ray itself,
or with `blender-asset-tracer` directly. The README section *Re-verifying an
entry yourself* has both recipes; use either, and check they agree.

### Required fields

Every entry needs all of these. The loader rejects an entry that is missing one
or carries one of the wrong type, and reports it as malformed rather than
believing it.

| field | what it must contain |
|---|---|
| `sha256` | SHA-256 of the script body: the UTF-8 encoding of the text datablock's lines joined with `\n`, blank lines included. |
| `script_name` | The datablock's name, exactly as it appears in the report. |
| `byte_size` | Length in bytes of that same UTF-8 body. |
| `origin` | The project or product, and which version, if it has one. |
| `source_url` | Where the containing file was fetched from. A `#member/path` fragment names a member inside a zip. It must resolve for somebody who is not you. |
| `fetched_on` | ISO date you fetched it. |
| `attested_by` | Your name. You are vouching that this hash is that script — nothing more. |
| `attested_on` | ISO date you vouched. |
| `notes` | What the script is for, and which of its behaviours set off Blend X-Ray's rules and why they are there. Written by you, from reading it. Never that it is harmless. |
| `generated` | Required JSON boolean. See below. |

`structure` is the one optional field: `{"scheme": 1, "sha256": ..., "literals": [...]}`,
generated with `blend_xray.structure.structure_of(body)`. It is only valid on an
entry that also declares `"generated": true`, and the loader rejects the
contradiction.

### Setting `generated` yourself

`true` when the generator that wrote the script bakes something per-file into
the body — a rig id, a file name, a random identifier — so that no two copies
share a hash. `false` when the same bytes ship in every copy of a release.

Nothing infers this for you, and it used to be derived, wrongly. Only a `false`
entry may stand a block down from the "needs a human" branch, and the reason is
about readership rather than about the code: a release many thousands of people
have downloaded and read is not something one artist alone can usefully be
asked to review at midnight. A body that exactly one person has ever downloaded
gets no such argument. Getting this field wrong is how a per-file generated
script ends up described as one many people have already read.

### Read the script

This is the human step, and it is the point of the whole exercise. It happens
once per hash, not once per file that contains it. Write `notes` from having
read the body — say what the script is for, and say plainly which of its
behaviours trigger Blend X-Ray's rules and why they are legitimately there.

### Before you open the pull request

```bash
python -m pytest tests/test_identity.py
```

That checks every shipped entry for shape, cross-checks `generated` against the
structural form, and holds the database file itself to the never-say-safe rule.
Run the full suite too.

In the pull request, say **where you fetched the file from, on what date, and
what you did to check the hash**, so a reviewer can repeat it rather than take
your word for it.

### What we cannot promise you

Every entry in the database today carries **a single person's attestation** —
the maintainer's. There is no second reviewer, no signature, and no
transparency log, and `attested_by` says so on every line it prints. Your entry
will carry your name under the same conditions. That limitation is documented
in the README's *Known gaps*, and it is a real one: an attacker who could edit
`known_scripts.json` in an installed copy could add their own script's hash and
stand it down. The file's integrity is the integrity of the install.

## Translations

Adding a language is a data change, not a code change: add a dict to
`CATALOGUE` in `blend_xray/strings.py` and it becomes available to `--lang` and
to the window's selector. Two things to know:

- The catalogue test holds **every** language to the never-say-safe rule, over
  the whole catalogue and not just the strings a scan happens to print. A
  French dialog once used *propre* in its "your own account" sense and the test
  caught it.
- `origin` and `notes` in the known-good database are **not** translated. They
  are a transcription of what a source says, stored once, in English. The
  wording around them is translated.

## Reporting a bug

Ordinary bugs: open an issue. Include the Blend X-Ray version, your Python
version, your operating system, and — if it is about a specific file — where
that file came from. Please do not attach a `.blend` you believe is malicious.

**A vulnerability in Blend X-Ray itself is different.** Do not open a public
issue for it. `SECURITY.md` says how to report it privately.
