# SPDX-License-Identifier: GPL-3.0-or-later
"""Parser hardening for hostile .blend files.

Why this module exists
----------------------
The BAM/BAT parser lineage reads block lengths, array counts and string
lengths straight out of attacker-controlled header fields with no upper bound.
A crafted file can therefore declare a 4 GiB array in a 200-byte file and
trigger a huge allocation, or ship a compressed stream that expands to
gigabytes.

So Blend X-Ray never hands a file to blender-asset-tracer until it has walked the
block table itself and checked that every declared length actually fits inside
the remaining bytes of the file. Compressed files are expanded through a hard
byte cap first. Everything here is read-only and allocates in bounded chunks.
"""

from __future__ import annotations

import dataclasses
import gzip
import struct
import time
from pathlib import Path
from typing import Any, BinaryIO, Final

from . import strings

BLENDER_MAGIC: Final = b"BLENDER"
GZIP_MAGIC: Final = b"\x1f\x8b"
ZSTD_MAGIC: Final = b"\x28\xb5\x2f\xfd"

# .blend file headers come in two layouts. Both are parsed here; see
# `parse_file_header` for the byte-level description and the upstream sources.
#
#: Legacy: "BLENDER" + pointer-size char + endianness char + 3 version chars.
LEGACY_HEADER_SIZE: Final = 12
#: File format version 1 (Blender 5.0+): 17 bytes, self-describing length.
LARGE_HEADER_SIZE: Final = 17
#: Bytes we must have in hand before either layout can be identified.
MAX_HEADER_SIZE: Final = LARGE_HEADER_SIZE
#: Back-compat alias for the legacy size. New code should say which one it means.
FILE_HEADER_SIZE: Final = LEGACY_HEADER_SIZE

# Block header ("BHead") layouts, per source/blender/blenloader_core/BLO_core_bhead.hh
# and the reference parser in scripts/modules/_blendfile_header.py
# (BlendFileHeader.create_block_header_struct). Selection follows
# BlenderHeader::bhead_type(): pointer size 4 -> BHead4, else format version 0
# -> SmallBHead8, else LargeBHead8.
#
#: BHead4 (20 bytes):      code[4], len(i32), old(u32), SDNAnr(i32), nr(i32).
_BHEAD_V0_32: Final = "4siIii"
#: SmallBHead8 (24 bytes): code[4], len(i32), old(u64), SDNAnr(i32), nr(i32).
_BHEAD_V0_64: Final = "4siQii"
#: LargeBHead8 (32 bytes): code[4], SDNAnr(i32), old(u64), len(i64), nr(i64).
#: The order genuinely differs -- SDNAnr moved ahead of ``old``, and len/nr
#: widened to 64 bits so one datablock may exceed 2 GiB. Signed formats are
#: deliberate: a negative declared length must still reach
#: :func:`_check_block_length` rather than wrap into a huge unsigned value.
_BHEAD_V1: Final = "4siQqq"

#: A terminating ENDB may be written as a bare 4-byte code plus one u32 rather
#: than a full block header. Upstream tolerates this exact case in
#: ``BlockHeader.__init__`` (scripts/modules/_blendfile_header.py), so refusing
#: it would mean calling a legitimate file truncated.
_SHORT_ENDB: Final = struct.Struct("<4sI")

_CHUNK: Final = 1 << 20  # 1 MiB, the unit for every bounded read.


class MalformedBlendError(Exception):
    """The file is not a .blend file we are willing to keep parsing."""


class NotABlendFileError(MalformedBlendError):
    """The file is not a Blender file at all (wrong magic, too short)."""


@dataclasses.dataclass(frozen=True)
class Limits:
    """Hard caps. Every one of these is a refusal point, not a warning."""

    #: Refuse to even open a file bigger than this (2 GiB).
    max_file_bytes: int = 2 * 1024**3
    #: Refuse a compressed stream that expands past this (4 GiB).
    max_decompressed_bytes: int = 4 * 1024**3
    #: Refuse a file declaring an absurd number of blocks.
    max_blocks: int = 4_000_000
    #: Wall-clock budget for parsing one file.
    max_seconds: float = 60.0
    #: Never materialise a single string/array field larger than this (64 MiB).
    max_field_bytes: int = 64 * 1024**2
    #: Longest script body we will read out of a text datablock (16 MiB).
    max_script_bytes: int = 16 * 1024**2


