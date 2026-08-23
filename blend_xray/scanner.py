# SPDX-License-Identifier: GPL-3.0-or-later
"""Parse a .blend file and inventory the places code can hide in it.

Nothing here launches Blender and nothing here executes anything found in the
file. The file is validated structurally by :mod:`blend_xray.guards` first, then
read with blender-asset-tracer in pure-Python mode.

DNA field names drift between Blender versions (2.79 stored a Text's path in
``name``; modern builds use ``filepath``), so every field read goes through
:func:`_first_field` or :func:`_read_path_field`, which try several candidate
names and tolerate absence rather than assuming one layout.
"""

from __future__ import annotations

import contextlib
import tempfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from . import dna_constants as dna
from . import driver_expr, explain, guards, identity, libpath, strings
from .models import (
    Category,
    DriverFinding,
    OSLFinding,
    PathFinding,
    ScanResult,
    TextFinding,
)

REQUIRED_BAT_VERSION = "1.23"

#: How often the text-line walk polls the wall-clock budget. Every line would
#: put a ``time.monotonic()`` call in the hot loop of a million-line body for
#: no useful extra precision; every 64 lines keeps the overshoot to a fraction
#: of a millisecond of reading.
DEADLINE_POLL_LINES = 64

#: Longest byte string this tool will accept as a *path* field (64 KiB).
#: Blender's own ``FILE_MAX`` is 1024 and Windows' extended limit is 32767, so
#: this refuses only fields that were never paths. A structural constant, not a
#: user budget: no legitimate file gets near it and no setting should raise it.
MAX_PATH_FIELD_BYTES = 64 * 1024


class ToolError(Exception):
    """Blend X-Ray itself is misconfigured (exit code 3)."""


def assert_bat_version() -> str:
    """Refuse to run against blender-asset-tracer 2.x.

    BAT 2.x dropped standalone parsing and requires a Blender 5.1+ install to
    do its work. Silently accepting it would turn Blend X-Ray into a tool that
    needs the very application we are trying not to launch.
    """
    try:
        from importlib.metadata import PackageNotFoundError, version
    except ImportError as exc:  # pragma: no cover - stdlib since 3.8
        raise ToolError(str(exc)) from exc

    try:
        found = version("blender-asset-tracer")
    except PackageNotFoundError as exc:
        raise ToolError(strings.t("err_bat_missing")) from exc

    if found != REQUIRED_BAT_VERSION:
        raise ToolError(strings.t("err_bat_version", found=found))
    return found


def _first_field(block: Any, names: tuple[bytes, ...], **kwargs: Any) -> Any:
    """Return the first present field among ``names``, else ``None``."""
    for name in names:
        try:
            if not block.has_field(name):
                continue
            return block.get(name, **kwargs)
        except Exception:
            continue
    return None


def _blocks_of_type(bfile: Any, type_name: bytes) -> Iterator[Any]:
    """Yield every block whose DNA struct is ``type_name``."""
    index = bfile.sdna_index_from_id.get(type_name)
    if index is None:
        return
    for block in bfile.blocks:
        if block.sdna_index == index:
            yield block


def _decode(raw: Any) -> str:
    if raw is None:
        return ""
    if isinstance(raw, bytes):
        return raw.decode("utf-8", errors="replace")
    return str(raw)


def _read_path_field(block: Any, names: tuple[bytes, ...]) -> str | None:
    """Read a path field that may be a ``char[N]`` array or a ``char *``.

    Blender uses both spellings depending on the struct and the version, and
    ``block.get()`` on a pointer returns the raw address -- which would render
    a null pointer as the literal string "0". ``get_pointer`` normalises this:
    it dereferences integers and passes non-integers (an actual char array)
    straight through.

    A ``char *`` path is bounded only by the block's declared length, which
    :func:`guards._check_block_length` compares against the *file*, not against
    anything path-shaped. So a small hostile file can declare a "path" of tens
    of megabytes, and every consumer of this function then pays for it --
    :func:`blend_xray.libpath.classify_library_path` most of all, whose cost
    grows with the number of ``/`` segments. That is how a file could still
    outrun ``--max-seconds`` inside a single datablock after the deadline was
    threaded through every stage: the deadline is polled between items, and
    this was one item. :data:`MAX_PATH_FIELD_BYTES` closes it at the read.
    """
    for name in names:
        try:
            if not block.has_field(name):
                continue
            value = block.get_pointer(name, default=None)
        except Exception:
            continue
        if value is None:
            continue
        if isinstance(value, (bytes, bytearray)):
            text = _decode(_checked_path_bytes(bytes(value)))
        elif hasattr(value, "as_bytes_string"):
            try:
                raw = value.as_bytes_string()
            except Exception:
                continue
            text = _decode(_checked_path_bytes(raw))
        else:
            continue
        if text:
            return text
    return None


