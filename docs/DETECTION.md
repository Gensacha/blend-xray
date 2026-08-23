# What Blend X-Ray detects, and how it survives a hostile file

Reference detail for the categories Blend X-Ray inventories, and for the guards
that run before any of it. The [README](../README.md) has the summary; this file
has the field names and the numbers.

Values below were read from the Blender source tree (branch `main`, retrieved
2026-08-23) rather than guessed. They are cited in
`blend_xray/dna_constants.py` alongside the verbatim upstream comment.

## Before any of it: the version floor

Everything in this file is read out of the scanned file's **own SDNA** — the
`DNA1` block, where Blender records the layout of every struct it has just
saved. That is what lets Blend X-Ray find a `Text` body or a `ChannelDriver`
expression in a file written by a Blender it has never heard of, instead of
carrying a table of per-version byte offsets.

A `.blend` written **before Blender 2.45** has no `DNA1` block, because the SDNA
system did not exist yet. There is no layout to look anything up in, so the scan
stops with `No DNA1 block in file` and reports nothing at all. This is a refusal,
not an empty inventory, and the exit code is 2.

Measured over a 677-file corpus: the lowest file version that parsed is **2.45**;
the highest that was refused is **2.42**; and all 80 such refusals were intact,
uncorrupted files — magic bytes, header and `ENDB` all present — with header
versions from **1.28** to **2.42**. The floor is 2.45, not "2.4x". See
[the README](../README.md#the-99-refusals-and-the-version-floor).

## Auto-run scripts — `struct Text` (`DNA_text_types.h`)

Every text datablock is reported. Ones carrying **`TXT_ISSCRIPT` (`1 << 4`)** are
flagged loudly — Blender's own comment for that flag is *"Load the script as a
Python module when loading the `.blend` file."* This is the CGTrader vector.
`TXT_ISMEM` (`1 << 2`), `TXT_ISEXT` (`1 << 3`), `TXT_ISDIRTY` (`1 << 0`) and
`Text.filepath` are reported too.

## Driver expressions — `struct ChannelDriver` (`DNA_anim_types.h`)

`char expression[256]`, with `eDriver_Types` (`DRIVER_TYPE_AVERAGE = 0`,
`PYTHON = 1`, `SUM = 2`, `MIN = 3`, `MAX = 4`) and `eDriver_Flags` (including
`DRIVER_FLAG_USE_SELF = 1 << 6`, `DRIVER_FLAG_PYTHON_BLOCKED = 1 << 5`).

Expressions are **classified rather than flagged equally**. Blender evaluates
"simple expressions" in a restricted C evaluator that runs even with Python
disabled. An expression needing anything outside that set requires full Python,
and therefore only runs if script auto-execution is enabled. Blend X-Ray tells
you which kind you are looking at, and why.

The accepted set is transcribed from `builtin_ops[]` and `parse_unary()` in
[`expr_pylike_eval.cc`](https://raw.githubusercontent.com/blender/blender/e6d1620ad53feed4a83e3b168f0a2ea74f4de6ce/source/blender/blenlib/intern/expr_pylike_eval.cc),
not from that file's own header comment, which is stale and omits four of the
functions. It is `radians degrees abs fabs floor ceil trunc round int sin cos tan
asin acos atan atan2 exp log sqrt pow fmod lerp clamp smoothstep`, plus variadic
`min`/`max`, the constants `pi True False`, and `frame` — which the driver layer
injects as parameter 0. Arity is checked too, because a call at the wrong arity
fails the evaluator's own `CHECK_ERROR`.

There is **no `sign`**, and the operators `**`, `%` and `//` are **not**
supported: `parse_mul()` has a case for `*` and `/` and nothing else, and there
is no power level anywhere in the file. So `frame ** 2` falls through to
`BPY_driver_exec` and does require auto-run.

**Only `DRIVER_TYPE_PYTHON` uses the expression field at all.**
`evaluate_driver()` sends `AVERAGE`/`SUM` to `evaluate_driver_sum()` and
`MIN`/`MAX` to `evaluate_driver_min_max()`, and `driver_compile_simple_expr()`
returns false outright for any other type
([`fcurve_driver.cc`](https://raw.githubusercontent.com/blender/blender/e6d1620ad53feed4a83e3b168f0a2ea74f4de6ce/source/blender/blenkernel/intern/fcurve_driver.cc)).
For those driver types the stored expression is inert data. Blend X-Ray still
prints it — it is in the file — but says plainly that Blender never reads it, and
does not describe an evaluation that will not happen.

That test **fails open**. If the driver's `type` field cannot be read as an
integer — a corrupt or hostile file — Blend X-Ray treats the expression as
evaluated and analyses it in full, rather than concluding from a field it could
not read that the code is inert.

An expression that does need full Python is run through the **same explanation
engine as a text datablock**, and its findings drive the banner and the closing
recommendation exactly as a script's would. A driver is a code path under the
same auto-execution gate; treating it as a lesser one was a blind spot.

## OSL / script nodes — `struct NodeShaderScript` (`DNA_node_types.h`)

`mode` (`NODE_SCRIPT_INTERNAL = 0` points at a Text block;
`NODE_SCRIPT_EXTERNAL = 1` uses `filepath[1024]`), plus `bytecode` and
`bytecode_hash[64]`.

**Reported at lower severity, and explicitly not presented as an auto-run
vector**: OSL script nodes are Cycles-only, OSL is off by default, and they run
at render time rather than at file load.

An internal script node's Text is *not* named on `NodeShaderScript` — the link
lives on the owning `bNode`'s `id` pointer — so the report does not name it and
does not pretend to. It says the code comes from a text block inside the file and
points at the text blocks it has already listed.

## Linked libraries — `struct Library` (`DNA_ID.h`)

`filepath[1024]`. Blend-relative `//` paths are resolved, and Blend X-Ray flags
absolute paths, `..` escapes outside the file's own folder, UNC network paths
(`\\server\share`, with the host named), and drive-letter paths.

An absolute path is reported as what it is — a fixed location on the machine that
saved the file — and **not** as one that points outside the file's own folder.
That claim used to be printed for every absolute path without ever being checked,
and it is wrong whenever the linked library sits beside the `.blend` that links
it. Containment is now computed, as pure text over `PurePath` with no filesystem
call of any kind, and it is only *claimed* when the comparison establishes it: a
`false` there means "not established", never "proven outside", because nothing
about a path written on somebody else's machine can be checked against a folder
on this one. The seven absolute paths in the measured corpora are all of that
kind and all get the neutral wording.

Only UNC and drive-letter paths spend a banner. Absolute paths and `//../..`
fired on essentially every linked library in the corpora, because
`//../../lib/x.blend` is the standard production layout — they stay in the
inventory and carry no alarm.

## Other datablock file paths

Images, sounds, fonts, caches and movie clips are inventoried as informational —
a file pointing at a network share is worth seeing.

---

# Hardening against hostile files

The BAM/BAT parser lineage reads block lengths, array counts and string lengths
straight out of attacker-controlled header fields **with no upper bound**. A
crafted file can declare a 4 GiB array inside a 200-byte file and trigger a huge
allocation.

So Blend X-Ray never hands a file to `blender-asset-tracer` until
`blend_xray/guards.py` has independently:

- validated the file header — both layouts, the classic 12-byte one and the
  17-byte one Blender 5.0 writes (magic, header size, file format version,
  pointer size, endianness, version digits) — and used the layout it found to
  pick the matching block-header layout, since file format version 1 reorders the
  fields as well as widening them;
- walked the entire block table itself, checking that **every declared block
  length fits inside the remaining bytes of the file** — reading only the block
  headers (20, 24 or 32 bytes, depending on the layout the file declares) and
  seeking over payloads, so a hostile length field can never cause an allocation;
- rejected negative lengths, missing `ENDB`, and absurd block counts (the ceiling
  is 4 000 000);
- expanded any gzip/zstd stream through a **hard decompressed-size cap** (4 GiB),
  reading in bounded 1 MiB chunks so a decompression bomb costs one chunk over
  the cap and nothing more;
- enforced a wall-clock budget, checked between chunks and between stages.

The whole file is capped at 2 GiB and any single field read at 64 MiB. String and
array fields are bounds-checked again at read time, and the `TextLine` walk
detects cyclic linked lists rather than spinning forever.

Failures produce a plain message — *"This file looks malformed or hostile, so
Blend X-Ray stopped reading it"* — and exit code `2`, never a crash or a hang.
A budget that expires here, during pre-flight and before the inventory has begun,
is also exit code `2`: nothing was read, so there is no partial inventory to
report.

The `ast` parsing layer is bounded too: source above 2 MiB is not parsed, source
nested deeper than 180 brackets is refused before `ast.parse` can exhaust the C
stack, and `RecursionError`/`MemoryError` are caught. Any of these falls back to
regex literal extraction and says so.
