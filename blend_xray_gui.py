#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Standalone launcher for the Blend X-Ray window, no install required.

    python blend_xray_gui.py                  # open the window
    python blend_xray_gui.py suspicious.blend # open it on a file

This is also the file PyInstaller builds into the portable executable, and the
target of the optional Windows right-click entry.
"""

from __future__ import annotations

import sys

from blend_xray.gui.app import main

if __name__ == "__main__":
    sys.exit(main())
