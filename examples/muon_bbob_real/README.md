# Real-data replay: Muon_ES vs Open_ES on BBOB

InsightFlow's offline replay on **real Weights & Biases logs** — 144 runs drawn from
the `muones-bbob` project (2,556 finished runs total: 19 evolution strategies × 24
BBOB functions × seeds), extracted with
[`eval/wandb_to_replay.py`](../../eval/wandb_to_replay.py). The metric is
`score = −log₁₀(best_fitness)` (higher is better; fitness is a minimization
objective spanning many orders of magnitude, so log scale is the honest transform).

## The claim and the verdict

**C1: "Muon_ES reaches better final fitness than Open_ES across BBOB functions."**
In the full data Muon_ES beats Open_ES on **22 / 24** functions (pooled +0.67
log-decades). InsightFlow agrees: **C1 = supported (conf 0.78), paper-ready.**

## The replay result (the headline)

Given the *already-known* results, would InsightFlow have reached that verdict with
fewer runs than the order they were actually run in?

```
Runs-to-decision by replay policy (lower is better):
  actual         115     # the real wall-clock order the runs happened in
  insightflow     58     # <-- InsightFlow's order reaches the SAME verdict in ~half
  grid           115
  random          68
  cheap_first    115
  seeds_first     88
```

**InsightFlow reaches the supported verdict in 58 runs vs the actual 115 — 49.6%
fewer — and beats every baseline policy.** It gets there by establishing breadth
across the 24 functions early (one Muon_ES/Open_ES pair per function) instead of the
actual depth-first order, so the "holds across functions" claim resolves sooner.

## Honest scientific context (this is not cherry-picked)

The same data shows the Muon modification is a **general but not universal** win —
InsightFlow reaches *different* verdicts for the sibling claims:

| claim (across 24 BBOB fns) | functions won | verdict |
|----------------------------|:-------------:|:-------:|
| Muon_ES  vs Open_ES | 22/24 | supported |
| MuonARS  vs ARS     | 23/24 | supported |
| MuonPGPE vs PGPE    | 22/24 | supported |
| **MuonSNES vs SNES**| **2/24** | **refuted** |

Adding Muon helps Open-ES / ARS / PGPE but **hurts SNES** — a real negative result
the claim graph surfaces rather than hides. (CMA-ES remains the strongest baseline,
beating Open_ES on 24/24 — a sanity check.)

## Reproduce

```bash
cp -r examples/muon_bbob_real /tmp/bbob && cd /tmp/bbob
uv run insightflow init -C .
uv run insightflow import-csv --path runs.csv --metric score -C .
uv run insightflow readiness -C .          # C1 supported, paper-ready
uv run insightflow replay -C .             # insightflow 58 vs actual 115
```

To regenerate from W&B (config-driven project: `es_name` × `fn_name` × `seed` ×
`best_fitness`), see the extraction snippet in the session notes; the committed
`runs.csv` uses the first 3 seeds per function with `score = −log₁₀(best_fitness)`.
