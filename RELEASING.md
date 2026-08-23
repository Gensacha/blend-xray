# Release checklist

For the author. This covers the first publication to GitHub and every release
after it.

## 0. What this release ships

**Both: the source on GitHub, and an unsigned Windows zip on Gumroad and on
the author's own site.**

| Artefact | Where | What it is |
|---|---|---|
| Source | <https://github.com/gensacha/blend-xray> | The primary artefact. Readable, auditable, runnable from Python. |
| `BlendXRay-0.1.0-windows-x64.zip` | Gumroad (pay what you want, 0 EUR minimum) and the author's site | `BlendXRay.exe` + `LICENSE` + `THIRD-PARTY-LICENSES.txt` + `README.txt` + `LISEZ-MOI.txt` + `SOURCE.txt` + `exemple-fichier-piege.blend`. One file, no installer, no admin rights. Nothing is written outside the report unless the user presses "Add to right-click menu", which writes two `HKEY_CURRENT_USER` keys after showing them in full. |

An earlier draft of this checklist said *source only, no binary*. That decision
is reversed, and the reasoning behind the reversal is worth keeping because it
is the same reasoning the product page has to carry.

**Why a binary at all.** The people this tool is for are students and hobbyists
downloading rigs and asset packs. They will not open a terminal, create a
virtualenv and `pip install .` — and a tool nobody can run protects nobody. The
source stays the primary artefact and the honest escape hatch; the zip is how
the tool reaches the audience that needs it.

**Why it is unsigned.** `BlendXRay.exe` carries no code-signing certificate.
Windows SmartScreen therefore shows *"Windows protected your PC"* the first
time it runs on a machine, and the user has to click **More info** → **Run
anyway**, once per machine. A code-signing certificate costs roughly
200–400 EUR a year and ties the binary to a legal identity. That expense is
deferred, not refused. Note also that buying one would not make the warning
disappear on release day: SmartScreen's reputation score builds up only after a
binary has been downloaded a great many times, so a brand-new certificate still
leaves a period of warnings.

**The warning is announced, not discovered.** This is the part that makes
shipping an unsigned binary defensible rather than sloppy. A user who meets
SmartScreen without warning concludes the download is bad; a user who was told
about it first, in advance, by the author, concludes the page is honest. So the
explanation — what the box says, which link hides the button, why the
certificate is missing, and what the box does and does not tell you about the
file — appears in three places before the user ever double-clicks:

- on the product page itself, not only in the zip;
- in `README.txt` inside the zip;
- in `LISEZ-MOI.txt` inside the zip.

**And the same goes for antivirus, which is the one people actually meet
first.** SmartScreen fires after the download; a scanner can eat the zip during
it. An unsigned one-file PyInstaller build is a shape many engines dislike on
its own, and `exemple-fichier-piege.blend` deliberately contains the literal
text `powershell -NoProfile -WindowStyle Hidden -Command` beside
`urllib.request.urlopen` — most engines look inside archives. An artist whose
Defender quarantines a security tool concludes the tool is malware. Say it in
the same three places, in the same breath as SmartScreen, and do not tell
anyone to add a folder exclusion.

Beside it, every time, the same escape hatch: *if you would rather not run a
downloaded binary from someone you have no reason to trust — which is the
argument this tool makes about `.blend` files — then don't; the source is
public, read it and run it from Python.* A tool that tells people not to run
unverified downloads cannot pretend that its own download is an exception. It
can only be straight about it and leave the other door open.

**`dist/` stays gitignored.** The zip is a release asset — uploaded to a
release page and to Gumroad, never committed. Nothing in this section changes
that.

## 1. Before the first push

