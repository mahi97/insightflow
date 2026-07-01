# Real-data evaluation

The synthetic benchmark ([`docs/evaluation.md`](evaluation.md)) shows the
*scheduler* is efficient under controlled ground truth. This page validates
InsightFlow on **real research logs** — actual Weights & Biases runs from finished
projects — using the [`eval/wandb_to_replay.py`](../eval/wandb_to_replay.py)
adapter (`extract` a project → `build` a claim/experiment/CSV case → `init` →
`import-csv` → `replay`/`readiness`). Every case below ships as a committed,
reproducible example with real numbers and a regression test.

## Case 1 — decisive replay: Muon_ES vs Open_ES on BBOB (headline)

[`examples/muon_bbob_real`](../examples/muon_bbob_real) — 144 runs from a project of
2,556 finished runs (19 evolution strategies × 24 BBOB functions × seeds),
`score = −log₁₀(best_fitness)`.

Claim "Muon_ES beats Open_ES across BBOB functions" is decisively **supported**
(22/24 functions). Offline replay — *would InsightFlow have reached that verdict
with fewer runs than the order the runs actually happened in?*

| policy | runs to decision |
|--------|-----------------:|
| actual (real order) | 115 |
| **InsightFlow** | **58** |
| grid | 115 |
| random | 68 |
| seeds_first | 88 |

**49.6% fewer runs than the real order**, best of all policies — by covering
breadth across the 24 functions before the actual depth-first order did. This is
the core value proposition demonstrated on real logs: reach the claim verdict
sooner by acquiring decisive evidence first.

The finding is not cherry-picked. Sibling claims reach *different* verdicts:
MuonARS vs ARS (23/24) and MuonPGPE vs PGPE (22/24) are supported, but **MuonSNES
vs SNES is refuted (2/24)** — the Muon modification helps most ES families yet
hurts SNES, a real negative result the claim graph surfaces.

## Case 2 — anti-overclaim: GFA vs LoRA on GLUE

[`examples/gfa_vs_lora_real`](../examples/gfa_vs_lora_real) — 447 finished GLUE
runs (RoBERTa-large), best-of-sweep per task.

Best GFA beats best LoRA by only **+0.011 pooled** (wins 4/5 tasks narrowly, loses
mrpc). A naive pooled rule would report "GFA beats LoRA across GLUE." InsightFlow
returns **C1 = weak, not paper-ready** (effect 0.011 vs min 0.010, on the decision
boundary) and withholds the verdict. Replay abstains by design — a weak claim has
no decisive history to replay against. This is the tool doing its central job:
**refusing to certify a borderline result** a reviewer would attack.

## Case 3 — powered agent-vs-ledger pilot

[`eval/AGENT_STUDY.md`](../eval/AGENT_STUDY.md) — six real Opus agents deciding
claims in the [`agent_env`](../eval/agent_env.py) world, guided (may consult
`insightflow plan/readiness`) vs naive.

Honest, **modest** result: both 2/3 correct; guided 8.5 vs naive 9.5 mean runs when
correct. A strong agent reasons well unaided on clear-cut scenarios; the tool's
observed contributions were surfacing the verdict earlier and not overclaiming
where evidence was thin. We do **not** claim a large agent-interface effect from
this small pilot — the synthetic policy benchmark remains the stronger evidence for
the scheduler itself.

## What these cases do and don't show

- **Do:** InsightFlow runs on real, messy W&B logs; on a decisive real claim it
  reaches the verdict with ~half the runs of the real order; on a borderline real
  claim it correctly withholds "supported"; it reaches opposite verdicts for
  sibling claims (Muon helps most ES, not SNES).
- **Don't:** these are single finished projects, not a powered multi-project study;
  the replay assumes the logged runs are the candidate set (it reorders history, it
  does not invent unrun experiments); best-of-sweep vs mean-of-sweep is a modelling
  choice made explicit per case. Larger multi-project replay and a powered agent
  study remain future work.
