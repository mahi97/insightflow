# InsightFlow Acceptance Tests

Claude Code must not stop until these pass or until it explicitly reports what could not be completed and why.

## Required commands

```bash
uv sync
uv run pytest
uv run ruff check .
uv run insightflow demo --force
uv run insightflow state
uv run insightflow plan
uv run insightflow benchmark --steps 5
uv run insightflow validate
```

## Functional acceptance

The project is acceptable only if:

1. `uv sync` succeeds.
2. The CLI entrypoint exists.
3. `demo --force` creates a complete toy project state.
4. `state` prints completed, pending, and claim summaries.
5. `plan` produces ranked actions with rationales.
6. `plan` writes a Markdown report.
7. `benchmark` runs at least one synthetic benchmark.
8. W&B importer is implemented and has mocked tests.
9. Tests do not require live W&B credentials.
10. The scheduler distinguishes extra seeds from new conditions.
11. The scheduler can postpone low-value table-completion runs.
12. The seed policy is tested.
13. The code uses uv-compatible pyproject dependencies.
14. Docs explain current limitations honestly.

## Quality acceptance

The project should have:

- typed core models
- clear modules
- useful error messages
- deterministic scoring
- audit logs or decision records
- readable Markdown reports
- no major placeholder functions pretending to be implemented

## Red flags that must be fixed

- CLI exists but commands are stubs.
- W&B import is only pseudocode.
- Scheduler just sorts by cost.
- No tests for ranking behavior.
- No synthetic benchmark.
- No config validation.
- Claude instructions tell the agent to hallucinate decisions without running the CLI.
- The README oversells features not built.
