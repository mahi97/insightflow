# How to Use This Build Brief with Claude Code

1. Create an empty repository.
2. Copy these files into the repository:
   - `MASTER_PROMPT_FOR_CLAUDE_CODE.md`
   - `PRODUCT_SPEC.md`
   - `ARCHITECTURE_SPEC.md`
   - `ACCEPTANCE_TESTS.md`
3. Open Claude Code in the repository root.
4. Paste the full contents of `MASTER_PROMPT_FOR_CLAUDE_CODE.md`.
5. Tell Claude:

```text
Read PRODUCT_SPEC.md, ARCHITECTURE_SPEC.md, and ACCEPTANCE_TESTS.md before writing code. Build the project fully. Do not stop at a sample. Use uv for all tasks. Keep going until the acceptance tests pass.
```

6. When Claude reports completion, run the acceptance commands yourself:

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

7. If anything fails, paste the failing output back to Claude and say:

```text
Fix these failures. Do not change the acceptance criteria unless absolutely necessary. Preserve the product goal: adaptive research scheduling for time-to-insight.
```
