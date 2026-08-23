# SPDX-License-Identifier: GPL-3.0-or-later
"""English string catalogue. Data only -- the machinery lives in :mod:`strings`.

Split out of ``strings.py`` when the combined catalogue passed this project's
file-size ceiling: two languages of prose plus the lookup machinery in one
module had grown past 900 lines and was still growing with every new surface.
The split is per language and nothing else, so adding a third language is
still "add a file, add one line to :data:`blend_xray.strings.CATALOGUE`".

Style rules, enforced by tests and identical in every language:
  * We describe what code *does*, never whether it is safe.
  * There is deliberately no "SAFE", no "clean", no risk score, no percentage,
    not even inside a negation -- a skimming reader picks up the word and
    drops the "not". Asserted by tests/test_scanner.py::test_report_never_says_safe.
  * When something is obfuscated we say we cannot tell, instead of guessing.
  * Blender's own on-screen UI labels ("Auto Run Python Scripts", "Register",
    "Preferences > Save & Load", ...) and code-level identifiers (TXT_ISSCRIPT,
    struct/flag/function names) are never translated: that is what the reader
    sees on screen or in their own script, so translating it would make the
    report harder to act on, not easier.
"""

from __future__ import annotations

from typing import Final

EN: Final[dict[str, str]] = {
    # -- tool identity -----------------------------------------------------
    "tool_name": "Blend X-Ray",
    "tool_tagline": "Inventory the code hidden inside a .blend file, without opening Blender.",
    "never_runs": "Blend X-Ray never launches Blender and never executes anything it finds.",
    # -- scan lifecycle ----------------------------------------------------
    "scanning_file": "Scanning: {path}",
    "scanned_n_files": "Scanned {count} file(s).",
    "no_files_matched": "No .blend files matched: {target}",
    # -- the inventory framing (never a verdict) ---------------------------
    "categories_checked_header": "Checked {count} categories:",
    "scan_timed_out_notice": (
        "PARTIAL INSPECTION -- the {limit}-second budget ran out while reading "
        "{stage}. Everything below describes only the part of the file that was "
        "read before that."
    ),
    "stage_text": "Python text blocks",
    "stage_driver": "driver expressions",
    "stage_osl": "OSL / script nodes",
    "stage_library": "linked libraries",
    "stage_filepath": "other datablock file paths",
    "stage_preflight": "the file's structure",
    # Deliberately avoids the words "safe" and "clean" even inside a negation:
    # a skimming reader picks up the word, not the "not". This is asserted by
    # tests/test_scanner.py::test_report_never_says_safe.
    "nothing_found": (
        "No embedded code found in the categories checked. That describes what "
        "Blend X-Ray looked for, and nothing more -- it only knows about the "
        "categories listed above, so treat it as an inventory rather than a "
        "clearance."
    ),
    "findings_header": "Found {summary}. Here they are:",
    "not_a_verdict": (
        "This is an inventory, not a verdict. Blend X-Ray reports what is in the "
        "file; deciding whether to trust it is your call."
    ),
    # -- the one-glance banner ---------------------------------------------
    # Three tiers and no more. There is deliberately no fourth, green,
    # "all clear" tier: see the reasoning in blend_xray/banner.py.
    # Each headline says what was FOUND. None of them rates the file.
    "banner_red_headline": "This file contains code that reaches outside Blender.",
    "banner_amber_headline": "This file contains code that needs a second pair of eyes.",
    "banner_neutral_headline": "Nothing found in the {count} categories checked.",
    # Used instead of the line above when the file does contain code, but
    # none of it reaches outside Blender and none of it needs a second
    # reader. Saying "nothing found" there would be untrue, and this banner
    # is read by people who will not read the list underneath it.
    "banner_neutral_headline_accounted": (
        "Nothing reaching outside Blender, in the {count} categories checked."
    ),
    # The plain sentence under the headline. It is assembled from the rules
    # that actually fired, so it names behaviour an artist can picture --
    # never a rule key and never a category name.
    # A scan that hit its time budget stops mid-file. The banner must not be
    # able to say "nothing found" about a file it did not finish reading, so
    # this headline replaces the neutral and amber ones whenever that happens.
    # RED keeps its own headline: something was already found reaching outside
    # Blender, and that outranks the caveat.
    "banner_timeout_headline": (
        "Blend X-Ray ran out of time on this file. What follows is a partial "
        "inspection."
    ),
    "banner_sentence": "It {actions}.",
    "banner_join_and": "and",
    "banner_recognised": (
        "Some of this code is on record as a published release ({names}). That is "
        "reported here; it is not a reason to keep the line above off your screen."
    ),
    "banner_neutral_not_clearance": (
        "This is not a clearance. It describes what was looked at, and nothing beyond it."
    ),
    "banner_neutral_checked": "Looked at: {categories}",
    # -- banner: what was found, in words an artist can picture ------------
    "banner_what_x_network": "contacts the internet",
    "banner_what_x_subprocess": "runs a program on your machine",
    "banner_what_x_living_off_land": "drives a built-in system tool to run commands",
    "banner_what_x_obfuscation": "decodes something and then runs the result as code",
    "banner_what_x_opaque_blob": "carries a long block of encoded data",
    "banner_what_x_persistence": "writes itself somewhere that starts with your system",
    "banner_what_x_credentials": "reads where passwords and crypto wallets are kept",
    "banner_what_x_lowlevel": "reaches into your operating system at a low level",
    "banner_what_library_unc": "links to a file on a network share",
    "banner_what_x_network_listen": "opens a port other machines can connect to",
    "banner_what_x_builtins_indirection": "reaches Python's built-ins by name at run time",
    "banner_what_x_indirect_call": "runs whatever another call handed back",
    "banner_what_x_assembled_name": "assembles the name of what it calls out of pieces",
    "banner_what_x_dynamic_code": "builds and runs code while it is running",
    "banner_what_x_file_write": "writes files",
    "banner_what_x_file_delete": "deletes files",
    "banner_what_x_makedirs": "creates folders",
    "banner_what_x_compile_code": "turns text into runnable code",
    "banner_what_x_deserialise": "reads saved Python data that can run code as it loads",
    "banner_what_x_runtime_import": "loads a module by name while it runs",
    "banner_what_x_opens_browser": "opens a web address in your browser",
    "banner_what_x_decodes_data": "decodes or decompresses data it carries",
    "banner_what_x_split_literal": "builds text out of separate pieces",
    "banner_what_x_handler_persist": "installs a handler that keeps running after you open other files",
    "banner_what_x_handler_register": "installs a handler that runs on Blender's own events",
    "banner_what_driver_code": "carries a driver expression that runs Python",
    "banner_what_library_drive_letter": "links to a file by a fixed drive letter",
    "banner_what_driver_not_simple": "has a driver expression that needs full Python",
    "banner_what_osl_bytecode": "carries precompiled shader bytecode",
    "banner_what_autorun_unrecognised": "is set to run a script the moment the file opens",
    "banner_what_unreadable_script": "contains a script Blend X-Ray could not read",
    "banner_what_scan_timed_out": "took longer to inspect than the time budget allowed",
    # -- closing recommendation --------------------------------------------
    # An alarming finding on its own leaves a non-programmer with a red flag they
    # cannot interpret, which is how a warning gets dismissed. These turn the
    # finding into a next action without ever pronouncing the file trustworthy.
    "recommend_header": "Recommendation",
    "recommend_needs_human": (
        "This file contains code Blend X-Ray cannot judge for you. Before you open it "
        "in Blender, ask someone who reads Python to look at the blocks marked "
        "above. If nobody can look at it, leave the file closed -- no asset is "
        "worth a compromised machine."
    ),
    "recommend_looks_ordinary": (
        "Nothing here matched the patterns Blend X-Ray treats as alarming, and the "
        "findings above are the kind an ordinary asset or rig file contains. That "
        "describes what was found and promises nothing beyond it, so read them "
        "yourself if you have any doubt."
    ),
    # Fires instead of recommend_needs_human when every alarming block in the
    # file was recognised, byte for byte, as belonging to a published release.
    # It does not say the file is harmless -- it says the blocks are not this
    # one artist's problem to review alone, and points at the origin so they can
    # judge that origin for themselves.
    "recommend_known_release": (
        "The code flagged in this file is on record as belonging to a published release, "
        "named block by block above with the origin it was recorded from. Nothing was "
        "removed from the list and nothing was toned down. This is not being handed to "
        "you for review because it is not a script only you can check -- it is one many "
        "people have already downloaded and read. What is left for you to judge is the "
        "origin named above: if it is not somewhere you would knowingly take a file from, "
        "treat this like any other unread script."
    ),
    # Never softened and never omitted: a scan that stopped early has looked at
    # part of the file, and every "nothing matched" sentence below it would be a
    # statement about the part it never reached.
    "recommend_timed_out": (
        "This inspection stopped before it finished. Blend X-Ray reached its "
        "{limit}-second budget while reading {stage} and did not look at the rest "
        "of the file, so nothing above describes what is in the part it never "
        "reached. Raise --max-seconds and scan it again, or treat this file as "
        "uninspected."
    ),
    "recommend_autorun_present": (
        "At least one script in this file is marked to run automatically the moment "
        "the file opens. Keep \"Auto Run Python Scripts\" turned off in "
        "Preferences > Save & Load unless you have read that script."
    ),
    # A script Blend X-Ray could not parse gets NO rule applied to it, so silence
    # about it means "not looked at", never "nothing there". Saying so is the
    # whole point: an unexamined script must never be summarised as ordinary.
    "recommend_unreadable": (
        "Blend X-Ray could not read {count} script(s) in this file, so none of its "
        "checks were applied to them and nothing above describes what they do. "
        "That is a gap in the inspection, not a result. Read them yourself, or "
        "ask someone who can."
    ),
    # -- category labels ---------------------------------------------------
    "cat_text": "Python text blocks (auto-run scripts)",
    "cat_driver": "Driver expressions",
    "cat_osl": "OSL / script nodes",
    "cat_library": "Linked libraries",
    "cat_filepath": "Other datablock file paths",
    # -- text datablocks ---------------------------------------------------
    "text_block_title": "Text block: {name}",
    "text_autorun_flag": (
        "MARKED AUTO-RUN (TXT_ISSCRIPT). Blender's own comment for this flag is: "
        '"Load the script as a Python module when loading the .blend file." '
        "This is the flag the November 2025 CGTrader campaign used."
    ),
    "text_not_autorun": "Not marked auto-run (TXT_ISSCRIPT is not set).",
    "text_flags": "Flags: {flags}",
    "text_filepath": "Text filepath: {path}",
    "text_is_mem": "TXT_ISMEM set: the text lives inside the .blend, not on disk.",
    "text_is_ext": "TXT_ISEXT set: the text is meant to come from an external file.",
    "text_source_header": "Source:",
    "text_truncated": "-- truncated at {shown} of {total} characters; re-run with --full to see all --",
    "text_empty": "(this text block is empty)",
    # -- drivers -----------------------------------------------------------
    "driver_title": "Driver expression on {owner}",
    "driver_type": "Driver type: {type_name}",
    "driver_expression": "Expression: {expr}",
    "driver_simple": (
        "Looks like a simple arithmetic expression. Blender evaluates these in "
        "a restricted built-in evaluator (no Python), so this kind of "
        "expression still works with Python auto-run disabled."
    ),
    "driver_suspicious": (
        "Uses names outside the restricted simple-expression evaluator, so it "
        "needs full Python -- which means it only runs if script auto-execution "
        "is enabled. Worth reading."
    ),
    # Printed instead of either line above when the driver's type means Blender
    # never reads the expression field at all. evaluate_driver() sends AVERAGE
    # and SUM to evaluate_driver_sum() and MIN/MAX to evaluate_driver_min_max();
    # only DRIVER_TYPE_PYTHON reaches the expression.
    "driver_expression_unused": (
        "Blender does not use this text. A {type_name} driver is worked out from "
        "the values of its inputs, and the expression field is never read for it. "
        "It is shown because it is stored in the file, not because it runs."
    ),
    "driver_use_self": "DRIVER_FLAG_USE_SELF is set: the expression can reach the object it drives.",
    "driver_flags": "Driver flags: {flags}",
    # -- OSL / script nodes ------------------------------------------------
    "osl_title": "Script node in node tree: {owner}",
    "osl_lower_severity": (
        "Lower severity: OSL script nodes are Cycles-only, OSL is off by "
        "default, and they run at render time -- not when the file is opened. "
        "This is not an auto-run vector."
    ),
    # "named below" promised a name nothing printed: NodeShaderScript does not
    # carry it, and the reader was left hunting for a line that never existed.
    "osl_internal": (
        "mode = NODE_SCRIPT_INTERNAL: the code comes from a text block stored "
        "inside this file. The node's own record does not carry that block's "
        "name, so look through the text blocks listed in this report."
    ),
    "osl_external": "mode = NODE_SCRIPT_EXTERNAL: the code comes from an external file.",
    "osl_filepath": "Script node filepath: {path}",
    "osl_has_bytecode": "This node carries {size} bytes of precompiled bytecode.",
    "osl_bytecode_hash": "Bytecode hash: {hash}",
    # -- libraries ---------------------------------------------------------
    "library_title": "Linked library: {path}",
    "library_relative": "Blend-relative path ('//'), resolves to: {resolved}",
    # Says what an absolute path *is*, and stops there. The old wording --
    # "this points outside the file's own folder" -- was asserted without ever
    # being checked, and it is wrong whenever the library sits beside the
    # .blend that links it. Containment is only claimed by the line below,
    # which is printed only when a text comparison established it.
    "library_absolute": (
        "ABSOLUTE PATH -- this names a fixed location on the machine that saved "
        "the file, not a place relative to the .blend."
    ),
    "library_absolute_inside": (
        "ABSOLUTE PATH -- this names a fixed location on the machine that saved "
        "the file. Written out, it does land inside this file's own folder."
    ),
    "library_escapes": "PATH ESCAPES the file's folder via '..' -- resolves to: {resolved}",
    "library_unc": "UNC NETWORK PATH -- this points at a network share ({host}).",
    # Printed above the line that says what the path really is. "//" is the
    # spelling an artist has seen a thousand times on ordinary linked assets,
    # so a path wearing it has to be called a disguise before anything else,
    # or the next line gets read as routine.
    "library_disguised": (
        "WRITTEN TO LOOK LIKE AN ORDINARY LINK -- this path starts with Blender's "
        "'//' marker, which normally means \"next to this .blend file\", but it "
        "carries extra separators that make it point at a root of its own instead."
    ),
    "library_drive": "DRIVE LETTER PATH -- this points at a specific drive on the opener's machine.",
    "library_ok_relative": "Stays inside the file's own folder.",
    # -- other filepaths ---------------------------------------------------
    "filepath_title": "{kind}: {name}",
    "filepath_value": "  path: {path}",
    "filepath_informational": (
        "Informational only. These are the external files the .blend expects to "
        "load. A path pointing at a network share or another machine is worth a look."
    ),
    # -- explanation layer -------------------------------------------------
    "explain_header": "What this code does, in plain language:",
    "explain_evidence": "(evidence: {evidence})",
    "explain_literals_header": "Strings found inside the code (URLs, paths, commands):",
    "explain_no_literals": "No URLs, paths or shell commands were found as plain text in this code.",
    "explain_unparseable": (
        "This code could not be parsed as Python, so Blend X-Ray could not analyse "
        "its structure. Reason: {reason}. Falling back to plain text search."
    ),
    "explain_too_large": (
        "This code is {size} bytes, larger than the {limit} byte analysis limit, "
        "so Blend X-Ray did not parse it. The raw text is still shown below."
    ),
    "explain_parse_exhausted": (
        "Parsing this code exhausted Python's parser (it is nested extremely "
        "deeply). That is unusual for hand-written code and is itself worth noting."
    ),
    "explain_obfuscated_honest": (
        "I can't tell you what this does, because it is deliberately hidden. "
        "That is itself the strongest signal here."
    ),
    "explain_obfuscated_partial": (
        "Part of this code is deliberately hidden and only becomes readable while it "
        "runs, so the list above is incomplete -- Blend X-Ray cannot see the concealed "
        "part. A legitimate rig or asset script has no reason to hide anything."
    ),
    "explain_nothing_notable": (
        "Nothing in this code matched any of the behaviours Blend X-Ray knows how "
        "to describe. That does not mean it does nothing -- it means Blend X-Ray "
        "has no rule for it. Read it yourself, or ask someone who reads Python."
    ),
    "explain_baseline": (
        "For comparison: a legitimate rig or asset script normally defines UI "
        "panels and operators (classes deriving from bpy.types.Panel or "
        "bpy.types.Operator), registers them in register()/unregister(), and "
        "touches nothing outside Blender. It has no reason to open a network "
        "connection, launch a program, or decode a hidden blob."
    ),
    # -- explanation rules -------------------------------------------------
    # Benign / expected in a legitimate asset file.
    "x_import_geometry": "imports 3D geometry",
    "x_ui_panel": ("defines a UI panel or operator -- this is what a normal rig script looks like"),
    "x_register": "registers its panels and operators with Blender (normal for an add-on or rig)",
    "x_driver_namespace": "registers driver helper functions used by a rig",
    # Worth showing the user.
    "x_file_write": "writes files to disk",
    "x_file_delete": "deletes files",
    "x_makedirs": "creates folders on disk",
    # Two handler sentences, because Blender treats the two cases differently.
    # Only a callback carrying @persistent survives the next file load; every
    # other handler is stripped by BPY_app_handlers_reset(false) before the
    # incoming file's own scripts run. Saying "every file you open afterwards"
    # about an undecorated handler was false on ~27 findings across the
    # institutional corpus, CloudRig among them.
    "x_handler_persist": (
        "installs a handler marked @persistent, so it keeps running on every file you "
        "open afterwards, not just this one"
    ),
    "x_handler_register": (
        "hooks itself into Blender's own events -- things like frame changes and file "
        "loads -- and runs each time one happens, until you open another file"
    ),
    "x_compile_code": (
        "turns text into runnable code without running it; something else has to run the result"
    ),
    "x_deserialise": (
        "reads saved Python data in a format that can run code as it is being read, so what "
        "runs depends on the data file rather than on this script"
    ),
    "x_runtime_import": (
        "loads a module by name while it runs; the name is written in the file, so you can "
        "see which one"
    ),
    "x_opens_browser": "hands a web address to your browser to open",
    "x_decodes_data": (
        "turns encoded or compressed data back into its original form, so you cannot read "
        "that data straight from the file"
    ),
    "x_split_literal": (
        "builds text by gluing pieces together, which keeps the finished text out of any "
        "search of the file"
    ),
    # Alarming.
    "x_network": "connects to the internet",
    "x_network_listen": (
        "opens a port on your machine that other machines can connect to"
    ),
    "x_subprocess": "runs an external program on your machine",
    "x_living_off_land": (
        "launches a Windows system tool that is commonly used to download and run things ({tools})"
    ),
    "x_dynamic_code": (
        "builds and runs code while it executes, so what it does is not visible in the file"
    ),
    # Says what was established -- a decoded value reaching an execution --
    # and not the conclusion the older sentence jumped to. The old wording
    # ("the content is deliberately hidden") was printed whenever a decode and
    # an exec merely appeared in the same file, which on real add-ons is
    # routinely two unrelated things.
    "x_obfuscation": (
        "decodes data and then runs the result as code, so what it finally does is not "
        "written anywhere in the file"
    ),
    # The three shapes of hiding. Each says what the code is arranging, never
    # what it will do -- once the names are gone that cannot be known, and
    # claiming otherwise would be the guess this tool refuses to make.
    "x_builtins_indirection": (
        "reaches Python's built-in functions by name at run time, which keeps the name of "
        "what it uses out of the file"
    ),
    "x_indirect_call": (
        "runs whatever another call handed back, so the name of what it finally runs is "
        "written nowhere in the file"
    ),
    "x_assembled_name": (
        "assembles the name of what it loads or calls out of separate pieces, so that name "
        "appears nowhere in the file"
    ),
    "x_opaque_blob": (
        "contains a {size}-character block of encoded text, which is not "
        "something a normal script needs"
    ),
    "x_persistence": "sets itself to start again automatically",
    "x_lowlevel": "calls low-level system functions",
    "x_credentials": "reads locations where passwords or wallets are stored",
    # Literal kinds.
    "lit_url": "URL",
    "lit_host": "host name",
    "lit_path": "file path",
    "lit_command": "shell command",
    "lit_blob": "encoded blob",
    # -- known-script identity layer ---------------------------------------
    # These lines say what a block IS. None of them says, or may be reworded to
    # imply, that a block is harmless: "byte-identical to cloudrig.py from
    # Blender Studio" stays true forever and anyone can re-check it, while
    # "harmless" becomes false the day a bug is found in CloudRig.
    # The evidence lines spell out what strong and medium evidence actually
    # mean, because an artist cannot act on the bare words.
    "identity_header": "Identity",
    "identity_line": "{script_name} -- {origin}",
    "identity_evidence_byte": (
        "Evidence: every byte of this block is identical to a copy Blend X-Ray has on "
        "record. That is the strongest match this database can make -- change one "
        "character anywhere in the script and it stops matching."
    ),
    "identity_evidence_structure": (
        "Evidence: the code is put together exactly like a copy on record, but the text "
        "inside the quotation marks is not the same. That is a weaker match, and it is "
        "weaker in the direction that matters: anyone editing this script can keep the "
        "structure untouched and change only the quoted text, which is where a download "
        "address would sit. Every difference is listed below, and this block still counts "
        "towards the recommendation."
    ),
    # Printed when a byte match lands on a script that is generated afresh per
    # file. The match is real and strong, but it identifies one generated copy
    # rather than a release many people share, so it does not stand the block
    # down -- and saying why keeps that from reading as an inconsistency.
    "identity_generated_byte": (
        "This script is written afresh for every rig, so matching it byte for byte "
        "identifies this one generated copy -- not a release that many people share and "
        "have read between them. It stays on the list for someone to look at."
    ),
    "identity_source": "On record from: {url} (fetched {fetched_on})",
    "identity_attested": (
        "Attested by {attested_by} on {attested_on}. That is one person's word that this "
        "hash belongs to that script -- not a review of what the script does."
    ),
    "identity_notes": "What that script is: {notes}",
    "identity_scope": (
        "This says what the block is, not what it is worth trusting. Everything listed "
        "above was still found inside it, at the severity it was found with."
    ),
    "identity_diff_header": "Quoted text that differs from the copy on record ({count}):",
    "identity_diff_line": "#{index}: on record {reference} -> in this file {actual}",
    "identity_diff_more": "... and {count} further difference(s) not shown.",
    "identity_diff_none": (
        "No quoted text differs. The two copies are apart only in spacing, comments or "
        "the order of lines."
    ),
    "identity_db_missing": (
        "The known-script database is not at {path}, so no block was checked against it. "
        "Everything else in this report was produced as usual."
    ),
    "identity_db_unreadable": (
        "The known-script database could not be read ({reason}), so no block was checked "
        "against it. Everything else in this report was produced as usual."
    ),
    "identity_db_schema": (
        "The known-script database is in a shape this version does not know ({found}), so "
        "no block was checked against it. Everything else in this report was produced as usual."
    ),
    "identity_bad_entry": "Known-script database entry #{index} was skipped: {reason}",
    # -- headline summary --------------------------------------------------
    "summary_blocks_found": "{count} code block(s) found.",
    "summary_look_at_this": "<-- look at this one",
    "summary_and_hidden": "and hides part of what it does",
    # Bracketed count, not "2 defines ...": a bare number turns the
    # description into a sentence subject and needs plural agreement,
    # which would have to be re-solved for every translated language.
    "summary_line": "  {count}x  {description} {marker}",
    # -- errors ------------------------------------------------------------
    "err_malformed": (
        "This file looks malformed or hostile, so Blend X-Ray stopped reading it. Reason: {reason}"
    ),
    "err_not_blend": "This is not a Blender file: {reason}",
    "err_unreadable": "Could not read {path}: {reason}",
    "err_bat_version": (
        "Blend X-Ray requires blender-asset-tracer 1.23, but version {found} is "
        "installed.\n"
        "Versions 2.x removed standalone parsing and require a Blender 5.1+ "
        "installation, which would defeat the whole point of this tool "
        "(inspecting a file WITHOUT opening Blender).\n"
        "Fix it with:  pip install -r requirements.txt"
    ),
    "err_bat_missing": (
        "blender-asset-tracer is not installed. Blend X-Ray cannot parse .blend "
        "files without it.\n"
        "Fix it with:  pip install -r requirements.txt"
    ),
    "err_tool": "Blend X-Ray hit an internal error: {reason}",
    # -- file header -------------------------------------------------------
    "compression_none": "not compressed",
    "compression_gzip": "gzip-compressed",
    "compression_zstd": "Zstandard-compressed",
    "compression_unrecognised": "unrecognised compression",
    "file_meta": (
        "Blender file version {version}, {pointers}-byte pointers, "
        "{compression}, {blocks} blocks."
    ),
    "warnings_header": "Warnings",
    # -- graphical interface -----------------------------------------------
    # Same rules as everywhere else: no verdict, no "safe", no green. The
    # window is a different surface for the same inventory, not a softer one.
    "gui_drop_prompt": "Drop a .blend file here, or use the buttons below.",
    "gui_drop_unavailable": (
        "Drag-and-drop is not available in this build (the optional tkinterdnd2 "
        "package is missing). Use the buttons below instead -- everything else works."
    ),
    "gui_choose_file": "Choose a file...",
    "gui_choose_folder": "Choose a folder...",
    "gui_file_dialog_title": "Choose a .blend file",
    "gui_folder_dialog_title": "Choose a folder to search for .blend files",
    "gui_blend_filter": "Blender files",
    "gui_all_files": "All files",
    "gui_cancel": "Cancel",
    "gui_cancel_pending": "Stopping after the file currently being read...",
    "gui_copy_report": "Copy report",
    "gui_copied": "The report was copied to the clipboard as plain text.",
    "gui_copy_nothing": "There is no report to copy yet.",
    "gui_language": "Language:",
    "gui_status_idle": "Nothing loaded. Choose a .blend file or a folder to begin.",
    "gui_status_reading": "Reading: {path}",
    "gui_status_counted": "Read {done} of {total} file(s).",
    "gui_status_done": "Finished reading {total} file(s).",
    "gui_status_cancelled": (
        "Stopped at your request after {done} of {total} file(s). What is shown "
        "below covers only the files that were already read."
    ),
    "gui_status_no_files": "No .blend files were found in: {target}",
    "gui_source_show": "Show the raw source ({lines} lines)",
    "gui_source_hide": "Hide the raw source",
    "gui_source_hint": (
        "The raw source is shown last on purpose: it is the least useful thing on "
        "screen for a reader who does not write Python."
    ),
    "gui_source_capped": (
        "This block was longer than the per-file reading limit, so only its first "
        "part was read. What is shown below is incomplete."
    ),
    "gui_error_header": "This file could not be read",
    # A failure while *drawing* a result, as opposed to while reading a file.
    # It is shown in the window because in a windowed build there is nowhere
    # else: sys.stderr is None. See blend_xray/gui/app.py::_handle_guarded.
    "gui_draw_failed": "This result could not be displayed: {reason}",
    # -- Windows right-click entry (optional, never an install step) --------
    "gui_shell_add": "Add to right-click menu",
    "gui_shell_remove": "Remove from right-click menu",
    # Shown when an entry exists but points somewhere this copy of the tool no
    # longer lives -- see blend_xray/gui/shell_integration.py::is_current.
    "gui_shell_repair": "Repair right-click menu",
    "gui_shell_stale": (
        "There is already an entry, but it runs a copy of Blend X-Ray that is no "
        "longer at that location, so the menu item currently does nothing. This "
        "is what it points at now:\n{command}\n\nConfirming replaces it with the "
        "command below."
    ),
    "gui_shell_verb": "Inspect with {tool}",
    "gui_shell_dialog_title": "Change to the Windows registry",
    "gui_shell_explain": (
        "This tool asks you not to run code you have not looked at. It holds "
        "itself to the same rule: nothing is written to the registry until you "
        "have read exactly what will be written."
    ),
    "gui_shell_confirm_add": (
        "This creates one registry key under your own user account "
        "(HKEY_CURRENT_USER). It needs no administrator rights, changes nothing "
        "for other accounts on this machine, and the Remove button undoes it.\n\n"
        "Key:\n{key}\n\nValue of that key's \\command sub-key:\n{command}\n\n"
        "Create it?"
    ),
    "gui_shell_confirm_remove": (
        "This deletes the following registry key, and nothing else.\n\n"
        "Key:\n{key}\n\nDelete it?"
    ),
    "gui_shell_added": 'Added. Right-click any .blend file and choose "{label}".',
    "gui_shell_removed": "Removed. The right-click entry is gone.",
    "gui_shell_failed": "The registry could not be changed: {reason}",
    # -- guard messages ----------------------------------------------------
    # Distinct from guard_short_file on purpose: nothing has been measured at
    # the point this is raised, so claiming a size would be inventing one.
    "guard_not_a_file": (
        "there is no readable file at this path -- it is missing, is not a file, "
        "or could not be read"
    ),
    "guard_short_file": "the file is only {size} bytes, too small to be a .blend file",
    "guard_bad_magic": "it does not start with the BLENDER magic bytes",
    "guard_bad_pointer_size": "the header declares an invalid pointer size ({char!r})",
    "guard_bad_endian": "the header declares an invalid endianness ({char!r})",
    "guard_bad_header_size": "the header declares an unknown header size ({size})",
    "guard_bad_format_version": "the header declares an unsupported file format version ({value!r})",
    "guard_bad_version": "the header declares a non-numeric Blender version ({chars!r})",
    "guard_block_overruns": (
        "a block at offset {offset} declares a length of {declared} bytes, but "
        "only {remaining} bytes remain in the file"
    ),
    "guard_block_negative": "a block at offset {offset} declares a negative length ({declared})",
    "guard_truncated": "the file ends in the middle of a block header at offset {offset}",
    "guard_no_endb": "the file has no ENDB block, so it is truncated or incomplete",
    "guard_too_many_blocks": "the file declares more than {limit} blocks",
    "guard_decompress_bomb": (
        "decompressing this file produced more than {limit} bytes, which is a "
        "decompression bomb pattern"
    ),
    "guard_decompress_failed": "the compressed data could not be decompressed: {reason}",
    "guard_file_too_large": "the file is {size} bytes, above the {limit} byte limit",
    "guard_timeout": "reading this file took longer than {limit} seconds",
    "guard_path_too_long": (
        "a datablock declares a file path of {declared} bytes, past the {limit}-byte "
        "limit -- no filesystem holds a path that long, so this field is not one"
    ),
    "guard_string_too_long": (
        "a string field declares {declared} bytes, but only {remaining} bytes remain in the file"
    ),
}
