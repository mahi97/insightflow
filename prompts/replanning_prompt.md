# Prompt: Replan after new results

Use this when runs have finished and new evidence has landed.

---

New results are in. Update the plan and tell me what changed.

1. Make sure the results are in the ledger. If they came from W&B:
   `uv run insightflow import-wandb --entity E --project P --metric <metric>`.
   If recorded manually:
   `uv run insightflow log-result --experiment-id <id> --metric <name>=<value> --status completed`.
2. Run `uv run insightflow state` and `uv run insightflow plan` again.
3. Compare against the previous plan and report **what changed and why**:
   - Did any claim's status move (e.g., `needs_more_evidence` → `supported`, or
     toward `weak`/`refuted`)? What drove it?
   - Did a result make a planned run unnecessary (now redundant/avoided)?
   - Did a surprising or borderline result justify **adding a seed** where breadth
     was previously preferred?
   - Did a negative result on a cheap proxy mean an **expensive branch should be
     postponed or dropped**?
   - Are there new **dangerous gaps** (a missing baseline now on the critical
     path, generality still unverified)?
4. Give the updated **top runs**, **postpone**, and **avoid** lists, each tied to
   a claim/decision, with costs.

Do not launch anything. Ground every statement in the new `state`/`plan` output;
do not infer results that were not recorded.
