# Documentation Workflow

Documentation should match current behavior, not planned behavior.

## Where To Put Things

- `docs/getting_started/`: user learning path and first-sketch material.
- `docs/reference/`: API behavior grouped by topic.
- `docs/contribute/`: architecture, runtime, testing, and maintainer workflow.

## When To Update Docs

Update docs when changing:

- public APIs or user-visible behavior
- canvas runtime behavior
- pixels, images, text, export, or HiDPI behavior
- backend or renderer contracts
- packaging, install, release, or CI workflow

Use Mermaid diagrams in contributor docs when a workflow or ownership boundary
is easier to understand visually.

When docs mention source paths or package layout, run:

```sh
uv run python scripts/structure_audit.py
```

The audit catches stale renamed package paths and helps keep contributor docs in
sync with the current layout taxonomy.
