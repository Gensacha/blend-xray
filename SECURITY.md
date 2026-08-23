# Security policy

Blend X-Ray is a tool people point at files they already distrust. If it can be
made to misreport, hang, crash, or execute something, that matters more than any
feature. Reports are welcome.

## Reporting a vulnerability

**Do not open a public issue.**

Report privately, one of two ways:

- **GitHub private vulnerability reporting** — on the repository, go to the
  *Security* tab and choose *Report a vulnerability*. This is preferred: it
  keeps the report, the discussion and the fix in one place, and nothing is
  public until it is ready to be.
- **Email** — `gensacha@hotmail.fr`

Please include:

- what you did, in enough detail to repeat it;
- what happened, and what you expected instead;
- the Blend X-Ray version, your Python version and your operating system. Where
  to read the version depends on how you got the tool, and each route works
  without the others:
  - **the zip** — the window's title bar reads `Blend X-Ray 0.1.0`, and
    right-clicking `BlendXRay.exe` → *Properties* → *Details* shows the same
    number in *File version* and *Product version*;
  - **the command line** — `blend-xray --version`, which answers even when the
    install is too broken to scan anything;
  - **a saved report** — the `version` key at the top of `--json` output;
  - **an installed package** — `pip show blend-xray`;
- a `.blend` file that triggers it, **if you built it yourself**. Please do not
  send a sample you believe is real malware. If the bug needs a hostile file,
  send the builder script rather than the binary — `tests/blend_builder.py`
  constructs `.blend` files from scratch and is how every hostile fixture in
  this project is made.

### What to expect

This project is maintained by **one person, in their spare time**, alongside
other work. There is no security team, no rota, and no service-level agreement.

- Acknowledgement: I will try to reply within a week. If you have heard nothing
  after two weeks, please send a reminder — assume it was missed, not ignored.
- Fix: as soon as I reasonably can. A serious bug gets a release of its own; a
  minor one rides along with the next.
- Credit: I will credit you in the release notes by whatever name you prefer,
  or leave you out entirely if you would rather.
- Disclosure: please give me a chance to fix it before publishing. I am not
  going to argue about a deadline you set, and I would rather you disclose
  responsibly and publicly than not report at all.

## What counts as a vulnerability here

In rough order of how much it worries me:

1. **Anything that causes execution.** Blend X-Ray's central promise is that it
   never runs what it finds. An input that gets code executed — through the
   `ast` layer, through `blender-asset-tracer`, through the report renderer,
   through the known-good database loader — is the most serious class of bug
   this project has.
2. **A crafted file that makes the report lie.** Forged or hidden report lines,
   spoofed provenance, a finding suppressed by something under the file's
   control. The report is what a user acts on; a file that can edit it defeats
   the tool completely.
3. **Denial of service from a crafted file** — unbounded allocation, a hang, an
   unhandled crash. The guards in `blend_xray/guards.py` exist for exactly this
   and a way past them is a real bug.
4. **A path traversal or a write outside the intended location.** Blend X-Ray
   should write nothing except its report.
5. **A false negative with a concrete construction.** "It could be evaded"
   is documented and expected (see below); "here is a script it describes
   *wrongly*, and here it is" is a bug worth fixing.

## Threat model, honestly

### What Blend X-Ray defends against

The case it was built for: an artist downloads a `.blend` from a marketplace or
a forum, and wants to know what is inside it before opening it in Blender. It
finds embedded Python, driver expressions, OSL script nodes and linked-library
paths, and it explains them in plain language without running anything. Against
the November 2025 CGTrader campaign — a Python payload in a text datablock,
marked to auto-run, that contacts a remote host and launches PowerShell — the
relevant findings are exactly the ones it reports at its loudest severity.

It is a **reading aid for a decision a human makes**. It is not an antivirus,
not a sandbox, and not a gate.

### What Blend X-Ray cannot do

**A determined attacker can evade static analysis, and no amount of rule-writing
changes that.** This is a property of the approach, not a defect to be fixed.
The README's section *What static analysis cannot do* spells it out with working
code: every name a rule looks for can be split across `+` and reached through
`getattr`, at which point the name tables match nothing. Blend X-Ray responds by
reporting the *shape* of the hiding rather than pretending to see through it,
which raises the cost of hiding without closing the door.

Also outside what it can know:

- **Anything outside the file.** External text blocks, external OSL and linked
  libraries are reported by path and never followed or read. What is at the far
  end of that path is not inspected.
- **A block that does not parse** falls back to a plain-text sweep and is
  marked as such. A syntax error is a place the rules did not reach.
- **Data-driven behaviour.** `pickle.load()` is reported; what it executes lives
  in a data file this tool does not open.
- **Whole categories are not inventoried at all** — Geometry Nodes, VSE strip
  paths, packed file contents, custom properties. They are listed in the
  README's *Known gaps* so that silence is not mistaken for absence.
- **It has never been tested against a real malicious sample.** None was
  obtained, by design.

This is why the tool never prints "safe" or "clean", has no score and no green
tier, and says in the banner that a finding of nothing means nothing was found
*in the categories checked*. A tool that overpromises here is worse than no
tool, because it converts a suspicious user into a confident one.

### The known-good database is a trust boundary

`blend_xray/known_scripts.json` records that a script body is byte-identical to
a published release. Every entry today rests on **one person's attestation**.
There is no second reviewer, no signature and no transparency log.

An attacker who can edit that file in an installed copy can add their own
script's hash and stand it down from the "needs a human" branch. The file's
integrity is the integrity of the install and nothing more. Entries never
suppress the red tier, precisely so that a compromised or stale entry cannot
hide a file that talks to the internet, launches a program or conceals its own
code.

Reports about the database — a bad entry, a `source_url` that does not resolve,
a hash that does not reproduce — are welcome and should be treated as security
reports, not as data corrections.

## Out of scope

- "The tool can be evaded by obfuscation." Documented above and in the README.
  A *specific* construction that produces a confidently wrong description is in
  scope; the general observation is not.
- Vulnerabilities in `blender-asset-tracer`, Blender, Python or the operating
  system. Report those upstream. If Blend X-Ray's guards fail to contain an
  upstream bug, that part is in scope here.
- The unsigned executable and its SmartScreen warning. The published Windows
  zip carries an unsigned `BlendXRay.exe`; that is a known and documented state
  of the project, explained on the download page, in `README.md` and in both
  readmes inside the zip. Signing is deferred, and reports that it is missing
  add nothing. A report that the published SHA-256 does not match the published
  file **is** in scope, and urgent.
- Anything requiring an attacker who already has write access to your machine
  or to your Python environment.

## Supported versions

The project is pre-1.0 and there is one maintainer. **Only the latest release is
supported.** Fixes go on top of `main`; there are no backports.
