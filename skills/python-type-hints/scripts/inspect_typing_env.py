#!/usr/bin/env python3
"""Inspect a Python repository for typing and validation configuration."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

CONFIG_FILES = (
    "pyproject.toml",
    "pyrightconfig.json",
    "basedpyrightconfig.json",
    ".python-version",
    "tox.ini",
    "setup.cfg",
    "mypy.ini",
    "uv.lock",
    "poetry.lock",
    "Pipfile",
)


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def detect_python_version(root: Path) -> tuple[str | None, str | None]:
    candidates: list[tuple[Path, list[str]]] = [
        (root / ".python-version", [r"^\s*([0-9]+\.[0-9]+(?:\.[0-9]+)?)"]),
        (root / "pyproject.toml", [
            r"requires-python\s*=\s*[\"']([^\"']+)",
            r"pythonVersion\s*=\s*[\"']([^\"']+)",
            r"python\s*=\s*[\"']([^\"']+)",
        ]),
        (root / "pyrightconfig.json", [r'"pythonVersion"\s*:\s*"([^"]+)"']),
        (root / "basedpyrightconfig.json", [r'"pythonVersion"\s*:\s*"([^"]+)"']),
        (root / "tox.ini", [r"basepython\s*=\s*python([0-9]+\.[0-9]+)"]),
    ]
    for path, patterns in candidates:
        text = read_text(path)
        if not text:
            continue
        for pattern in patterns:
            match = re.search(pattern, text, re.MULTILINE)
            if match:
                return match.group(1).strip(), str(path.relative_to(root))
    return None, None


def detect_pyright_config(root: Path) -> dict[str, Any]:
    result: dict[str, Any] = {"file": None, "mode": None, "python_version": None}
    for name in ("pyrightconfig.json", "basedpyrightconfig.json"):
        path = root / name
        if not path.exists():
            continue
        result["file"] = name
        try:
            data = json.loads(read_text(path))
        except json.JSONDecodeError:
            data = {}
        result["mode"] = data.get("typeCheckingMode")
        result["python_version"] = data.get("pythonVersion")
        return result

    pyproject = root / "pyproject.toml"
    text = read_text(pyproject)
    if "[tool.pyright]" in text or "[tool.basedpyright]" in text:
        result["file"] = "pyproject.toml"
        section = re.split(r"^\[", text, flags=re.MULTILINE)
        relevant = next((s for s in section if s.startswith("tool.pyright]") or s.startswith("tool.basedpyright]")), "")
        mode = re.search(r"typeCheckingMode\s*=\s*[\"']([^\"']+)", relevant)
        pyver = re.search(r"pythonVersion\s*=\s*[\"']([^\"']+)", relevant)
        result["mode"] = mode.group(1) if mode else None
        result["python_version"] = pyver.group(1) if pyver else None
    return result


def command_exists(command: str) -> bool:
    return shutil.which(command) is not None


def detect_commands(root: Path) -> dict[str, list[str]]:
    commands: dict[str, list[str]] = {"pyright": [], "tests": [], "lint_format": []}
    pyproject = read_text(root / "pyproject.toml")
    makefile = read_text(root / "Makefile")
    taskfile = read_text(root / "Taskfile.yml") or read_text(root / "Taskfile.yaml")

    if (root / "uv.lock").exists() or "[tool.uv" in pyproject:
        commands["pyright"].append("uv run pyright")
        commands["tests"].append("uv run pytest")
    if (root / "poetry.lock").exists() or "[tool.poetry" in pyproject:
        commands["pyright"].append("poetry run pyright")
        commands["tests"].append("poetry run pytest")
    if command_exists("pyright"):
        commands["pyright"].append("pyright")
    elif command_exists("basedpyright"):
        commands["pyright"].append("basedpyright")

    for target, category in (("typecheck", "pyright"), ("pyright", "pyright"), ("test", "tests"), ("lint", "lint_format"), ("format", "lint_format")):
        if re.search(rf"^{re.escape(target)}\s*:", makefile, re.MULTILINE):
            commands[category].insert(0, f"make {target}")
        if re.search(rf"^\s{{0,4}}{re.escape(target)}\s*:", taskfile, re.MULTILINE):
            commands[category].insert(0, f"task {target}")

    if "[tool.pytest" in pyproject and not commands["tests"]:
        commands["tests"].append("pytest")
    if "[tool.ruff" in pyproject:
        commands["lint_format"].extend(["ruff check .", "ruff format --check ."])

    return {key: list(dict.fromkeys(values)) for key, values in commands.items()}


def git_changed_files(root: Path) -> list[str]:
    if not (root / ".git").exists() or not command_exists("git"):
        return []
    proc = subprocess.run(
        ["git", "status", "--short"], cwd=root, text=True, capture_output=True, check=False
    )
    files: list[str] = []
    for line in proc.stdout.splitlines():
        if len(line) >= 4:
            path = line[3:].split(" -> ")[-1]
            if path.endswith((".py", ".pyi")):
                files.append(path)
    return files


def inspect(root: Path) -> dict[str, Any]:
    python_version, version_source = detect_python_version(root)
    return {
        "root": str(root),
        "python_version": python_version,
        "python_version_source": version_source,
        "pyright": detect_pyright_config(root),
        "commands": detect_commands(root),
        "present_config_files": [name for name in CONFIG_FILES if (root / name).exists()],
        "changed_python_files": git_changed_files(root),
    }


def render_markdown(data: dict[str, Any]) -> str:
    pyright = data["pyright"]
    commands = data["commands"]
    lines = ["# Typing environment", ""]
    lines.append(f"- Repository: `{data['root']}`")
    lines.append(f"- Python constraint/version: `{data['python_version'] or 'not detected'}`")
    lines.append(f"- Version source: `{data['python_version_source'] or 'not detected'}`")
    lines.append(f"- Pyright config: `{pyright['file'] or 'not detected'}`")
    lines.append(f"- Type checking mode: `{pyright['mode'] or 'not detected'}`")
    lines.append("")
    for label, values in commands.items():
        lines.append(f"## {label.replace('_', ' ').title()} commands")
        if values:
            lines.extend(f"- `{value}`" for value in values)
        else:
            lines.append("- None detected")
        lines.append("")
    if data["changed_python_files"]:
        lines.append("## Changed Python files")
        lines.extend(f"- `{path}`" for path in data["changed_python_files"])
    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", nargs="?", default=".", help="Repository root")
    parser.add_argument("--format", choices=("json", "markdown"), default="json")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    if not root.is_dir():
        parser.error(f"not a directory: {root}")
    data = inspect(root)
    if args.format == "json":
        print(json.dumps(data, indent=2, sort_keys=True))
    else:
        print(render_markdown(data), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
