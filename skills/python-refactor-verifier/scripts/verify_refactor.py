#!/usr/bin/env python3
"""Verify that a Python refactor only renames functions/call sites and adds imports."""

from __future__ import annotations

import argparse
import ast
import copy
import io
import json
import sys
import tokenize
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence


@dataclass(frozen=True)
class Violation:
    file: str
    rule: str
    detail: str
    line: int | None = None
    end_line: int | None = None


@dataclass(frozen=True)
class FunctionRecord:
    qualname: str
    name: str
    node: ast.FunctionDef | ast.AsyncFunctionDef
    lineno: int
    end_lineno: int


IGNORED_DIRS = {".git", ".hg", ".svn", ".tox", ".venv", "venv", "__pycache__", ".mypy_cache", ".pytest_cache", ".ruff_cache"}


def python_files(root: Path) -> dict[str, Path]:
    result: dict[str, Path] = {}
    for path in root.rglob("*.py"):
        if any(part in IGNORED_DIRS for part in path.relative_to(root).parts):
            continue
        result[path.relative_to(root).as_posix()] = path
    return result


def parse(path: Path) -> tuple[str, ast.Module]:
    source = path.read_text(encoding="utf-8")
    return source, ast.parse(source, filename=str(path), type_comments=True)


def comment_tokens(source: str) -> list[str]:
    tokens = tokenize.generate_tokens(io.StringIO(source).readline)
    return [tok.string for tok in tokens if tok.type == tokenize.COMMENT]


def import_dump(node: ast.AST) -> str:
    return ast.dump(node, include_attributes=False)


def imports(tree: ast.Module) -> Counter[str]:
    return Counter(import_dump(node) for node in tree.body if isinstance(node, (ast.Import, ast.ImportFrom)))


def collect_functions(tree: ast.AST) -> list[FunctionRecord]:
    found: list[FunctionRecord] = []

    def visit(node: ast.AST, parents: tuple[str, ...]) -> None:
        child_index = 0
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                qual = ".".join((*parents, f"fn[{child_index}]"))
                found.append(FunctionRecord(qual, child.name, child, child.lineno, child.end_lineno or child.lineno))
                visit(child, (*parents, f"fn[{child_index}]"))
                child_index += 1
            elif isinstance(child, ast.ClassDef):
                visit(child, (*parents, f"class:{child.name}"))
            else:
                visit(child, parents)

    visit(tree, ())
    return found


def function_mapping(old_tree: ast.Module, new_tree: ast.Module) -> tuple[dict[str, str], list[Violation]]:
    old = collect_functions(old_tree)
    new = collect_functions(new_tree)
    violations: list[Violation] = []
    if len(old) != len(new):
        violations.append(Violation("", "function-count", f"function count changed from {len(old)} to {len(new)}", None, None))
        return {}, violations

    mapping: dict[str, str] = {}
    reverse: dict[str, str] = {}
    for left, right in zip(old, new):
        if left.qualname != right.qualname:
            violations.append(Violation("", "function-structure", f"function nesting/order changed near {left.name!r} and {right.name!r}", left.lineno, None))
            continue
        if left.name != right.name:
            prior = mapping.get(left.name)
            if prior is not None and prior != right.name:
                violations.append(Violation("", "rename-consistency", f"{left.name!r} maps to both {prior!r} and {right.name!r}", left.lineno, None))
            prior_old = reverse.get(right.name)
            if prior_old is not None and prior_old != left.name:
                violations.append(Violation("", "rename-collision", f"both {prior_old!r} and {left.name!r} map to {right.name!r}", right.lineno, None))
            mapping[left.name] = right.name
            reverse[right.name] = left.name
    return mapping, violations


class Canonicalize(ast.NodeTransformer):
    def __init__(self, rename_to_old: dict[str, str]) -> None:
        self.rename_to_old = rename_to_old

    def visit_Import(self, node: ast.Import) -> None:
        return None

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        return None

    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.AST:
        node = self.generic_visit(node)
        node.name = self.rename_to_old.get(node.name, node.name)
        return node

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> ast.AST:
        node = self.generic_visit(node)
        node.name = self.rename_to_old.get(node.name, node.name)
        return node

    def visit_Name(self, node: ast.Name) -> ast.AST:
        node.id = self.rename_to_old.get(node.id, node.id)
        return node

    def visit_Attribute(self, node: ast.Attribute) -> ast.AST:
        node = self.generic_visit(node)
        node.attr = self.rename_to_old.get(node.attr, node.attr)
        return node


def canonical_dump(tree: ast.Module, rename_to_old: dict[str, str]) -> str:
    clone = copy.deepcopy(tree)
    canonical = Canonicalize(rename_to_old).visit(clone)
    return ast.dump(canonical, include_attributes=False)