- [ ] **The placeholders are filled.** There were two marked ones: the GitHub
      account in every project URL, now `gensacha`, and the security contact in
      `SECURITY.md`, now `gensacha@hotmail.fr`. Both are done. Verify on every
      release anyway, because a new file can reintroduce one by copy-paste:

      ```bash
      grep -rn "OWNER\|PLACEHOLDER" \
        --include="*.md" --include="*.txt" --include="*.toml" \
        --include="*.spec" --include="*.py" --include="*.ps1" \
        --exclude=RELEASING.md \
        --exclude-dir=.venv --exclude-dir=.git --exclude-dir=build .
      ```

      Expect hits in exactly three files. Two are unrelated to publishing:
      `blend_xray/structure.py` defines `STR_PLACEHOLDER` and
      `BYTES_PLACEHOLDER`, which are literal-substitution sentinels in the
      structural matcher, and this file is excluded because it names the
      placeholders in order to describe them. The third **is** a real one and is
      meant to be: `README.md` carries `GUMROAD_URL_PLACEHOLDER` on its download
      line, so this grep refuses to pass until the storefront URL exists and has
      been pasted in. Fill it, then re-run. Anything else the grep finds is a
      genuine leftover.

      An earlier version of this grep covered only `*.md` and `*.toml`. It
      therefore missed the three `.txt` readmes that go **inside the zip**, and
      they shipped carrying the placeholder account name in their repository
      URL. The include list above is the fix; keep it in step with the file
      types the project actually contains.

- [ ] **Grep the zip too, not only the checkout.** The bundle's text files are
      tracked now, in `bundle/`, so the grep above does reach them — but the zip
      is *built*, and a stale zip beside a fixed checkout is exactly the failure
      that shipped a placeholder account name once already. Check the built
      artefact itself:

      ```bash
      python -c "import zipfile,sys; z=zipfile.ZipFile(sys.argv[1]); [print(n.filename,l) for n in z.infolist() if n.filename.endswith('.txt') for l in z.read(n).decode('utf-8').splitlines() if 'OWNER' in l or 'PLACEHOLDER' in l]" dist/BlendXRay-0.1.0-windows-x64.zip
      ```

      No output means no placeholder survived into the shipped file.

- [ ] **Check the author name** in `pyproject.toml` (`authors`, `maintainers`)
      is how you want to be credited in public.
- [ ] **Confirm nothing private is staged.** `git status --short` and read
      every line. In particular there must be no `.venv/`, no `dist/`, no
      `build/`, no `*.egg-info/`, no `.pytest_cache/`, no `.ruff_cache/`, no
      absolute paths from this machine in any tracked file, and no `.blend`
      files from the measurement corpora — those are kept in a scratch area
      outside the checkout and are not part of the repository. The one `.blend`
      that *is* tracked is `bundle/exemple-fichier-piege.blend`; `.gitignore`
      un-ignores it explicitly and nothing else.
- [ ] **`.gitignore` covers the artefacts.** It already lists `.venv/`,
      `build/`, `dist/`, `*.egg-info/` and the tool caches. If you have ever run
      `pip install -e .` or a PyInstaller build in the checkout, verify that
      what it produced is ignored rather than merely absent.

## 2. Tests and lint before you push

```bash
python -m pytest              # expect: 798 passed, 6 skipped (803/1 with the corpus)
python -m ruff check .        # expect: All checks passed!
```

The one skip asserts off-Windows behaviour of the registry toggle and is
expected to skip on Windows.

⚠️ **Two counts are correct, and they describe different machines.**
`tests/test_guards.py` runs five tests against real Blender demo files from
blender.org. Those are third-party downloads and are not in this repository, so
the tests skip unless `BLEND_XRAY_CORPUS` points at a directory holding them. A
clean clone therefore reports **798 passed, 6 skipped**, and a machine with the
corpus reports **803 passed, 1 skipped**. Do not read the higher skip count as a
regression. The remaining historical note below concerns that path
stops being hard-coded.

Then verify the package actually installs and runs from a fresh environment —
not from your development venv, which has everything already:

```bash
python -m venv /tmp/bx-check          # anywhere outside the checkout
/tmp/bx-check/bin/pip install .       # Scripts\pip.exe on Windows
/tmp/bx-check/bin/blend-xray scan some-file.blend
```

The console entry point must exist and the scan must produce a report. If it
does not, the packaging metadata is wrong and no amount of README is going to
fix it for a user.

## 3. Create the repository and push