def _checked_path_bytes(raw: bytes) -> bytes:
    """Refuse a "path" field no filesystem could ever hold.

    Blender's own ``FILE_MAX`` is 1024 bytes and the longest path across a
    ~100-file corpus of real .blend files is 125 characters, so the cap here
    has three orders of magnitude of headroom over anything legitimate. Past
    it, the field is not a path that got long -- it is a payload wearing a path
    field, and the honest answer is the same refusal
    :func:`guards.check_field_size` already gives an absurd string length.
    """
    if len(raw) > MAX_PATH_FIELD_BYTES:
        raise guards.MalformedBlendError(
            strings.t("guard_path_too_long", declared=len(raw), limit=MAX_PATH_FIELD_BYTES)
        )
    return raw


# --------------------------------------------------------------------------
# struct Text  (DNA_text_types.h)
# --------------------------------------------------------------------------
def _read_text_lines(
    bfile: Any, block: Any, limits: guards.Limits, deadline: guards.Deadline
) -> tuple[str, int, bool]:
    """Walk the ``lines`` ListBase of TextLine structs and join them.

    Returns ``(source, total_bytes, truncated)``.

    **Every line is kept, including the empty ones.** Blender stores a text
    datablock as one TextLine per line with the newlines stripped, so the body
    is the lines joined back together with ``\\n`` -- and a blank line is a
    TextLine holding the empty string, not the absence of a line. Dropping
    those turned ``import os\\n\\n\\nx = 1\\n`` into ``import os\\nx = 1``: the
    displayed source was not what Blender would run, and
    :func:`blend_xray.identity.sha256_of` hashed a reconstruction instead of
    the file's content, which broke the one promise the identity layer makes --
    that anyone can re-extract the block and re-compute the same digest. Two
    bodies differing only in blank lines also collided, on the single match
    class that is allowed to suppress escalation.

    The byte budget is enforced while walking, so a file claiming a million
    lines cannot exhaust memory. The joining newline is counted against it too:
    ``total`` is the length of the string this returns, which is what keeps the
    cap meaningful now that a line contributing no characters still contributes
    a list entry. A body of nothing but blank lines is bounded exactly like any
    other.

    The time budget is enforced here too, and it has to be: the byte cap is
    16 MiB, and a file can spend the entire wall-clock budget inside one
    datablock without ever reaching it. Polled every
    :data:`DEADLINE_POLL_LINES` lines rather than every line, because
    ``time.monotonic()`` per line is measurable on a million-line body and the
    granularity buys nothing.
    """
    parts: list[str] = []
    total = 0
    truncated = False

    try:
        line_block = block.get_pointer((b"lines", b"first"))
    except Exception:
        return "", 0, False

    seen: set[int] = set()
    while line_block is not None:
        if line_block.addr_old in seen:
            break  # cyclic list: hostile or corrupt, stop rather than spin
        seen.add(line_block.addr_old)
        if len(seen) % DEADLINE_POLL_LINES == 0 and deadline.expired:
            truncated = True
            break

        # TextLine.line is a `char *`, so it must be dereferenced. Reading it
        # with .get() would yield the pointer's integer value, not the text.
        chunk = ""
        try:
            text_ptr = line_block.get_pointer(b"line")
            if text_ptr is not None:
                declared = _first_field(line_block, (b"len",))
                if isinstance(declared, int):
                    guards.check_field_size(declared, text_ptr.size, limits)
                chunk = _decode(text_ptr.as_bytes_string())
        except guards.MalformedBlendError:
            raise
        except Exception:
            chunk = ""

        total += len(chunk) + (1 if parts else 0)  # +1 for the joining newline
        if total > limits.max_script_bytes:
            truncated = True
            break
        parts.append(chunk)

        try:
            line_block = line_block.get_pointer(b"next")
        except Exception:
            break

    return "\n".join(parts), total, truncated


