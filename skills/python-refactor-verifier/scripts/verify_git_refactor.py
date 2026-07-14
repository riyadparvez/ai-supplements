#!/usr/bin/env python3
"""Compare two Git revisions using verify_refactor.py."""

from __future__ import annotations

import argparse
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path
from typing import Sequence


def validate_ref(repo: Path, ref: str) -> None:
    """Validate that a Git ref exists in the repository."""
    proc = subprocess.run(
        ["git", "-C", str(repo), "cat-file", "-t", ref],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if proc.returncode:
        raise RuntimeError(f"Git ref '{ref}' not found in repository {repo}")


def export_ref(repo: Path, ref: str, destination: Path) -> None:
    """Export a Git revision to a directory."""
    archive = destination.parent / f"{destination.name}.tar"
    with archive.open("wb") as handle:
        proc = subprocess.run(
            ["git", "-C", str(repo), "archive", "--format=tar", ref],
            stdout=handle,
            stderr=subprocess.PIPE,
            check=False,
        )
    if proc.returncode:
        raise RuntimeError(f"Failed to export Git ref '{ref}': {proc.stderr.decode('utf-8', errors='replace').strip()}")
    destination.mkdir(parents=True)
    with tarfile.open(archive) as bundle:
        bundle.extractall(destination, filter="data")
    archive.unlink()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base", help="original Git revision")
    parser.add_argument("head", help="refactored Git revision")
    parser.add_argument("--repo", type=Path, default=Path.cwd(), help="Git repository path (default: current directory)")
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    parser.add_argument("--verbose", action="store_true", help="show detailed output")
    parser.add_argument("--ignore-rule", action="append", dest="ignore_rules", default=[], help="ignore specific violation rules (can be used multiple times)")
    args = parser.parse_args(argv)

    verifier = Path(__file__).with_name("verify_refactor.py")
    try:
        # Validate Git refs exist before attempting to export
        repo_path = args.repo.resolve()
        validate_ref(repo_path, args.base)
        validate_ref(repo_path, args.head)

        with tempfile.TemporaryDirectory(prefix="refactor-check-") as temp:
            root = Path(temp)
            before, after = root / "before", root / "after"
            export_ref(repo_path, args.base, before)
            export_ref(repo_path, args.head, after)
            command = [sys.executable, str(verifier), str(before), str(after)]
            if args.json:
                command.append("--json")
            if args.verbose:
                command.append("--verbose")
            for rule in args.ignore_rules:
                command.extend(["--ignore-rule", rule])
            return subprocess.run(command, check=False).returncode
    except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