There is no remote configured yet. Create the repository on GitHub **empty** —
no README, no `.gitignore`, no licence, since all three already exist here and
an initialised remote will only give you a merge to resolve.

```bash
# from the root of the checkout
git remote add origin https://github.com/gensacha/blend-xray.git
git branch -M main
git push -u origin main
```

Use the SSH form (`git@github.com:gensacha/blend-xray.git`) instead if that is
how you authenticate. `gensacha` is the account slug; the display name on the
profile is something else, and only the slug belongs in a URL.

## 4. Before making the repository public

- [ ] **Read the rendered README on GitHub.** Markdown that looks right in an
      editor can break on GitHub — check the tables, the code fences and the
      anchor links in particular.
- [ ] **Every claim in the README is still true.** The measured numbers, the
      test count, the version pins. A stale number in a security tool's README
      costs more credibility than a missing feature. In particular, the README
      section about the downloadable executable must describe the decision in
      §0 above and not the reversed one — and so must `docs/GUI.md`, which
      carried the reversed decision ("no prebuilt binary is published") long
      after it stopped being true. When §0 changes, grep the whole tree for the
      old position rather than fixing the file you happened to remember.
- [ ] **Every source citation names the vendor that actually made the claim.**
      The two writeups behind the *Why it exists* section do not say the same
      things: the VirusTotal detection ratio, the `Rig_Ui.py` filename, the
      six-month duration and the Russian-linked attribution are Morphisec's
      alone; "Cloudflare Workers" is Kaspersky's phrasing and Morphisec never
      uses the word. A miscited claim in a security tool's README is checkable
      in a minute by exactly the audience most likely to check.
- [ ] **`LICENSE` is the full GPLv3 text** and `pyproject.toml` says
      `GPL-3.0-or-later`.
- [ ] **The install instructions work on a machine that is not yours.** If you
      can, have somebody follow them from a fresh checkout and tell you every
      command they had to guess.
- [ ] **Enable private vulnerability reporting**: repository *Settings* →
      *Security* → *Private vulnerability reporting* → *Enable*. `SECURITY.md`
      tells people to use it, so it needs to exist.
- [ ] **Set the repository description and topics** — `blender`, `security`,
      `static-analysis`, `malware-analysis`, `python`. This is how people
      searching after the next incident will find it.
- [ ] **Decide about Discussions.** For a tool aimed at students, a Discussions
      tab is usually more useful than issues alone.
- [ ] **Turn on branch protection for `main`** if anyone else will ever push.

## 5. Build the Windows bundle

The window build is a PyInstaller one-file executable. From the project venv:

```bash
python -m pip install "pyinstaller>=6.6"
python -m PyInstaller --noconfirm --clean blend-xray.spec
```

`blend-xray.spec` has three load-bearing lines documented in its own docstring —
`copy_metadata("blender-asset-tracer")`, `upx=False`, and the
`blend_xray/known_scripts.json` data entry. Do not let a tidy-up remove any of
them. After every build, confirm the first and the third actually landed. The
frozen archive can be listed directly:

```bash
python -m PyInstaller.utils.cliutils.archive_viewer --list --brief dist/BlendXRay.exe
```

Look for a `blender_asset_tracer-*.dist-info/METADATA` entry and for
`blend_xray/known_scripts.json`. The practical check is the same one from the
other end: run the frozen build's own CLI on a file and read the report. If the
version guard cannot read `blender-asset-tracer`'s metadata the tool refuses to
start at all — the guard fails closed, which is correct, and which also makes
the exe useless. If `known_scripts.json` is missing the report says the
known-script database was not found. Both symptoms are visible in one scan,
which is why the smoke test in §6 is the real gate.

⚠️ **Never launch `BlendXRay.exe` to test it from a script.** It is built
`console=False` and its entry point calls `mainloop()` unconditionally, so
*every* invocation opens a window — including `--help`. For command-line smoke
tests, build a second, console-mode executable from the CLI entry point in a
scratch directory and drive that. The console twin is a test fixture: it never
enters `dist/` and never enters the zip.

### Zip layout

The zip is flat — seven entries, no top-level folder, so an unzip-in-place puts
everything beside the `.exe`:

