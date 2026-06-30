---
description: Assess paper/project readiness over the claim graph (verdicts, blocked claims, reviewer attacks, next research actions)
---

Run `uv run insightflow readiness` in the current project and report, grounded in
its output (never invented):

- which claims are supported / refuted / weak / still need evidence, and which
  **main** claims are **blocked** by an unmet supporting subclaim;
- the most dangerous reviewer attacks, ranked;
- missing baselines, thin generality, and insufficient seeds;
- the recommended next research actions (which may be runs, a literature/novelty
  check, a reviewer attack, a claim refinement, or a theorem attempt).

Tie every recommendation to a claim and a decision. The CLI and ledger are the
source of truth; you are the interface, not the authority. $ARGUMENTS