@dataclasses.dataclass(frozen=True)
class BlendHeader:
    pointer_size: int
    little_endian: bool
    #: Blender's own version number as digits, leading zeros stripped: "403"
    #: is 4.3, "500" is 5.0. Both header layouts normalise to this spelling.
    version: str
    #: 0 for the legacy header, 1 for the 17-byte header (Blender 5.0+).
    #: This also selects the block header layout -- see :data:`_BHEAD_V1`.
    file_format_version: int = 0
    #: Bytes the header occupies, i.e. the offset of the first block header.
    header_size: int = LEGACY_HEADER_SIZE


@dataclasses.dataclass(frozen=True)
class Preflight:
    """Outcome of the independent structural check."""

    path: Path
    header: BlendHeader
    block_count: int
    #: Path to uncompressed bytes -- the original file, or a temp file we made.
    data_path: Path
    was_compressed: bool
    compression: str


class Deadline:
    """A wall-clock budget that callers poll during long walks.

    Two ways to poll, because the budget means different things at different
    stages. Before the file has been parsed at all, running out of time is a
    refusal and :meth:`check` raises. Once datablocks are being inventoried
    there is already a partial answer worth showing, so the scanner polls
    :attr:`expired` instead and stops, keeping what it has and saying loudly
    that it stopped -- see :mod:`blend_xray.scanner`. Silently returning a
    short inventory would be the worst of the three outcomes: it reads exactly
    like a file with nothing in it.
    """

    def __init__(self, seconds: float) -> None:
        self._limit = seconds
        self._start = time.monotonic()

    @property
    def limit(self) -> float:
        return self._limit

    @property
    def expired(self) -> bool:
        """Whether the budget is spent. Never raises; safe to poll in a loop."""
        return time.monotonic() - self._start > self._limit

    def check(self) -> None:
        if self.expired:
            raise MalformedBlendError(strings.t("guard_timeout", limit=self._limit))


def detect_compression(head: bytes) -> str:
    if head.startswith(GZIP_MAGIC):
        return "gzip"
    if head.startswith(ZSTD_MAGIC):
        return "zstd"
    if head.startswith(BLENDER_MAGIC):
        return "none"
    return "unknown"


def _copy_capped(
    src: BinaryIO, dst: BinaryIO, limit: int, deadline: Deadline | None = None
) -> int:
    """Stream ``src`` into ``dst``, aborting past ``limit`` bytes or the deadline.

    This is the decompression-bomb guard: we never call ``.read()`` without a
    size, so a 10 KiB file that expands to 40 GiB costs us one chunk over the
    cap and nothing more.

    The byte cap alone was not enough. It is 4 GiB, which is a bound on the
    damage but not on the wait: a stream that expands slowly could hold the
    tool for minutes writing a temp file the user never asked for, with
    ``--max-seconds`` in the command line saying otherwise. The time budget is
    therefore checked per chunk as well, and whichever limit is reached first
    ends it.
    """
    written = 0
    while True:
        if deadline is not None:
            deadline.check()
        chunk = src.read(_CHUNK)
        if not chunk:
            return written
        written += len(chunk)
        if written > limit:
            raise MalformedBlendError(strings.t("guard_decompress_bomb", limit=limit))
        dst.write(chunk)


def _decompress_to(
    path: Path, dest: Path, kind: str, limits: Limits, deadline: Deadline | None = None
) -> None:
    """Expand ``path`` into ``dest`` under the bomb cap and the time budget."""
    try:
        if kind == "gzip":
            with gzip.open(path, "rb") as src, dest.open("wb") as dst:
                _copy_capped(src, dst, limits.max_decompressed_bytes, deadline)
            return

        import zstandard  # imported lazily: only needed for Blender 3.0+ files

        dctx = zstandard.ZstdDecompressor()
        with path.open("rb") as raw, dest.open("wb") as dst, dctx.stream_reader(raw) as src:
            _copy_capped(src, dst, limits.max_decompressed_bytes, deadline)
    except MalformedBlendError:
        raise
    except ImportError as exc:
        raise MalformedBlendError(strings.t("guard_decompress_failed", reason=str(exc))) from exc
    except Exception as exc:
        raise MalformedBlendError(strings.t("guard_decompress_failed", reason=str(exc))) from exc