```
BlendXRay.exe
LICENSE
THIRD-PARTY-LICENSES.txt
LISEZ-MOI.txt
README.txt
SOURCE.txt
exemple-fichier-piege.blend
```

**Everything except the `.exe` and `LICENSE` comes out of `bundle/`, which is
tracked.** An earlier version of this checklist said these files were staged in
a scratch directory outside the repository; they were, and a release built on
any other machine would silently have shipped without them, so they were moved
into version control. `LICENSE` comes from the checkout root. `BlendXRay.exe`
is the only built artefact in the zip.

### Assembling the zip: `build_zip.ps1`

Run it after `build_exe.ps1`:

```powershell
.\build_exe.ps1     # produces dist\BlendXRay.exe
.\build_zip.ps1     # produces dist\BlendXRay-<version>-windows-x64.zip
```

It prints the entry list as it writes, then both SHA-256 digests, so the numbers
that go on the page come out of the same run that produced the file.

**Do not assemble this archive by hand.** Both defects this release has had came
from doing exactly that: a demo file shipped carrying an `OWNER` placeholder URL,
and a zip shipped without `THIRD-PARTY-LICENSES.txt` — which the bundled
BSD-3-clause and MIT components *require* in a binary redistribution. Neither is
visible by looking at the archive, and neither is reachable by a grep over the
working tree, because the only copy that mattered existed solely inside a built
artefact. A hand-assembled release cannot be reviewed. The script's `$layout`
table is the reviewable version of the seven-entry list above, and it is what
makes the entry list a claim somebody can check against a diff.

Three properties are worth knowing about, because a future edit could remove any
of them without anything failing:

- **The entry list is written out, not globbed.** Directory enumeration order is
  not a contract, and a glob over `bundle/` would silently ship whatever wandered
  into it. Adding a file to `bundle/` does not add it to the release; adding it
  to `$layout` does.
- **Timestamps are normalised** to a constant (`-Timestamp`, default
  1980-01-01, the DOS zip epoch). The source files' own mtimes change on every
  edit and every re-checkout, and would otherwise leak into the digest.
- **The archive is read back and compared to `$layout`** before the digests are
  printed, rather than the writes being trusted.

Together those mean two runs over identical inputs give a byte-identical archive,
so a digest that moved means an input moved. The one thing it does *not* promise
is a digest stable across .NET runtime versions — the deflate encoder lives in
the runtime — so rebuild a release zip on the machine that built its exe. This is
a narrower guarantee than reproducibility and should not be described as more:
the exe inside is a PyInstaller one-file build and is not itself reproducible,
which is the point `docs/gumroad.md` §3 makes to readers in both languages.

- [ ] **Regenerate `bundle/THIRD-PARTY-LICENSES.txt` whenever `blend-xray.spec`
      changes.** It reproduces the licence and copyright notices of everything
      frozen into the executable, and the BSD-3-clause and MIT ones *require*
      that in a binary redistribution. Its contents follow the spec: narrowing
      the `excludes` list, or adding a dependency, changes what is inside the
      exe and therefore what has to be in this file. List what a build actually
      contains and reconcile it against the file's own CONTENTS block:

      ```bash
      python -m PyInstaller.utils.cliutils.archive_viewer --list --brief dist/BlendXRay.exe
      pip-licenses --format=plain-vertical --with-license-file   # from the project venv
      ```

      Over-listing a component that is no longer bundled is untidy; omitting one
      that is bundled is a licence violation. Check in that direction.

### After every rebuild

- [ ] **Recompute both SHA-256 digests.** Any change to any file in the zip
      changes the zip's digest, and a rebuilt `.exe` changes its own. Publishing
      a digest that does not match the file is worse than publishing none: it
      teaches the one reader who checked that checking is pointless.

      ```powershell
      Get-FileHash .\dist\BlendXRay-0.1.0-windows-x64.zip -Algorithm SHA256
      Get-FileHash .\dist\BlendXRay.exe -Algorithm SHA256
      ```

- [ ] **Update every place the digests appear.** Today that is `docs/gumroad.md`
      (the working notes for the product page) and, once published, the product
      page itself and the GitHub release notes.
