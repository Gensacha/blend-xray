# SPDX-License-Identifier: GPL-3.0-or-later
"""Blend X-Ray -- inspect a .blend file for embedded code without opening Blender.

Blend X-Ray is a defensive inspection tool. It parses a .blend file and reports an
inventory of the places code can hide in it. It never launches Blender and
never executes anything it finds.

Blend X-Ray is free software, licensed GPLv3-or-later. It links against
blender-asset-tracer, which is GPLv2-or-later; see LICENSE and the README.
"""

from __future__ import annotations

# The literal lives in _version.py; see that module for why it is not written
# here. This re-export is what every caller uses -- `from blend_xray import
# __version__` -- and it is what keeps a bump to a single line in a single file.
from ._version import __version__

__all__ = ["__version__"]
