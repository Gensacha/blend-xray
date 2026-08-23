# Gumroad / downloads page — working notes

Not part of the zip. A working document for the author: copy the parts you want,
edit them in your own voice, throw away the rest.

This file used to live at `dist/GUMROAD.md`, inside a gitignored directory, one
`--clean` away from being lost. It is tracked here instead. The digests below
are the published ones, so it must not go back to being untracked.

Artefact: `dist/BlendXRay-0.1.0-windows-x64.zip`, rebuilt 2026-08-24 from a
checkout of the source repository.

**The Gumroad page is the front door, not a mirror.** The download link goes
directly in the LinkedIn post rather than in a comment, and for that audience
Gumroad is the single public entry point. So the page has to stand on its own,
in French and in English, and carry all four of these — nothing deferred to a
README somebody has to unzip first:

1. what the tool does, and what it explicitly does not claim;
2. the SmartScreen explanation — unsigned binary, what the warning means, which
   buttons, why signing is deferred — and the antivirus sentence beside it, for
   the reader whose scanner eats the download before SmartScreen ever runs;
3. both SHA-256 digests, with the command that checks them;
4. a prominent link to <https://github.com/gensacha/blend-xray> for anyone who
   would rather read the source than run a binary. That is the honest escape
   hatch. It belongs above the fold, not in a footer.

Suggested order on the page: price line → what it is (short) → the GitHub link →
what you get → SmartScreen and antivirus → digests → the long description in
both languages.

⚠️ **Publish the source before the download.** GPLv3 §6(d) lets the binary sit
on a storefront with its source elsewhere only while the directions shipped
with it actually resolve. `SOURCE.txt` points at the repository and the release
tag, so the repository must be public and the tag pushed *before* the zip is
uploaded anywhere. A zip that ships first is a live licence violation for as
long as that link 404s. See §7 of `RELEASING.md`.

---

## 1. The price line — read this before writing anything else

Gumroad is set to **pay what you want, 0 EUR minimum**. The tool is free. GitHub
has no mechanism for someone to leave a couple of euros, which is the only
reason the binary sits on a storefront at all.

Two things the page must get right, in both languages:

- **The zero has to be unmistakable.** If a suggested amount reads like a price,
  people who were told the tool is free will bounce at the checkout. Either
  suggest nothing, or suggest something small and visibly optional.
- **A payment is a tip and buys nothing.** No extra features, no support
  commitment, no warranty, no priority on issues. Gumroad's interface calls
  every transaction a *purchase*, and a security tool somebody paid for sits
  differently in their head from one they were given — they start expecting it
  to answer for itself. One sentence closes that gap. Leaving it implicit is
  what creates the problem three months later.

This is also the only line that has to agree with the licence: GPLv3 comes with
no warranty, and the project's whole argument is that it will not promise you
anything about a file. A tip cannot buy an assurance the tool refuses to give
anyone.

### English

> **Free. Pay what you want, starting at 0 EUR.**
>
> Type 0 and download it — that is the intended price and nothing is withheld.
> If you want to leave a euro or two, the button takes it and it is appreciated.
>
> To be plain about what that money is: it is a tip, and it buys nothing. Not a
> feature, not support, not priority, not a warranty. The file is the same file,
> the licence is the same GPLv3 with no warranty attached, and the tool will not
> tell you a .blend is fine whether you paid or not. It gives you an inventory
> either way.

### French

> **Gratuit. Prix libre, à partir de 0 EUR.**
>
> Tapez 0 et téléchargez : c'est le prix prévu, et rien n'est mis de côté. Si
> vous voulez laisser un ou deux euros, le bouton les accepte et c'est apprécié.
>
> Pour être clair sur ce qu'est cet argent : c'est un pourboire, et il n'achète
> rien. Ni fonctionnalité, ni assistance, ni priorité, ni garantie. Le fichier
> est le même fichier, la licence est la même GPLv3 sans aucune garantie, et
> l'outil ne vous dira pas qu'un .blend ne pose pas de problème, que vous ayez
> payé ou non. Il vous donne un inventaire dans les deux cas.

---

## 2. The GitHub link — put it high on the page

Not a footer link. Someone who reads "do not run unverified executables you
downloaded" three paragraphs later needs the alternative to already be in view.

### English

> **Would rather read the code than run a binary? Do that instead.**
> Everything is public, GPLv3, and small enough to read in one sitting:
> <https://github.com/gensacha/blend-xray>

### French

> **Vous préférez lire le code plutôt que lancer un binaire ? Faites-le.**
> Tout est public, sous GPLv3, et assez court pour être lu d'une traite :
> <https://github.com/gensacha/blend-xray>

