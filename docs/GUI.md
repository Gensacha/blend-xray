# The window

The audience for this tool is 3D students and artists, and a terminal is a
barrier for most of them. So there is a window, over the same scanner the command
line uses.

```bash
python blend_xray_gui.py                  # open it
python blend_xray_gui.py suspicious.blend # open it on a file
python -m blend_xray.gui                  # same thing, as a module
```

Installing the package also puts a `blend-xray-gui` command on your PATH. It
needs nothing beyond the standard library's `tkinter`; drag-and-drop is the one
optional extra (`pip install ".[gui]"`).

It shows the same inventory the CLI does, in the same words, from the same string
catalogue, with the same rules: **no green anywhere, no score, no badge, and
never the word "safe"** — in any language, not even inside a negation. Green
reads as "all clear" at a glance, and a glance is all most people give a security
tool.

## What it does

- **Drop a file on it, or use "Choose a file…" / "Choose a folder…".**
  Drag-and-drop needs `tkinterdnd2`. Without it the window says so once and the
  buttons do the same job — drag-and-drop is a bonus, never a requirement.
- **Scans run on a worker thread**, so a folder scan never freezes the window.
  There is a progress indicator and a Cancel button.
- **Per code block**: plain-language explanation first, then the strings found
  inside the code (URLs, paths, commands), then the raw source **last** and
  collapsed behind a "Show the raw source" toggle.
- **The Recommendation is drawn near the top**, not at the bottom. It is the part
  that turns a finding into an action, and the bottom of a long scrolling report
  is where things go to be ignored.
- **Language selector** (`en` / `fr`), defaulting to your OS locale. Switching
  re-renders what is on screen; it does not re-scan.
- **"Copy report"** puts the whole thing on the clipboard as plain text, raw
  source expanded, so you can paste it to someone who reads Python.

## The optional right-click entry

There is one button, and it carries one of three labels. It is a toggle inside
the app, never an install step, and it obeys the same rule the tool asks of you
— do not run what you have not looked at:

| Button label | When it is shown |
| --- | --- |
| **"Add to right-click menu"** | No entry exists for this user. |
| **"Remove from right-click menu"** | An entry exists **and** the command stored in it is the command this copy of the tool would write. |
| **"Repair right-click menu"** | An entry exists but the command stored in it points at a path this build no longer occupies. |

