# SPDX-License-Identifier: GPL-3.0-or-later
"""Blender DNA constants used by Blend X-Ray.

Every value here was read from the Blender source tree (branch ``main``,
retrieved 2026-08-23) rather than guessed. The source path and the verbatim
upstream comment are cited next to each value so a suspicious user can check
them without trusting us.
"""

from __future__ import annotations

from typing import Final

# --------------------------------------------------------------------------
# Block codes (2-byte ID codes at the head of each .blend file block).
# --------------------------------------------------------------------------
CODE_TEXT: Final = b"TX"
CODE_LIBRARY: Final = b"LI"
CODE_IMAGE: Final = b"IM"
CODE_SOUND: Final = b"SO"
CODE_VFONT: Final = b"VF"
CODE_CACHEFILE: Final = b"CF"
CODE_MOVIECLIP: Final = b"MC"
CODE_DNA1: Final = b"DNA1"
CODE_ENDB: Final = b"ENDB"

#: ID blocks whose ``filepath`` field is inventoried as informational context.
INFORMATIONAL_PATH_CODES: Final = (
    CODE_IMAGE,
    CODE_SOUND,
    CODE_VFONT,
    CODE_CACHEFILE,
    CODE_MOVIECLIP,
)

# --------------------------------------------------------------------------
# enum eText_Flag  --  source/blender/makesdna/DNA_text_types.h
#
# Confirmed verbatim from source:
#     enum eText_Flag : int {
#       /** Set if the file in run-time differs from the file on disk, or if
#           there is no file on disk. */
#       TXT_ISDIRTY = 1 << 0,
#       /** When the text hasn't been written to a file. #Text.filepath may be
#           NULL or invalid. */
#       TXT_ISMEM = 1 << 2,
#       /** Should always be set if the Text is not to be written into the
#           `.blend`. */
#       TXT_ISEXT = 1 << 3,
#       /** Load the script as a Python module when loading the `.blend`
#           file. */
#       TXT_ISSCRIPT = 1 << 4,
#       TXT_FLAG_UNUSED_8 = 1 << 8, /* cleared */
#       TXT_FLAG_UNUSED_9 = 1 << 9, /* cleared */
#       /** Use space instead of tabs. */
#       TXT_TABSTOSPACES = 1 << 10,
#     };
#
# Note bit 1 (1 << 1) is absent upstream -- it is not a flag we should invent.
# --------------------------------------------------------------------------
TXT_ISDIRTY: Final = 1 << 0  # 1
TXT_ISMEM: Final = 1 << 2  # 4
TXT_ISEXT: Final = 1 << 3  # 8
TXT_ISSCRIPT: Final = 1 << 4  # 16  <-- the CGTrader / StealC V2 auto-run vector
TXT_TABSTOSPACES: Final = 1 << 10  # 1024

TEXT_FLAG_NAMES: Final = {
    TXT_ISDIRTY: "TXT_ISDIRTY",
    TXT_ISMEM: "TXT_ISMEM",
    TXT_ISEXT: "TXT_ISEXT",
    TXT_ISSCRIPT: "TXT_ISSCRIPT",
    TXT_TABSTOSPACES: "TXT_TABSTOSPACES",
}

# --------------------------------------------------------------------------
# enum eDriver_Types  --  source/blender/makesdna/DNA_anim_enums.h
#
# Confirmed verbatim from source (values are implicit sequential ints):
#     enum eDriver_Types : int {
#       /** target values are averaged together. */
#       DRIVER_TYPE_AVERAGE = 0,
#       /** python expression/function relates targets. */
#       DRIVER_TYPE_PYTHON,
#       /** sum of all values. */
#       DRIVER_TYPE_SUM,
#       /** smallest value. */
#       DRIVER_TYPE_MIN,
#       /** largest value. */
#       DRIVER_TYPE_MAX,
#     };
# --------------------------------------------------------------------------
DRIVER_TYPE_AVERAGE: Final = 0
DRIVER_TYPE_PYTHON: Final = 1
DRIVER_TYPE_SUM: Final = 2
DRIVER_TYPE_MIN: Final = 3
DRIVER_TYPE_MAX: Final = 4

DRIVER_TYPE_NAMES: Final = {
    DRIVER_TYPE_AVERAGE: "DRIVER_TYPE_AVERAGE",
    DRIVER_TYPE_PYTHON: "DRIVER_TYPE_PYTHON",
    DRIVER_TYPE_SUM: "DRIVER_TYPE_SUM",
    DRIVER_TYPE_MIN: "DRIVER_TYPE_MIN",
    DRIVER_TYPE_MAX: "DRIVER_TYPE_MAX",
}

