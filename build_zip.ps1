# SPDX-License-Identifier: GPL-3.0-or-later
#
# Assemble the published Windows zip from tracked sources.
#
#     .\build_zip.ps1
#
# Input:  dist\BlendXRay.exe (from .\build_exe.ps1), LICENSE, and bundle\.
# Output: dist\BlendXRay-<version>-windows-x64.zip -- seven flat entries.
#
# Why this is a script and not a sequence of manual steps.
# --------------------------------------------------------
# The first zip of this project was assembled by hand. It shipped a demo file
# still carrying an `OWNER` placeholder URL, and it shipped without
# THIRD-PARTY-LICENSES.txt -- which the bundled BSD-3-clause and MIT components
# require in a binary redistribution. Neither omission is visible by looking at
# the archive; both are invisible to a grep over the working tree, because the
# only copy that mattered lived inside a built artefact. A hand-assembled
# release cannot be reviewed, so it is not assembled by hand any more. Every
# byte in the zip now comes from a tracked path named below.
#
# Determinism.
# ------------
# Two runs over identical inputs produce a byte-identical archive, so a digest
# that changes means an input changed. Three things make that true:
#
#   1. The entry list and its order are fixed here, not discovered by globbing
#      a directory -- directory enumeration order is not a contract, and a
#      glob would also silently pick up anything that wandered into bundle\.
#   2. Every entry's modification time is forced to $Timestamp. A
#      time-of-build stamp would change the digest on every run and make the
#      published hash unverifiable against a rebuild.
#   3. The compression level is pinned.
#
# The one thing this does NOT promise is a digest stable across .NET runtime
# versions: the deflate encoder lives in the runtime, and a different runtime
# may emit different -- still valid -- compressed bytes. Rebuild a release zip
# on the machine that built its exe.
#
# The zip is flat: no top-level folder, so unzip-in-place puts the text files
# beside the executable where the README tells readers to look for them.

[CmdletBinding()]
param(
    # A constant, not "now" -- a time-of-build stamp would change the digest on
    # every run and make the published hash unverifiable against a rebuild.
    #
    # This is the 0.1.0 release date rather than the 1980 DOS epoch that
    # reproducible-zip tooling conventionally uses. The epoch buys nothing
    # here: the PyInstaller executable inside is not itself reproducible, so
    # the archive can never match across machines anyway -- and it costs the
    # user something real, because every file they extract shows as dated 1980,
    # which reads as broken. Bump this with the version, and record it in the
    # release notes: any change to it changes the published digest.
    [datetimeoffset] $Timestamp = [datetimeoffset]::new(2026, 8, 24, 12, 0, 0, [timespan]::Zero),

    [ValidateSet("Optimal", "SmallestSize", "Fastest", "NoCompression")]
    [string] $CompressionLevel = "Optimal"
)

$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

# The version is read from the same file blend-xray.spec parses, so the zip
# filename cannot drift from the version the exe reports at --version.
$versionFile = Join-Path $PSScriptRoot "blend_xray\_version.py"
$versionText = Get-Content -LiteralPath $versionFile -Raw -Encoding UTF8
$match = [regex]::Match($versionText, '(?m)^__version__\s*=\s*["'']([^"'']+)["'']')
if (-not $match.Success) {
    throw "No __version__ assignment in $versionFile"
}
$version = $match.Groups[1].Value

# Entry name -> source path, in the order they are written into the archive.
# This list IS the zip layout documented in RELEASING.md section 5. Adding a
# file to bundle\ does not add it to the release; adding it here does.
$layout = [ordered]@{
    "BlendXRay.exe"              = "dist\BlendXRay.exe"
    "LICENSE"                    = "LICENSE"
    "THIRD-PARTY-LICENSES.txt"   = "bundle\THIRD-PARTY-LICENSES.txt"
    "LISEZ-MOI.txt"              = "bundle\LISEZ-MOI.txt"
    "README.txt"                 = "bundle\README.txt"
    "SOURCE.txt"                 = "bundle\SOURCE.txt"
    "exemple-fichier-piege.blend" = "bundle\exemple-fichier-piege.blend"
}

