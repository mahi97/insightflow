# Real-data case study: GFA vs LoRA on GLUE

This is InsightFlow run on **real Weights & Biases logs** — 447 finished runs from
the `gfa-vs-lora` project (GFA vs LoRA on five GLUE tasks, RoBERTa-large), pulled
and shaped with [`eval/wandb_to_replay.py`](../../eval/wandb_to_replay.py). It is a
faithful, unflattering test: the conclusion is *not* a clean win for the method.

## The data (best-of-sweep per task, the standard reported-number comparison)

| task | GFA (best) | LoRA (best) | effect |
|------|-----------:|------------:|-------:|
| cola | 0.604 | 0.579 | **+0.025** |
| rte  | 0.567 | 0.531 | **+0.036** |
| mnli | 0.891 | 0.888 | +0.004 |
| sst2 | 0.958 | 0.954 | +0.003 |
| mrpc | 0.812 | 0.825 | **−0.012** |

Pooled effect **+0.011**. GFA's *mean* over its hyperparameter sweep is far lower
(e.g. 0.183 on cola), so averaging the sweep as if the runs were seeds would be
wrong — best-of-sweep vs best-of-sweep is the fair comparison.

## Naive pooled call vs InsightFlow

A naive rule ("pooled effect +0.011 ≥ 0.01 → supported") would report **"GFA beats
LoRA across GLUE."** InsightFlow does **not**:

```
| claim | own | effective | conf | ... | effect | min_eff | near_bdry |
| C1    | weak | weak     | 0.52 |     | 0.011  | 0.010   | yes       |
```

**C1 is WEAK, not paper-ready** — the margin (0.011) barely clears the minimum
effect (0.010), is within noise on 3/5 tasks (+0.003, +0.004), and is *negative* on
mrpc. InsightFlow flags it as sitting on the decision boundary and withholds the
"supported" verdict. That is the tool's core job — stopping a borderline result
from being overclaimed as a clean generalization.

Replay abstains here on purpose: because the full history does not *decide* the
claim (it is weak, not supported/refuted), there is no verdict to replay a policy
against. (For replay-runs-saved on a *decisive* history, see
[`examples/replay_example`](../replay_example).)

## Reproduce

```bash
cp -r examples/gfa_vs_lora_real /tmp/gfa && cd /tmp/gfa
uv run insightflow init -C .
uv run insightflow import-csv --path runs.csv --metric score -C .
uv run insightflow readiness -C .     # -> C1 weak, not paper-ready
```

To regenerate `runs.csv` from W&B yourself:

```bash
uv run python eval/wandb_to_replay.py extract --project mahi97/gfa-vs-lora --out rows.json
uv run python eval/wandb_to_replay.py build --rows rows.json --method gfa --baseline lora --out .
```

(`build` above uses every run per cell; the committed `runs.csv` uses best-of-sweep
per task, the fair reported-number comparison — see the session notes.)
