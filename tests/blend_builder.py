# SPDX-License-Identifier: GPL-3.0-or-later
"""Build minimal, synthetic .blend files for the test suite.

Everything here is generated from scratch. No real malware sample and no real
production .blend file is used or required by the tests.

The layout follows what blender-asset-tracer's ``decode_structs`` expects:

    'SDNA' 'NAME' <u32 n> <names..>   pad4
           'TYPE' <u32 t> <typenames..> pad4
           'TLEN' <u16 * t>             pad4
           'STRC' <u32 s> <s * (u16 type_idx, u16 nfields, nfields * (u16, u16))>

Two file layouts can be emitted, because Blender writes both:

* the legacy 12-byte header with ``SmallBHead8`` block headers,
  ``<4s i Q i i`` (code, length, old address, SDNA index, count);
* the 17-byte header Blender 5.0 writes (file format version 1) with
  ``LargeBHead8`` block headers, ``<4s i Q q q`` (code, SDNA index, old
  address, length, count) -- a different field *order*, not just wider fields.

See ``BLO_core_bhead.hh`` and ``BLO_core_blend_header.hh`` upstream.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field

BASE_TYPE_SIZES: dict[str, int] = {
    "char": 1,
    "uchar": 1,
    "short": 2,
    "ushort": 2,
    "int": 4,
    "float": 4,
    "double": 8,
    "void": 0,
}

#: (struct name, [(field type, field name)]) -- a subset of Blender's DNA big
#: enough to exercise every Blend X-Ray detector.
STRUCT_DEFS: list[tuple[str, list[tuple[str, str]]]] = [
    ("ID", [("char", "name[66]"), ("char", "_pad[6]")]),
    ("ListBase", [("void", "*first"), ("void", "*last")]),
    (
        "TextLine",
        [
            ("TextLine", "*next"),
            ("TextLine", "*prev"),
            ("char", "*line"),
            ("char", "*format"),
            ("int", "len"),
            ("int", "_pad0"),
        ],
    ),
    (
        "Text",
        [
            ("ID", "id"),
            ("char", "*filepath"),
            ("int", "flags"),
            ("int", "_pad0"),
            ("ListBase", "lines"),
        ],
    ),
    ("Library", [("ID", "id"), ("char", "filepath[1024]")]),
    (
        "ChannelDriver",
        [("char", "expression[256]"), ("int", "type"), ("int", "flag")],
    ),
    (
        "NodeShaderScript",
        [
            ("int", "mode"),
            ("int", "flag"),
            ("char", "filepath[1024]"),
            ("char", "bytecode_hash[64]"),
            ("char", "*bytecode"),
        ],
    ),
]

POINTER_SIZE = 8
#: SmallBHead8, used by legacy-header files.
BHEAD = struct.Struct("<4siQii")
#: LargeBHead8, used by file format version 1.
BHEAD_LARGE = struct.Struct("<4siQqq")

LEGACY_FILE_HEADER = b"BLENDER-v"
LARGE_FILE_HEADER = b"BLENDER17-01v"


def _array_size(name: str) -> int:
    if "[" not in name:
        return 1
    total = 1
    for part in name.split("[")[1:]:
        total *= int(part.rstrip("]"))
    return total


def _field_size(ftype: str, fname: str, type_sizes: dict[str, int]) -> int:
    n = _array_size(fname)
    if fname.startswith("*"):
        return POINTER_SIZE * n
    return type_sizes[ftype] * n


def build_sdna() -> tuple[bytes, dict[str, int], dict[str, int]]:
    """Return ``(sdna_bytes, sdna_index_by_name, struct_size_by_name)``."""
    names: list[str] = []
    name_index: dict[str, int] = {}
    for _, fields in STRUCT_DEFS:
        for _, fname in fields:
            if fname not in name_index:
                name_index[fname] = len(names)
                names.append(fname)

    type_names: list[str] = list(BASE_TYPE_SIZES)
    for sname, _ in STRUCT_DEFS:
        if sname not in type_names:
            type_names.append(sname)
    type_index = {t: i for i, t in enumerate(type_names)}

    sizes: dict[str, int] = dict(BASE_TYPE_SIZES)
    for sname, fields in STRUCT_DEFS:
        sizes[sname] = sum(_field_size(ft, fn, sizes) for ft, fn in fields)

    def pad4(buf: bytearray) -> None:
        while len(buf) % 4:
            buf.append(0)

    out = bytearray(b"SDNA")
    out += b"NAME" + struct.pack("<I", len(names))
    for n in names:
        out += n.encode("ascii") + b"\x00"
    pad4(out)

    out += b"TYPE" + struct.pack("<I", len(type_names))
    for t in type_names:
        out += t.encode("ascii") + b"\x00"
    pad4(out)

    out += b"TLEN"
    for t in type_names:
        out += struct.pack("<H", sizes[t])
    pad4(out)

    out += b"STRC" + struct.pack("<I", len(STRUCT_DEFS))
    sdna_index: dict[str, int] = {}
    for idx, (sname, fields) in enumerate(STRUCT_DEFS):
        sdna_index[sname] = idx
        out += struct.pack("<HH", type_index[sname], len(fields))
        for ftype, fname in fields:
            out += struct.pack("<HH", type_index[ftype], name_index[fname])

    return bytes(out), sdna_index, sizes


@dataclass
class Block:
    code: bytes
    address: int
    sdna_index: int
    count: int
    data: bytes


@dataclass
class BlendBuilder:
    """Accumulate blocks, then emit a parseable .blend file."""

    blocks: list[Block] = field(default_factory=list)
    _next_addr: int = 0x1000

    def __post_init__(self) -> None:
        self.sdna_bytes, self.sdna_index, self.sizes = build_sdna()

    def new_address(self) -> int:
        self._next_addr += 0x100
        return self._next_addr

    def add(self, code: bytes, sdna_name: str, data: bytes, address: int | None = None) -> int:
        addr = self.new_address() if address is None else address
        self.blocks.append(Block(code, addr, self.sdna_index[sdna_name], 1, data))
        return addr

    def add_raw(self, data: bytes, address: int | None = None) -> int:
        """A DATA block of raw bytes (what a ``char *`` points at)."""
        addr = self.new_address() if address is None else address
        self.blocks.append(Block(b"DATA", addr, self.sdna_index["ID"], 1, data))
        return addr

    # -- typed helpers ---------------------------------------------------
    def add_text(self, name: str, body: str, flags: int, filepath: str = "") -> int:
        """Add a ``Text`` datablock whose lines are a real TextLine chain."""
        lines = body.split("\n")
        line_addrs = [self.new_address() for _ in lines]
        first = line_addrs[0] if line_addrs else 0

        for i, text in enumerate(lines):
            raw = text.encode("utf-8")
            data_addr = self.add_raw(raw + b"\x00")
            nxt = line_addrs[i + 1] if i + 1 < len(line_addrs) else 0
            prv = line_addrs[i - 1] if i else 0
            payload = struct.pack("<QQQQii", nxt, prv, data_addr, 0, len(raw), 0)
            self.add(b"DATA", "TextLine", payload, address=line_addrs[i])

        path_addr = self.add_raw(filepath.encode("utf-8") + b"\x00") if filepath else 0
        id_bytes = b"TX" + name.encode("utf-8")
        id_bytes = id_bytes[:65].ljust(72, b"\x00")
        last = line_addrs[-1] if line_addrs else 0
        payload = id_bytes + struct.pack("<QiiQQ", path_addr, flags, 0, first, last)
        return self.add(b"TX", "Text", payload)

    def add_library(self, filepath: str) -> int:
        id_bytes = (b"LI" + filepath.encode("utf-8"))[:65].ljust(72, b"\x00")
        return self.add(b"LI", "Library", id_bytes + filepath.encode("utf-8").ljust(1024, b"\x00"))

    def add_driver(self, expression: str, dtype: int = 1, flag: int = 0) -> int:
        payload = expression.encode("utf-8").ljust(256, b"\x00") + struct.pack("<ii", dtype, flag)
        return self.add(b"DATA", "ChannelDriver", payload)

    def add_script_node(
        self,
        mode: int,
        filepath: str = "",
        bytecode_hash: str = "",
        bytecode: bytes | None = None,
    ) -> int:
        """Add a ``NodeShaderScript``, optionally with real compiled bytecode.

        ``bytecode`` is written as its own DATA block and pointed at, because
        that is the only way ``_scan_osl`` can measure its size: it dereferences
        the ``char *`` and reads the target block's length. Passing ``None``
        leaves a null pointer, which is the ordinary case.
        """
        bytecode_addr = 0 if bytecode is None else self.add_raw(bytecode)
        payload = (
            struct.pack("<ii", mode, 0)
            + filepath.encode("utf-8").ljust(1024, b"\x00")
            + bytecode_hash.encode("utf-8").ljust(64, b"\x00")
            + struct.pack("<Q", bytecode_addr)
        )
        return self.add(b"DATA", "NodeShaderScript", payload)

    # -- emit ------------------------------------------------------------
    @staticmethod
    def _pack_block_header(blk: Block, large: bool) -> bytes:
        """Pack one block header in whichever layout the file declares."""
        code = blk.code.ljust(4, b"\x00")
        if large:
            return BHEAD_LARGE.pack(code, blk.sdna_index, blk.address, len(blk.data), blk.count)
        return BHEAD.pack(code, len(blk.data), blk.address, blk.sdna_index, blk.count)

    def to_bytes(self, version: bytes = b"404", *, large_header: bool = False) -> bytes:
        """Serialise to a complete .blend file.

        DNA1 is emitted first so that blocks referring to SDNA indices are
        resolvable no matter how the reader orders its work.

        ``large_header`` switches to the Blender 5.0 file format version 1
        layout; ``version`` is then zero-padded to the four digits that header
        carries (``b"500"`` becomes ``0500``).
        """
        if large_header:
            out = bytearray(LARGE_FILE_HEADER + version.rjust(4, b"0"))
        else:
            out = bytearray(LEGACY_FILE_HEADER + version)
        dna_block = Block(b"DNA1", 0, 0, 1, self.sdna_bytes)
        for blk in [dna_block, *self.blocks]:
            out += self._pack_block_header(blk, large_header)
            out += blk.data
        out += self._pack_block_header(Block(b"ENDB", 0, 0, 0, b""), large_header)
        return bytes(out)


def minimal_blend(*, large_header: bool = False) -> bytes:
    """A valid .blend with no scripts at all -- the 'nothing found' path."""
    version = b"500" if large_header else b"404"
    return BlendBuilder().to_bytes(version, large_header=large_header)
