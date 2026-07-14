---
name: python-type-hints
description: add, improve, or review python type hints for functions, methods, classes, modules, callbacks, decorators, async code, data structures, and public APIs. use when asked to type python code, remove implicit or explicit any, fix pyright errors, introduce generics or protocols, modernize annotations, or make a python project pass strict pyright checks. in plan mode, inspect and propose an actionable typing plan without editing. in auto-edit mode, edit the code, validate it with pyright and tests, and report the completed changes.
---

# Python Type Hints

Add precise, maintainable Python type hints while preserving runtime behavior and avoiding unnecessary redesign.

## Determine the operating mode

Check the active Claude Code mode before acting.

- In **plan mode**, inspect the relevant code and configuration, then provide a concrete file-by-file plan. Do not modify files.
- In **auto-edit mode**, inspect, edit, format if appropriate, run Pyright, run focused tests, and summarize the actual changes.
- If the mode is unavailable, infer it from the available permissions. Never claim to have edited files when edits were not permitted.

## Establish the typing baseline

Before proposing or making changes:

1. Find the supported Python version in `pyproject.toml`, `.python-version`, `uv.lock`, `tox.ini`, CI configuration, or equivalent.
2. Find Pyright configuration in `pyproject.toml`, `pyrightconfig.json`, or `basedpyrightconfig.json`.
3. Inspect existing annotation style, imports, lint rules, framework conventions, and test setup.
4. Identify the requested scope. Prefer the smallest coherent scope that can be validated.
5. Run `scripts/inspect_typing_env.py` when execution is allowed to detect the Python version, Pyright configuration, repository commands, and changed Python files.
6. Run the existing Pyright command when execution is allowed. Record pre-existing errors separately from errors introduced by the change.

Do not silently change the configured Python version or Pyright strictness.

## Type from behavior, not names

Infer types from all relevant evidence:

- call sites and returned values
- mutations and attribute assignments
- exception and sentinel behavior
- tests and fixtures
- base classes and implemented protocols
- framework or library APIs
- serialization and database boundaries
- overload behavior and narrowing branches

Do not guess a narrow type from a variable name alone. When evidence is incomplete, prefer a safe abstraction or explicitly state the uncertainty.

## Apply annotations in this order

1. Public functions, methods, constructors, and class attributes.
2. Return types, including generators, coroutines, context managers, and `Never` paths.
3. Shared aliases and structured mappings.
4. Generic relationships between inputs and outputs.
5. Callbacks, decorators, protocols, and overloads.
6. Local annotations only where inference is insufficient or narrowing needs help.

Use the modern syntax supported by the project's minimum Python version. Do not modernize unrelated code merely to use newer syntax.

## Prefer precise abstractions

- Accept the least restrictive useful interface: `Iterable`, `Sequence`, `Mapping`, `Collection`, `Callable`, or a small `Protocol` when concrete containers are unnecessary.
- Return concrete types when callers rely on their concrete behavior.
- Preserve relationships with `TypeVar`, `ParamSpec`, `Concatenate`, `Self`, or overloads rather than weakening them into unions or `Any`.
- Use `TypedDict` for stable dictionary-shaped records and dataclasses or models when runtime structure is appropriate.
- Use `Literal` or enums for genuinely closed value sets.
- Use `TypeGuard` or `TypeIs` only when a helper truly performs reusable narrowing.
- Use `ClassVar` for class-only state and `Final` for values that must not be reassigned.
- Model absence with `None` only when absence is part of the actual contract.

Consult [references/pyright-patterns.md](references/pyright-patterns.md) for difficult patterns.

## Treat `Any` as an escape hatch

Aim to eliminate both explicit and implicit `Any` in the requested scope.

Before using `Any`, try:

1. a generic parameter
2. `object` plus narrowing
3. a protocol
4. a typed dictionary or model
5. an overload
6. a narrow cast at an untyped boundary
7. a local stub or library-specific typing package

Use `Any` only when the value is intentionally dynamically typed or an external boundary cannot be described reasonably. Keep it local and explain why it is unavoidable.

Never replace Pyright errors with broad `Any`, `# type: ignore`, or configuration suppressions merely to make the checker green.

## Preserve runtime behavior

Type-hint work must not accidentally alter semantics.

- Avoid changing defaults, exception behavior, mutation, ordering, I/O, or public return shapes.
- Avoid introducing runtime imports solely for annotations when they create cycles or optional-dependency failures.
- Use `TYPE_CHECKING`, quoted annotations, or postponed evaluation as appropriate for the supported Python version and framework.
- Verify whether frameworks inspect annotations at runtime before moving imports behind `TYPE_CHECKING`.
- Do not convert data structures, APIs, or class hierarchies unless necessary for sound typing and clearly within scope.

Small runtime guards are acceptable when they expose an already-required invariant and improve safety. Call them out explicitly.

## Handle untyped boundaries deliberately

For JSON, database rows, environment variables, third-party SDKs, plugins, and dynamically imported objects:

1. keep the untyped value at the boundary
2. validate or narrow it once
3. expose a typed value to the rest of the code

Prefer parsing and validation over repeated casts. A cast documents an invariant; it does not validate one.

## Plan-mode output

Provide:

- the current typing baseline and important constraints
- the main sources of imprecision or Pyright failures
- a file-by-file sequence of proposed edits
- noteworthy type design decisions
- validation commands to run
- risks, uncertain contracts, or likely follow-up work

Include representative signatures when they clarify the proposal, but do not produce a large speculative patch.

## Bundled scripts

Use the scripts from the skill directory; do not copy them into the target repository.

- Run `python scripts/inspect_typing_env.py <repo> --format markdown` to establish the repository baseline and discover likely commands. Treat its command suggestions as candidates; prefer explicit repository documentation and CI commands when they disagree.
- Run `python scripts/pyright_delta.py --root <repo> --command "<pyright command>" --baseline <snapshot> --save-baseline [targets...]` before edits.
- Run the same `pyright_delta.py` command without `--save-baseline` after edits. Add `--fail-on-new` in auto-edit mode so newly introduced Pyright errors fail validation.
- Store snapshots outside tracked source files, such as a temporary directory, unless the user explicitly wants an artifact committed.
- A moved diagnostic may appear as one resolved and one new diagnostic because comparison includes file and position. Inspect such cases instead of assuming a regression.

## Auto-edit workflow

1. Inspect the environment with `scripts/inspect_typing_env.py`.
2. Save a baseline with `scripts/pyright_delta.py`, using the repository-defined Pyright command.
3. Make a focused batch of edits.
4. Run formatting or linting only through the project's existing commands.
5. Compare Pyright against the saved baseline with `--fail-on-new`.
6. Run focused tests for changed behavior, followed by the broader relevant suite when practical.
7. Inspect the diff for accidental runtime changes and annotation churn.
8. Repeat until the requested scope passes or a concrete blocker remains.

Do not expand into repository-wide cleanup unless the user requested it.

## Validation requirements

Prefer repository-defined commands. Otherwise use an available command such as:

```bash
pyright
```

For a scoped change, a targeted command is acceptable during iteration, but finish with the configured project command whenever practical.

A completed auto-edit response must state:

- files changed
- important typing decisions
- Pyright result
- tests or checks run
- remaining errors, exclusions, or unavoidable `Any`

Be explicit when validation could not run because dependencies or tools were unavailable.