def _decode_version(raw: bytes) -> str:
    """Turn the header's version digits into Blender's own version number.

    Legacy files spell 4.3 as ``403``; format-version-1 files zero-pad the same
    number to four digits (``0500`` for 5.0). Normalising to ``str(int(...))``
    means both spellings reach the report as "403" / "500". Anything that is
    not a run of ASCII digits is a refusal, matching upstream, which parses
    these bytes with a plain ``atoi``/``int()`` and cannot represent garbage.
    """
    if not raw.isdigit():
        raise MalformedBlendError(
            strings.t("guard_bad_version", chars=raw.decode("latin-1", errors="replace"))
        )
    return str(int(raw))


def format_version(version: str) -> str:
    """Write a header version number the way Blender writes it: ``500`` -> ``5.0``.

    The digits in the header are ``BLENDER_FILE_VERSION``, which upstream
    defines as major x 100 + minor (source/blender/blenloader_core/
    BLO_core_blend_header.hh). Printed verbatim they read as "Blender file
    version 500", "version 249", "version 403" -- true, and uncheckable by an
    artist, who has never seen those numbers anywhere in Blender's own
    interface. Blender calls them 5.0, 2.49 and 4.3.

    The two header layouts spell the *same* number differently -- three digits
    in the legacy header, four zero-padded in file format version 1 -- and
    :func:`_decode_version` has already normalised both to the integer's
    shortest spelling by the time anything gets here, so one formula covers
    both. The minor part is not zero-padded, because ``403`` is Blender 4.3 and
    ``249`` is Blender 2.49: the minor is a number, not a pair of digits.

    Anything that is not a run of digits is passed through untouched. The raw
    string is what stays in ``--json``; this is presentation only.
    """
    if not version.isdigit():
        return version
    number = int(version)
    return f"{number // 100}.{number % 100}"


def _parse_legacy_header(head: bytes) -> BlendHeader:
    """Parse the classic 12-byte header (file format version 0).

    Upstream calls this ``BLEND_FILE_FORMAT_VERSION_0`` and documents it as::

        0-6:  'BLENDER'
        7:    '-' for 8-byte pointers (SmallBHead8) or '_' for 4-byte (BHead4)
        8:    'v' for little endian or 'V' for big endian
        9-11: 3 ASCII digits encoding BLENDER_FILE_VERSION ('305' = 3.5)

    -- source/blender/blenloader_core/BLO_core_blend_header.hh
    """
    ptr_char = head[7:8]
    pointer_size = 4 if ptr_char == b"_" else 8

    endian_char = head[8:9]
    if endian_char == b"v":
        little_endian = True
    elif endian_char == b"V":
        little_endian = False
    else:
        raise MalformedBlendError(strings.t("guard_bad_endian", char=endian_char.decode("latin-1")))

    return _make_header(pointer_size, little_endian, head[9:12], 0, LEGACY_HEADER_SIZE)


def _parse_large_header(head: bytes) -> BlendHeader:
    """Parse the 17-byte header Blender 5.0 writes (file format version 1).

    Upstream calls this ``BLEND_FILE_FORMAT_VERSION_1`` and documents it as::

        0-6:   'BLENDER'
        7-8:   size of the header in bytes as ASCII digits (always '17' now)
        9:     always '-'
        10-11: File version format as ASCII digits (always '01' currently)
        12:    always 'v'
        13-16: 4 ASCII digits encoding BLENDER_FILE_VERSION ('0405' = 4.5)

    -- source/blender/blenloader_core/BLO_core_blend_header.hh

    Bytes 9 and 12 are now fixed separators, not fields: format version 1 has
    no 4-byte-pointer and no big-endian variant, so both are hard-checked and
    the values are hardcoded, exactly as ``BLO_readfile_blender_header_decode``
    does in source/blender/blenloader_core/intern/blo_core_blend_header.cc.
    Note the ``17`` is the header size and has nothing to do with
    ``BLENDER_FILE_SUBVERSION`` (also 17 today) -- that lives in the GLOB block.
    """
    declared_size = int(head[7:9])
    if declared_size != LARGE_HEADER_SIZE:
        raise MalformedBlendError(strings.t("guard_bad_header_size", size=declared_size))
    if len(head) < LARGE_HEADER_SIZE:
        raise NotABlendFileError(strings.t("guard_short_file", size=len(head)))

    ptr_char = head[9:10]
    if ptr_char != b"-":
        raise MalformedBlendError(
            strings.t("guard_bad_pointer_size", char=ptr_char.decode("latin-1"))
        )

    format_version = head[10:12]
    if not format_version.isdigit() or int(format_version) != 1:
        raise MalformedBlendError(
            strings.t("guard_bad_format_version", value=format_version.decode("latin-1"))
        )

    endian_char = head[12:13]
    if endian_char != b"v":
        raise MalformedBlendError(strings.t("guard_bad_endian", char=endian_char.decode("latin-1")))

    return _make_header(8, True, head[13:17], 1, LARGE_HEADER_SIZE)


