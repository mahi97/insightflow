# Prompt: Autonomous research loop (no human approver)

Use this when an agent runs an entire research project end to end, executing and
recording experiments itself. See `docs/agent_driven_project.md` for the full
guide.

---

You are running a research project autonomously. **InsightFlow is your experiment
brain and your durable memory — not your memory, the ledger.** Never decide what
to run from memory or intuition; decide from `uv run insightflow plan`.

Setup (once):
- Encode the paper's assertions as `configs/claims.yaml` (target metric, minimum
  effect, required seeds, importance, reviewer risk).
- Enumerate every runnable cell in `configs/experiments.yaml` (with `command`,
  `claim_links`, `dependencies`, costs, and baselines tagged `baseline`).
- Set a real `budget_gpu_hours` in `configs/resources.yaml`.
- `uv run insightflow validate`, then `export INSIGHTFLOW_GUARD=block`.

Loop (repeat):
1. `uv run insightflow state` — rehydrate: what is done, pending, decided.
2. `uv run insightflow plan` — get the ranked queue, postponed, avoided, warnings.
3. Take the **top immediate-queue** item(s). Confirm each is not postponed/avoided
   and is within budget. If a run is expensive and not in the queue, do not run it.
4. Launch it yourself (shell / cluster / W&B).
5. Record the outcome: `uv run insightflow log-result --experiment-id ID
   --metric <name>=<value> --status completed --cost C --wall-time T`
   (or `uv run insightflow import-wandb ...`). For in-flight runs, record
   `--status running` with partial history and let the partial-run policy advise
   continue/stop/promote.
6. `uv run insightflow plan` again. Did any claim's status change?

Stop when every paper-critical claim is `supported` or `refuted` (read the
claim-confidence table) **or** the budget is exhausted — not when the grid is
full.

Then write up from the ledger, not from memory: methods from the configs, the
"what we ran and why" appendix from `.insightflow/decisions.jsonl`, the results
table from `reports/claim_confidence.md`, and the "compute saved" figure from
`uv run insightflow benchmark --format json`. Report what you did **not** run and
why; that is the contribution. Back final claims with the measured effects and
seed counts in the ledger, not the heuristic confidence number alone.
