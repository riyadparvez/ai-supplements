#!/usr/bin/env python3
"""Run Pyright in JSON mode and compare diagnostics with a saved baseline."""

from __future__ import annotations

import argparse
import json
import shlex
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any, cast


def normalize_diagnostic(item: dict[str, Any], root: Path) -> tuple[str, int, int, str, str]:
    file_path = Path(str(item.get("file", "")))
    try:
        file_name = str(file_path.resolve().relative_to(root.resolve()))
    except (ValueError, OSError):
        file_name = str(file_path)
    start = item.get("range", {}).get("start", {})
    return (
        file_name,
        int(start.get("line", 0)) + 1,
        int(start.get("character", 0)) + 1,
        str(item.get("severity", "error")),
        str(item.get("message", "")).strip(),
    )


def load_snapshot(path: Path) -> list[tuple[str, int, int, str, str]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = cast(list[list[object]], data.get("diagnostics", []))
    return [cast(tuple[str, int, int, str, str], tuple(row)) for row in rows]


def save_snapshot(path: Path, command: list[str], diagnostics: list[tuple[str, int, int, str, str]]) -> None:
    payload = {"command": command, "diagnostics": diagnostics}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def run_pyright(root: Path, command: list[str], targets: list[str]) -> tuple[int, dict[str, Any]]:
    full_command = [*command, "--outputjson", *targets]
    proc = subprocess.run(full_command, cwd=root, text=True, capture_output=True, check=False)
    raw = proc.stdout.strip()
    if not raw:
        print(proc.stderr.strip() or "Pyright produced no JSON output", file=sys.stderr)
        return proc.returncode or 2, {}
    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        print("Could not parse Pyright JSON output", file=sys.stderr)
        print(raw, file=sys.stderr)
        return 2, {}
    if proc.stderr.strip():
        print(proc.stderr.strip(), file=sys.stderr)
    return proc.returncode, result


def format_diag(diag: tuple[str, int, int, str, str]) -> str:
    file_name, line, column, severity, message = diag
    return f"{file_name}:{line}:{column}: {severity}: {message}"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--command", default="pyright", help="Command prefix, e.g. 'uv run pyright'")
    parser.add_argument("--baseline", required=True, help="Baseline snapshot path")
    parser.add_argument("--save-baseline", action="store_true")
    parser.add_argument("--fail-on-new", action="store_true")
    parser.add_argument("targets", nargs="*")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    baseline_path = Path(args.baseline)
    if not baseline_path.is_absolute():
        baseline_path = root / baseline_path
    command = shlex.split(args.command)
    exit_code, result = run_pyright(root, command, args.targets)
    if not result:
        return exit_code

    diagnostics = sorted(normalize_diagnostic(item, root) for item in result.get("generalDiagnostics", []))
    errors = [diag for diag in diagnostics if diag[3] == "error"]

    if args.save_baseline:
        save_snapshot(baseline_path, command, diagnostics)
        print(f"Saved {len(diagnostics)} diagnostics ({len(errors)} errors) to {baseline_path}")
        return 0

    if not baseline_path.exists():
        print(f"Baseline does not exist: {baseline_path}", file=sys.stderr)
        return 2

    baseline = load_snapshot(baseline_path)
    current_counts = Counter(diagnostics)
    baseline_counts = Counter(baseline)
    new_items = sorted((current_counts - baseline_counts).elements())
    resolved_items = sorted((baseline_counts - current_counts).elements())

    print(f"Current diagnostics: {len(diagnostics)} ({len(errors)} errors)")
    print(f"New diagnostics: {len(new_items)}")
    for item in new_items:
        print(f"+ {format_diag(item)}")
    print(f"Resolved diagnostics: {len(resolved_items)}")
    for item in resolved_items:
        print(f"- {format_diag(item)}")

    if args.fail_on_new and any(item[3] == "error" for item in new_items):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
