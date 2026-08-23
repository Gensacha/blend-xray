# SPDX-License-Identifier: GPL-3.0-or-later
"""The one place the version number is written.

It sits in its own module rather than directly in ``__init__.py`` because the
build reads it *statically*, and setuptools' module lookup for
``[tool.setuptools.dynamic]`` tries ``<root>/blend_xray.py`` -- the
double-click launcher at the repository root -- before
``<root>/blend_xray/__init__.py``. It finds the launcher, fails to see a
version in it, falls back to importing it, and the import raises. Pointing the
build at ``blend_xray._version`` is unambiguous: nothing else in the tree
answers to that path.

``blend_xray.__version__`` re-exports this, so every caller still reads the
version from the package and a bump is still exactly one line, in one file.
"""

from __future__ import annotations

__version__ = "0.1.0"
