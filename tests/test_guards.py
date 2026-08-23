# SPDX-License-Identifier: GPL-3.0-or-later
"""Hardening tests: malformed, truncated, oversized and non-blend inputs.

Every fixture is generated in-process. No real malware sample is used.
"""

from __future__ import annotations

import gzip
import os
import struct
from pathlib import Path

import pytest

from blend_xray import guards, strings
from blend_xray.guards import Limits, MalformedBlendError, NotABlendFileError

from .blend_builder import BHEAD, BHEAD_LARGE, BlendBuilder, minimal_blend

LIMITS = Limits()

#: Real Blender 5.x demo files from blender.org, used to prove the 17-byte
#: header path against files this project did not build. They are not in the
#: repository -- they are third-party downloads -- so every test using them
#: skips rather than fails when absent.
#:
#: Point BLEND_XRAY_CORPUS at a directory holding them to run these. Without
#: it they skip, which means a clean checkout reports fewer passing tests than
#: a machine that has the corpus: that is expected, and the skip reason says so.
CORPUS = Path(os.environ.get("BLEND_XRAY_CORPUS", "")) if os.environ.get("BLEND_XRAY_CORPUS") else None
REAL_LARGE_HEADER_FILES = (
    "demo_mandelbrot_grow.blend",
    "demo_raycast-line.blend",
    "demo_skeleton-arm-xray.blend",
    "demo_cowboi_storytools.blend",
    "demo_gn_sample_sound_frequencies.blend",
)


def _write(tmp_path: Path, name: str, payload: bytes) -> Path:
    path = tmp_path / name
    path.write_bytes(payload)
    return path


def test_valid_synthetic_blend_passes_preflight(tmp_path: Path) -> None:
    path = _write(tmp_path, "ok.blend", minimal_blend())
    pre = guards.preflight(path, LIMITS, tmp_path)
    assert pre.header.pointer_size == 8
    assert pre.header.little_endian is True
    assert pre.compression == "none"
    assert pre.block_count >= 2  # DNA1 + ENDB


# -- not a blend file ------------------------------------------------------
@pytest.mark.parametrize(
    "payload",
    [
        b"PK\x03\x04" + b"\x00" * 100,  # a zip
        b"%PDF-1.7\n" + b"\x00" * 100,  # a pdf
        b"just some text, definitely not a blend file",
    ],
)
def test_not_a_blend_file(tmp_path: Path, payload: bytes) -> None:
    path = _write(tmp_path, "thing.blend", payload)
    with pytest.raises(NotABlendFileError):
        guards.preflight(path, LIMITS, tmp_path)


def test_empty_file_is_rejected(tmp_path: Path) -> None:
    path = _write(tmp_path, "empty.blend", b"")
    with pytest.raises(NotABlendFileError):
        guards.preflight(path, LIMITS, tmp_path)


# -- malformed header ------------------------------------------------------
def test_malformed_header_bad_pointer_size(tmp_path: Path) -> None:
    path = _write(tmp_path, "bad.blend", b"BLENDERXv403" + b"\x00" * 64)
    with pytest.raises(MalformedBlendError) as exc:
        guards.preflight(path, LIMITS, tmp_path)
    assert "pointer size" in str(exc.value)


def test_malformed_header_bad_endianness(tmp_path: Path) -> None:
    path = _write(tmp_path, "bad.blend", b"BLENDER-Q403" + b"\x00" * 64)
    with pytest.raises(MalformedBlendError) as exc:
        guards.preflight(path, LIMITS, tmp_path)
    assert "endianness" in str(exc.value)


def test_header_too_short(tmp_path: Path) -> None:
    path = _write(tmp_path, "short.blend", b"BLEND")
    with pytest.raises(NotABlendFileError):
        guards.preflight(path, LIMITS, tmp_path)


# -- truncated file --------------------------------------------------------
def test_truncated_mid_block_header(tmp_path: Path) -> None:
    """The file stops in the middle of a block header."""
    full = minimal_blend()
    path = _write(tmp_path, "trunc.blend", full[: len(full) - 10])
    with pytest.raises(MalformedBlendError):
        guards.preflight(path, LIMITS, tmp_path)