def _make_header(
    pointer_size: int, little_endian: bool, version: bytes, fmt_version: int, size: int
) -> BlendHeader:
    return BlendHeader(
        pointer_size=pointer_size,
        little_endian=little_endian,
        version=_decode_version(version),
        file_format_version=fmt_version,
        header_size=size,
    )


def parse_file_header(head: bytes) -> BlendHeader:
    """Validate a .blend file header of either layout, or refuse the file.

    Blender 5.0 introduced a second, longer header alongside the classic
    12-byte one, so both are accepted here -- and only those two. Widening the
    parser is not permission to guess: every field is still checked against the
    single value upstream can emit, and an unknown header size, pointer size,
    format version, endianness or version spelling is still a refusal.

    The discriminator is byte 7 alone, as upstream does it::

        const bool is_legacy_header = ELEM(header_bytes[7], '_', '-');

    -- BLO_readfile_blender_header_decode(),
    source/blender/blenloader_core/intern/blo_core_blend_header.cc

    So the layout must never be inferred from the Blender version: 4.5 can read
    and (optionally) write either one.
    """
    if len(head) < LEGACY_HEADER_SIZE:
        raise NotABlendFileError(strings.t("guard_short_file", size=len(head)))
    if not head.startswith(BLENDER_MAGIC):
        raise NotABlendFileError(strings.t("guard_bad_magic"))

    marker = head[7:8]
    if marker in (b"_", b"-"):
        return _parse_legacy_header(head)
    if head[7:9].isdigit():
        return _parse_large_header(head)
    raise MalformedBlendError(strings.t("guard_bad_pointer_size", char=marker.decode("latin-1")))


def _check_block_length(declared: int, offset: int, total: int) -> None:
    """Refuse a block whose declared payload cannot fit in the file.

    This is the bounds check the upstream parser lineage lacks: ``declared``
    comes straight from attacker-controlled bytes, so it is compared against
    the bytes actually remaining before anything allocates.
    """
    if declared < 0:
        raise MalformedBlendError(
            strings.t("guard_block_negative", offset=offset, declared=declared)
        )
    remaining = total - offset
    if declared > remaining:
        raise MalformedBlendError(
            strings.t(
                "guard_block_overruns",
                offset=offset,
                declared=declared,
                remaining=remaining,
            )
        )


def block_header_format(header: BlendHeader) -> str:
    """The ``struct`` format for this file's block headers.

    Format version 1 moved ``len`` behind ``old`` and widened it to 64 bits, so
    the layout cannot be derived from the pointer size alone.
    """
    endian = "<" if header.little_endian else ">"
    if header.file_format_version == 1:
        return endian + _BHEAD_V1
    return endian + (_BHEAD_V0_64 if header.pointer_size == 8 else _BHEAD_V0_32)


def _is_short_endb(raw: bytes, offset: int, total: int) -> bool:
    """True only for the upstream-tolerated 8-byte ``ENDB`` tail at EOF.

    Kept deliberately narrow: exactly 8 bytes, code exactly ``ENDB``, and the
    file must end there. Anything else that runs short is still truncated.
    """
    if len(raw) != _SHORT_ENDB.size or offset + len(raw) != total:
        return False
    code, _value = _SHORT_ENDB.unpack(raw)
    return code == b"ENDB"