# Fail before writing anything, and name every missing input at once rather
# than one per run.
$missing = @()
foreach ($entry in $layout.GetEnumerator()) {
    $source = Join-Path $PSScriptRoot $entry.Value
    if (-not (Test-Path -LiteralPath $source -PathType Leaf)) {
        $missing += $entry.Value
    }
}
if ($missing.Count -gt 0) {
    $list = $missing -join ", "
    if ($missing -contains "dist\BlendXRay.exe") {
        throw "Missing input(s): $list -- run .\build_exe.ps1 first"
    }
    throw "Missing input(s): $list"
}

$zipPath = Join-Path $PSScriptRoot "dist\BlendXRay-$version-windows-x64.zip"
if (Test-Path -LiteralPath $zipPath) {
    Remove-Item -LiteralPath $zipPath -Force
}

Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem

$level = [System.IO.Compression.CompressionLevel]::$CompressionLevel

Write-Host "==> Assembling $zipPath"
$stream = [System.IO.File]::Open($zipPath, [System.IO.FileMode]::CreateNew)
try {
    $archive = [System.IO.Compression.ZipArchive]::new(
        $stream, [System.IO.Compression.ZipArchiveMode]::Create, $true)
    try {
        foreach ($item in $layout.GetEnumerator()) {
            $name = $item.Key
            $source = Join-Path $PSScriptRoot $item.Value
            $entry = $archive.CreateEntry($name, $level)
            # Normalised, not inherited: the source files' own mtimes change
            # every time one is edited or re-checked-out, and would leak into
            # the digest.
            $entry.LastWriteTime = $Timestamp
            $entryStream = $entry.Open()
            try {
                $fileStream = [System.IO.File]::OpenRead($source)
                try {
                    $fileStream.CopyTo($entryStream)
                } finally {
                    $fileStream.Dispose()
                }
            } finally {
                $entryStream.Dispose()
            }
            Write-Host ("    {0,-28} <- {1}" -f $name, $item.Value)
        }
    } finally {
        $archive.Dispose()
    }
} finally {
    $stream.Dispose()
}

# Read the archive back rather than trusting the writes above.
$readBack = [System.IO.Compression.ZipFile]::OpenRead($zipPath)
try {
    $written = @($readBack.Entries | ForEach-Object { $_.FullName })
} finally {
    $readBack.Dispose()
}
$expected = @($layout.Keys)
if (Compare-Object -ReferenceObject $expected -DifferenceObject $written -SyncWindow 0) {
    throw "Archive contents differ from the layout: got [$($written -join ', ')]"
}

$zipItem = Get-Item -LiteralPath $zipPath
$digest = (Get-FileHash -LiteralPath $zipPath -Algorithm SHA256).Hash.ToLower()
$exeDigest = (Get-FileHash -LiteralPath (Join-Path $PSScriptRoot "dist\BlendXRay.exe") -Algorithm SHA256).Hash.ToLower()
$exeItem = Get-Item -LiteralPath (Join-Path $PSScriptRoot "dist\BlendXRay.exe")

Write-Host ""
Write-Host "==> $($written.Count) entries, $($zipItem.Length) bytes"
Write-Host ""
Write-Host "BlendXRay-$version-windows-x64.zip"
Write-Host "  size    $($zipItem.Length) bytes"
Write-Host "  SHA-256 $digest"
Write-Host ""
Write-Host "BlendXRay.exe  (inside the zip)"
Write-Host "  size    $($exeItem.Length) bytes"
Write-Host "  SHA-256 $exeDigest"
Write-Host ""
Write-Host "Both digests go in docs\gumroad.md section 3, the product page and the"
Write-Host "GitHub release notes. See RELEASING.md, 'After every rebuild'."