def test_truncated_body_is_caught_as_overrun(tmp_path: Path) -> None:
    """A block declares more payload than the file actually contains."""
    builder = BlendBuilder()
    builder.add_text("script.py", "print(1)", flags=0)
    full = builder.to_bytes()
    path = _write(tmp_path, "trunc2.blend", full[: len(full) // 2])
    with pytest.raises(MalformedBlendError):
        guards.preflight(path, LIMITS, tmp_path)


def test_missing_endb_block(tmp_path: Path) -> None:
    full = minimal_blend()
    # Drop the trailing ENDB header entirely.
    path = _write(tmp_path, "noendb.blend", full[: -BHEAD.size])
    with pytest.raises(MalformedBlendError) as exc:
        guards.preflight(path, LIMITS, tmp_path)
    assert "ENDB" in str(exc.value)


# -- oversized length field (the core hardening guard) ---------------------
def test_oversized_block_length_is_refused(tmp_path: Path) -> None:
    """A block claims 4 GiB of payload inside a ~200 byte file.

    This is the case the BAM/BAT parser lineage reads without an upper bound.
    We must refuse it instead of attempting the allocation.
    """
    payload = bytearray(b"BLENDER" + b"-v403")
    payload += BHEAD.pack(b"DATA", 0xFFFFFFF, 0x1000, 0, 1)
    payload += b"\x00" * 64
    path = _write(tmp_path, "huge.blend", bytes(payload))

    with pytest.raises(MalformedBlendError) as exc:
        guards.preflight(path, LIMITS, tmp_path)
    message = str(exc.value)
    assert "bytes remain" in message


def test_negative_block_length_is_refused(tmp_path: Path) -> None:
    payload = bytearray(b"BLENDER" + b"-v403")
    payload += BHEAD.pack(b"DATA", -1, 0x1000, 0, 1)
    payload += b"\x00" * 64
    path = _write(tmp_path, "neg.blend", bytes(payload))
    with pytest.raises(MalformedBlendError) as exc:
        guards.preflight(path, LIMITS, tmp_path)
    assert "negative" in str(exc.value)


def test_block_count_cap(tmp_path: Path) -> None:
    payload = bytearray(b"BLENDER" + b"-v403")
    for _ in range(50):
        payload += BHEAD.pack(b"DATA", 0, 0, 0, 1)
    payload += BHEAD.pack(b"ENDB", 0, 0, 0, 0)
    path = _write(tmp_path, "many.blend", bytes(payload))

    with pytest.raises(MalformedBlendError) as exc:
        guards.preflight(path, Limits(max_blocks=10), tmp_path)
    assert "more than" in str(exc.value)


def test_file_size_cap(tmp_path: Path) -> None:
    path = _write(tmp_path, "big.blend", minimal_blend())
    with pytest.raises(MalformedBlendError) as exc:
        guards.preflight(path, Limits(max_file_bytes=10), tmp_path)
    assert "above the" in str(exc.value)


def test_check_field_size_bounds() -> None:
    guards.check_field_size(10, 100, LIMITS)  # fits: no raise
    with pytest.raises(MalformedBlendError):
        guards.check_field_size(1000, 100, LIMITS)
    with pytest.raises(MalformedBlendError):
        guards.check_field_size(-1, 100, LIMITS)
    with pytest.raises(MalformedBlendError):
        guards.check_field_size(10**12, 10**13, LIMITS)


# -- decompression bombs ---------------------------------------------------
def test_gzip_decompression_bomb_is_capped(tmp_path: Path) -> None:
    """A small gzip that expands far past the cap must be refused."""
    path = tmp_path / "bomb.blend"
    with gzip.open(path, "wb") as fh:
        fh.write(b"\x00" * (8 * 1024 * 1024))

    with pytest.raises(MalformedBlendError) as exc:
        guards.preflight(path, Limits(max_decompressed_bytes=1024), tmp_path)
    assert "decompression bomb" in str(exc.value)


def test_gzipped_valid_blend_round_trips(tmp_path: Path) -> None:
    path = tmp_path / "packed.blend"
    with gzip.open(path, "wb") as fh:
        fh.write(minimal_blend())

    pre = guards.preflight(path, LIMITS, tmp_path)
    assert pre.was_compressed is True
    assert pre.compression == "gzip"
    assert pre.data_path != path


def test_corrupt_gzip_stream_is_refused(tmp_path: Path) -> None:
    path = _write(tmp_path, "corrupt.blend", b"\x1f\x8b" + b"\xff" * 200)
    with pytest.raises(MalformedBlendError):
        guards.preflight(path, LIMITS, tmp_path)


def test_deadline_expires() -> None:
    deadline = guards.Deadline(-1.0)  # already past
    with pytest.raises(MalformedBlendError) as exc:
        deadline.check()
    assert "longer than" in str(exc.value)


def test_detect_compression() -> None:
    assert guards.detect_compression(b"BLENDER-v403") == "none"
    assert guards.detect_compression(b"\x1f\x8b\x08\x00") == "gzip"
    assert guards.detect_compression(b"\x28\xb5\x2f\xfd\x00") == "zstd"
    assert guards.detect_compression(b"nope") == "unknown"


def test_parse_file_header_values() -> None:
    header = guards.parse_file_header(b"BLENDER-v403")
    assert (header.pointer_size, header.little_endian, header.version) == (8, True, "403")
    assert (header.file_format_version, header.header_size) == (0, 12)
    header32 = guards.parse_file_header(b"BLENDER_V279")
    assert (header32.pointer_size, header32.little_endian) == (4, False)


# -- file format version 1: the 17-byte header Blender 5.0 writes ----------
def test_parse_large_file_header_values() -> None:
    """``BLENDER17-01v0500`` -- header size 17, always 8-byte, always little."""
    header = guards.parse_file_header(b"BLENDER17-01v0500")
    assert header.pointer_size == 8
    assert header.little_endian is True
    assert header.file_format_version == 1
    assert header.header_size == 17
    # 0500 and 403 are the same integer field, so both reach the report the
    # same way: 5.0 is "500", not "0500".
    assert header.version == "500"


def test_parse_large_file_header_reads_minor_versions() -> None:
    assert guards.parse_file_header(b"BLENDER17-01v0501").version == "501"
    assert guards.parse_file_header(b"BLENDER17-01v0502").version == "502"


def test_large_header_synthetic_blend_passes_preflight(tmp_path: Path) -> None:
    path = _write(tmp_path, "v1.blend", minimal_blend(large_header=True))
    pre = guards.preflight(path, LIMITS, tmp_path)
    assert pre.header.file_format_version == 1
    assert pre.header.header_size == 17
    assert pre.header.pointer_size == 8
    assert pre.header.version == "500"
    assert pre.block_count >= 2  # DNA1 + ENDB


def test_large_header_blend_survives_gzip_round_trip(tmp_path: Path) -> None:
    """The header is read after decompression, so the extra 5 bytes must be
    read from the *decompressed* stream, not the compressed one."""
    path = tmp_path / "v1.blend.gz"
    with gzip.open(path, "wb") as fh:
        fh.write(minimal_blend(large_header=True))
    pre = guards.preflight(path, LIMITS, tmp_path)
    assert pre.compression == "gzip"
    assert pre.header.file_format_version == 1


# -- widening the parser must not mean accepting anything ------------------
@pytest.mark.parametrize(
    ("header", "expected"),
    [
        # Byte 7 is neither a pointer-size char nor a digit: pure garbage.
        (b"BLENDERZZZZZZZZZZ", "pointer size"),
        (b"BLENDER\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00", "pointer size"),
        # A header size upstream never emits.
        (b"BLENDER18-01v0500", "header size"),
        (b"BLENDER99-01v0500", "header size"),
        # Byte 9 is a fixed '-' separator in this layout.
        (b"BLENDER17_01v0500", "pointer size"),
        # Only file format version 01 exists.
        (b"BLENDER17-02v0500", "file format version"),
        (b"BLENDER17-99v0500", "file format version"),
        # Byte 12 is a fixed 'v'; format version 1 has no big-endian variant.
        (b"BLENDER17-01V0500", "endianness"),
        # The version field must be digits in both layouts.
        (b"BLENDER17-01vABCD", "version"),
        (b"BLENDER-vABC", "version"),
    ],
)
def test_malformed_header_refused(tmp_path: Path, header: bytes, expected: str) -> None:
    path = _write(tmp_path, "bad.blend", header + b"\x00" * 64)
    with pytest.raises(MalformedBlendError) as exc:
        guards.preflight(path, LIMITS, tmp_path)
    assert expected in str(exc.value)


def test_large_header_truncated_before_end_is_not_a_blend(tmp_path: Path) -> None:
    """17 bytes are declared but only 12 exist."""
    path = _write(tmp_path, "short.blend", b"BLENDER17-01")
    with pytest.raises(NotABlendFileError):
        guards.preflight(path, LIMITS, tmp_path)


def test_large_header_oversized_block_length_is_refused(tmp_path: Path) -> None:
    """The bounds check must apply to the 64-bit length field too."""
    payload = bytearray(b"BLENDER17-01v0500")
    payload += BHEAD_LARGE.pack(b"DATA", 0, 0x1000, 1 << 40, 1)
    payload += b"\x00" * 64
    path = _write(tmp_path, "huge_v1.blend", bytes(payload))
    with pytest.raises(MalformedBlendError) as exc:
        guards.preflight(path, LIMITS, tmp_path)
    assert "bytes remain" in str(exc.value)


def test_large_header_negative_block_length_is_refused(tmp_path: Path) -> None:
    payload = bytearray(b"BLENDER17-01v0500")
    payload += BHEAD_LARGE.pack(b"DATA", 0, 0x1000, -1, 1)
    payload += b"\x00" * 64
    path = _write(tmp_path, "neg_v1.blend", bytes(payload))
    with pytest.raises(MalformedBlendError) as exc:
        guards.preflight(path, LIMITS, tmp_path)
    assert "negative" in str(exc.value)


def test_legacy_block_layout_is_not_used_for_format_version_1(tmp_path: Path) -> None:
    """A v1 header with v0 block headers must not be read as if it parsed.

    This is the failure mode of a half-fix: accept the new header, then keep
    walking with the 24-byte layout.
    """
    path = _write(tmp_path, "mixed.blend", b"BLENDER17-01v0500" + minimal_blend()[12:])
    with pytest.raises(MalformedBlendError):
        guards.preflight(path, LIMITS, tmp_path)


# -- the upstream-tolerated short ENDB tail --------------------------------
def test_short_endb_tail_is_accepted(tmp_path: Path) -> None:
    full = minimal_blend()
    body = full[: -BHEAD.size] + struct.pack("<4sI", b"ENDB", 0)
    path = _write(tmp_path, "shortendb.blend", body)
    pre = guards.preflight(path, LIMITS, tmp_path)
    assert pre.block_count >= 2


def test_short_tail_that_is_not_endb_is_still_truncated(tmp_path: Path) -> None:
    full = minimal_blend()
    body = full[: -BHEAD.size] + struct.pack("<4sI", b"DATA", 0)
    path = _write(tmp_path, "shorttail.blend", body)
    with pytest.raises(MalformedBlendError):
        guards.preflight(path, LIMITS, tmp_path)


# -- the real blender.org files, when they are present ---------------------
@pytest.mark.parametrize("name", REAL_LARGE_HEADER_FILES)
def test_real_blender_5_demo_files_are_accepted(tmp_path: Path, name: str) -> None:
    if CORPUS is None:
        pytest.skip("set BLEND_XRAY_CORPUS to a directory of blender.org demo files to run this")
    path = CORPUS / name
    if not path.is_file():
        pytest.skip(f"corpus file {name} is not present in {CORPUS}")
    pre = guards.preflight(path, LIMITS, tmp_path)
    assert pre.header.file_format_version == 1
    assert pre.header.pointer_size == 8
    assert pre.header.version.startswith("5")
    assert pre.compression == "zstd"
    assert pre.block_count > 0


def test_directory_is_not_a_blend(tmp_path: Path) -> None:
    with pytest.raises(NotABlendFileError):
        guards.preflight(tmp_path, LIMITS, tmp_path)


# -- the message has to be true, not merely a message ------------------------
@pytest.mark.parametrize("kind", ["missing", "directory"])
def test_an_unstattable_path_is_not_reported_as_an_empty_file(
    tmp_path: Path, kind: str
) -> None:
    """A path that is absent or is a directory was never measured at 0 bytes.

    preflight() raised "the file is only 0 bytes, too small to be a .blend
    file" for anything ``is_file()`` refused, which is a stated fact about a
    file that in these cases does not exist. A tool whose whole argument is
    that it only reports what it observed does not get to invent an observed
    size.
    """
    target = tmp_path / "gone.blend" if kind == "missing" else tmp_path
    with pytest.raises(NotABlendFileError) as caught:
        guards.preflight(target, LIMITS, tmp_path)
    message = str(caught.value)
    assert message == strings.t("guard_not_a_file")
    assert "0 bytes" not in message
    assert "bytes" not in message


def test_a_genuinely_short_file_still_reports_its_real_size(tmp_path: Path) -> None:
    """The size claim survives where a size was actually measured."""
    path = _write(tmp_path, "tiny.blend", b"BLENDER")
    with pytest.raises(NotABlendFileError) as caught:
        guards.preflight(path, LIMITS, tmp_path)
    assert str(caught.value) == strings.t("guard_short_file", size=7)


def test_block_header_layout_matches_expectation() -> None:
    """Guards and the test builder must agree on the block header layouts.

    Sizes come from ``BLO_core_bhead.hh``: SmallBHead8 is 24 bytes,
    LargeBHead8 is 32.
    """
    legacy = guards.parse_file_header(b"BLENDER-v403")
    assert BHEAD.size == struct.calcsize(guards.block_header_format(legacy)) == 24

    large = guards.parse_file_header(b"BLENDER17-01v0500")
    assert BHEAD_LARGE.size == struct.calcsize(guards.block_header_format(large)) == 32

    legacy32 = guards.parse_file_header(b"BLENDER_v279")
    assert struct.calcsize(guards.block_header_format(legacy32)) == 20


# -- the version number the reader actually sees -------------------------------
# The header stores BLENDER_FILE_VERSION -- major x 100 + minor
# (BLO_core_blend_header.hh) -- and the report printed those digits verbatim:
# "Blender file version 500", "version 249", "version 403". True, and
# uncheckable by an artist, who has only ever seen Blender call them 5.0, 2.49
# and 4.3.
@pytest.mark.parametrize(
    ("raw", "shown"),
    [
        ("500", "5.0"),
        ("403", "4.3"),
        ("249", "2.49"),
        ("293", "2.93"),
        ("279", "2.79"),
        ("405", "4.5"),
    ],
)
def test_a_header_version_is_shown_the_way_blender_writes_it(raw: str, shown: str) -> None:
    assert guards.format_version(raw) == shown


@pytest.mark.parametrize("raw", ["", "abc", "4.5", "v500"])
def test_anything_that_is_not_digits_is_passed_through_untouched(raw: str) -> None:
    """A version this tool cannot read is echoed, never guessed at."""
    assert guards.format_version(raw) == raw


@pytest.mark.parametrize(
    ("header", "shown"),
    [
        (b"BLENDER-v403", "4.3"),
        (b"BLENDER-v249", "2.49"),
        (b"BLENDER_v279", "2.79"),
        (b"BLENDER17-01v0500", "5.0"),
        (b"BLENDER17-01v0405", "4.5"),
    ],
)
def test_both_header_layouts_reach_the_same_display(header: bytes, shown: str) -> None:
    """Three digits or four zero-padded ones, the encoded number is the same."""
    parsed = guards.parse_file_header(header)
    assert guards.format_version(parsed.version) == shown


def test_the_two_layouts_spelling_one_version_agree() -> None:
    legacy = guards.parse_file_header(b"BLENDER-v405")
    large = guards.parse_file_header(b"BLENDER17-01v0405")
    assert legacy.file_format_version != large.file_format_version
    assert legacy.version == large.version == "405"
    assert guards.format_version(legacy.version) == guards.format_version(large.version) == "4.5"
