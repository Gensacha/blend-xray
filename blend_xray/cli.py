# SPDX-License-Identifier: GPL-3.0-or-later
"""Command line interface: ``blend-xray scan <target>``.

Exit codes (documented in the README and stable):

    0  nothing found in the categories checked
    1  findings present
    2  a file was malformed, hostile-looking, or not a .blend file
    3  tool error (bad install, wrong blender-asset-tracer version)

There are no network calls, no telemetry and no auto-update anywhere in
Blend X-Ray. The only thing it touches is the file you point it at.
"""

from __future__ import annotations

import argparse
import glob
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from . import __version__, guards, report, scanner, strings
from .models import ERROR_STRING_KEYS, ScanResult
from .sanitise import printable_line

EXIT_OK = 0
EXIT_FINDINGS = 1
EXIT_MALFORMED = 2
EXIT_TOOL_ERROR = 3


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="blend-xray",
        description=f"{strings.t('tool_tagline')} {strings.t('never_runs')}",
        epilog=(
            "Exit codes: 0 nothing found, 1 findings present, "
            "2 malformed/unparseable file, 3 tool error."
        ),
    )
    # Before the subparsers, not under ``scan``: a copy too broken to scan
    # anything must still be able to say which build it is. See
    # tests/test_version.py.
    parser.add_argument(
        "--version", action="version", version=f"{parser.prog} {__version__}",
        help="Print the version and exit.",
    )
    parser.add_argument(
        "--lang",
        choices=strings.SUPPORTED_LANGUAGES,
        default=None,
        help=(
            "Interface language. Detected from the OS locale when omitted; "
            "falls back to English."
        ),
    )
    _add_scan_command(parser.add_subparsers(dest="command", required=True))
    return parser


def _add_scan_command(sub: argparse._SubParsersAction) -> None:
    """The ``scan`` subcommand and its flags."""
    scan = sub.add_parser("scan", help="Inventory one or more .blend files.")
    scan.add_argument(
        "targets",
        nargs="+",
        help="A .blend file, a directory to search recursively, or a glob pattern.",
    )
    scan.add_argument("--json", action="store_true", help="Machine-readable output.")
    scan.add_argument("--full", action="store_true", help="Print complete script bodies.")
    scan.add_argument(
        "--quiet", "-q", action="store_true", help="Findings only; omit context sections."
    )
    scan.add_argument(
        "--color",
        choices=("auto", "always", "never"),
        default="auto",
        help="Colour output. 'auto' disables colour when piped.",
    )
    scan.add_argument(
        "--max-seconds",
        type=float,
        default=guards.Limits().max_seconds,
        help="Per-file wall-clock parsing budget.",
    )


def expand_targets(targets: Sequence[str]) -> list[Path]:
    """Resolve files, directories (recursive) and glob patterns to .blend paths."""
    found: list[Path] = []
    seen: set[Path] = set()

    def push(path: Path) -> None:
        resolved = path.resolve(strict=False)
        if resolved not in seen and path.is_file():
            seen.add(resolved)
            found.append(path)

    for target in targets:
        path = Path(target)
        if path.is_dir():
            for match in sorted(path.rglob("*.blend")):
                push(match)
            continue
        if path.is_file():
            push(path)
            continue
        for match in sorted(glob.glob(target, recursive=True)):
            candidate = Path(match)
            if candidate.is_dir():
                for nested in sorted(candidate.rglob("*.blend")):
                    push(nested)
            elif candidate.suffix.lower() == ".blend" or len(targets) == 1:
                push(candidate)
    return found


def _scan_one(
    path: Path, limits: guards.Limits, results: list[ScanResult], errors: list[dict[str, Any]]
) -> int:
    """Scan one file, recording either a result or a structured error."""
    try:
        results.append(scanner.scan_file(path, limits))
        return EXIT_OK
    except guards.NotABlendFileError as exc:
        errors.append({"path": str(path), "kind": "not_a_blend", "message": str(exc)})
        return EXIT_MALFORMED
    except guards.MalformedBlendError as exc:
        errors.append({"path": str(path), "kind": "malformed", "message": str(exc)})
        return EXIT_MALFORMED
    except scanner.ToolError as exc:
        errors.append({"path": str(path), "kind": "tool_error", "message": str(exc)})
        return EXIT_TOOL_ERROR
    except OSError as exc:
        errors.append({"path": str(path), "kind": "unreadable", "message": str(exc)})
        return EXIT_MALFORMED


def _print_errors(errors: list[dict[str, Any]], pal: report.Palette, stream: Any) -> None:
    for err in errors:
        path = err["path"]
        key = ERROR_STRING_KEYS.get(err["kind"], "err_unreadable")
        text = strings.t(key, path=path, reason=err["message"])
        print(pal.alarm(f"{printable_line(path)}: {text}"), file=stream)


def run(argv: Sequence[str] | None = None, stdout: Any = None, stderr: Any = None) -> int:
    """Entry point. Returns the process exit code; never raises for file errors."""
    out = stdout or sys.stdout
    err = stderr or sys.stderr

    # Auto-detect before parsing so --help itself renders in the detected
    # language; an explicit --lang then always wins for the rest of the run.
    strings.set_language(strings.detect_language())
    args = build_parser().parse_args(argv)
    if args.lang:
        strings.set_language(args.lang)

    force_color = {"auto": None, "always": True, "never": False}[args.color]
    pal = report.make_palette(out, force_color)

    try:
        scanner.assert_bat_version()
    except scanner.ToolError as exc:
        print(pal.alarm(str(exc)), file=err)
        return EXIT_TOOL_ERROR

    paths = expand_targets(args.targets)
    if not paths:
        print(
            pal.notable(strings.t("no_files_matched", target=", ".join(args.targets))),
            file=err,
        )
        return EXIT_TOOL_ERROR

    limits = guards.Limits(max_seconds=args.max_seconds)
    results: list[ScanResult] = []
    errors: list[dict[str, Any]] = []
    worst = EXIT_OK
    for path in paths:
        worst = max(worst, _scan_one(path, limits, results, errors))

    if args.json:
        print(report.format_json(results, errors), file=out)
    else:
        for index, result in enumerate(results):
            if index:
                print(file=out)
            print(
                report.format_text_report(result, pal, full=args.full, quiet=args.quiet),
                file=out,
            )
        if errors:
            _print_errors(errors, pal, err)
        if len(paths) > 1 and not args.quiet:
            print(pal.dim(strings.t("scanned_n_files", count=len(paths))), file=out)

    if worst >= EXIT_MALFORMED:
        return worst
    # needs_attention, not has_findings: exiting 0 on a file the scan gave up
    # on would report it as having come back with nothing in it.
    return EXIT_FINDINGS if any(r.needs_attention for r in results) else EXIT_OK


def main() -> int:
    try:
        return run()
    except KeyboardInterrupt:
        return EXIT_TOOL_ERROR
    except Exception as exc:
        print(strings.t("err_tool", reason=str(exc)), file=sys.stderr)
        return EXIT_TOOL_ERROR


if __name__ == "__main__":
    raise SystemExit(main())