def _mark_timeout(result: ScanResult, stage: Category, deadline: guards.Deadline) -> bool:
    """Record that the budget ran out at ``stage``. Always returns ``False``.

    The ``False`` is the signal the stage functions return to say "stop", so
    the caller cannot record a timeout and carry on by accident.
    """
    if not result.timed_out:
        result.timed_out = True
        result.timed_out_at = str(stage)
        result.time_budget = deadline.limit
    return False


def _identity_of(
    source: str, database: identity.Database, result: ScanResult
) -> identity.IdentityMatch | None:
    """Look one body up in the known-script database, tolerating any failure.

    A damaged database must cost identity context and nothing else, so a
    lookup that blows up is downgraded to a scan warning rather than allowed
    to take the file's whole inventory with it.
    """
    if not source.strip() or not database.usable:
        return None
    try:
        return database.match(source)
    except Exception as exc:
        result.warnings.append(f"identity lookup: {exc}")
        return None


def _load_identity_database(result: ScanResult) -> identity.Database:
    """Fetch the known-script database, downgrading any failure to a warning.

    ``identity.load_database`` already promises never to raise. This is the
    belt to that pair of braces: a scan must not be lost to an unanticipated
    failure in an optional context layer, so an empty database with a stated
    reason is always the worst case here.
    """
    try:
        database = identity.default_database()
    except Exception as exc:
        result.warnings.append(f"known-script database: {exc}")
        return identity.Database()
    result.warnings.extend(database.problems)
    return database


def _read_text_block(
    bfile: Any,
    block: Any,
    limits: guards.Limits,
    deadline: guards.Deadline,
    database: identity.Database,
    result: ScanResult,
) -> TextFinding | None:
    """One text datablock, or ``None`` when the budget ran out reading it.

    The deadline is polled between the two costs of a block, not only around
    it. Pulling a 14 MiB body out of the DNA is one expense; ``ast.parse``,
    the literal sweep and the known-script lookup over that body are another,
    and a single block can spend the whole budget on either half.

    Returning ``None`` rather than a half-analysed finding is deliberate: a
    ``TextFinding`` with no explanation is how this tool represents an *empty*
    block, so emitting one for a block we simply did not get to would state
    the opposite of the truth. The caller records the timeout instead.
    """
    name = _decode(block.id_name)[2:] or "<unnamed>"
    flags = _first_field(block, (b"flags", b"flag")) or 0
    if not isinstance(flags, int):
        flags = 0
    filepath = _read_path_field(block, (b"filepath", b"name"))
    source, size, truncated = _read_text_lines(bfile, block, limits, deadline)
    if deadline.expired:
        return None

    explanation = explain.explain_source(source, deadline) if source.strip() else None
    # Checked again on the way out. The literal sweep inside explain_source
    # stops when the budget goes, so an explanation produced across the
    # boundary is a partial sweep -- and a partial sweep says "nothing
    # notable" about strings it never looked at. Dropping the block and
    # letting the scan-level notice speak is honest; keeping it is not.
    if deadline.expired:
        return None

    return TextFinding(
        name=name,
        filepath=filepath,
        flags=flags,
        flag_names=tuple(dna.decode_flags(flags, dna.TEXT_FLAG_NAMES)),
        is_autorun=bool(flags & dna.TXT_ISSCRIPT),
        is_memory=bool(flags & dna.TXT_ISMEM),
        is_external=bool(flags & dna.TXT_ISEXT),
        source=source,
        source_bytes=size,
        truncated=truncated,
        explanation=explanation,
        identity=_identity_of(source, database, result),
    )


