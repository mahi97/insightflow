#!/usr/bin/env python
"""Turn a real Weights & Biases project into an InsightFlow replay case.

Real research projects rarely store a tidy (method, condition, seed, metric) —
they encode it in run names and log messy, per-framework metric keys. This adapter
makes the mapping explicit and reproducible, in two steps so the slow network pull
is separate from the (fast, offline) config generation:

  extract  pull finished runs, parse each into a row, write rows.json
  build    from rows.json, pick a method vs a baseline across the conditions where
           both were run, and emit claims.yaml + experiments.yaml + runs.csv
           (ordered by the runs' real wall-clock start = the actual arrival order)

Then the existing pipeline runs the counterfactual:

  uv run insightflow init -C OUT
  uv run insightflow import-csv --path OUT/runs.csv --metric score -C OUT
  uv run insightflow replay -C OUT

Defaults target the `gfa-vs-lora` GLUE project (names like
`gfa-sst2-roberta-large-r1-s42`); override the regexes for other projects.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

GLUE_TASKS = ["cola", "sst2", "mrpc", "stsb", "qqp", "mnli", "qnli", "rte", "wnli"]
# GLUE reports different headline metrics per task.
TASK_METRIC = {"cola": "eval/matthews_correlation", "stsb": "eval/pearson",
               "mrpc": "eval/f1", "qqp": "eval/f1"}


def cmd_extract(args: argparse.Namespace) -> None:
    import wandb

    api = wandb.Api()
    method_re = re.compile(args.method_regex)
    task_re = re.compile(args.task_regex)
    group_re = re.compile(args.group_regex) if args.group_regex else None
    seed_re = re.compile(args.seed_regex)

    rows = []
    for path in args.project:
        n = 0
        for r in api.runs(path, filters={"state": "finished"}, per_page=100):
            n += 1
            name = r.name.lower()
            mm = method_re.search(name)
            tm = task_re.search(name)
            if not mm or not tm:
                continue
            method = mm.group(1)
            task = tm.group(1)
            if task not in GLUE_TASKS:
                continue
            s = r.summary._json_dict if hasattr(r.summary, "_json_dict") else {}
            metric = TASK_METRIC.get(task, "eval/accuracy")
            val = s.get(metric)
            if val is None:
                val = s.get("eval/accuracy")
            if not isinstance(val, (int, float)):
                continue
            gm = group_re.search(name) if group_re else None
            sm = seed_re.search(name)
            rows.append({
                "project": path, "method": method, "task": task,
                "group": gm.group(1) if gm else "na",
                "seed": int(sm.group(1)) if sm else 0,
                "metric": metric, "value": float(val),
                "runtime": float(s.get("_runtime", 0.0) or 0.0),
                "created_at": str(r.created_at), "run_id": r.id, "name": r.name,
            })
        print(f"{path}: scanned {n} finished runs", file=sys.stderr)

    Path(args.out).write_text(json.dumps(rows, indent=2))
    # coverage summary
    cov = defaultdict(lambda: defaultdict(int))
    for row in rows:
        cov[row["method"]][(row["task"], row["group"])] += 1
    print(f"wrote {len(rows)} rows -> {args.out}", file=sys.stderr)
    print("coverage (method -> {(task,group): n}):")
    for m, cells in sorted(cov.items()):
        print(f"  {m}: {dict(sorted(cells.items()))}")


def cmd_build(args: argparse.Namespace) -> None:
    rows = json.loads(Path(args.rows).read_text())
    if args.group:
        rows = [r for r in rows if r["group"] == args.group]
    roles = {args.method: "method", args.baseline: "baseline"}
    rows = [r for r in rows if r["method"] in roles]

    tasks = args.tasks.split(",") if args.tasks else None
    if not tasks:  # auto: conditions where BOTH method and baseline were run
        by_task = defaultdict(set)
        for r in rows:
            by_task[r["task"]].add(r["method"])
        tasks = sorted(t for t, ms in by_task.items() if {args.method, args.baseline} <= ms)
    rows = [r for r in rows if r["task"] in tasks]
    if not tasks:
        raise SystemExit("no conditions where both method and baseline were run; check names/group")

    # One cell per (role, task, seed); if duplicates, keep the earliest run
    # (the real first observation of that cell).
    rows.sort(key=lambda r: r["created_at"])
    seen, cells = set(), []
    for r in rows:
        key = (roles[r["method"]], r["task"], r["seed"])
        if key in seen:
            continue
        seen.add(key)
        cells.append(r)

    out = Path(args.out)
    (out / "configs").mkdir(parents=True, exist_ok=True)
    from insightflow.utils import write_yaml

    claim = {
        "id": "C1", "type": "empirical",
        "statement": f"{args.method} improves {args.metric_name} over {args.baseline} "
                     f"across GLUE tasks ({', '.join(tasks)}).",
        "importance": "high", "target_metric": "score",
        "minimum_effect_size": args.min_effect, "required_seeds": 1, "reviewer_risk": 0.7,
    }
    exps, csv_rows = [], []
    for r in cells:
        role = roles[r["method"]]
        eid = f"{role}_{r['task']}_s{r['seed']}"
        exps.append({
            "id": eid, "method": r["method"] if role == "method" else f"baseline_{args.baseline}",
            "dataset": r["task"], "condition": "default", "seed": r["seed"],
            "claim_links": ["C1"], "expected_cost": 1.0, "expected_time": 1.0,
            "tags": [role],
        })
        csv_rows.append((eid, r["created_at"], r["value"]))

    write_yaml(out / "configs" / "claims.yaml", {"claims": [claim]})
    write_yaml(out / "configs" / "experiments.yaml", {"experiments": exps})
    csv_rows.sort(key=lambda x: x[1])  # real arrival order
    with (out / "runs.csv").open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["id", "created_at", "score"])
        for eid, created, val in csv_rows:
            w.writerow([eid, created, round(val, 5)])

    # per-task effect + honest verdict hint
    by = defaultdict(dict)
    for r in cells:
        by[r["task"]].setdefault(roles[r["method"]], []).append(r["value"])
    print(f"Built replay case at {out} ({len(cells)} cells across {len(tasks)} tasks)")
    print(f"Metric: per-task GLUE headline metric, mapped to claim target 'score'. "
          f"min_effect={args.min_effect}")
    print(f"\n  {'task':6} {'method':>8} {'baseline':>9} {'effect':>8}")
    effs = []
    for t in tasks:
        m = by[t].get("method", [])
        b = by[t].get("baseline", [])
        if m and b:
            me, be = sum(m) / len(m), sum(b) / len(b)
            effs.append(me - be)
            print(f"  {t:6} {me:8.3f} {be:9.3f} {me - be:+8.3f}")
    if effs:
        pooled = sum(effs) / len(effs)
        verdict = ("supported" if pooled >= args.min_effect
                   else "refuted" if pooled <= 0 else "weak")
        print(f"\n  pooled effect = {pooled:+.3f}  ->  data-implied verdict: {verdict.upper()}")


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    e = sub.add_parser("extract")
    e.add_argument("--project", nargs="+", required=True, help="entity/project (repeatable)")
    e.add_argument("--out", required=True)
    e.add_argument("--method-regex", default=r"^(gfa|lora)")
    e.add_argument("--task-regex", default=r"-(" + "|".join(GLUE_TASKS) + r")-")
    e.add_argument("--group-regex", default=r"-r(\d+)")
    e.add_argument("--seed-regex", default=r"-s(\d+)")
    e.set_defaults(func=cmd_extract)

    b = sub.add_parser("build")
    b.add_argument("--rows", required=True)
    b.add_argument("--method", required=True)
    b.add_argument("--baseline", required=True)
    b.add_argument("--group", default=None, help="fix a group (e.g. rank '1') for a fair comparison")
    b.add_argument("--tasks", default=None, help="comma list; default = auto (both-covered)")
    b.add_argument("--metric-name", default="accuracy")
    b.add_argument("--min-effect", type=float, default=0.01)
    b.add_argument("--out", required=True)
    b.set_defaults(func=cmd_build)

    args = p.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    sys.exit(main())
