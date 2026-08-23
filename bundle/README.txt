BLEND X-RAY 0.1.0 -- lists the code hidden inside a .blend file, without
opening Blender.

Copyright (C) 2026 Sacha Geneviève. Free software under the GNU General Public
License v3 or later; full text in the LICENSE file beside this one. It comes
with ABSOLUTELY NO WARRANTY.

WHAT IT IS
A .blend file can carry Python, and Blender can be set to run that code the
moment the file opens. Blend X-Ray reads the file and lists what is in there:
script blocks, driver expressions, OSL / script nodes, linked libraries, file
paths -- and says in ordinary words what each one does. It never launches
Blender and never runs, imports or evaluates anything it finds; it reads bytes.
It makes no internet connection of its own, sends no telemetry, self-updates
never. It gives you an inventory, not a verdict. Deciding whether to trust a
file stays your call.

DO THIS FIRST -- IT MATTERS MORE THAN THIS TOOL
Blender has a setting that decides whether a downloaded file's script is allowed
to run by itself. Turned off, an embedded script does not run when you open the
file, and this whole class of attack does not start. It is the actual
protection; Blend X-Ray only tells you what is in there.

  Edit > Preferences > Save & Load > "Auto Run Python Scripts"

Make sure that box is UNTICKED, and leave it that way. It ships unticked, but
tutorials and rig add-ons often tell you to turn it on and it then stays on for
years. Blender's own warning box turns it on too: when a file wants to auto-run
scripts, that box offers a tick called "Permanently allow execution of scripts",
and ticking it switches the preference on for every file you open afterwards,
not only that one. If a rig needs it, tick the preference for that one session
and untick it again. Check this now, before you scan anything.

HOW TO RUN IT
Unzip this folder anywhere, double-click BlendXRay.exe (see the warnings below
on first run), then drop a .blend on the window or use "Choose a file...".
Point it at a folder and it goes through every .blend inside.

Nothing is installed. No administrator rights are asked for, no service is left
running, and no uninstaller is needed -- delete the folder and the program is
gone.

There is one thing it can write outside its own report, and only if you press
the button for it. "Add to right-click menu" adds an "Inspect with Blend X-Ray"
entry to the menu you get when you right-click a .blend in Explorer. It writes
two registry keys under HKEY_CURRENT_USER -- your own account only, no
administrator prompt, no change for anyone else on the machine -- and it does
not take over the .blend file association, so double-clicking a .blend still
opens Blender. The window shows you the exact keys and the exact command before
it writes anything, and nothing happens until you agree.

That one button carries three labels, and the one you see tells you what the
entry is currently doing:

  "Add to right-click menu"      There is no entry yet.

  "Remove from right-click       An entry exists and it runs this copy of
  menu"                          BlendXRay.exe. Pressing it deletes both keys
                                 and nothing else.

  "Repair right-click menu"      An entry exists, but it points at a location
                                 where BlendXRay.exe no longer is, so the menu
                                 item currently does nothing at all. Pressing
                                 it shows you the out-of-date command first,
                                 then replaces it.

The third state is easy to end up in without doing anything wrong. If you
double-click BlendXRay.exe straight out of the zip instead of unzipping it
first, Windows quietly extracts it to a temporary folder and deletes that
folder again later, so the entry ends up pointing at nothing. Moving, renaming
or re-extracting the folder afterwards does the same. Unzip the folder where
you mean to keep it, and add the menu entry from there.

If you ever use that button, press "Remove from right-click menu" before you
delete the folder. Otherwise the two keys stay behind pointing at an .exe that
is no longer there, and the menu entry does nothing. If you have already
deleted the folder, put the .exe back in the same place for a moment -- the
button has to read "Remove" before it will delete the keys -- press it, and
then delete it again.

THE WINDOWS WARNING ON FIRST RUN
Windows shows a blue box saying "Windows protected your PC" the first time you
start BlendXRay.exe. Expect it. It appears because this .exe is not
code-signed -- a signing certificate costs 200 to 400 EUR a year and that has
been put off for now. The box means Windows does not recognise the publisher.
It is a statement about a missing certificate, not about what the file
contains.

To get past it:
  1. Click "More info", the small link inside the blue box. The button you
     need stays hidden until you do.
  2. Click "Run anyway".
Windows asks once per machine.