- [ ] **Say what the digest proves, wherever you publish it.** It identifies the
      artefact that was uploaded, so a reader can confirm their download arrived
      intact. It is **not** a reproducible build: PyInstaller one-file
      executables are not deterministic, so a third party compiling the same
      source gets a different digest and that difference proves nothing in
      either direction. Only reading the source establishes what the source
      does. For a tool whose whole argument is that you should not trust an
      unverifiable download, that gap is far better stated by the author than
      found by a reader. `docs/gumroad.md` §3 carries the sentence in both
      languages; use the same wording in the release notes.
- [ ] **Read the version back off the built `.exe`.** The version now reaches
      four surfaces — `--version`, the `version` key in `--json`, the window
      title and the exe's VERSIONINFO resource — and all four read
      `blend_xray.__version__`, so they cannot disagree with each other. What
      they *can* disagree with is the zip filename and the tag, which nothing
      checks. The resource is the one you cannot see without asking:

      ```powershell
      (Get-Item .\dist\BlendXRay.exe).VersionInfo |
        Format-List FileVersion, ProductVersion, ProductName
      ```

      Blank there, on an unsigned binary, reads to a cautious user as one more
      reason not to run it — which is the user this tool is for. If PyInstaller
      could not build the resource the spec returns `None` and the build carries
      on without one, so absence here is silent.
- [ ] **Smoke-test the rebuilt artefact** through the console twin — see §6.

## 6. Smoke test before publishing

Three scans and one question, on the artefact you are about to publish, through
the console twin:

| Input | Expected |
|---|---|
| `exemple-fichier-piege.blend` from the zip | red banner, the URL and `powershell` both visible in the report |
| An ordinary `.blend` with no scripts | grey banner: nothing found in the categories checked |
| A file that is not a `.blend` | exit code 2 |
| `--version`, with no subcommand | `blend-xray 0.1.0`, exit code 0 — the version the tag and the zip filename must match |

If the first one does not go red, the identity database or the collectors did
not survive freezing and the bundle must not ship.

## 7. Publishing

### The order matters, and it is a licence condition

**Push the repository and the tag before the zip reaches Gumroad or the
author's site. Not the same afternoon — before.**

The binary is distributed on a storefront while its source lives on GitHub.
GPLv3 §6(d) permits exactly that, but only on the condition that the offer
shipped with the binary actually resolves: the user has to be able to follow the
directions in `SOURCE.txt` and reach the corresponding source. If the zip is
uploaded first, that link 404s, and for as long as it does the distribution is
in breach — of the licence this project chose to publish under, in a project
whose entire pitch is that it means what it says. It is also the single easiest
thing to get wrong on release day, because uploading a file feels like the last
step and pushing a repository feels like the first.

So: repository public → tag pushed → GitHub release drafted and its assets
attached → *then* the storefront.

### Version numbers: where they actually live

`pyproject.toml` no longer holds the version. It is declared `dynamic` and read
from `blend_xray._version.__version__`, and `blend-xray.spec` parses that same
file with `ast` rather than importing it. So a bump touches:

| site | what to change |
|---|---|
| `blend_xray/_version.py` | `__version__` — **the single source of truth**; `pyproject.toml` and the spec both read it, and `blend_xray/__init__.py` re-exports it |
| `bundle/README.txt` | first line, `BLEND X-RAY x.y.z` |
| `bundle/LISEZ-MOI.txt` | first line, `BLEND X-RAY x.y.z` |
| `bundle/THIRD-PARTY-LICENSES.txt` | second line |
| the zip filename | `BlendXRay-x.y.z-windows-x64.zip` |
| the git tag | `vx.y.z` |

The tag, the zip filename and `__version__` must agree. Nothing checks this for
you.

