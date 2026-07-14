#!/usr/bin/env python3
"""Validate that a Python module changed only by moving top-level functions."""

from __future__ import annotations

import argparse
import ast
import io
import sys
import tokenize
from collections import Counter
from dataclasses import dataclass
from pathlib import Path


FunctionNode = ast.FunctionDef | ast.AsyncFunctionDef


@dataclass(frozen=True)
class FunctionBlock:
    identity: tuple[str, int]
    name: str
    text: str
    start_line: int
    end_line: int


def _line_offsets(text: str) -> list[int]:
    offsets = [0]
    for line in text.splitlines(keepends=True):
        offsets.append(offsets[-1] + len(line))
    return offsets


def _function_blocks(text: str, filename: str) -> list[FunctionBlock]:
    tree = ast.parse(text, filename=filename, type_comments=True)
    offsets = _line_offsets(text)
    seen: Counter[str] = Counter()
    blocks: list[FunctionBlock] = []

    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.end_lineno is None or node.end_col_offset is None:
            raise ValueError(f"Missing source positions for function {node.name!r}")

        seen[node.name] += 1
        start_line = min(
            [node.lineno, *(decorator.lineno for decorator in node.decorator_list)]
        )
        start = offsets[start_line - 1]
        end = offsets[node.end_lineno - 1] + node.end_col_offset
        blocks.append(
            FunctionBlock(
                identity=(node.name, seen[node.name]),
                name=node.name,
                text=text[start:end],
                start_line=start_line,
                end_line=node.end_lineno,
            )
        )
    return blocks


def _non_function_ast(text: str, filename: str) -> list[str]:
    tree = ast.parse(text, filename=filename, type_comments=True)
    return [
        ast.dump(node, include_attributes=False, annotate_fields=True)
        for node in tree.body
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]


def _function_line_ranges(blocks: list[FunctionBlock]) -> list[tuple[int, int]]:
    return [(block.start_line, block.end_line) for block in blocks]


def _inside(line: int, ranges: list[tuple[int, int]]) -> bool:
    return any(start <= line <= end for start, end in ranges)


def _outside_significant_tokens(text: str, blocks: list[FunctionBlock]) -> list[tuple[int, str]]:
    ignored = {
        tokenize.ENCODING,
        tokenize.ENDMARKER,
        tokenize.INDENT,
        tokenize.DEDENT,
        tokenize.NEWLINE,
        tokenize.NL,
    }
    ranges = _function_line_ranges(blocks)
    result: list[tuple[int, str]] = []
    for token in tokenize.tokenize(io.BytesIO(text.encode("utf-8")).readline):
        if token.type in ignored or _inside(token.start[0], ranges):
            continue
        result.append((token.type, token.string))
    return result


def validate(original_path: Path, revised_path: Path) -> list[str]:
    original = original_path.read_text(encoding="utf-8")
    revised = revised_path.read_text(encoding="utf-8")

    original_blocks = _function_blocks(original, str(original_path))
    revised_blocks = _function_blocks(revised, str(revised_path))
    errors: list[str] = []

    original_by_id = {block.identity: block for block in original_blocks}
    revised_by_id = {block.identity: block for block in revised_blocks}

    if set(original_by_id) != set(revised_by_id):
        missing = sorted(set(original_by_id) - set(revised_by_id))
        added = sorted(set(revised_by_id) - set(original_by_id))
        if missing:
            errors.append(f"Top-level functions missing or renamed: {missing}")
        if added:
            errors.append(f"Top-level functions added or renamed: {added}")

    for identity in sorted(set(original_by_id) & set(revised_by_id)):
        before = original_by_id[identity]
        after = revised_by_id[identity]
        if before.text != after.text:
            errors.append(
                f"Function {before.name!r} changed internally or lost/changed decorators. "
                "Move the original block byte-for-byte."
            )

    if _non_function_ast(original, str(original_path)) != _non_function_ast(
        revised, str(revised_path)
    ):
        errors.append("Classes, variables, imports, or other non-function syntax changed or moved.")

    if _outside_significant_tokens(original, original_blocks) != _outside_significant_tokens(
        revised, revised_blocks
    ):
        errors.append("Significant module-level code or comments outside functions changed or moved.")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify that only complete top-level Python function blocks moved."
    )
    parser.add_argument("original", type=Path)
    parser.add_argument("reorganized", type=Path)
    args = parser.parse_args()

    try:
        errors = validate(args.original, args.reorganized)
    except (OSError, SyntaxError, UnicodeError, ValueError) as exc:
        print(f"VALIDATION ERROR: {exc}", file=sys.stderr)
        return 2

    if errors:
        print("FAILED: changes were not move-only.", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1

    print("PASSED: only complete top-level function blocks were moved.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
