# SPDX-License-Identifier: GPL-3.0-or-later
#
# Build the portable Blend X-Ray window into a single unsigned .exe.
#
#     .\build_exe.ps1
#
# Output: dist\BlendXRay.exe -- one file, no installer, no admin rights.
# The build itself needs the project venv (see README "Install"); it does not
# need Blender, and nothing here reaches the network beyond `pip install`.
#
# The executable is NOT code-signed. Windows SmartScreen will warn the first
# time it runs on a new machine. That is a deliberate deferral, documented in
# the README: the source remains the primary artifact for anyone who wants to
# audit this before trusting it.

$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

$python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    throw "No venv at .venv\Scripts\python.exe. Create it first: py -3.12 -m venv .venv"
}

Write-Host "==> Installing build dependencies"
& $python -m pip install --disable-pip-version-check -q "pyinstaller>=6.6"
if ($LASTEXITCODE -ne 0) { throw "pip install failed" }

# tkinterdnd2 is optional. If it is present it gets bundled and the window
# accepts dropped files; if it is absent the window falls back to its buttons.
& $python -c "import tkinterdnd2" 2>$null
if ($LASTEXITCODE -eq 0) {
    Write-Host "==> tkinterdnd2 found: drag-and-drop will be bundled"
} else {
    Write-Host "==> tkinterdnd2 absent: building without drag-and-drop"
}

Write-Host "==> Building"
& $python -m PyInstaller --noconfirm --clean blend-xray.spec
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }

$exe = Join-Path $PSScriptRoot "dist\BlendXRay.exe"
if (-not (Test-Path $exe)) { throw "Expected $exe, which is not there" }

$size = [math]::Round((Get-Item $exe).Length / 1MB, 1)
Write-Host "==> Built $exe ($size MB, unsigned)"