---

## 3. Hashes — publish these on the page

Publishing the hashes is the cheapest credibility the project can buy: it lets
anyone confirm that the file they downloaded is the file you built, without
trusting the page it came from.

```
BlendXRay-0.1.0-windows-x64.zip
  size    12 759 404 bytes (12.17 MiB)
  SHA-256 e3c8c3a064debb198de6f3b9adb024dfc7edf2ce0ddefde1028f1c720255bd73

BlendXRay.exe  (inside the zip)
  size    12 983 360 bytes (12.38 MiB)
  SHA-256 d02487f66c07ccfc762ae24d2d0d6177b21f40e56b5d6587e0e3238c75b05940
```

Both lines were measured with `Get-FileHash` — the command below, the one the
page tells readers to run — off the artefacts in `dist/` after `.\build_zip.ps1`
assembled the archive from tracked sources. The exe digest was then measured a
second time off the copy extracted back *out* of that zip and came back the same
value, which is what makes the second line a statement about the file a reader
downloads rather than about a file that happened to sit next to it.

An earlier zip in `dist/` carried the digest `40d23135…` over a 15 486 357-byte
file. It is superseded and must not be published: it predates this executable,
predates the current `bundle/` text files, and was missing
`THIRD-PARTY-LICENSES.txt` altogether.

How a reader checks it, in PowerShell:

```powershell
Get-FileHash .\BlendXRay-0.1.0-windows-x64.zip -Algorithm SHA256
```

Put that command on the page too — a hash nobody knows how to use is decoration.
And a line telling people what to do when it does not match: *if the digest
differs from the one on this page, delete the file and tell me.*

⚠️ These digests are only valid for this build. Any change to any file in the
zip — including a one-word edit to a `.txt` inside it — changes the zip's digest.
Recompute both after every rebuild and update them here **and** on the page.
Publishing a digest that does not match the file is worse than publishing none:
it teaches the one reader who bothered to check that checking is pointless.

⚠️ **Say what the digest is for, and what it is not.** It identifies *the file
that was uploaded* — it lets a reader confirm their download was not altered in
transit or swapped on the way. It is **not** a reproducible build: PyInstaller
one-file executables are not deterministic, so somebody building from the same
source will get a different digest and that difference proves nothing either
way. For a tool whose argument is that you should not trust unverifiable
downloads, that gap is much better stated than discovered. One sentence on the
page:

> This SHA-256 identifies the file I uploaded, so you can check your download
> arrived intact. It is not a reproducible build — building the same source
> yourself produces a different digest, so it cannot prove the binary was built
> from the source you can read. Only reading the source can do that.

And the French:

> Ce SHA-256 identifie le fichier que j'ai mis en ligne : il vous permet de
> vérifier que votre téléchargement est arrivé intact. Ce n'est pas une
> compilation reproductible — recompiler vous-même le même code source donne une
> empreinte différente, donc elle ne peut pas prouver que le binaire vient bien
> du code que vous pouvez lire. Seule la lecture du code source le peut.

---

## 4. What you get — the bullet list for the page

- `BlendXRay.exe` — the tool, one file, no installer. Unzip and double-click.
  Windows 64-bit. Nothing is installed and no administrator rights are asked
  for; delete the folder and the program is gone. The one thing it can write
  outside its own report is optional and behind a button: "Add to right-click
  menu" writes two keys under `HKEY_CURRENT_USER` — your own account only — and
  shows you both in full before writing them. The same button then reads "Remove
  from right-click menu" and deletes them; it reads "Repair right-click menu"
  instead when the entry survives but the `.exe` has moved, in which case it
  shows you the out-of-date command before replacing it.
- `LISEZ-MOI.txt` / `README.txt` — one page each, French and English: how to run
  it, how to read what it shows you, what the Windows warning on first run is,
  and what to do when your antivirus objects.
- `exemple-fichier-piege.blend` — a demonstration file built from scratch, with
  an auto-run `Rig_Ui.py` that contacts a URL and hands a command to PowerShell,
  and an ordinary rig UI panel beside it. Drop it in and watch the banner go
  red. It carries no working payload: the URL is in the `.invalid` domain and
  cannot resolve, and the tool never executes what it reads.
- `LICENSE` + `SOURCE.txt` — GPLv3-or-later, and the link to the full source at
  the tag this build was made from.