def _scan_texts(
    bfile: Any, limits: guards.Limits, result: ScanResult, deadline: guards.Deadline
) -> bool:
    database = _load_identity_database(result)
    for block in bfile.find_blocks_from_code(dna.CODE_TEXT):
        if deadline.expired:
            return _mark_timeout(result, Category.TEXT, deadline)
        try:
            finding = _read_text_block(bfile, block, limits, deadline, database, result)
        except (guards.MalformedBlendError, MemoryError, RecursionError):
            # Exhaustion is not a per-block problem to note and walk past. It
            # says the file beat the parser, and scan_file turns it into a
            # refusal. Listed explicitly because the analysis this now wraps
            # can raise both, and the broad clause below would otherwise
            # downgrade a failed scan to a footnote.
            raise
        except Exception as exc:
            result.warnings.append(f"text block: {exc}")
            continue
        if finding is None:
            return _mark_timeout(result, Category.TEXT, deadline)
        result.texts.append(finding)
    return True


# --------------------------------------------------------------------------
# struct ChannelDriver  (DNA_anim_types.h)
# --------------------------------------------------------------------------
def _driver_owner_map(bfile: Any, deadline: guards.Deadline) -> dict[int, str]:
    """Map ChannelDriver block address -> owning FCurve's RNA path.

    Bounded by the same budget as everything else: this walks every FCurve
    in the file, and a file can declare a great many of them. Running out of
    time here costs owner labels, not the driver findings themselves, which
    fall back to "<unattached driver>".
    """
    owners: dict[int, str] = {}
    for fcurve in _blocks_of_type(bfile, b"FCurve"):
        if deadline.expired:
            break
        try:
            driver = fcurve.get_pointer(b"driver")
            if driver is None:
                continue
            # DNA declares this as `*rna_path` (char *), so `get()` would hand back
            # the raw address and stringify it. _read_path_field dereferences it.
            rna = _read_path_field(fcurve, (b"rna_path",))
            index = _first_field(fcurve, (b"array_index",))
            label = rna or "<unknown property>"
            if isinstance(index, int) and index:
                label = f"{label}[{index}]"
            owners[driver.addr_old] = label
        except guards.MalformedBlendError:
            raise
        except Exception:
            continue
    return owners


def _driver_evaluates_expression(dtype: Any) -> bool:
    """Whether Blender reads the ``expression`` field for this driver type.

    ``evaluate_driver`` sends ``DRIVER_TYPE_AVERAGE``/``SUM`` to
    ``evaluate_driver_sum`` and ``MIN``/``MAX`` to ``evaluate_driver_min_max``;
    only ``DRIVER_TYPE_PYTHON`` reaches ``evaluate_driver_python``, and
    ``driver_compile_simple_expr`` refuses before it starts unless the type is
    ``DRIVER_TYPE_PYTHON`` (``if (driver->type != DRIVER_TYPE_PYTHON) { return
    false; }``). For the other types the stored expression is never read, so
    describing how it would be evaluated is a claim about nothing --
    3,527 of the 22,520 driver findings across the two corpora are exactly
    this case.

    https://raw.githubusercontent.com/blender/blender/e6d1620ad53feed4a83e3b168f0a2ea74f4de6ce/source/blender/blenkernel/intern/fcurve_driver.cc

    An unreadable or non-integer type field is treated as *evaluated*. We would
    rather over-report an inert expression than let a corrupt or hostile type
    field switch the analysis off, and a missing field is not evidence that the
    driver is one of the arithmetic kinds.
    """
    return not isinstance(dtype, int) or dtype == dna.DRIVER_TYPE_PYTHON


def _explain_driver(
    expression: str, cache: dict[str, explain.Explanation], deadline: guards.Deadline
) -> explain.Explanation:
    """Run one driver expression through the full explanation engine.

    Drivers were previously classified by :mod:`blend_xray.driver_expr` alone,
    so no network, subprocess or dynamic-code rule ever reached them and a
    payload sitting in a driver could not influence the banner or the closing
    recommendation. ``__import__('os').system('calc.exe')`` in a driver came
    back as "worth reading" under "nothing here matched the patterns Blend
    X-Ray treats as alarming".

    Cost is contained two ways, because the corpora hold 22,520 drivers across
    101 files. Only expressions the simple-expression classifier already
    rejected get here -- a simple expression is arithmetic over driver
    variables by construction, so it cannot contain a call, an attribute or a
    string for any rule to match -- and identical expressions are analysed
    once per scan. In practice that is 2 parses for the whole corpus.
    """
    cached = cache.get(expression)
    if cached is not None:
        return cached
    # ``ambient_names``: a driver is evaluated against a namespace Blender
    # assembled, and it is one expression, so it can hold neither the import
    # that would ground a module name nor the assignment that would make a
    # local variable look like one. Requiring the import here would have made
    # ``os.system('calc.exe')`` in a driver report nothing at all.
    result = explain.explain_source(expression, deadline, ambient_names=True)
    cache[expression] = result
    return result


