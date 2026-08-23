# SPDX-License-Identifier: GPL-3.0-or-later
"""``python -m blend_xray.gui`` -- open the window.

This is the form the Windows right-click entry falls back to when the
repository launcher script is not where it expects it (an installed wheel,
for instance). See :mod:`blend_xray.gui.shell_integration`.
"""

from __future__ import annotations

from .app import main

if __name__ == "__main__":
    raise SystemExit(main())