- `THIRD-PARTY-LICENSES.txt` — the licence and copyright notices of everything
  the executable bundles: `blender-asset-tracer`, `zstandard`, `tkinterdnd2`,
  CPython with Tcl/Tk, and OpenSSL's `libcrypto-3.dll`. Several of those licences
  require it in a binary redistribution. The list is derived from the build's own
  table of contents and has to be regenerated whenever `blend-xray.spec` changes
  what is frozen.

---

## 5. Product description — English

> **Blend X-Ray — see the code inside a .blend before you open it**
>
> A .blend file can carry Python, and Blender can be set to run it the moment
> the file opens. That is how the November 2025 CGTrader campaign worked: rigs
> and asset packs that looked ordinary, with a script marked to auto-run sitting
> inside them. Antivirus engines do not parse .blend internals, and Blender's own
> warning tells you a file wants to run scripts without telling you what they do.
>
> Blend X-Ray parses the file and lists what is in it — script blocks, driver
> expressions, OSL and script nodes, linked libraries, file paths — and explains
> each one in ordinary words: this one contacts the internet, this one starts a
> program on your machine, this one defines a UI panel like every rig script
> does. It shows you the code it is talking about and the exact words in that
> code that produced each line.
>
> It never launches Blender and never runs, imports or evaluates a line of what
> it finds. It reads bytes. It makes no internet connection of its own and sends
> no telemetry.
>
> **What it does not claim.** It gives you an inventory, not a verdict. It is
> not an antivirus and it does not detect malware; it reports where code can
> hide in a .blend and names what that code does. It can be evaded — a script
> written to look ordinary will read as ordinary. There is no green tick
> anywhere in it, and there never will be: a tick on a file that later turns out
> to be malicious is exactly the promise this tool tells you not to accept from
> anyone. When nothing fires, it says so in grey and lists what it actually
> looked at. Deciding whether to trust a file stays your call, and the tool's
> job is to give you something to decide with.
>
> Free, GPLv3, the whole source is public. Windows, one file, no installer.
>
> Copyright (C) 2026 Sacha Geneviève. GPLv3-or-later, with no warranty of any
> kind. Blender is a registered trademark of the Blender Foundation; Blend X-Ray
> is an independent project, not affiliated with or endorsed by it.

## 6. Product description — French

> **Blend X-Ray — voir le code contenu dans un .blend avant de l'ouvrir**
>
> Un fichier .blend peut transporter du Python, et Blender peut être réglé pour
> l'exécuter à la seconde où le fichier s'ouvre. C'est ainsi qu'a fonctionné la
> campagne CGTrader de novembre 2025 : des rigs et des packs d'assets d'aspect
> ordinaire, avec à l'intérieur un script marqué en exécution automatique. Les
> antivirus n'analysent pas l'intérieur d'un .blend, et l'avertissement de
> Blender vous dit qu'un fichier veut exécuter des scripts sans vous dire ce
> qu'ils font.
>
> Blend X-Ray analyse le fichier et liste ce qu'il y a dedans — blocs de script,
> expressions de drivers, nœuds OSL et script, bibliothèques liées, chemins de
> fichiers — et explique chacun en mots ordinaires : celui-ci contacte
> internet, celui-là lance un programme sur votre machine, cet autre définit un
> panneau d'interface comme le fait tout script de rig. Il vous montre le code
> dont il parle, et les mots exacts de ce code qui ont amené chaque ligne.
>
> Il ne lance jamais Blender et n'exécute, n'importe ni n'évalue jamais une
> ligne de ce qu'il trouve. Il lit des octets. Il ne se connecte jamais à
> internet de lui-même et n'envoie aucune statistique.
>
> **Ce qu'il ne prétend pas faire.** Il vous donne un inventaire, pas un
> verdict. Ce n'est pas un antivirus et il ne détecte pas les logiciels
> malveillants ; il signale les endroits où du code peut se cacher dans un
> .blend et nomme ce que ce code fait. On peut le contourner — un script écrit
> pour avoir l'air ordinaire aura l'air ordinaire. Il n'y a aucune coche verte
> nulle part, et il n'y en aura jamais : une coche sur un fichier qui se révèle
> plus tard malveillant, c'est exactement la promesse que cet outil vous dit de
> n'accepter de personne. Quand rien ne réagit, il l'écrit en gris et liste ce
> qu'il a effectivement regardé. Décider si un fichier mérite votre confiance
> reste votre décision, et le travail de l'outil est de vous donner de quoi
> décider.
>
> Gratuit, GPLv3, code source entièrement public. Windows, un seul fichier,
> aucun installeur.
>
> Copyright (C) 2026 Sacha Geneviève. GPLv3 ou ultérieure, sans aucune garantie.
> Blender est une marque déposée de la Blender Foundation ; Blend X-Ray est un
> projet indépendant, sans affiliation ni approbation de sa part.

