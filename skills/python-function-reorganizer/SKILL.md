---
name: python-function-reorganizer
description: Reorganize Python modules by moving existing top-level functions without changing their implementation. Use when asked to reorder, group, or relocate Python functions while guaranteeing that function bodies, signatures, decorators, comments inside functions, classes, variables, imports, and other module code remain unchanged. Validate the before-and-after files and reject edits that do more than move whole top-level function blocks.
---

# Python Function Reorganizer

Reorganize Python conservatively. Treat this as a move-only operation, not a normal refactor.

## Hard constraints

- Move only complete top-level `def` or `async def` blocks.
- Preserve each moved function byte-for-byte from its first decorator through its final line.
- Preserve all decorators in their original order and spelling.
- Do not edit code, comments, docstrings, annotations, defaults, whitespace, or blank lines inside a function.
- Do not rename functions, classes, variables, parameters, imports, or constants.
- Do not move or modify classes, assignments, imports, executable statements, or module-level variables.
- Do not move methods independently of their class.
- Do not add helpers, compatibility aliases, comments, formatting, or cleanup changes.

If the requested organization requires any forbidden edit, stop and explain that the request exceeds a move-only reorganization.

## Workflow

1. Read the complete source file before editing.
2. Identify the exact top-level functions to move and their destination order.
3. Copy each entire function block, including contiguous decorators, without editing its contents.
4. Change only the placement of those complete blocks.
5. Save the result to a separate file when possible.
6. Run:

```bash
python scripts/validate_move_only.py ORIGINAL.py REORGANIZED.py
```

7. Do not present the reorganization as complete unless validation passes.

## Validation interpretation

The validator must confirm all of the following:

- The same top-level functions exist before and after.
- Every function block is textually identical, including decorators and inline comments.
- Non-function syntax and significant tokens are unchanged and remain in the same order.
- At least one function changed position, unless the requested order already matched the source.

If validation fails, revert the edit and redo it as a pure block move. Never fix validation by weakening the validator.

## Output

Report:

- Which top-level functions moved.
- Their old and new ordinal positions.
- Whether move-only validation passed.
- Any requested changes that were intentionally not made because they violated the constraints.
