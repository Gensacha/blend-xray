# SPDX-License-Identifier: GPL-3.0-or-later
"""Make file-derived text safe to print, without hiding what was in the file.

Why this module exists
----------------------
Blend X-Ray prints text that came out of a hostile file: script bodies, string
literals, datablock names, library paths, driver expressions, parser error
messages. A terminal treats some of those bytes as *commands*, not as text. An
ESC byte followed by ``[32m`` paints the rest of the line green; ``ESC[8m``
makes it invisible; ``ESC[A`` moves the cursor up so file content can overwrite
a line the tool already printed. That turns the file into the author of the
tool's own report -- the worst possible failure for something whose entire job
is showing people, accurately, what a script says.

``str.splitlines()`` does not split on ESC, and ``--color never`` only stops
*us* from emitting colour; neither one stops bytes that came from the file. So
sanitising has to happen to the data, at one choke point, and must not be
inferred from a colour setting.

Replace, never delete
---------------------
Every escape here is *visible*: ESC becomes the four characters ``\\x1b``. A
file carrying terminal control bytes is telling you something about itself, and
silently dropping them would conceal exactly the signal a reader wants. The
report shows that the bytes were there and refuses to obey them.

What counts as dangerous
------------------------
* C0 controls (U+0000-U+001F) and DEL (U+007F) -- ESC, BEL, backspace, and the
  carriage return that lets a line overwrite itself.
* C1 controls (U+0080-U+009F) -- a UTF-8 terminal decodes U+009B as CSI, a full
  escape-sequence introducer with no ESC byte in sight.
* U+2028 / U+2029, the line and paragraph separators -- invisible line breaks
  that ``splitlines()`` honours and a reader cannot see.
* The bidi controls, all of them, not only the strong ones: U+202A-U+202E and
  U+2066-U+2069 (embeddings, overrides, isolates) and also U+200E, U+200F and
  U+061C (the left-to-right, right-to-left and arabic letter marks). These
  reorder a line *visually* while leaving the bytes unchanged, so
  ``os.system("rm -rf /")`` can be made to read as a comment. For a tool whose
  whole output is "here is what this script says", a character that makes a
  line say something other than what it does is as dangerous as ESC. The marks
  are weaker than an override on their own, but "weaker" is not a reason to
  print one invisibly in a report about hidden behaviour.
* The zero-width characters U+200B-U+200D, U+2060 and U+FEFF. They occupy no
  space and can split an identifier or a URL so it does not match what the
  reader searches for. Blender writes no BOM into a text datablock, so one
  appearing inside a body is worth seeing rather than swallowing.

``\\t`` survives everywhere (it is real layout in real source), and ``\\n``
survives in :func:`printable_block`, which is what line-splitting needs.
"""

from __future__ import annotations

import re
from typing import Final

#: Ranges that must never reach a terminal, as ``(first, last)`` code points.
#: Spelled numerically on purpose: writing U+202E into this file as a literal
#: character would put an invisible bidi override inside the very module that
#: exists to neutralise them, and no reviewer could see it.
DANGEROUS_RANGES: Final[tuple[tuple[int, int], ...]] = (
    (0x00, 0x08),  # C0 up to backspace (0x09 TAB is kept)
    (0x0B, 0x1F),  # C0 from vertical tab on, ESC included (0x0A LF handled below)
    (0x7F, 0x9F),  # DEL and the C1 controls
    (0x061C, 0x061C),  # arabic letter mark
    (0x200B, 0x200F),  # zero-width space/non-joiner/joiner, then LRM and RLM
    (0x2028, 0x2029),  # line separator, paragraph separator
    (0x202A, 0x202E),  # bidi embeddings and overrides
    (0x2060, 0x2060),  # word joiner
    (0x2066, 0x2069),  # bidi isolates
    (0xFEFF, 0xFEFF),  # zero-width no-break space, i.e. a BOM anywhere but the start
)

_CLASS: Final = "".join(f"\\u{lo:04x}-\\u{hi:04x}" for lo, hi in DANGEROUS_RANGES)

#: Line mode: newline and carriage return are escaped along with the rest,
#: because a single-line field containing one is forging the report's layout.
_LINE_RE: Final = re.compile(f"[{_CLASS}\\n\\r]")

#: Block mode: ``\n`` is the line structure the renderer relies on and stays.
_BLOCK_RE: Final = re.compile(f"[{_CLASS}\\r]")


def _escape(match: re.Match[str]) -> str:
    """One dangerous character, spelled the way Python spells it."""
    point = ord(match.group())
    if point < 0x100:
        return f"\\x{point:02x}"
    return f"\\u{point:04x}"


def printable_line(value: object) -> str:
    """One field, made safe for a single line of output.

    Newlines are escaped too: a datablock name or a library path containing one
    is not "multi-line text", it is a field trying to occupy lines the report
    never gave it.
    """
    text = value if isinstance(value, str) else str(value)
    return _LINE_RE.sub(_escape, text)


def printable_block(text: str) -> str:
    """A multi-line body (a script source dump), made safe to print.

    ``\\r\\n`` is folded to ``\\n`` first, the way every editor and
    ``str.splitlines()`` already read it, so a script written on Windows does
    not sprout a visible ``\\x0d`` at the end of every line. A lone ``\\r``
    survives that fold and *is* escaped -- on its own it is a cursor return that
    lets the rest of a line overwrite the start of it.

    Afterwards the only line break left in the string is ``\\n``, so
    ``splitlines()`` cannot be steered into breaking somewhere invisible.
    """
    return _BLOCK_RE.sub(_escape, text.replace("\r\n", "\n"))


def is_dangerous(text: str) -> bool:
    """Whether ``text`` holds anything :func:`printable_line` would escape.

    Exposed so callers can *say* the file carried terminal control bytes rather
    than only neutralise them, and so tests can assert on the same rule the
    renderer uses instead of a second copy of it.
    """
    return bool(_LINE_RE.search(text))
