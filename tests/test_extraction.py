# SPDX-License-Identifier: GPL-3.0-or-later
"""Text-datablock extraction is byte-exact, and its two guards still hold.

The defect these close: ``scanner._read_text_lines`` skipped any line whose
reconstructed content was empty, so **every blank line vanished** from the
source the tool analysed, displayed and hashed. ``import os\\n\\n\\nx = 1\\n``
came back as ``import os\\nx = 1``.

That broke the one thing :mod:`blend_xray.identity` promises is verifiable by
anyone, forever -- "re-download the file, re-extract the block, re-compute the
hash". The tool was hashing a reconstruction, so nobody re-hashing the real
bytes could reproduce a recorded digest. It also collided two bodies that
differ only in blank lines, on the single match class allowed to suppress
escalation.

Blender stores a text datablock as one ``TextLine`` per line with the newlines
stripped (``text_from_buf`` in ``BKE_text``), including a final empty line when
the buffer ends in ``\\n``. So the body is the lines joined with ``\\n`` and a
blank line is a TextLine holding the empty string -- not the absence of a line.

Keeping the blank lines must not weaken the two guards on the walk, so the size
cap and the cycle guard are asserted here as well.
"""

from __future__ import annotations

import hashlib
import json
import struct
from pathlib import Path

import pytest

from blend_xray import guards, identity, scanner

from .blend_builder import BlendBuilder

#: The exact reproduction from the review.
REPRO = "import os\n\n\nx = 1\n"

BODIES = [
    REPRO,
    "",
    "\n",
    "\n\n\n",
    "a",
    "a\n",
    "\nleading blank\n",
    "trailing blanks\n\n\n",
    "one\n\ntwo\n\n\nthree",
    "def f():\n\n    return 1\n\n\nf()\n",
    "accents: éàü\n\nand a tab:\there\n",
]


def _blend_with(tmp_path: Path, body: str, name: str = "notes.py") -> Path:
    builder = BlendBuilder()
    builder.add_text(name, body, flags=0)
    path = tmp_path / "text.blend"
    path.write_bytes(builder.to_bytes())
    return path


def _extract(tmp_path: Path, body: str) -> str:
    return scanner.scan_file(_blend_with(tmp_path, body)).texts[0].source


# -- the round trip -----------------------------------------------------------
def test_the_reported_reproduction_no_longer_loses_its_blank_lines(tmp_path: Path) -> None:
    assert _extract(tmp_path, REPRO) == REPRO
    assert _extract(tmp_path, REPRO) != "import os\nx = 1"


@pytest.mark.parametrize("body", BODIES)
def test_extraction_round_trip_is_byte_exact(tmp_path: Path, body: str) -> None:
    """What went into the .blend is what comes back out of it, byte for byte."""
    assert _extract(tmp_path, body) == body


@pytest.mark.parametrize("body", BODIES)
def test_the_recorded_hash_is_a_hash_of_the_real_content(tmp_path: Path, body: str) -> None:
    """Anyone re-hashing the extracted block must get the recorded digest.

    Computed here with plain :mod:`hashlib` over the original body rather than
    through :func:`identity.sha256_of`, so the two halves of the promise are
    checked against each other instead of against themselves.
    """
    extracted = _extract(tmp_path, body)
    assert identity.sha256_of(extracted) == hashlib.sha256(body.encode("utf-8")).hexdigest()


def test_source_bytes_counts_the_body_that_is_returned(tmp_path: Path) -> None:
    """The reported size is the length of the source, newlines included."""
    finding = scanner.scan_file(_blend_with(tmp_path, REPRO)).texts[0]
    assert finding.source == REPRO
    assert finding.source_bytes == len(REPRO)
    assert finding.truncated is False


# -- what the lossy reconstruction cost the identity layer --------------------
def test_two_bodies_differing_only_in_blank_lines_no_longer_collide(tmp_path: Path) -> None:
    dense = "import bpy\nx = 1\n"
    spaced = "import bpy\n\n\nx = 1\n"
    assert identity.sha256_of(_extract(tmp_path, dense)) != identity.sha256_of(
        _extract(tmp_path, spaced)
    )


def test_a_database_keyed_on_one_spacing_does_not_match_the_other(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dense = "import bpy\nx = 1\n"
    spaced = "import bpy\n\n\nx = 1\n"
    entry = {
        "sha256": identity.sha256_of(dense),
        "script_name": "spacing.py",
        "byte_size": len(dense.encode("utf-8")),
        "origin": "Example Rig, Example Studio, release 2.1",
        "source_url": "https://example.invalid/rigs/example-2.1.zip",
        "fetched_on": "2026-08-23",
        "attested_by": "test fixture (single attester)",
        "attested_on": "2026-08-23",
        "notes": "Test fixture.",
        "generated": False,
    }
    path = tmp_path / "known_scripts.json"
    path.write_text(
        json.dumps({"schema": identity.SCHEMA_VERSION, "entries": [entry]}), encoding="utf-8"
    )
    monkeypatch.setattr(identity, "DATABASE_PATH", path)
    identity.clear_cache()
    try:
        assert scanner.scan_file(_blend_with(tmp_path, dense)).texts[0].identity is not None
        assert scanner.scan_file(_blend_with(tmp_path, spaced)).texts[0].identity is None
    finally:
        identity.clear_cache()


# -- the guards on the walk ---------------------------------------------------
def test_a_body_of_nothing_but_blank_lines_is_still_bounded(tmp_path: Path) -> None:
    """Blank lines cost a newline each, so the byte cap still bounds the walk.

    Before, an empty line contributed nothing at all to the running total; a
    file could then declare a million of them and the size cap would never
    notice. Counting the joining newline is what keeps the budget meaningful
    now that an empty line is kept.
    """
    body = "\n" * 5000
    path = _blend_with(tmp_path, body)
    limits = guards.Limits(max_script_bytes=100)
    finding = scanner.scan_file(path, limits).texts[0]
    assert finding.truncated is True
    assert len(finding.source) <= 100


def test_a_cyclic_line_list_stops_instead_of_spinning(tmp_path: Path) -> None:
    """The cycle guard is unchanged by keeping blank lines."""
    builder = BlendBuilder()
    first, second = builder.new_address(), builder.new_address()
    data_first = builder.add_raw(b"one\x00")
    data_second = builder.add_raw(b"two\x00")
    # second.next points back at first: a two-element ring.
    builder.add(
        b"DATA", "TextLine", struct.pack("<QQQQii", second, 0, data_first, 0, 3, 0), address=first
    )
    builder.add(
        b"DATA", "TextLine", struct.pack("<QQQQii", first, first, data_second, 0, 3, 0),
        address=second,
    )
    id_bytes = (b"TX" + b"loop.py")[:65].ljust(72, b"\x00")
    builder.add(b"TX", "Text", id_bytes + struct.pack("<QiiQQ", 0, 0, 0, first, second))
    path = tmp_path / "cycle.blend"
    path.write_bytes(builder.to_bytes())

    finding = scanner.scan_file(path).texts[0]
    assert finding.source == "one\ntwo"
