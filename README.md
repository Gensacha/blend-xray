# Blend X-Ray

**Inventory the code hidden inside a `.blend` file — without opening Blender.**

You downloaded a `.blend` from a marketplace, a forum or a Discord. Before you
open it, you would like to know whether there is code inside it and what that
code does. Blend X-Ray reads the file's bytes, finds the embedded Python, driver
expressions, OSL script nodes and linked-library paths, and explains each one in
plain language. It never launches Blender and never runs a line of what it finds.
It is written for 3D artists and students, by a VFX artist and Houdini teacher —
not by a security professional, and it does not pretend otherwise.

**Download for Windows** (no Python needed) — a zip holding one `.exe`, pay what
you want with a 0 EUR minimum:
**<https://7179206757975.gumroad.com/l/blend-xray>**. The
executable is **unsigned**, so Windows and possibly your antivirus will complain
on first run — read
[The downloadable executable, and why it is unsigned](#the-downloadable-executable-and-why-it-is-unsigned)
before you download it. Prefer to run it from source? [Quick start](#quick-start).

## Why it exists

In November 2025, Morphisec disclosed a campaign it describes as having been
active for at least six months: `.blend` files uploaded as free 3D models to
**CGTrader** carried an embedded Python script. If the user had Blender's
*Auto Run Python Scripts* setting enabled, the script ran the moment the file was
opened. It pulled down a PowerShell loader — Kaspersky names the host as a
Cloudflare Workers domain — and that fetched the **StealC V2** infostealer and,
per Morphisec, a second Python-based stealer alongside it. Both writeups describe
the same collection targets: browsers, browser extensions, cryptocurrency
wallets, messaging apps, VPN clients and email clients. Two details matter for
this tool:

- **The malicious script was named `Rig_Ui.py`** (Morphisec). That differs only
  in capitalisation from `rig_ui.py`, the script Blender's own Rigify add-on
  writes into every rig it generates — the single most ordinary thing to find
  inside a character `.blend`. The payload was sitting where a rig script
  belongs. (The Rigify resemblance is this project's observation, not
  Morphisec's; check it against any rig you have generated yourself.)
- **Morphisec reported that the samples it identified had "an extremely low
  detection ratio" on VirusTotal.** Low, not zero — but low enough that a file
  every scanner you own passes over tells you very little, because antivirus
  engines do not parse `.blend` internals.

Sources — each claim above belongs to the vendor named beside it, and the two
writeups do not say the same things:
[Morphisec, 24 November 2025](https://www.morphisec.com/blog/morphisec-thwarts-russian-linked-stealc-v2-campaign-targeting-blender-users-via-malicious-blend-files/)
·
[Kaspersky, 10 December 2025](https://www.kaspersky.com/blog/malicious-blender-model-files/54948/)

Blender does warn you when a file wants to auto-run scripts, and the warning does
not work. It is worth quoting exactly, because the wording is the problem. From
Blender's own source — `source/blender/windowmanager/intern/wm_files.cc` — the
title reads *"For security reasons, automatic execution of Python scripts in this
file was disabled:"*, the body adds *"This may lead to unexpected behavior"*, and
the two buttons are **Allow Execution** and **Ignore**. Between them sits a
checkbox: *"Permanently allow execution of scripts"*.

Nothing in that box says what the scripts do, or what they could do. Told that
something is dangerous with no explanation of the danger, people conclude it must
be a false alarm and click through. And the checkbox is the part that turns one
bad click into a standing condition: it does not whitelist this file, it flips
the global *Auto Run Python Scripts* preference on and persists it, so every
`.blend` opened afterwards runs its scripts without asking again. The setting the
CGTrader campaign depended on is one checkbox away, in the dialog that is
supposed to be protecting you, offered at the exact moment the user has decided
the warning is noise.

Blend X-Ray exists to put something readable between the download and that click.

## What it does not claim

This is the important half, and it is at the top on purpose.

- **It is not an antivirus, a sandbox, or a gate.** It is a reading aid for a
  decision you make yourself, maintained by one person in their spare time.
- **It will never tell you a file is safe.** There is no "clean", no score, no
  percentage, no green colour and no tick, in any language. A finding of nothing
  means *nothing was found in the categories it checked* — the report says so in
  those words and lists what those categories were.
- **A determined attacker can evade it.** Static analysis has a hard ceiling and
  no amount of rule-writing removes it.
  [What static analysis cannot do](#what-static-analysis-cannot-do), below, shows
  working code that defeats every name-based rule in the tool. Anyone who tells
  you their static scanner cannot be evaded is selling something.
- **Whole categories are not covered at all.** Geometry Nodes, Video Sequence
  Editor strip paths, packed file contents and custom properties are not
  inventoried. See [Known gaps](#known-gaps).
- **It has never been run against a real malicious sample.** None was obtained,
  by design. See [What was and was not verified](#what-was-and-was-not-verified).

## Quick start

Python 3.11 or 3.12 — **not 3.13 or newer**, for a reason explained under
[Install](#install).

```bash
py -3.12 -m venv .venv          # Windows; python3.12 -m venv .venv elsewhere
.venv\Scripts\activate          # Windows; source .venv/bin/activate elsewhere
pip install .
blend-xray scan suspicious.blend
```

There is also a window you can double-click and drop a file on —
see [docs/GUI.md](docs/GUI.md).

## The two rules Blend X-Ray follows

**1. It never runs anything.** Blend X-Ray never launches Blender and never
executes, imports, or evaluates a single line of what it finds. It parses bytes.
That is the whole point: the file may be hostile, so nothing in it is allowed to
run.

**2. It gives you an inventory, never a verdict.** Blend X-Ray will never print
"SAFE" or "clean", and there is no score or percentage anywhere in the output —
not even a green colour, because green reads as "all clear" at a glance. False
confidence is the exact failure mode this tool exists to prevent. It reports what
it found and lists what it checked; you decide.

Those two rules are why a third one exists. Real rig files legitimately do
alarming-looking things — Blender Studio's `cloudrig.py` genuinely calls
`eval()` — and on a first-party corpus that made 36% of files ask for a human
review nobody could give. So Blend X-Ray also carries a database of script
**identities**. Identity, never safety, and it never removes a finding. See
[The known-good identity layer](#the-known-good-identity-layer).

## Why it explains the code instead of just printing it

Printing raw Python at an artist who does not read Python reproduces Blender's
own failure exactly. So Blend X-Ray parses each script with Python's `ast`
module — which builds a syntax tree and **does not execute the code** — and
translates what it finds:

```text
6 code block(s) found.
  2x  connects to the internet <-- look at this one
  1x  reads saved Python data in a format that can run code as it is being read
```

Every statement names its concrete evidence — the function called, the literal
found — so a technical friend can verify the claim rather than trust it. When
code is deliberately obfuscated, Blend X-Ray does not invent an explanation:

> I can't tell you what this does, because it is deliberately hidden. That is
> itself the strongest signal here.

## Install

**Python 3.11 or 3.12.** Not newer: `blender-asset-tracer` 1.23 predates Python
3.13, and on Python 3.14 the dependency set does not resolve at all. Create the
environment against 3.12 **explicitly**, as in [Quick start](#quick-start) above,
rather than letting the launcher pick its default — on a machine with 3.14
installed, a bare `py -m venv` gives an environment this will not install into.

`pip install .` is what gives you the `blend-xray` command. To run it out of the
checkout without installing the package, install only the dependencies — but then
the command is `python blend_xray.py`, because nothing put `blend-xray` on PATH:

```bash
pip install -r requirements.txt
python blend_xray.py scan suspicious.blend
```

The window needs nothing extra either way — it is standard-library `tkinter`, and
drag-and-drop is the one optional add-on (`pip install ".[gui]"`).

### The `blender-asset-tracer` version trap

Two things about this dependency are load-bearing, and both look like something a
tidy-minded person would "fix".

**1. It is pinned to `blender-asset-tracer==1.23`, and must stay there.** BAT 2.x
removed standalone parsing and requires a **Blender 5.1+ installation** to work.
Accepting it would turn Blend X-Ray into a tool that needs the very application
we are trying not to launch — the entire premise, gone. `blend_xray/scanner.py`
asserts the installed version at runtime and refuses to run against anything
else, so the failure is loud rather than silent.

**2. Do not use the `[zstandard]` extra.** Install `blender-asset-tracer==1.23`
and a current `zstandard` **separately**, which is what `requirements.txt` and
`pyproject.toml` both do. BAT's own extra resolves to `zstandard ^0.16`
(`>=0.16,<0.17`), and 0.16.0 is a 2021 release that **ships no wheel for Python
3.11 or 3.12**, so pip must compile it from source. On a developer machine with a
C toolchain that build succeeds — it was tried here — but on a machine without
one, which is most artists' machines, it fails and takes the whole install down.
It also pins a four-year-old decompression library and clashes with this
project's own `zstandard>=0.22`. BAT only does a plain `import zstandard` against
the stable decompression API, so a current release works and is what we pin
instead. `zstandard` itself is not optional — Blender 3.0+ writes
zstd-compressed files and you cannot read a modern `.blend` without it.

## Usage

```bash
blend-xray scan suspicious.blend           # one file
blend-xray scan ./downloads/               # a directory, searched recursively
blend-xray scan "assets/**/*.blend"        # a glob pattern
python blend_xray.py scan suspicious.blend # from a checkout, not installed
```

### Options

`--lang` and `--version` are flags on the **main** command and must come *before*
`scan`; everything else belongs to `scan` and comes after it.

| Flag | Position | Effect |
| --- | --- | --- |
| `--lang en\|fr` | before `scan` | Interface language. Detected from your OS locale when omitted, falling back to English. `blend-xray --lang en scan file.blend`; putting it after `scan` is an argparse error. |
| `--version` | instead of `scan` | Print the version and exit `0`: `blend-xray --version` → `blend-xray 0.1.0`. It is answered during argument parsing, so no subcommand is needed — an install too broken to scan can still say which build it is. |
| `--json` | after `scan` | Machine-readable output. |
| `--full` | after `scan` | Print complete script bodies. The default previews the first 1500 characters. |
| `--quiet`, `-q` | after `scan` | Banner and file path only; omit the inventory and context sections. |
| `--color auto\|always\|never` | after `scan` | Colour handling. `auto` disables colour when the output is piped. |
| `--max-seconds N` | after `scan` | Wall-clock budget for the whole scan of **each** file, default 60. If it runs out the report is a partial inventory and says so, loudly, in the banner and in the closing recommendation. |

### Exit codes

| Code | Meaning |
| --- | --- |
| `0` | Nothing found in the categories checked. |
| `1` | Findings present, or the budget ran out *during the inventory* so the file was covered only in part. |
| `2` | A file was malformed, hostile-looking, or not a `.blend` file — including a budget that ran out during the pre-flight checks, before the inventory began, since nothing was read at all. |
| `3` | Tool error: bad install, wrong `blender-asset-tracer` version, or no files matched. |

`scan` exits `1` whenever it finds anything at all, which for most real files it
will. That is the documented "findings present" code, not a failure, so do not
chain it with `&&`.

## How to read a report

Here is a real one, abridged, from a Blender Game Engine networking demo in the
measured community corpus — it genuinely does networking:

```text
+----------------------------------------------------------------------------+
| [X] This file contains code that reaches outside Blender.                  |
|     It contacts the internet.                                              |
+----------------------------------------------------------------------------+
Blend X-Ray -- bge_networked_gridland.blend
Blender file version 2.77, 8-byte pointers, not compressed, 2151 blocks.
Blend X-Ray never launches Blender and never executes anything it finds.

Checked 5 categories:
  - Python text blocks (auto-run scripts)
  - Driver expressions
  ...

6 code block(s) found.
  2x  connects to the internet <-- look at this one

--- Python text blocks (auto-run scripts) -----------------------
Text block: helpers.py
  Not marked auto-run (TXT_ISSCRIPT is not set).
  What this code does, in plain language:
    * reads saved Python data in a format that can run code as it is being read
        (evidence: pickle.loads)
  No URLs, paths or shell commands were found as plain text in this code.
  Source:
    ...
```

### 1. The banner

One box, readable in a second, because the rest of the report is not. It is
decided by what was found — never by what the file is worth.

| Tier | Colour | Fires when |
| --- | --- | --- |
| **red** | red | Something reaches outside Blender: an outbound connection, a listening port, a subprocess, a living-off-the-land binary, persistence, credential/wallet paths, low-level system modules, a UNC linked-library path — or code hiding itself, meaning decode-then-execute, a `__builtins__` lookup, a call on the value another call returned, or a name assembled out of string fragments. |
| **amber** | amber | Everything else that was found: `eval`/`exec`, a long opaque blob, a decode or decompression on its own, `compile()`, a runtime import, a pickle load, a name built by gluing string pieces together, an auto-run script that is not recognised, a script that could not be parsed, file writes, deletes and folder creation, handing a URL to your browser, a registered or `@persistent` handler, a driver needing full Python, OSL bytecode, a drive-letter library path. |
| **neutral** | grey | Neither of the above fired, and the scan finished. |

A scan that ran out of its `--max-seconds` budget is **never neutral**: the
timeout joins the amber set and gets a headline of its own, above both the amber
and the neutral wording, because "nothing found" over a scan that stopped early
is a lie. A red banner keeps its own headline — something was already found
reaching outside Blender — but the timeout still rides along in the sentence, so
the banner cannot claim a completeness it does not have.

Membership of the red set is a promise that each rule's own sentence supports
that headline, so it is machine-checked in `tests/test_banner.py` rather than
left to review. An opaque blob is deliberately *not* in it: "carries a long block
of encoded data" describes data sitting in the file, which opens no socket and is
not necessarily code — an embedded icon looks the same. It stays alarming and
spends an amber; the shape that makes a blob dangerous, decoded and then
executed, is a separate rule, and that one is red. `--quiet` keeps the banner and
drops the rest.

**There is no green tier, no tick and no "OK" symbol, and there must never be
one.** This project's own public argument is that antivirus does not inspect
`.blend` internals. A green tick on a file that later turns out to be malicious
is the one screenshot that would end its credibility, because it would be exactly
the promise we tell people not to trust from anyone else. The neutral banner is
grey, carries "this is not a clearance" and lists what was actually looked at,
which reads just as fast and promises nothing. It comes in two wordings:
*"Nothing found in the N categories checked"* when the file contains nothing at
all, and *"Nothing reaching outside Blender, in the N categories checked"* when
it holds findings that did not rise to a tier.

A byte-identical match to a published release **suppresses amber** and **never
suppresses red** — see
[The known-good identity layer](#the-known-good-identity-layer).

The box is drawn with box-drawing characters when the output stream can encode
them, and falls back to pure ASCII (`+---+`, `[X]`, `[!]`, `[-]`) when it cannot
— a stock `cmd.exe` is cp1252 and would otherwise raise `UnicodeEncodeError`.

### 2. The summary, then each block

The summary is one line per distinct headline, with a repeat count, so twenty
copies of the same rig script read as `20x` rather than twenty paragraphs. The
`<-- look at this one` marker points at the blocks that put the file in its tier.

Then, per block: what Blender will do with it (the auto-run flags), the
plain-language explanation with its evidence, the strings found inside the code
(URLs, paths, shell commands), and the raw source **last**. If you read one part,
read the evidence in brackets — that is the bit you can check yourself.

### 3. The closing recommendation

Either "ask someone who reads Python to look at this", or a note that the
alarming block is a recognised published release and which one, or "looks
ordinary" — which still is not a clearance.

### `--json`

The same decision, in language-independent keys:

```json
"banner": {
  "tier": "neutral",
  "reasons": [],
  "recognised": [],
  "timed_out": false
}
```

The document that carries it has six top-level keys:

| key | value |
| --- | --- |
| `tool` | The tool's display name. |
| `version` | The version of Blend X-Ray that produced the document — `"0.1.0"`. A stored report that cannot say which build wrote it cannot be compared with a later one. |
| `schema` | The shape of the document: `1`. It moves independently of `version`; **adding a key does not change it**, so `version` changing and `schema` staying at `1` is the normal case. |
| `lang` | `"en"` or `"fr"` — which catalogue produced the human-readable `text`/`message` fields. Every `key`, `severity` and identifier is language-independent; those two field families are not. |
| `files` | One object per scanned file, each with its `banner` attached. |
| `errors` | Files that could not be read, with the reason. |

`tier` is one of `red`, `amber`, `neutral`; `reasons` are the stable rule keys
that chose it; `recognised` names any published release recognised among the
blocks that caused a red banner; `timed_out` is `true` when the scan hit its
`--max-seconds` budget, and the file object beside it also carries `timed_out_at`
and `time_budget`.

**One caveat if you pipe `--json` somewhere.** The human-readable report escapes
terminal control characters that came out of the scanned file, so a file cannot
forge or hide lines of the report (see `blend_xray/sanitise.py`). Three JSON
fields are deliberately *not* escaped that way — `source`, `raw_path` and
`expression` are byte-exact, because a consumer that hashes or diffs them needs
them byte-exact. `json.dumps` escapes them at the JSON syntax level, so the JSON
text itself can be printed without that risk, but if you decode it and print one
of those fields directly (`jq -r '.files[0].texts[0].source'`) you are printing
attacker-controlled bytes straight at your terminal. Pipe it through `cat -v`, or
use the normal report, which already does this for you. The provenance fields
from the known-good database are *not* in that exemption: they are stripped at
load time and escaped again on the way out, because a database field must not be
able to repaint the report around it.

## Measured on real files

The alarm rate decides whether a tool like this gets used or ignored, so it was
measured rather than estimated. The figures below come from a **677-file
campaign** run against the current code. They replace an earlier 102-file
measurement — the two corpora in [docs/IDENTITY.md](docs/IDENTITY.md), 101 of
whose files were scannable — which was too small to carry the claims that were
resting on it.

### How the corpus was assembled

**677 distinct `.blend` files**, deduplicated on SHA-256, were downloaded from
public sources, scanned one at a time and deleted immediately — disk never held
more than one file. Nothing was opened in Blender. No account was created and no
login was used anywhere, which is why Blend Swap is absent: it requires an
account to download.

Three independent lanes, because each is biased in a different direction and
three biases agreeing is worth more than one deepened:

| lane | files | how it was assembled |
| --- | ---: | --- |
| **GitHub, by file path** | 205 | Code search for `.blend` files by path, across 70 repositories, capped at 15 files per repository. Deliberately steered toward shader and OSL repositories — that is where all 20 OSL-carrying files came from. |
| **GitHub, by repository topic** | 202 | Repositories harvested by Blender-related topic (game engines, add-ons, rig libraries, asset dumps), 61 of them, then walked for `.blend` files. This is the lane that reaches hobbyist game-engine work, where embedded Python is ordinary. |
| **blender.org, OpenGameArt, Poly Haven** | 270 | blender.org's own demo, splash, test and `old_demos` archives (217), OpenGameArt.org (28), Poly Haven CC0 models (25). This lane reaches back to the oldest published `.blend` files in existence. |

The two GitHub lanes were **deliberately biased toward files likely to contain
Python**. A corpus of static props would have proved nothing. The bias worked:
208 of the 677 files carry at least one text datablock, 547 blocks in total,
alongside 12,328 driver expressions and 148 linked libraries. Judge the numbers
with that in mind — this is a sample of freely published, legitimate work, so it
says something about false alarms on ordinary files and **nothing about
detection**, because none of these files is malicious.

### The numbers

| | count |
| --- | ---: |
| distinct files | **677** |
| parsable | **578** |
| refused before analysis | **99** |
| crashes, hangs, tool errors | **0** |
| files that raised "needs a human" | **21** — 3.6% of the parsable files |
| files carrying OSL script nodes | **20** |
| distinct Blender file versions among the parsable files | **48** — 2.45 through 5.03 |

**Banner tier, over the 578 parsable files:**

| lane | neutral | amber | red |
| --- | ---: | ---: | ---: |
| GitHub by file path (189 parsable) | 183 | 6 | 0 |
| GitHub by repository topic (202) | 174 | 27 | 1 |
| blender.org / OpenGameArt / Poly Haven (187) | 180 | 7 | 0 |
| **total (578)** | **537** | **40** | **1** |

The single red is a Blender Game Engine example file that imports `ctypes`. That
is what licenses the red tier to be loud: across 578 legitimate files the rules
in it fired on one, and that one genuinely did the thing the banner said. Read
the amber column honestly, though — 40 of 578 files show an amber banner. Amber
asks you to do nothing; it says something was found and is worth a glance. The
tool is not silent on legitimate work and is not meant to be.

**That column read three before this campaign, and the two it lost were both
false alarms the campaign found.**
`MolecularNodes/node_data_file.blend` was red because a local variable named
`socket` — which is what Blender's own node-socket type is called — was read as
the `socket` module. `DmrVBM-blender-to-gms2/poppie_vbm.blend` was red because a
`zlib` call and an `exec` appeared in the same file and were treated as one
hidden payload, when the `zlib` calls compress mesh and image data and never go
near the `exec`. Both were false, both are amber now, and both have regression
tests: `tests/test_call_grounding.py` and `tests/test_obfuscation_link.py`.

### The 99 refusals, and the version floor

Nothing crashed and nothing hung. The 99 files that produced no report were
refused, and the refusals break down like this:

| reason | files |
| --- | ---: |
| no `DNA1` block in the file | 80 |
| does not start with the `BLENDER` magic bytes — not a Blender file at all | 14 |
| truncated mid-header, or too small to be a `.blend` | 2 |
| unreadable by the harvesting script at the moment it was scanned (a file-lock race in the collector, not in the tool) | 3 |

**The 80 are a real limitation and it is worth stating plainly rather than
having a critic find it: Blend X-Ray cannot read a `.blend` written before
Blender 2.45.**

Those 80 files are not damaged. Magic bytes intact, header intact, `ENDB`
terminator present — they are ordinary, uncorrupted Blender files that Blender
itself would still open. What they do not contain is an SDNA (`DNA1`) block, in
which Blender writes down the layout of every struct it has just saved. That
block is the foundation of everything this tool does: it is what lets Blend
X-Ray locate a `Text` datablock's body, a `Library` path or a `ChannelDriver`
expression in a file written by a Blender version it has never heard of. Blender
did not always write one. The SDNA system arrives around 2.45, and in a file
older than that there is nothing to read — so the scan stops with
`No DNA1 block in file` rather than guessing at hard-coded per-version byte
offsets on files nobody can check. Refusing is the correct behaviour; not
documenting the refusal was not.

Measured over the campaign, with no overlap in either direction:

- the lowest file version that **parsed** is **2.45**;
- the highest file version that was **refused** is **2.42**;
- all 80 refusals carry a header version between **1.28 and 2.42**;
- the oldest file reached in testing carries a **Blender 1.28** header, from
  blender.org's own `old_demos` archive — which is where most of the 80 came
  from, and the reason this lane found the floor at all.

So the floor is **2.45**, not "2.4x". A 2.40, 2.41 or 2.42 file is refused like
any other pre-SDNA file. There is no workaround inside Blend X-Ray: the only
route to inventorying such a file is to open it in a Blender old enough to load
it and re-save, which is precisely the thing this tool exists to let you avoid.
Treat it as a hole, not a procedure.

## What it detects

Five categories, each inventoried from the file's own DNA rather than guessed:

- **Auto-run scripts** — text datablocks, and whether Blender is set to run them
  on load (`TXT_ISSCRIPT`). This is the CGTrader vector.
- **Driver expressions** — classified into those Blender's restricted C evaluator
  handles and those needing full Python, because only the second kind is a code
  path. The second kind gets the same explanation engine a script does.
- **OSL / script nodes** — reported at lower severity and explicitly not as an
  auto-run vector: they are Cycles-only, off by default, and run at render time.
- **Linked libraries** — absolute paths, `..` escapes, UNC network paths (host
  named) and drive-letter paths.
- **Other file paths** — images, sounds, fonts, caches, movie clips.

Field names, flag values, the transcribed simple-expression grammar, and the
guards that run before any of this — header validation, the block-table walk, the
decompression cap, the time budget — are in
[docs/DETECTION.md](docs/DETECTION.md).

## The known-good identity layer

Real rig files legitimately do alarming things. On the institutional corpus,
nineteen files carried the *same* script — Blender Studio's `cloudrig.py`, which
genuinely calls `eval()` — and asking one artist to review it nineteen times is
how a true positive gets trained into background noise. So Blend X-Ray carries a
database of script **identities**.

### The rule: entries record identity, never safety

An entry says:

> this block is byte-identical to `cloudrig.py` as shipped in *this* published
> file, fetched from *this* URL on *this* date, attested by *this* person.

It never says, and may never be reworded to say, "this script is harmless". The
first claim is verifiable by anyone, forever — re-download, re-extract, re-hash.
The second would become false the day somebody finds a bug in CloudRig, and we
would have signed it. Several of the scripts recorded in the database really do
call `eval()` or `exec()`, and Blend X-Ray still reports that at full severity
for every one of them.

**A match never removes, hides or downgrades a finding.** It adds context and,
for byte matches on shared releases only, changes which closing recommendation is
printed. There are two kinds of match — byte-identical, and
same-structure-different-literals — and only the first can stand a block down.
The reasoning behind that asymmetry, and what a corrupt database costs, is in
**[docs/IDENTITY.md](docs/IDENTITY.md)**.

### The database

`blend_xray/known_scripts.json`. A plain JSON file in the repository, readable
and re-verifiable by anyone, not a binary and not generated at install time. It
currently holds **20 entries**, at **schema version 2**.

```json
{
  "schema": 2,
  "entries": [
    {
      "sha256": "73890850112239c7d7d9368eee07aaa4098dfc84dbb8c213ab8e0c556760dd11",
      "script_name": "cloudrig.py",
      "byte_size": 66599,
      "origin": "CloudRig rig UI script, Blender Studio -- the copy embedded in the Sprite Fright open-movie shot 030_0020_A",
      "source_url": "https://download.blender.org/demo/sprite_fright_030_0020_A.zip#030_0020_A/lib/scripts/cloudrig.blend",
      "fetched_on": "2026-08-23",
      "attested_by": "Blend X-Ray maintainer (sole attester; not independently confirmed)",
      "attested_on": "2026-08-23",
      "notes": "The user-interface script CloudRig writes into a .blend when it generates a rig ... It calls eval() twice, on the 'op_<property>' and 'prop_hierarchy' custom properties stored on a bone in the same file ...",
      "generated": false
    }
  ]
}
```

All ten fields above are **required**; the loader reports an entry missing one,
or carrying one of the wrong type, as malformed rather than believing it.

| field | meaning |
|---|---|
| `sha256` | SHA-256 of the script body: the UTF-8 encoding of the text datablock's lines joined with `\n`, blank lines included. That is exactly how Blender stores and reloads a text block, so this is a hash of the file's real content and anyone who re-extracts the block gets the same digest. See the re-verification recipe below. |
| `script_name` | The datablock's name, as it appears in the report. |
| `byte_size` | Length in bytes of that same UTF-8 body, which is also the scanner's `source_bytes`. |
| `origin` | Project or product and, where a version exists, which one. |
| `source_url` | Where the containing file was fetched from. A `#member/path` fragment names a member inside a zip. |
| `fetched_on` | When it was fetched, ISO date. |
| `attested_by` | Who vouches that this hash is that script. **Currently one person, with no second reviewer and no signature.** |
| `attested_on` | When they vouched, ISO date. |
| `notes` | What the script is and what it legitimately does — including the behaviours that trigger Blend X-Ray's own rules, said plainly. |
| `generated` | Required boolean. `true` when the script is written afresh for each `.blend`, so a byte match identifies one generated copy rather than a shared release. Only `false` entries may stand a block down. Must be a real JSON boolean, and must not be `false` on an entry that also carries a `structure` block. |
| `structure` | Optional, and only on a `generated` entry. `{"scheme": 1, "sha256": ..., "literals": [...]}`. `literals` is the reference body's string-literal values in canonical order; a candidate's are compared against it position by position. |

A missing, corrupt, or half-broken database costs identity context and nothing
else: the scan still runs, the report still renders, and the reason the database
was skipped is printed rather than swallowed. It also has a size ceiling (8 MiB),
an entry-count ceiling (20 000) and a per-entry literal-count ceiling (200 000).

### Re-verifying an entry yourself

You need nothing but Python and the URL in the entry.

1. Download the file named by `source_url`. If the URL has a `#` fragment, it is
   a zip: extract that member.
2. Extract the script body with Blend X-Ray itself and hash it:

   ```bash
   blend-xray scan the-file.blend --json > out.json
   python -c "import hashlib,json,sys; d=json.load(open('out.json')); \
   [print(hashlib.sha256(t['source'].encode()).hexdigest(), t['name']) for t in d['files'][0]['texts']]"
   ```

   (`scan` exits 1 whenever it finds anything at all, which it will here. Do not
   chain the two commands with `&&`.)

3. Compare against `sha256` in the entry. If it matches, the entry's identity
   claim is true and you have checked it without trusting anybody.

Run against the *Sprite Fright* `cloudrig.blend` named in the example entry
above, step 2 prints
`73890850112239c7d7d9368eee07aaa4098dfc84dbb8c213ab8e0c556760dd11 cloudrig.py`.
You do not have to take Blend X-Ray's word for the extraction either: the same
body comes out of `blender-asset-tracer` on its own, with no Blend X-Ray code in
the path, and hashes to the same digest:

```python
import hashlib
from blender_asset_tracer.blendfile import BlendFile

bf = BlendFile("the-file.blend")
for block in bf.find_blocks_from_code(b"TX"):
    parts, line = [], block.get_pointer((b"lines", b"first"))
    while line is not None:
        ptr = line.get_pointer(b"line")
        parts.append("" if ptr is None else ptr.as_bytes_string().decode("utf-8", "replace"))
        line = line.get_pointer(b"next")
    body = "\n".join(parts).encode("utf-8")
    print(hashlib.sha256(body).hexdigest(), block.id_name.decode()[2:])
bf.close()
```

That loop is the whole definition of the hashed body: one `TextLine` per line,
newlines stripped by Blender on load and put back on join, and **every** line
kept — a blank line is a `TextLine` holding the empty string, not the absence of
a line. All 161 text datablocks across the two measured corpora come out
byte-identical from the two routes.

Note what this does and does not establish. It establishes that the recorded hash
really is that script from that source. It establishes nothing about whether the
script is worth running — for that, read the body, printed in the report and
described by the `notes` field.

### Contributing an entry

See [CONTRIBUTING.md](CONTRIBUTING.md), which covers the required provenance,
where the body must come from, how to set `generated`, and why a database entry
is treated as a security-relevant change.

## Privacy

No network calls. No telemetry. No auto-update — in the CLI and in the window
alike. Blend X-Ray reads the file you point it at and writes nothing except its
report. The single exception is opt-in, confirmed, and shown to you in full
before it happens: the window's "Add to right-click menu" button writes two keys
under `HKEY_CURRENT_USER`. See [docs/GUI.md](docs/GUI.md).

**In the frozen exe, that is now backed by what is in the file.** The build used
to sweep the whole `blender_asset_tracer` package, which dragged in BAT's
*upload* client and with it `requests`, `urllib3`, `certifi`, `idna` and
`charset-normalizer`, plus `_ssl.pyd` and `libssl-3.dll` — a complete HTTP and
TLS stack inside a tool whose documentation says it makes no network calls. The
behaviour was always the documented one; the bundle contradicted it, and a
shipped contradiction gets published rather than reported. The sweep is now
scoped to `blender_asset_tracer.blendfile`, the one subpackage this project
imports, and none of those components appears in the build's table of contents
any more.

Two things that sound like they should have gone with them did not, and saying
"no OpenSSL at all" would be false:

- **`libcrypto-3.dll` is still in the exe.** It is pulled in by `_hashlib.pyd`,
  which backs `hashlib`, which the tool uses to take the SHA-256 of a script for
  the known-good database. That is OpenSSL's cryptography library. What is gone
  is the TLS half: `libssl-3.dll`, `_ssl.pyd` and `certifi`'s `cacert.pem` are
  all absent, and so is the `ssl` module — the TLS implementation CPython would
  otherwise reach for is not in the file.
- **`_socket.pyd` is still in the exe.** Nothing in Blend X-Ray opens a socket.
  It arrives because the standard library's `platform` module imports `socket`,
  and so does `email.utils`, which `importlib.metadata` uses to parse the
  `blender-asset-tracer` metadata that the version guard reads. It is present in
  the file; no HTTP client and no TLS stack is present to use it.

You do not have to take that on trust. The frozen contents of any build are
listable:

```powershell
python -m PyInstaller.utils.cliutils.archive_viewer --list --brief BlendXRay.exe
```

## The downloadable executable, and why it is unsigned

**Two artefacts ship: this source, and a Windows zip.** The zip — seven flat
entries: `BlendXRay.exe`, the two readmes, `LICENSE`,
`THIRD-PARTY-LICENSES.txt`, `SOURCE.txt` and a demonstration `.blend` — is
published on Gumroad — pay what you want, 0 EUR minimum — and on the author's
own site. `blend-xray.spec` and `build_exe.ps1` are in the repository, so you
can build the identical thing yourself instead.

**The source is the primary artifact.** If you would rather not trust a binary —
and you should not have to — clone the repository, read it, and run it. The
whole tool is small enough to audit in one sitting, which is the point. The zip
exists because the people most exposed to a booby-trapped rig are students and
hobbyists who will not create a virtualenv to check one download, and a tool
nobody can run protects nobody.

**`BlendXRay.exe` is not code-signed.** Windows SmartScreen shows "Windows
protected your PC" the first time it runs on a machine, and you have to click
"More info" → "Run anyway", once per machine. A signing certificate costs
roughly 200–400 EUR a year and ties the binary to a legal identity; that is
deferred, not refused. Buying one would not remove the warning immediately in
any case — SmartScreen's reputation score only accumulates once a binary has
been downloaded a great many times.

**Your antivirus may also object, and may quarantine the download outright.** An
unsigned PyInstaller one-file executable is a shape a lot of engines treat as
suspicious on its own, and the zip additionally contains a demonstration `.blend`
whose sample script holds the literal text `powershell -NoProfile -WindowStyle
Hidden -Command` next to `urllib.request.urlopen` — many scanners read inside
archives and will react to those strings. That is a heuristic firing on what the
demonstration file is *for*, not a second opinion about the tool. If it happens
and you would rather not argue with your scanner, take the source route below
instead; do not add a blanket exclusion for a folder just to make a warning go
away.

That warning is stated up front on the download page and in both readmes inside
the zip, before anyone double-clicks, rather than left to be discovered. Running
an unverified executable you downloaded from the internet is the exact thing
this tool exists to warn you against, and that does not stop applying to this
tool's own download. What the warning means is that Windows does not recognise
the publisher; it says nothing about what is in the file. The digests are
published so you can at least confirm you have the file that was built, and the
source is here so you never have to take the binary's word for anything.

## Translations

Every user-facing string lives in a catalogue, behind a `t()` lookup: English in
`blend_xray/strings_en.py`, French in `blend_xray/strings_fr.py`, wired together
in `blend_xray/strings.py`. That includes every label, button and dialog in the
window — nothing is hardcoded in the GUI modules. Adding a language is a data
change: add a module and one entry to `CATALOGUE`.
`tests/test_gui.py::test_no_catalogue_string_says_safe_in_any_language` holds the
*whole catalogue*, in every language, to the never-say-safe rule — not just the
strings that happen to appear in a scan report. It has already caught one real
slip: a French dialog that used "propre" in its "your own account" sense.

## Licence — why GPLv3 and not MIT

**Copyright (C) 2026 Sacha Geneviève. Blend X-Ray is licensed GPLv3-or-later.**
See [LICENSE](LICENSE) for the full text and [COPYRIGHT](COPYRIGHT) for the
notice GPLv3 asks every program to carry. It comes with **no warranty**, to the
extent permitted by law.

The Windows zip also ships `THIRD-PARTY-LICENSES.txt`, reproducing the licence
and copyright notices of everything the executable bundles — several of those
licences require it in a binary redistribution. Its source is
[bundle/THIRD-PARTY-LICENSES.txt](bundle/THIRD-PARTY-LICENSES.txt).

This is a consequence, not a preference. Blend X-Ray imports
`blender-asset-tracer`, which is **GPLv2-or-later**. A work built on and linking
against a GPL library is a derivative work and must be distributed under
GPL-compatible terms. MIT would not be compatible. GPLv3 is, because
GPLv2-or-later permits redistribution under GPLv3. Saying so plainly matters more
than a licence header: anyone deciding whether to reuse this code needs to know
the constraint comes from a dependency they will also inherit, not from a
preference they could talk the author out of.

Practically, for a teacher handing this to students: you may use, study, modify
and share it freely, including in class, provided derivatives stay under the same
licence and ship their source.

### Trademarks

Blender is a registered trademark of the Blender Foundation. Blend X-Ray is an
independent project, not affiliated with or endorsed by it. The name deliberately
uses the file extension `.blend` rather than the mark itself, and should stay
that way.

## Development

```bash
py -3.12 -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
python -m pytest              # 798 passed, 6 skipped on a clean clone
python -m ruff check .
```

`tests/blend_builder.py` builds valid `.blend` files **from scratch**, including
a hand-written SDNA (DNA1) block, so the suite runs offline and deterministically.
No real malware sample is used, fetched, or required by any test — the hostile
scripts in `tests/test_explain.py` are written by hand and never executed. See
[CONTRIBUTING.md](CONTRIBUTING.md) for conventions and for how to contribute a
known-good database entry, and [SECURITY.md](SECURITY.md) for how to report a
vulnerability privately.

## What was and was not verified

Honesty about the limits of the testing matters more than a tidy-looking claim,
so:

**Verified by actually running it:**

- `pip install blender-asset-tracer==1.23 zstandard>=0.22` succeeds on Python
  3.12. `blender-asset-tracer[zstandard]==1.23` has **no wheel** for 3.11 or 3.12
  and must compile zstandard 0.16.0 from source; on this machine, which has a C
  toolchain, that build *succeeded*. The failure on a compiler-less machine is
  reasoned from that, not observed here — but the four-year-old pin and the clash
  with this project's `zstandard>=0.22` were observed, and are reason enough to
  split the dependency.
- **An install from scratch, in a fresh checkout**: a new 3.12 virtual
  environment in an empty directory, `pip install .`, then `blend-xray scan` on a
  real third-party `.blend` — the console entry point resolves and the report
  renders. The
  `pip install -r requirements.txt` route was checked separately; it deliberately
  does *not* create the `blend-xray` command.
- The full test suite: **798 passed, 6 skipped** on a clean clone, and **803
  passed, 1 skipped** with `BLEND_XRAY_CORPUS` pointed at a directory of
  blender.org demo files. One skip asserts off-Windows behaviour of the
  registry toggle; the other five need those third-party files, which are not
  redistributed here.
- `ruff check`: no findings.
- **The identity layer against both real corpora.** 102 third-party `.blend`
  files were re-scanned before and after seeding the database, and every file's
  inventory was compared block by block: no file that was ordinary became
  alarming, and no text block lost a finding, a severity, a parse state or an
  extracted literal.
- **The alarm and banner-tier rates** in
  [Measured on real files](#measured-on-real-files), re-measured on the current
  code by scanning every corpus file and tallying the result.
- **The window, driven for real**: built, scanned a hostile synthetic file,
  rendered the report into the widget, expanded and re-collapsed a raw-source
  toggle, switched to French and back, copied the report to the clipboard, and
  ran the cancel path. Both drag-and-drop states were exercised — with
  `tkinterdnd2` and without — and a `<<Drop>>` event carrying a path with spaces
  was parsed correctly.
- **The packaged executable**: `dist\BlendXRay.exe` built, launched on a `.blend`
  argument, and confirmed to open a window titled "Blend X-Ray 0.1.0" — the tool
  name and the version, which is how a user of the zip answers SECURITY.md's
  "which version are you on". Its VERSIONINFO resource was read back off the
  built file: *Properties* → *Details* now shows `0.1.0` under both *File
  version* and *Product version*, where it used to be blank. Its
  runtime bundle does contain `blender_asset_tracer-1.23.dist-info`, which is
  what `scanner.assert_bat_version()` reads — without it the frozen build would
  refuse to run.
- Parsing a real, third-party Blender 2.79 `.blend` file (1244 blocks) — confirms
  header parsing, block-table walking and DNA struct lookup against a file Blend
  X-Ray did not create — and synthetic Blender-4.04-shaped files exercising every
  detector.

**Not verified:**

- **OSL script nodes are now seen in real files, but thinly and from one kind of
  source.** The earlier 102-file measurement found zero `NodeShaderScript`
  datablocks; the 677-file campaign found **21 nodes across 20 files** — and they
  came from two repositories that exist to publish OSL shaders, not from ordinary
  work. Nearly all are `NODE_SCRIPT_EXTERNAL`, pointing at a sibling `.osl` file
  that Blend X-Ray reports by path and deliberately does not open; exactly one
  file carries `NODE_SCRIPT_INTERNAL` with compiled bytecode present, which is
  the case the tool cannot read by construction and says so. So the category is
  no longer untested — but "20 files from two shader repositories" is not a
  sample of what an artist downloads, and the synthetic builder in
  `tests/test_osl.py`, which drives all three shapes end to end, is still doing
  most of the work. `Text`, `Library` and `ChannelDriver` are exercised far more
  heavily: 547 text datablocks and 12,328 driver expressions across the campaign.
- **The structural matcher has never fired on a second real copy.** Its whole
  purpose is Rigify's per-rig `rig_ui.py`, and the corpora contain exactly one,
  which is the reference itself and therefore matches on bytes. The structural
  path is covered by tests — including one that injects a URL into a literal and
  asserts it is surfaced and still escalates — but the claim that a *different*
  real Rigify rig matches this reference structurally is reasoned, not observed.
- The real 2.79 file tested contained no `TX` or `LI` blocks, so the 2.79-era
  field-name fallbacks (`name` instead of `filepath`) are reasoned from the
  Blender source, not exercised end to end.
- **The published executable was checked through a console-mode twin, not by
  running the shipped window.** The shipped `BlendXRay.exe` is built
  `console=False`, so it cannot be driven from a command line to have its output
  read. What was verified is a second executable built from the same spec rules
  and the same source, with `console=True` and the CLI as its entry point: it
  scans the bundled demonstration file to a red banner, an ordinary `.blend` to
  the neutral banner, and a non-`.blend` to exit code 2. Both frozen builds were
  also listed with PyInstaller's archive viewer, and both contain
  `blend_xray/known_scripts.json` (55,455 bytes, the same as the source file) and
  `blender_asset_tracer-1.23.dist-info/METADATA` — so the identity database ships
  and `scanner.assert_bat_version()` can read the metadata it refuses to start
  without. The window's own behaviour on those same files is inferred from the
  shared code path, not observed.
- Behaviour against a genuinely malicious sample. None was obtained, by design.
- **A real mouse drag onto the window.**
- **The right-click entry has never been written to a real registry, and the
  Explorer menu item has never been observed working.** What changed is narrower
  than it sounds: `install()` and `uninstall()` are now executed in the test
  suite, against an in-memory stand-in for `winreg` that records writes instead
  of making them — the fresh install, the stale entry repaired in place, the
  uninstall, and the read-failure and write-failure paths. The real `HKCU` key
  was confirmed absent after those runs, so "nothing was written" is a check
  rather than an assumption. None of that observes Windows: the keys the code
  creates are still reasoned from the Windows documentation, and nobody has
  right-clicked a `.blend` file and watched the entry work. See
  [docs/GUI.md](docs/GUI.md).
- **The exe was not run on a machine other than the one that built it**, so the
  SmartScreen warning described above is the documented behaviour for unsigned
  binaries rather than something seen here, and neither is the antivirus
  behaviour: no scanner other than this machine's has been shown the zip.
- The window was not tested on macOS or Linux, and the install was not tested on
  Python 3.11 — only on 3.12.

## What static analysis cannot do

This section is here because a critic should not be the first person to say it.

Blend X-Ray reads a `.blend` file's Python without running it. That is the whole
point — running it is the thing we are trying to avoid — and it is also a hard
ceiling on what the tool can know. **A determined author can write a script Blend
X-Ray will not describe correctly, and no amount of rule-writing changes that.**

Concretely, the tool works by recognising *names*: `urllib.request.urlopen`,
`subprocess.Popen`, `os.system`. Python lets you reach any of those without
writing its name down:

```python
g = getattr
i = g(__builtins__, '__imp' + 'ort__')      # __import__ never appears
m = i('url' + 'lib.request')                # nor does urllib.request
g(m, 'url' + 'open')(url).read()            # nor does urlopen
```

Every name a rule looks for has been split across `+`, and the calls happen
through values rather than through names. Nothing in the name tables matches.

**What Blend X-Ray does about it, and what that is worth.** It reports the
*shape* of the hiding rather than pretending to see through it: reaching into
`__builtins__` by name, calling the value another call returned, assembling the
name of what you import or call out of separate pieces. Each is its own finding
with its own sentence, and each says what the code is arranging — never what it
will do, because once the names are gone that cannot be known, and guessing is
the failure this tool exists to avoid. The three rules are loud because they are
measured: across the 100 parseable script bodies in the two corpora of real,
legitimate `.blend` files, every one of them fires zero times.

That raises the cost of hiding. It does not close the door:

- **One more level of indirection defeats it.** Alias resolution here follows
  plain rebindings (`g = getattr`) and one assignment from a builtins lookup. A
  name assembled from a list comprehension, a dict lookup, a decoded blob or an
  arithmetic sequence of character codes resolves none of it. Real dataflow
  analysis of hostile input is not a fight a report generator wins.
- **The literals are the same story.** A URL split across a loop, or built from
  `chr()` calls, will not appear in the literals list.
- **A block that does not parse is not analysed.** Blend X-Ray falls back to a
  plain-text sweep and says so, and marks the block as unread if Blender would
  have run it — but a syntax error is a place the rules did not reach.
- **Anything outside the file is invisible.** External `Text` blocks, external
  OSL, and linked libraries are reported by path and never followed or read.
- **Data-driven behaviour is invisible.** `pickle.load()` is reported, and what
  it actually executes lives in a data file this tool does not open.

So a report with nothing alarming in it means the rules found nothing, over the
parts they could read. It is not a clearance, the banner says so in those words,
and that wording is deliberate.

## Known gaps

These are real coverage holes, listed so nobody mistakes silence for absence:

- **A `.blend` written before Blender 2.45 cannot be read at all.** It carries no
  SDNA (`DNA1`) block, and every detector in this tool works by reading the
  file's own struct layout out of that block, so there is nothing to walk. The
  scan stops with `No DNA1 block in file` and reports nothing — not "nothing
  found", but a refusal. Measured over the corpus: 80 intact, uncorrupted files
  with header versions from **1.28 to 2.42**, all refused; **2.45** is the lowest
  version that parses. Full explanation, and why refusing is the right answer, in
  [The 99 refusals, and the version floor](#the-99-refusals-and-the-version-floor).
- **Geometry Nodes** are not inventoried at all.
- **Video Sequence Editor strips** — `Sequence`/`Strip` filepaths are not
  inventoried. Sound *datablocks* are, but VSE strip paths are a separate field.
- **Packed files** (`PackedFile`) are detected only indirectly; their contents are
  not extracted or inspected.
- **Node group / node tree names** are not resolved, so an OSL finding reports
  `<shader node tree>` rather than the specific tree. Nor is the Text block an
  internal script node uses: the link is on the owning `bNode`, not on the
  `NodeShaderScript` this tool reads, and the report says so instead of naming
  one. A driver whose owning `FCurve` cannot be located likewise reports
  `<unattached driver>` instead of an RNA path.
- **External** `Text` and OSL files (`TXT_ISEXT`, `NODE_SCRIPT_EXTERNAL`) are
  reported by path only. Blend X-Ray deliberately does not follow paths off the
  scanned file and does not read them.
- Custom properties (`IDProperty`) are not inspected.
- Blend X-Ray does not detect malicious *data* — only code and paths.

In the known-good identity layer specifically:

- **Every entry rests on one person's word.** There is no second reviewer, no
  signature, no transparency log. `attested_by` says so on every line it prints.
  An attacker who could edit `known_scripts.json` in an installed copy could add
  their own script's hash and stand it down; the file's integrity is the
  integrity of the install, and nothing more.
- **The database is small and Blender-Studio-heavy.** 20 entries, seeded from two
  measured corpora. A script it does not know is simply unrecognised, which is
  the correct default, but do not read broad coverage into it.
- **Structural entries pin one revision.** The Rigify entry describes the
  `rig_ui.py` revision found in one published file. Other Rigify revisions have a
  different structure and will not match it.
- **`origin` and `notes` are not translated.** The wording around them is, in
  every language, but the recorded facts are stored once, in English, because
  they transcribe what a source says rather than being interface prose. A French
  reader gets a French report with two English sentences of provenance in it.

The window has gaps of its own — cancellation granularity, no pagination for
folders of hundreds of files — listed in [docs/GUI.md](docs/GUI.md).

A finding of "nothing" from Blend X-Ray means "nothing in the categories above".
It never means the file is fine.