YOUR ANTIVIRUS MAY ALSO OBJECT
It may warn about the download, or quarantine it outright, or delete this zip
while you are unpacking it. Two ordinary reasons, neither of them a second
opinion about the program:

  - An unsigned one-file executable built with PyInstaller is a shape a lot of
    scanning engines treat as suspicious by itself.
  - exemple-fichier-piege.blend, the demonstration file in this zip, contains a
    sample script written to look like the real attack. Many scanners read
    inside archives, and the words in that script are exactly the words they
    look for. It is a training dummy and carries no working payload -- see
    below -- but a scanner cannot tell the difference, and that is rather the
    point of it.

If that happens and you would rather not argue with your scanner, do not add a
blanket exclusion for a folder just to make a warning go away. Take the source
route instead.

IF YOU WOULD RATHER NOT RUN A DOWNLOADED BINARY
-- which is the argument this tool makes about .blend files -- then don't. The
source is public and short. Read it and run it from Python:

    https://github.com/gensacha/blend-xray
    py -3.12 -m venv .venv
    .venv\Scripts\activate
    pip install .
    blend-xray scan suspicious.blend

(Python 3.11 or 3.12, not 3.13 or newer -- the repository README says why.)

HOW TO READ THE RESULT
The first line of the report is the one to read. There are three:

  [✖] red    "This file contains code that reaches outside Blender."
             It contacts the network, starts a program, writes itself into
             your startup, reads where passwords are kept, or hides what it
             does. Don't open it in Blender; have someone who reads Python
             look first.
  [▲] amber  "This file contains code that needs a second pair of eyes."
             Something was found that the tool cannot settle alone. Rig
             scripts land here routinely. See the next section.
  [·] grey   "Nothing found in the 5 categories checked."
             None of the checks fired. Not a clearance: it describes what was
             looked at and nothing beyond it.

Below the banner each block is printed with its code, a plain list of what that
code does, and the exact words that produced each line. URLs, paths and shell
commands are listed separately, so you can see where a script wants to go.

WHAT TO DO WITH AN AMBER BANNER
Amber is the common case on real work, and it is not an alarm. It means the
tool found code and will not decide for you. In order:

  1. Read the plain-language lines under each block. They are the point of this
     tool -- you do not need to read the Python. If none of them mentions the
     internet, running another program, your files, or hiding what it does,
     what you are looking at is almost certainly rig or interface machinery.
  2. Look at the URLs, paths and commands the report lists separately. A rig UI
     script has no business contacting an address.
  3. With "Auto Run Python Scripts" unticked, as above, you can open the file
     and the script will not run. In Blender's Scripting workspace you can then
     see the script sitting there, and delete it if you do not want it.
  4. Still unsure? Ask whoever you got the file from what the script is for. A
     legitimate rig author answers that question easily. If the answer is
     evasive, or there is nobody to ask and nobody who reads Python, leave the
     file closed. No asset is worth a compromised machine.

WHAT THIS DOES NOT LOOK AT
A grey banner is not a pass. It means the five categories listed in the report
turned up nothing -- and there are parts of a .blend it does not inventory at
all:

  - Geometry Nodes.
  - Video Sequence Editor strip paths.
  - The contents of packed files.
  - Custom properties.
  - Anything outside the file. External scripts, external OSL and linked
    libraries are reported by their path only; Blend X-Ray never follows a path
    and never opens what is at the other end.
  - Files written before Blender 2.45, which it refuses outright rather than
    guess at.

It is also not an antivirus, and someone who wants to hide code from it can.
Nothing in a report ever means a file is fine.

THE EXAMPLE FILE
exemple-fichier-piege.blend is a demonstration file built from scratch for this
bundle: a "Rig_Ui.py" marked to auto-run that contacts a URL and hands a command
to PowerShell, and an ordinary rig UI panel next to it. It carries no working
payload -- the URL is in the .invalid domain and cannot resolve, and Blend X-Ray
does not execute what it reads. Drop it on the window: the banner goes red.

LICENCE AND SOURCE
Blend X-Ray is Copyright (C) 2026 Sacha Geneviève and is distributed under the
GNU General Public License v3 or later; full text in the LICENSE file beside
this one. It links against blender-asset-tracer (GPLv2-or-later).
THIRD-PARTY-LICENSES.txt, also in this zip, carries the licence and copyright
notices of everything else BlendXRay.exe bundles.
Source, issues and releases: https://github.com/gensacha/blend-xray

Blender is a registered trademark of the Blender Foundation. Blend X-Ray is an
independent project, not affiliated with or endorsed by it.