**Why the literal sits in `_version.py` rather than in `__init__.py`.** The
obvious declaration, `attr = "blend_xray.__version__"`, does not work in this
repository, and it fails in a way that looks like a broken environment rather
than a misconfiguration. setuptools resolves `attr:` with its own static module
lookup, and that lookup tries `<root>/blend_xray.py` — the double-click launcher
at the repository root — *before* `<root>/blend_xray/__init__.py`. It finds the
launcher, fails to read a version out of it, falls back to importing it, and the
import raises `ModuleNotFoundError`. Pointing the build at
`blend_xray._version` is unambiguous: nothing else in the tree answers to that
path. `blend_xray/__init__.py` re-exports the name, so every caller still reads
`from blend_xray import __version__` and a bump is still one line in one file —
just a different file. `tests/test_version.py` resolves the declared attribute
through setuptools and compares it with the value the tool reports, so a
declaration that does not actually resolve fails the suite instead of failing
the build.

### `SOURCE.txt` must name the tag

`bundle/SOURCE.txt` is the written offer that makes §6(d) work, so a bare link
to the repository root is not enough: the root moves, and the source
corresponding to *this* binary is the source at the tag it was built from. Point
it at `.../tree/v0.1.0`, and bump that path in step with everything else above.

It should also name `blender-asset-tracer`'s own upstream. Blend X-Ray links
against it, the executable bundles it, it is GPLv2-or-later, and it is therefore
part of the corresponding source a recipient is entitled to — a link to this
project alone does not cover it.

### GitHub release

```bash
git tag -a v0.1.0 -m "Blend X-Ray 0.1.0"
git push origin v0.1.0
```

Then draft the release from that tag and attach
`BlendXRay-0.1.0-windows-x64.zip`. In the notes:

- both SHA-256 digests, with the `Get-FileHash` command that checks them, **and
  the sentence saying the digest identifies the uploaded artefact and is not a
  reproducible build** — PyInstaller one-file executables are not deterministic,
  so rebuilding from the same source gives a different digest. Wording in
  `docs/gumroad.md` §3;
- one paragraph saying the binary is unsigned, what SmartScreen will do, that an
  antivirus may quarantine the download and why, and that signing is deferred —
  the same wording as the product page, so the two do not drift apart;
- the pointer to running from source for anyone who would rather.

### Gumroad and the author's site

`docs/gumroad.md` holds the working copy for the product page in both languages:
the description, the SmartScreen and antivirus sections, the digests, and the
vocabulary rule the copy has to respect. It is a working document, not part of
the zip. Copy from it, edit it in your own voice, and keep the digests in step
with whatever you actually upload.

It used to live at `dist/GUMROAD.md` — inside a gitignored directory, one
`--clean` from being lost, while this checklist named it as the record of the
published digests. It is tracked now. Do not move it back.

Gumroad is *pay what you want* with a 0 EUR minimum, and the page has to say so
plainly — see §1 of `docs/gumroad.md` for the wording, including the sentence
that a payment is a tip and buys nothing.

## 8. Publishing to PyPI (optional, later)

Not required, and not part of the first release. If you do:

```bash
python -m pip install build twine
python -m build                       # produces dist/*.whl and dist/*.tar.gz
python -m twine check dist/*
python -m twine upload dist/*
```

Note that `python -m build` writes into `dist/`, which is gitignored — that is
correct and it must stay uncommitted. Register the name on TestPyPI first if you
want to see the rendered project page before it is permanent.

## Never commit

- `dist/` — build output, including the unsigned `.exe` and the zip. Both are
  release assets, uploaded to a release page and to Gumroad, never tracked.
- `.venv/` — the environment, recreated from `pyproject.toml` on any machine.
- `build/`, `*.egg-info/` — packaging intermediates.
- `.pytest_cache/`, `.ruff_cache/`, `__pycache__/` — tool caches.
- Any `.blend` file **except `bundle/exemple-fichier-piege.blend`**. The test
  suite builds its own from scratch, and the measurement corpora are third-party
  files that are not ours to redistribute — hence the blanket `*.blend` rule in
  `.gitignore`. The demonstration file is the one exception: it was written from
  scratch for this bundle, it ships inside the zip, and `.gitignore` un-ignores
  it by name (`!bundle/*.blend`). It lived outside the checkout once, which is
  how a zip shipped carrying a placeholder account name that no grep over the
  working tree could see.