def _scan_drivers(bfile: Any, result: ScanResult, deadline: guards.Deadline) -> bool:
    owners = _driver_owner_map(bfile, deadline)
    cache: dict[str, explain.Explanation] = {}
    for block in _blocks_of_type(bfile, b"ChannelDriver"):
        if deadline.expired:
            return _mark_timeout(result, Category.DRIVER, deadline)
        try:
            expression = _decode(_first_field(block, (b"expression",), as_str=True))
            dtype = _first_field(block, (b"type",))
            flags = _first_field(block, (b"flag",)) or 0
        except guards.MalformedBlendError:
            raise
        except Exception as exc:
            result.warnings.append(f"driver block: {exc}")
            continue

        if not expression.strip():
            continue

        evaluated = _driver_evaluates_expression(dtype)
        is_simple: bool | None = None
        reason = ""
        explanation: explain.Explanation | None = None
        if evaluated:
            is_simple, reason = driver_expr.classify_expression(expression)
            if not is_simple:
                explanation = _explain_driver(expression, cache, deadline)

        type_key = dtype if isinstance(dtype, int) else None
        result.drivers.append(
            DriverFinding(
                owner=owners.get(block.addr_old, "<unattached driver>"),
                expression=expression[: dna.DRIVER_EXPRESSION_MAXLEN],
                driver_type=type_key if type_key is not None else -1,
                driver_type_name=dna.DRIVER_TYPE_NAMES.get(type_key, f"unknown({dtype})"),
                flags=flags if isinstance(flags, int) else 0,
                flag_names=tuple(dna.decode_flags(flags or 0, dna.DRIVER_FLAG_NAMES)),
                is_simple=is_simple,
                classification_reason=reason,
                expression_is_evaluated=evaluated,
                explanation=explanation,
            )
        )
    return True


# --------------------------------------------------------------------------
# struct NodeShaderScript  (DNA_node_types.h)
# --------------------------------------------------------------------------
def _scan_osl(bfile: Any, result: ScanResult, deadline: guards.Deadline) -> bool:
    for block in _blocks_of_type(bfile, b"NodeShaderScript"):
        if deadline.expired:
            return _mark_timeout(result, Category.OSL, deadline)
        try:
            mode = _first_field(block, (b"mode",))
            mode = mode if isinstance(mode, int) else dna.NODE_SCRIPT_INTERNAL
            filepath = _read_path_field(block, (b"filepath",))
            bhash = _decode(_first_field(block, (b"bytecode_hash",), as_str=True)) or None

            size = 0
            with contextlib.suppress(Exception):
                bc = block.get_pointer(b"bytecode")
                if bc is not None:
                    size = int(getattr(bc, "size", 0) or 0)
        except guards.MalformedBlendError:
            raise
        except Exception as exc:
            result.warnings.append(f"script node: {exc}")
            continue

        result.osl_nodes.append(
            OSLFinding(
                owner="<shader node tree>",
                mode=mode,
                mode_name=dna.NODE_SCRIPT_MODE_NAMES.get(mode, f"unknown({mode})"),
                filepath=filepath if mode == dna.NODE_SCRIPT_EXTERNAL else None,
                bytecode_bytes=size,
                bytecode_hash=bhash,
            )
        )
    return True


# --------------------------------------------------------------------------
# struct Library  (DNA_ID.h) and informational filepaths
# --------------------------------------------------------------------------
#: Re-exported so ``from blend_xray.scanner import classify_library_path``
#: keeps working. The implementation moved to :mod:`blend_xray.libpath` when it
#: stopped touching the filesystem -- that module's docstring carries the whole
#: reason, which is that ``resolve()`` on a path chosen by the scanned file was
#: an outbound SMB connection and an NTLM credential leak on Windows.
classify_library_path = libpath.classify_library_path