# --------------------------------------------------------------------------
# enum eDriver_Flags  --  source/blender/makesdna/DNA_anim_enums.h
#
# Confirmed verbatim from source:
#     enum eDriver_Flags : int {
#       /** Driver has invalid settings (internal flag). */
#       DRIVER_FLAG_INVALID = (1 << 0),
#       DRIVER_FLAG_DEPRECATED = (1 << 1),
#       // DRIVER_FLAG_LAYERING  = (1 << 2),   <- commented out upstream
#       /** Use when the expression needs to be recompiled. */
#       DRIVER_FLAG_RECOMPILE = (1 << 3),
#       /** The names are cached so they don't need have python unicode
#           versions created each time */
#       DRIVER_FLAG_RENAMEVAR = (1 << 4),
#       /* Set if the driver cannot run because it uses Python which isn't
#          allowed to execute. */
#       DRIVER_FLAG_PYTHON_BLOCKED = (1 << 5),
#       /** Include 'self' in the drivers namespace. */
#       DRIVER_FLAG_USE_SELF = (1 << 6),
#     };
# --------------------------------------------------------------------------
DRIVER_FLAG_INVALID: Final = 1 << 0  # 1
DRIVER_FLAG_DEPRECATED: Final = 1 << 1  # 2
DRIVER_FLAG_RECOMPILE: Final = 1 << 3  # 8
DRIVER_FLAG_RENAMEVAR: Final = 1 << 4  # 16
DRIVER_FLAG_PYTHON_BLOCKED: Final = 1 << 5  # 32
DRIVER_FLAG_USE_SELF: Final = 1 << 6  # 64

DRIVER_FLAG_NAMES: Final = {
    DRIVER_FLAG_INVALID: "DRIVER_FLAG_INVALID",
    DRIVER_FLAG_DEPRECATED: "DRIVER_FLAG_DEPRECATED",
    DRIVER_FLAG_RECOMPILE: "DRIVER_FLAG_RECOMPILE",
    DRIVER_FLAG_RENAMEVAR: "DRIVER_FLAG_RENAMEVAR",
    DRIVER_FLAG_PYTHON_BLOCKED: "DRIVER_FLAG_PYTHON_BLOCKED",
    DRIVER_FLAG_USE_SELF: "DRIVER_FLAG_USE_SELF",
}

#: ``char expression[256]`` -- struct ChannelDriver, DNA_anim_types.h line 316.
DRIVER_EXPRESSION_MAXLEN: Final = 256

# --------------------------------------------------------------------------
# struct NodeShaderScript  --  source/blender/makesdna/DNA_node_types.h
#
# Confirmed verbatim from source:
#     struct NodeShaderScript {
#       DNA_DEFINE_CXX_METHODS(NodeShaderScript)
#       int mode = 0;
#       int flag = 0;
#       char filepath[/*FILE_MAX*/ 1024] = "";
#       char bytecode_hash[64] = "";
#       char *bytecode = nullptr;
#     };
#
# and the mode enum, same header:
#     NODE_SCRIPT_INTERNAL = 0,
#     NODE_SCRIPT_EXTERNAL = 1,
# --------------------------------------------------------------------------
NODE_SCRIPT_INTERNAL: Final = 0
NODE_SCRIPT_EXTERNAL: Final = 1

NODE_SCRIPT_MODE_NAMES: Final = {
    NODE_SCRIPT_INTERNAL: "NODE_SCRIPT_INTERNAL",
    NODE_SCRIPT_EXTERNAL: "NODE_SCRIPT_EXTERNAL",
}

#: ``char filepath[FILE_MAX]`` -- FILE_MAX is 1024 in Blender.
FILE_MAX: Final = 1024


def decode_flags(value: int, names: dict[int, str]) -> list[str]:
    """Return the names of every bit set in ``value``.

    Unknown bits are reported as ``bit<N>`` rather than silently dropped, so
    the inventory never hides something we do not recognise.
    """
    if value < 0:
        # Blender stores these as signed ints; normalise to a 32-bit pattern.
        value &= 0xFFFFFFFF

    found = [name for bit, name in sorted(names.items()) if value & bit]
    known_mask = 0
    for bit in names:
        known_mask |= bit

    leftover = value & ~known_mask
    for shift in range(32):
        if leftover & (1 << shift):
            found.append(f"bit{shift}")
    return found
