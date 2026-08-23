# The known-good identity layer — why it exists and how it behaves

Background detail for the layer that recognises published scripts. The
[README](../README.md) carries the rule it rests on, the database schema and the
recipe for re-verifying any entry yourself; this file has the reasoning and the
measurements behind it.

## The problem it solves

On the 55-file institutional corpus, Blend X-Ray originally raised its top-level
"needs a human" recommendation on **20 files, 36.4%**. Every one of those alarms
was a true positive. Nineteen of them were *the same script*: Blender Studio's
`cloudrig.py`, which genuinely calls `eval()` on a custom property stored in the
file.

That is the failure this layer exists to fix. Twenty true positives an artist
cannot act on teach the artist to ignore the tool, which is exactly the outcome
Blend X-Ray was written to prevent.

## The two kinds of match

**Byte-identical** — strong evidence. Every byte of the block matches a recorded
copy; one changed character breaks it. This is the only match that stands a block
down from the "needs a human" branch, and the reasoning is about readership, not
about the code: a release many thousands of people have downloaded and read is
not something one artist alone can usefully be asked to review at midnight. The
report then prints a different closing paragraph naming the origin, and leaves
the artist one judgement to make — whether that origin is somewhere they would
knowingly take a file from.

**Same structure, different text in the quotes** — medium evidence, and it stands
nothing down. Blend X-Ray parses the script, replaces every string and bytes
literal *value* with a typed placeholder, keeps everything else, and hashes that.
This is what makes Rigify's `rig_ui.py` recognisable at all: Rigify writes a
per-rig `rig_id` into it, so its byte hash differs in **every single file** that
contains it and no byte database will ever match it.

A structural match is deliberately weaker, and it is weaker in the direction that
matters: an attacker can keep a well-known script's structure and change only its
string literals, which is precisely where a payload URL would sit — and, as the
CGTrader campaign showed, precisely where an attacker aims. So a structural match
reports **every literal that differs from the reference**, side by side, and the
file keeps escalating. Done right this is *more* informative than a byte match:
an injected URL becomes the one thing highlighted on screen.

There is one further restriction. An entry declares, in a `generated` field of
its own, whether the script is written afresh for each `.blend`. Matching such a
body byte for byte identifies *that one generated copy* — which precisely one
person has ever downloaded — so the readership argument that justifies standing a
block down is simply not available, and it keeps escalating. The report says so
in as many words.

That field used to be *derived*, from whether the entry carried a structural
form. The reasoning was that a structural form is only needed when the bytes
differ in every copy — true one way round and false the other. The database holds
an older, per-file generated CloudRig UI script with `script_id = "gabby"` baked
into it and **no** structural form, because only one copy was ever recorded and
nothing was generalised from it; the derivation read that as a shared release and
let it stand a block down. It is declared data now, and the loader refuses an
entry whose declaration contradicts what it carries: a `generated` that is not a
JSON boolean, or a `false` alongside a structural form, is reported as a
malformed entry rather than believed.

**No match** — Blend X-Ray says nothing about identity. An unrecognised script is
not thereby suspicious; it is unrecognised.

## How a match interacts with the banner

A byte-identical match to a published release **suppresses amber** and **never
suppresses red**.

Suppressing amber is defensible: "thousands of people have downloaded and read
this exact script" is a real answer to an `eval()` in a rig UI, and asking one
artist to review CloudRig twenty times over one rig collection is how a true
positive gets trained into background noise.

Suppressing red is not. Popularity is not an argument for hiding from a user that
a file talks to the internet, launches a program, or conceals its own code — a
compromised release, a typosquatted copy or a stale database entry all look
exactly like a match, and the cost of being wrong is the machine. When a
recognised script does trigger red, the banner stays red and *names* the
recognition beside it, so the reader gets both facts instead of one.

The match must be byte-identical for either effect, because a structural match's
whole weakness is that the string literals can be swapped while the shape holds.

## What a corrupt database costs

A missing, corrupt, or half-broken database costs identity context and nothing
else: the scan still runs, the report still renders, and the reason the database
was skipped is printed rather than swallowed. A database that loaded nothing
always says why.

That contract is enforced rather than assumed. A security review of this layer
found two inputs where it did not hold — a JSON number over CPython's 4300-digit
integer-conversion limit raises a bare `ValueError` out of `json.loads` (not a
`JSONDecodeError`), and deeply nested JSON raises `RecursionError` — and both
escaped the precise `except` tuple, propagated past `scan_file`, and aborted an
entire batch run. Both are now regression tests.

The file also has a size ceiling (8 MiB), an entry-count ceiling (20 000) and a
per-entry literal-count ceiling (200 000); a failed load is cached so a batch
scan diagnoses it once rather than once per file; and every provenance string is
stripped of terminal control characters at load time and escaped again on the way
out, because a database field must not be able to repaint the report around it.

## Measured effect

Re-running both corpora after seeding 20 entries:

| corpus | files | "needs a human" before | after |
|---|---:|---:|---:|
| institutional (first-party) | 55 | 20 — **36.4%** | 0 — **0%** |
| community | 47 (46 scannable) | 2 — **4.3%** | 2 — **4.3%** |

The community corpus is deliberately a control: only its recurring benign bodies
were seeded, so its rate is expected to stay put, and it does. A regression sweep
over all 102 files confirms no file that was ordinary became alarming, and no
text block lost a finding, a severity or an extracted literal.

The institutional figure reaching zero rather than the projected ~6% is not extra
suppression. The projection assumed two residual alarms from the library-path
branch; that branch has since been narrowed to UNC and drive-letter paths only,
and no file in the corpus has either. What remains is that **21 alarming blocks
are still reported in 20 institutional files**, in red, with their evidence —
they simply no longer end in "ask someone who reads Python to look at this".

Two later corrections were re-measured against the same corpora. Fixing the
extraction so blank lines survive re-keyed all twenty entries — every recorded
`sha256` and `byte_size` changed — and the recognition rate is unchanged by it:
47 of 101 institutional text blocks and 18 of 60 community ones still match, the
same blocks as before. Declaring `generated` instead of deriving it moved exactly
one file, `studio_gabby.blend`, from a neutral banner to an amber one: its
`cloudrig.py.001` is a per-file generated body that had been standing down the
"auto-run script that is not recognised" reason it should never have been allowed
to stand down. No file's closing recommendation changed, so the alarm rates still
hold.

## Known limits of this layer

- **Every entry rests on one person's word.** There is no second reviewer, no
  signature, no transparency log. `attested_by` says so on every line it prints.
  An attacker who could edit `known_scripts.json` in an installed copy could add
  their own script's hash and stand it down; the file's integrity is the
  integrity of the install, and nothing more.
- **The database is small and Blender-Studio-heavy.** 20 entries, seeded from two
  measured corpora. A script it does not know is simply unrecognised, which is
  the correct default, but do not read broad coverage into it.
- **Structural entries pin one revision.** The Rigify entry describes the
  `rig_ui.py` revision found in one published file. Other Rigify revisions will
  have a different structure and will not match it.
- **`origin` and `notes` are not translated.** The wording around them is, in
  every language, but the recorded facts themselves are stored once, in English,
  because they are a transcription of what a source says rather than interface
  prose. A French reader gets a French report with two English sentences of
  provenance in it.

## Contributing an entry

See [CONTRIBUTING.md](../CONTRIBUTING.md).
