#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Standalone launcher so Blend X-Ray runs without being installed.

python blend_xray.py scan suspicious.blend
"""

from __future__ import annotations

import sys

from blend_xray.cli import main

if __name__ == "__main__":
    sys.exit(main())
