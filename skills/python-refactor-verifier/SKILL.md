---
name: python-refactor-verifier
description: Verify highly constrained Python refactors where the only permitted code changes are renaming existing functions and all corresponding call sites, plus adding new imports. Use when reviewing a refactor, pull request, commit range, working tree snapshot, or two source directories for accidental code commenting/uncommenting, added or removed function-body code, inconsistent function renames, changed imports, or any other unauthorized Python modification. Run the bundled deterministic scripts and report a pass/fail result with exact violations.
---

# Python Refactor Verifier

Verify the refactor deterministically. Do not approve based on visual inspection alone.

## Accepted inputs

Use either:

- Two directories: original tree and refactored tree.
- A Git repository plus base and head revisions.

Ask for missing paths or revisions only when they cannot be inferred from the user's files or repository context.

## Required workflow

1. Identify the original and refactored snapshots.
2. Run the appropriate bundled verifier:
   - Directories:
     ```bash
     python scripts/verify_refactor.py BEFORE_DIR AFTER_DIR
     ```
   - Git revisions:
     ```bash
     python scripts/verify_git_refactor.py BASE_REF HEAD_REF --repo REPO_DIR
     ```
3. Treat exit code `0` as pass, `1` as policy violations, and `2` as invocation or Git failure.
4. Report every violation grouped by file and rule, with line numbers.
5. Never rewrite or repair code unless the user separately asks for changes.

Use `--json` for machine-readable output in CI or automation. Use `--ignore-rule` to skip certain violation types (can be used multiple times).

## Enforced policy

Permit only:

- Renaming an existing function or method.
- Renaming all references and call sites consistently with that function rename (includes direct calls, method invocations, and references in expressions).
- Adding new `import` or `from ... import ...` statements.

Reject:

- Added or removed Python files.
- Removed or modified existing imports.
- Added, removed, reordered, or otherwise changed code.
- Added or removed tokens inside any function body, except identifiers participating in an approved function rename.
- Parameter, variable, class, constant, attribute, or module renames unrelated to a function rename.
- Added, removed, or changed comments, including commenting code out or uncommenting code.
- Added or removed functions, methods, decorators, statements, expressions, arguments, defaults, annotations, or control flow.
- Inconsistent, ambiguous, or colliding function rename mappings.

## Interpretation notes

The verifier compares Python ASTs after removing imports and canonicalizing detected function renames. It also compares normalized tokens inside every function. This intentionally makes the policy stricter than a normal refactor review.

A function definition line may change only in its function name. A call expression may change only in the matching called function or method name. Formatting-only edits inside functions are tolerated only where tokenization remains identical; comment changes are never tolerated.

**Known limitation**: renames are matched by identifier text, not variable scope/binding. If an unrelated local variable elsewhere in the same file happens to share the renamed function's old or new name, a rename of that unrelated variable can be masked and go unreported. Treat a PASS as strong evidence, not an absolute guarantee, when identifier collisions are plausible.

## Output format

### Text output

Violations are reported with file location and line numbers:

```
[function-body] path/to/file.py:10-15: tokens inside function 'old_name' changed beyond permitted renames
[comments] path/to/file.py:5: comment tokens changed; code may have been commented out or uncommented
[imports] path/to/file.py: existing imports were removed or modified
```

### JSON output

Machine-readable format includes structured violation data:

```json
{
  "ok": false,
  "renames": {
    "module.py": {
      "old_function": "new_function"
    }
  },
  "violations": [
    {
      "file": "module.py",
      "rule": "function-body",
      "detail": "tokens inside function 'old' changed beyond permitted renames",
      "line": 10,
      "end_line": 15
    }
  ]
}
```

## Command-line options

- `--json`: Emit machine-readable JSON output
- `--verbose`: Show detailed output (text mode)
- `--ignore-rule RULE`: Ignore specific violation rules (can be used multiple times, e.g., `--ignore-rule comments --ignore-rule imports`)

Example with options:

```bash
python scripts/verify_refactor.py before/ after/ --json --ignore-rule comments
python scripts/verify_git_refactor.py origin/main HEAD --repo . --ignore-rule comments
```

## Examples

### Allowed: Basic function rename

```python
# Before
def calculate(x):
    return x * 2

result = calculate(5)

# After
def compute(x):
    return x * 2

result = compute(5)
```

**Result**: PASSED

### Allowed: Adding imports

```python
# Before
print("hello")

# After
import sys
print("hello")
```

**Result**: PASSED

### Allowed: Method rename in class

```python
# Before
class Calculator:
    def process(self, x):
        return x * 2

calc = Calculator()
calc.process(5)

# After
class Calculator:
    def execute(self, x):
        return x * 2

calc = Calculator()
calc.execute(5)
```

**Result**: PASSED

### Rejected: Missed call site

```python
# Before
def func():
    pass

x = func()
y = func()

# After
def renamed():
    pass

x = renamed()
y = func()  # ERROR: call site not renamed
```

**Result**: FAILED - `function-body` violation

### Rejected: Added line in function

```python
# Before
def f(x):
    return x

# After
def f(x):
    x += 1
    return x
```

**Result**: FAILED - `function-body` or `ast-change` violation

### Rejected: Commented out code

```python
# Before
def process():
    return data

# After
def process():
    # return data
    pass
```

**Result**: FAILED - `comments` violation

### Rejected: Removed import

```python
# Before
import sys
print(sys.version)

# After
print("version")
```

**Result**: FAILED - `imports` violation

## CI example

```bash
python path/to/skill/scripts/verify_git_refactor.py origin/main HEAD --repo .
```

Fail the CI job when the script exits nonzero. Preserve the verifier output as review evidence.

## Violation rules reference

| Rule | Meaning |
|------|---------|
| `function-count` | Number of functions changed (added/removed) |
| `function-structure` | Function nesting or order changed |
| `rename-consistency` | One function mapped to multiple different names |
| `rename-collision` | Multiple functions mapped to the same name |
| `ast-change` | Code changed beyond renames and new imports |
| `function-body` | Tokens inside a function changed (unpermitted) |
| `comments` | Comment tokens changed or code was commented/uncommented |
| `imports` | Existing imports were removed or modified |
| `file-added` | Python file was added |
| `file-removed` | Python file was removed |
| `parse` | Syntax error or encoding issue in a file |