The third state is the one worth explaining, because it is not exotic. The
command in the registry is an absolute path, baked in when the entry was created,
and two entirely ordinary sequences invalidate it without anyone touching the
registry: double-clicking `BlendXRay.exe` **from inside the downloaded zip**, in
which case Explorer silently extracts to `%TEMP%\Temp1_<zipname>\` and that
throwaway path is what gets recorded — Windows deletes the folder later; or
moving, renaming or re-extracting the folder afterwards. In both cases the menu
item still appears in Explorer and does nothing at all. A button reading "Remove"
would be telling the user the feature works, so the window compares the two
commands rather than merely checking that the key exists.

- **Before anything is written, the window shows you the exact registry key and
  the exact command.** Nothing happens until you agree. On the repair path the
  dialog additionally shows you the **stale command it is about to replace**, so
  what is being overwritten is visible before it is overwritten, not after.
- Repairing is one write, not an uninstall followed by a reinstall: the same key
  is opened and its value replaced, so a stale entry is never duplicated.
- **`HKEY_CURRENT_USER` only.** No `HKLM`, so no administrator prompt and no
  change for any other account on the machine.
- It registers a *verb* under
  `Software\Classes\SystemFileAssociations\.blend\shell\BlendXRay`, which adds a
  menu entry **without** taking over the `.blend` file association —
  double-clicking a `.blend` still opens Blender.
- Two keys, and that is the entire footprint. "Remove" deletes both and nothing
  else. Note which state offers it: removal is offered on the *current* entry,
  and a stale one is offered repair instead. `uninstall()` deletes a stale entry
  perfectly well, but to reach it from the window you have to put this build back
  where the entry points — or repair the entry first — so the button reads
  "Remove". Anyone tidying up before deleting the folder should do it while the
  button still says "Remove".
- A registry that cannot be read raises, rather than returning "no entry".
  Telling you the entry is absent when we simply could not look is the class of
  statement this tool exists to avoid. The button label has to say *something*,
  so it falls back to "Add"; press it and the failure reaches you as an error
  dialog carrying the reason the OS gave, never as a silent success.
- Windows only. On macOS and Linux the button is not drawn at all.

This is the only thing Blend X-Ray ever writes outside its own report. See the
README's *Privacy* section.

## Building the portable executable

`blend-xray.spec` and `build_exe.ps1` are in the repository:

```powershell
.\build_exe.ps1     # or: python -m PyInstaller --noconfirm --clean blend-xray.spec
```

Output: `dist\BlendXRay.exe` — a single file, 12,983,360 bytes (12.38 MiB) for
the current build, no installer, no registry write on startup, no admin rights.
`dist/` is gitignored and must stay that way.

**A prebuilt binary is published.** An earlier draft said it would not be, on the
grounds that an unsigned executable makes SmartScreen warn and that asking people
to click through that is asking them to do the exact thing this tool exists to
warn them against. That decision was reversed, and the argument that reversed it
is worth keeping: the people most exposed to a booby-trapped rig are students and
hobbyists who will not create a virtualenv to check one download, and a tool
nobody can run protects nobody. So the zip ships — on Gumroad, pay what you want
with a 0 EUR minimum, and on the GitHub releases page — with the warning
announced up front rather than discovered, and the source kept as the primary
artefact and the escape hatch for anyone who would rather not trust a binary.
`RELEASING.md` §0 carries the reasoning in full; the README's *The downloadable
executable, and why it is unsigned* carries the version users read.

Two consequences for anyone rebuilding it: the zip is assembled from `bundle/`,
which is tracked and contains the readmes, `SOURCE.txt`, `THIRD-PARTY-LICENSES.txt`
and the demonstration `.blend`; and `THIRD-PARTY-LICENSES.txt` has to be
regenerated whenever this spec changes what is frozen into the exe.

Three things in the spec are load-bearing and easy to lose in a "cleanup" — the
`blender-asset-tracer` distribution metadata (the version guard reads it, and a
frozen build without it refuses to run at all), the `known_scripts.json` data
file, and the console-free launcher mode. The spec file documents each in place.

## Known limits of the window

- **Cancel takes effect between files, not inside one.** A single very large file
  finishes being read before the worker stops. That is bounded rather than
  open-ended — `guards.Limits` already caps per-file wall-clock time, file size
  and decompressed size — but a click on Cancel can still take a few seconds.
- The right-click entry is registered for `.blend` **files** only. There is no
  "inspect this folder" entry; use "Choose a folder…" in the window.
- A folder holding hundreds of `.blend` files renders hundreds of reports into
  one scrolling view. It stays responsive while scanning, because drawing happens
  per file, but the view is not paginated or virtualised.
- It was not tested on macOS or Linux.
- No real mouse drag has ever been performed onto it. The drop *handler* was
  tested with a synthetic `<<Drop>>` event carrying the same data format Tk
  delivers, in both the with-`tkinterdnd2` and without states.
- **The right-click entry has never been written to a real registry, and has
  never been seen working in Explorer.** This used to say `install()` and
  `uninstall()` had never run at all. That is no longer true, and the difference
  is worth stating exactly, because it is smaller than "now covered". `plan()`,
  `launch_command()` and the HKCU-only invariants are tested as before. On top of
  that, `install()` and `uninstall()` are now *executed* by the suite — against
  an in-memory stand-in for `winreg` that records writes instead of performing
  them, exercising the fresh install, the stale entry repaired in place, both
  uninstall paths, and the read-failure and write-failure paths. The real `HKCU`
  key was checked afterwards and was absent, so "nothing was written to the
  machine" is an observation rather than an assumption.

  What that does **not** buy: no key has been created on a real Windows
  registry, no menu entry has been seen in Explorer, and nobody has right-clicked
  a `.blend` file and had the window open. The stand-in behaves the way the
  Windows documentation says `winreg` behaves; if that reading is wrong, these
  tests agree with the mistake. Everything about how Explorer treats the verb is
  still reasoned, not observed.
