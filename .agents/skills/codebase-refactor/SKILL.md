---
name: codebase-refactor
description: Use when asked to refactor a codebase for dead code, duplication, typing quality, complexity, package structure, API stability, tests, and public docstrings without changing behavior.
---

# Codebase Refactor

Use this skill when the user asks for a broad, behavior-preserving refactor pass across an existing codebase. The goal is to leave the codebase easier to read, debug, test, and contribute to while preserving the public API.

## Core Principles

- Preserve behavior and public APIs unless the user explicitly asks for a breaking change.
- Make focused, incremental edits. Prefer several safe refactors over one large risky rewrite.
- Respect existing architecture, project instructions, dependency policy, formatting, and test workflow.
- Do not commit changes unless the user explicitly asks.
- Do not remove meaningful code just to satisfy a metric. If a guideline conflicts with readability or maintainability, explain the tradeoff and choose readability.

## Refactoring Checklist

Prioritize changes that address these concerns:

1. Remove dead code.
2. Remove duplicated logic by extracting small, well-named helpers or shared modules.
3. Improve type annotations.
   - Avoid public signatures that use `Any` or `object` when a useful type can be named.
   - Prefer modern language features when supported by the project, such as Python 3.12 generic syntax.
   - Keep dynamic boundary types only when narrowing would be misleading or unsafe.
4. Keep functions focused and understandable.
   - Split long or complicated functions when a clear sub-responsibility can be named.
   - Avoid over-extraction that makes control flow harder to follow.
5. Keep files focused and reasonably sized.
   - Treat files over roughly 500 meaningful lines as refactor candidates.
   - Imports, exports, examples, generated bindings, and intentionally centralized API surfaces may be reasonable exceptions.
   - Project-specific exception: `crates/gummy_canvas/src/canvas/methods.rs` is an intentionally oversized PyO3 binding-surface exception; keep implementation logic in split helper modules.
   - Do not split a file if doing so makes the codebase harder to navigate.
6. Keep packages navigable.
   - Avoid too many sibling files in one package.
   - Multiple files with the same prefix are a smell; consider grouping them into a focused subpackage.
   - Do not create lots of tiny files just to satisfy a count.
7. Remove unnecessary abstractions that make code harder to read, debug, or contribute to.
8. Preserve public API signatures, imports, exports, and behavior.
9. Keep tests passing, including unit, integration, golden, benchmark, and project-specific validation where practical.
10. Ensure publicly exposed signatures have descriptive docstrings.
    - Explain behavior in beginner-friendly language.
    - Document arguments only when the description adds useful information beyond the name and type.
    - Document return values when useful.
    - Do not add a return-value section for functions that return `None`.
    - Overrides need their own docstrings.

## Working Process

1. Gather context before editing.
   - Inspect project instructions and existing architecture.
   - Search for large files, duplicate patterns, weak public annotations, and missing public docstrings.
   - Prefer project-provided audit scripts over inventing new conventions.

2. Choose a small refactor target.
   - Start with duplicated logic, obvious dead code, missing docstrings, or oversized focused modules.
   - Avoid public API changes.
   - Avoid broad renames unless they are internal and clearly improve readability.

3. Make behavior-preserving edits.
   - Extract helpers only when the helper has a clear responsibility and name.
   - Keep call sites readable.
   - Update nearby tests, docs, or type aliases when needed.

4. Validate incrementally.
   - Run the smallest relevant lint/type/test command after focused changes.
   - Escalate to broader validation before finishing.
   - If a benchmark or opt-in test uncovers a real issue caused by the refactor, fix the root cause rather than loosening the test.

5. Iterate until no high-value refactor opportunities remain within the requested scope.
   - Stop when remaining changes would be speculative, risky, or mostly aesthetic.
   - Report any known tradeoffs or intentionally retained exceptions.

## Useful Scans

Adapt these patterns to the language and project. Prefer existing project tools if available.

- Find oversized source files.
- Find duplicate code shapes or repeated helper logic.
- Find public functions/classes exported without docstrings.
- Find public signatures using overly broad types such as `Any` or `object`.
- Find package directories with many same-prefix files that may deserve grouping.
- Check for unused code with the project’s linting or compiler tools.

## Validation Expectations

Before declaring the refactor complete:

- Run formatting/linting checks used by the project.
- Run type checks where available.
- Run the full relevant test suite when practical.
- Run integration, golden, smoke, benchmark, or opt-in checks when they are part of the user’s stated requirements or directly affected by the refactor.
- Refresh editor diagnostics when available.
- Run whitespace checks such as `git diff --check` when working in a Git repository.

Do not claim validation passed unless it was actually run and passed. If validation cannot be run, say why.

## Final Response

When finished, summarize against criteria instead of posting validation evidence/logs unless the user asks for details:

- Refactor criteria status: dead code, duplication, typing quality, complexity, file/package size, public API compatibility, and public docstrings.
- Quality gates status: diagnostics, formatting/linting, type checks, tests, size/structure audits, and whitespace checks as clean/not clean.
- Any intentionally retained exceptions or follow-up criteria.
- Any public API compatibility notes.

Keep command details minimal. Mention specific commands only when a gate fails, validation could not be run, or the user explicitly asks for evidence.