def normalized_function_tokens(source: str, node: ast.FunctionDef | ast.AsyncFunctionDef, rename_to_old: dict[str, str]) -> list[tuple[int, str]]:
    lines = source.splitlines(keepends=True)
    segment = "".join(lines[node.lineno - 1 : node.end_lineno])
    out: list[tuple[int, str]] = []
    for tok in tokenize.generate_tokens(io.StringIO(segment).readline):
        if tok.type in {tokenize.ENCODING, tokenize.ENDMARKER, tokenize.INDENT, tokenize.DEDENT, tokenize.NL, tokenize.NEWLINE}:
            continue
        text = rename_to_old.get(tok.string, tok.string) if tok.type == tokenize.NAME else tok.string
        out.append((tok.type, text))
    return out


def compare_file(rel: str, old_path: Path, new_path: Path) -> tuple[list[Violation], dict[str, str]]:
    violations: list[Violation] = []
    try:
        old_source, old_tree = parse(old_path)
        new_source, new_tree = parse(new_path)
    except (SyntaxError, UnicodeDecodeError) as exc:
        return [Violation(rel, "parse", str(exc), None, None)], {}

    old_comments = comment_tokens(old_source)
    new_comments = comment_tokens(new_source)
    if old_comments != new_comments:
        violations.append(Violation(rel, "comments", "comment tokens changed; code may have been commented out or uncommented", None, None))

    old_imports = imports(old_tree)
    new_imports = imports(new_tree)
    removed_imports = old_imports - new_imports
    if removed_imports:
        violations.append(Violation(rel, "imports", "existing imports were removed or modified", None, None))

    mapping, mapping_violations = function_mapping(old_tree, new_tree)
    violations.extend(Violation(rel, v.rule, v.detail, v.line, v.end_line) for v in mapping_violations)
    rename_to_old = {new: old for old, new in mapping.items()}

    if not mapping_violations and canonical_dump(old_tree, {}) != canonical_dump(new_tree, rename_to_old):
        violations.append(Violation(rel, "ast-change", "code changed beyond function renames and added imports", None, None))

    old_functions = collect_functions(old_tree)
    new_functions = collect_functions(new_tree)
    if len(old_functions) == len(new_functions):
        for left, right in zip(old_functions, new_functions):
            old_tokens = normalized_function_tokens(old_source, left.node, {})
            new_tokens = normalized_function_tokens(new_source, right.node, rename_to_old)
            if old_tokens != new_tokens:
                violations.append(Violation(rel, "function-body", f"tokens inside function {left.name!r} changed beyond permitted renames", left.lineno, left.end_lineno))

    return violations, mapping


def verify(before: Path, after: Path) -> tuple[list[Violation], dict[str, dict[str, str]]]:
    violations: list[Violation] = []
    mappings: dict[str, dict[str, str]] = {}
    old_files = python_files(before)
    new_files = python_files(after)

    for rel in sorted(old_files.keys() - new_files.keys()):
        violations.append(Violation(rel, "file-removed", "Python file was removed"))
    for rel in sorted(new_files.keys() - old_files.keys()):
        violations.append(Violation(rel, "file-added", "Python file was added"))

    for rel in sorted(old_files.keys() & new_files.keys()):
        file_violations, mapping = compare_file(rel, old_files[rel], new_files[rel])
        violations.extend(file_violations)
        if mapping:
            mappings[rel] = mapping
    return violations, mappings


def format_location(v: Violation) -> str:
    if v.line is not None and v.end_line is not None and v.line != v.end_line:
        return f"{v.file}:{v.line}-{v.end_line}"
    elif v.line is not None:
        return f"{v.file}:{v.line}"
    return v.file


def print_text(violations: Sequence[Violation], mappings: dict[str, dict[str, str]], verbose: bool = False) -> None:
    if mappings:
        print("Detected function renames:")
        for file, mapping in sorted(mappings.items()):
            for old, new in sorted(mapping.items()):
                print(f"  {file}: {old} -> {new}")
    if violations:
        print(f"FAILED: {len(violations)} violation(s)")
        for item in violations:
            location = format_location(item)
            print(f"  [{item.rule}] {location}: {item.detail}")
    else:
        print("PASSED: only function renames, matching call-site renames, and added imports were detected")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("before", type=Path, help="directory containing the original Python tree")
    parser.add_argument("after", type=Path, help="directory containing the refactored Python tree")
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    parser.add_argument("--verbose", action="store_true", help="show detailed output (currently for text mode)")
    parser.add_argument("--ignore-rule", action="append", dest="ignore_rules", default=[], help="ignore specific violation rules (can be used multiple times)")
    args = parser.parse_args(argv)

    if not args.before.is_dir() or not args.after.is_dir():
        parser.error("before and after must both be directories")

    violations, mappings = verify(args.before.resolve(), args.after.resolve())

    # Filter violations by ignored rules
    if args.ignore_rules:
        violations = [v for v in violations if v.rule not in args.ignore_rules]

    if args.json:
        violations_json = [{"file": v.file, "rule": v.rule, "detail": v.detail, "line": v.line, "end_line": v.end_line} for v in violations]
        print(json.dumps({"ok": not violations, "renames": mappings, "violations": violations_json}, indent=2))
    else:
        print_text(violations, mappings, verbose=args.verbose)
    return 1 if violations else 0


if __name__ == "__main__":
    raise SystemExit(main())