def _scan_libraries(
    bfile: Any, blend_dir: Path, result: ScanResult, deadline: guards.Deadline
) -> bool:
    for block in bfile.find_blocks_from_code(dna.CODE_LIBRARY):
        if deadline.expired:
            return _mark_timeout(result, Category.LIBRARY, deadline)
        # The classification sits inside the guard, not after it. Every
        # other stage wraps all of its per-block work; this one used to
        # wrap only the read, so anything classify_library_path could ever
        # raise would take the whole scan down instead of costing one
        # library entry, which is not how any sibling category behaves.
        try:
            raw = _read_path_field(block, (b"filepath", b"name")) or ""
            if raw:
                result.libraries.append(classify_library_path(raw, blend_dir))
        except guards.MalformedBlendError:
            raise
        except Exception as exc:
            result.warnings.append(f"library block: {exc}")
            continue
    return True


def _scan_filepaths(bfile: Any, result: ScanResult, deadline: guards.Deadline) -> bool:
    for code in dna.INFORMATIONAL_PATH_CODES:
        # Polled per code as well as per block: enumerating the blocks of a
        # code is itself work, and a category with no blocks at all would
        # otherwise never consult the budget and report itself as finished.
        if deadline.expired:
            return _mark_timeout(result, Category.FILEPATH, deadline)
        for block in bfile.find_blocks_from_code(code):
            if deadline.expired:
                return _mark_timeout(result, Category.FILEPATH, deadline)
            try:
                raw = _read_path_field(block, (b"filepath", b"name")) or ""
                name = _decode(block.id_name)[2:]
            except guards.MalformedBlendError:
                raise
            except Exception:
                continue
            if raw:
                result.filepaths.append(PathFinding(kind=code.decode("ascii"), name=name, path=raw))
    return True


def _inventory(
    bfile: Any, path: Path, limits: guards.Limits, result: ScanResult, deadline: guards.Deadline
) -> None:
    """Run every category in order, stopping at the first that runs out of time.

    Each stage returns ``False`` once the budget is spent, and the chain stops
    there rather than starting a category it cannot finish. What was already
    collected stays in ``result``; ``result.timed_out`` records that the rest
    was never looked at, and every surface is required to say so.
    """
    stages = (
        lambda: _scan_texts(bfile, limits, result, deadline),
        lambda: _scan_drivers(bfile, result, deadline),
        lambda: _scan_osl(bfile, result, deadline),
        lambda: _scan_libraries(bfile, path.parent, result, deadline),
        lambda: _scan_filepaths(bfile, result, deadline),
    )
    for stage in stages:
        if not stage():
            return


def scan_file(path: Path, limits: guards.Limits | None = None) -> ScanResult:
    """Inventory one .blend file.

    Raises :class:`guards.MalformedBlendError` (exit 2) for hostile or broken
    files and :class:`ToolError` (exit 3) for tool misconfiguration.

    ``limits.max_seconds`` covers this whole function, not just the structural
    walk inside :func:`guards.preflight`. One :class:`guards.Deadline` is made
    here and handed down: expiry before the file is parsed is still a refusal,
    expiry once datablocks are being read produces a partial result that says
    it is partial.
    """
    limits = limits or guards.Limits()
    assert_bat_version()

    from blender_asset_tracer.blendfile import BlendFile

    deadline = guards.Deadline(limits.max_seconds)
    result = ScanResult(path=path, categories_checked=tuple(Category))
    with tempfile.TemporaryDirectory(prefix="blend-xray-") as tmp:
        pre = guards.preflight(path, limits, Path(tmp), deadline)
        result.blender_version = pre.header.version
        result.pointer_size = pre.header.pointer_size
        result.compression = pre.compression
        result.block_count = pre.block_count

        try:
            bfile = BlendFile(pre.data_path)
        except Exception as exc:
            raise guards.MalformedBlendError(str(exc)) from exc

        try:
            _inventory(bfile, path, limits, result, deadline)
        except guards.MalformedBlendError:
            raise
        except (MemoryError, RecursionError) as exc:
            raise guards.MalformedBlendError(type(exc).__name__) from exc
        finally:
            with contextlib.suppress(Exception):
                bfile.close()

    return result