def _declared_length(header: BlendHeader, fields: tuple[Any, ...]) -> int:
    """Pull the payload length out of an unpacked block header."""
    # v0: (code, len, old, SDNAnr, nr) -- v1: (code, SDNAnr, old, len, nr).
    return int(fields[3] if header.file_format_version == 1 else fields[1])


def walk_block_table(
    data_path: Path, header: BlendHeader, limits: Limits, deadline: Deadline
) -> int:
    """Walk every block header, checking declared lengths against the file.

    Only block *headers* are read; payloads are seeked over. A hostile length
    field therefore fails :func:`_check_block_length` instead of allocating.
    """
    total = data_path.stat().st_size
    bhead_fmt = block_header_format(header)
    bhead_size = struct.calcsize(bhead_fmt)

    count = 0
    saw_endb = False
    with data_path.open("rb") as fh:
        fh.seek(header.header_size)
        offset = header.header_size

        while True:
            deadline.check()
            raw = fh.read(bhead_size)
            if len(raw) == 0:
                break
            if len(raw) < bhead_size:
                if _is_short_endb(raw, offset, total):
                    return count + 1  # ENDB seen, so the no-ENDB check below is moot
                raise MalformedBlendError(strings.t("guard_truncated", offset=offset))

            fields = struct.unpack(bhead_fmt, raw)
            code = fields[0]
            declared = _declared_length(header, fields)
            offset += bhead_size

            _check_block_length(declared, offset, total)

            count += 1
            if count > limits.max_blocks:
                raise MalformedBlendError(
                    strings.t("guard_too_many_blocks", limit=limits.max_blocks)
                )

            if code.startswith(b"ENDB"):
                saw_endb = True
                break

            fh.seek(declared, 1)
            offset += declared

    if not saw_endb:
        raise MalformedBlendError(strings.t("guard_no_endb"))
    return count


def preflight(
    path: Path, limits: Limits, workdir: Path, deadline: Deadline | None = None
) -> Preflight:
    """Validate ``path`` structurally before any real parser touches it.

    ``workdir`` receives the decompressed copy when the file is compressed;
    the caller owns its lifetime.

    ``deadline`` is accepted rather than always created here so that the
    budget spans the *whole* scan. When preflight owned it, ``--max-seconds``
    bounded the structural walk and nothing else, and everything after it --
    parsing, text reconstruction, ``ast.parse``, the literal sweeps -- ran with
    no time limit at all while the flag claimed otherwise.
    """
    # Not "0 bytes": nothing has been measured yet. See tests/test_guards.py.
    if not path.is_file():
        raise NotABlendFileError(strings.t("guard_not_a_file"))

    size = path.stat().st_size
    if size > limits.max_file_bytes:
        raise MalformedBlendError(
            strings.t("guard_file_too_large", size=size, limit=limits.max_file_bytes)
        )
    if size < LEGACY_HEADER_SIZE:
        raise NotABlendFileError(strings.t("guard_short_file", size=size))

    if deadline is None:
        deadline = Deadline(limits.max_seconds)
    with path.open("rb") as fh:
        head = fh.read(max(MAX_HEADER_SIZE, len(ZSTD_MAGIC)))

    compression = detect_compression(head)
    if compression == "unknown":
        raise NotABlendFileError(strings.t("guard_bad_magic"))

    data_path = path
    was_compressed = compression != "none"
    if was_compressed:
        data_path = workdir / (path.stem + ".decompressed")
        _decompress_to(path, data_path, compression, limits, deadline)
        with data_path.open("rb") as fh:
            head = fh.read(MAX_HEADER_SIZE)

    header = parse_file_header(head)
    deadline.check()
    block_count = walk_block_table(data_path, header, limits, deadline)

    return Preflight(
        path=path,
        header=header,
        block_count=block_count,
        data_path=data_path,
        was_compressed=was_compressed,
        compression=compression,
    )


def check_field_size(declared: int, remaining: int, limits: Limits) -> None:
    """Bounds-check a declared string/array length before materialising it."""
    if declared < 0 or declared > remaining or declared > limits.max_field_bytes:
        raise MalformedBlendError(
            strings.t("guard_string_too_long", declared=declared, remaining=remaining)
        )
