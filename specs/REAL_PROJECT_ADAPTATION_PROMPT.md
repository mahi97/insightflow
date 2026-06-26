# Prompt for Applying Built InsightFlow to a Real Research Project

Use the built InsightFlow project to analyze this research repository.

Your objective is to minimize time-to-insight and compute waste for the remaining experiments.

Steps:

1. Read `CLAUDE.md` and the InsightFlow docs.
2. Inspect the current repository structure.
3. Identify training scripts, config files, W&B usage, Slurm scripts, and result logs.
4. Create or update InsightFlow configs:
   - claims.yaml
   - experiments.yaml
   - resources.yaml
   - policy.yaml
5. Import W&B runs if credentials are available.
6. Run:

```bash
uv run insightflow state
uv run insightflow plan
```

7. Produce a research scheduling report with:
   - current completed evidence
   - weak claims
   - dangerous missing baselines
   - top next runs
   - seeds to postpone
   - expensive runs to delay
   - experiments that are likely unnecessary
   - exact launch commands if available

Do not launch expensive runs without human approval.
Do not complete the grid blindly.
Do not invent run results.
Every recommendation must point to a claim or decision.