---

## 7. The SmartScreen paragraph — for the product page

Put this on the page itself, not only in the zip. A buyer who meets the warning
without having been told about it concludes the download is bad; a buyer who was
told about it first concludes the page is honest. Suggested heading: **"Windows
will warn you the first time — here is why"**.

### English

> **Windows will warn you the first time you run it.**
>
> BlendXRay.exe is not code-signed. Windows shows a blue box saying *"Windows
> protected your PC"*, and the button you need is hidden behind the **More
> info** link inside that box; click it, then click **Run anyway**. Windows asks
> once per machine.
>
> The reason is a certificate, not the file. A code-signing certificate costs
> 200–400 EUR a year, and SmartScreen's reputation score only builds up once a
> binary has been downloaded a great many times — so a new certificate would not
> remove the warning immediately either. That expense is deferred. The warning
> means Windows does not recognise the publisher; it says nothing about what is
> in the file.
>
> **Your antivirus may object too, and may quarantine the download.** Two
> ordinary reasons, neither of them a second opinion about the program: an
> unsigned one-file PyInstaller executable is a shape many engines treat as
> suspicious by itself, and the demonstration .blend in the zip contains a
> sample script written to look like the real attack — many scanners read
> inside archives and those are exactly the words they look for. It carries no
> working payload. If it happens, take the source route below rather than
> adding a blanket exclusion for a folder.
>
> If you would rather not run a downloaded binary from someone you have no
> reason to trust — which is the argument this tool makes about .blend files —
> then don't. The source is public and short: read it and run it from Python
> instead. <https://github.com/gensacha/blend-xray>

### French

> **Windows vous avertira au premier lancement.**
>
> BlendXRay.exe n'est pas signé numériquement. Windows affiche un cadre bleu
> « Windows a protégé votre ordinateur », et le bouton dont vous avez besoin est
> caché derrière le lien **Informations complémentaires** à l'intérieur du
> cadre : cliquez dessus, puis sur **Exécuter quand même**. Windows ne pose la
> question qu'une fois par machine.
>
> La raison tient à un certificat, pas au fichier. Un certificat de signature de
> code coûte 200 à 400 EUR par an, et la réputation SmartScreen ne se construit
> qu'à partir d'un grand nombre de téléchargements — un certificat neuf ne ferait
> donc pas disparaître l'avertissement du jour au lendemain. Cette dépense est
> reportée. L'avertissement signifie que Windows ne reconnaît pas l'éditeur ; il
> ne dit rien du contenu du fichier.
>
> **Votre antivirus peut lui aussi réagir, voire mettre le téléchargement en
> quarantaine.** Deux raisons ordinaires, et aucune des deux n'est un second
> avis sur le programme : un exécutable PyInstaller en un seul fichier et non
> signé est une forme que beaucoup de moteurs jugent suspecte à elle seule, et
> le .blend de démonstration contenu dans l'archive porte un script d'exemple
> écrit pour ressembler à la vraie attaque — beaucoup d'antivirus lisent à
> l'intérieur des archives, et ce sont précisément les mots qu'ils cherchent. Ce
> script ne contient aucune charge active. Si cela arrive, prenez la voie du
> code source ci-dessous plutôt que d'ajouter une exclusion générale sur un
> dossier.
>
> Si vous préférez ne pas lancer un binaire téléchargé chez quelqu'un que rien
> ne vous oblige à croire — c'est exactement l'argument que cet outil tient au
> sujet des .blend — alors ne le lancez pas. Le code source est public et court :
> lisez-le et lancez-le depuis Python. <https://github.com/gensacha/blend-xray>

---

## 8. Words this project does not use

The vocabulary rule is machine-checked in the test suite and applies to the page
copy as much as to the tool: never **safe**, **clean**, **no threat**,
**verdict:** or **100%** in English, and never **sûr**, **sain**, **propre** or
**sans danger** in French — not even inside a negation, because a skimming
reader keeps the word and drops the "not". There is no green tier and no tick.
"Nothing found in the categories checked" is the strongest thing the tool ever
says, and the page should not say anything stronger on its behalf.

Also worth keeping out of the copy: no apology for the SmartScreen warning, and
no claim that the tool detects malware. It reports an inventory of where code
can hide in a .blend, and names what that code does.

One more, now that money is involved: nothing on the page may imply that paying
changes the answer the tool gives, gets you a look at a file, or buys any
undertaking about a file's contents. The tip is goodwill. It is not a support
contract and it is not an assurance.
