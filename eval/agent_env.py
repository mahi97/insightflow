#!/usr/bin/env python
"""Agent-vs-ledger evaluation environment.

A deterministic world a *real* LLM agent acts in, so we can measure whether the
InsightFlow interface actually helps an agent reach correct claim verdicts with
fewer experiments — not just whether the deterministic scheduler does.

The environment is the InsightFlow ledger + a hidden ground truth (from the
simulator). An agent:

  1. inspects state          -> `insightflow state -C DIR`  (or `menu` below)
  2. runs one experiment     -> `agent_env.py run   --dir DIR --exp EXP_ID`
  3. (guided only) asks      -> `insightflow plan/readiness -C DIR`
  4. commits a verdict       -> `agent_env.py decide --dir DIR --claim C --verdict supported|refuted`

Each `run` reveals that experiment's deterministic result and records it to the
ledger (so `insightflow state` reflects it) and costs one "run". The goal is the
CORRECT verdict for every claim in as FEW runs as possible. `score` grades the
committed verdicts against the hidden ground truth. The agent never sees the
ground truth; the ledger remains the single source of truth for observed results.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from insightflow.ledger import Ledger
from insightflow.schemas import ClaimStatus
from insightflow.simulator import SCENARIOS, SimProject
from insightflow.utils import write_yaml

STATE_FILE = ".env_state.json"


def _project(scenario: str, seed: int) -> SimProject:
    if scenario not in SCENARIOS:
        raise SystemExit(f"unknown scenario {scenario!r}; choices: {', '.join(SCENARIOS)}")
    return SCENARIOS[scenario](seed, f"{scenario}{seed}")


def _load_env(dir_: Path) -> dict:
    return json.loads((dir_ / STATE_FILE).read_text())


def _save_env(dir_: Path, env: dict) -> None:
    (dir_ / STATE_FILE).write_text(json.dumps(env, indent=2))


def cmd_setup(args: argparse.Namespace) -> None:
    dir_ = Path(args.dir).resolve()
    (dir_ / "configs").mkdir(parents=True, exist_ok=True)
    project = _project(args.scenario, args.seed)
    # Write configs with every experiment PENDING and no results revealed.
    claims = [c.model_dump(mode="json") for c in project.claims]
    exps = []
    for e in project.experiments:
        d = e.model_dump(mode="json")
        d["status"] = "pending"
        exps.append(d)
    write_yaml(dir_ / "configs" / "claims.yaml", {"claims": claims})
    write_yaml(dir_ / "configs" / "experiments.yaml", {"experiments": exps})
    Ledger(dir_).initialize(force=True)
    env = {
        "scenario": args.scenario,
        "seed": args.seed,
        "runs": 0,
        "revealed": [],
        "verdicts": {},
    }
    _save_env(dir_, env)
    truth = project.ground_truth_statuses()
    decidable = [c.id for c in project.claims
                 if truth[c.id] in (ClaimStatus.supported, ClaimStatus.refuted)]
    print(f"Set up '{args.scenario}' (seed {args.seed}) at {dir_}")
    print(f"Claims to decide: {', '.join(decidable)}")
    print(f"Experiments available: {len(project.experiments)}")


def cmd_menu(args: argparse.Namespace) -> None:
    dir_ = Path(args.dir).resolve()
    env = _load_env(dir_)
    project = _project(env["scenario"], env["seed"])
    revealed = set(env["revealed"])
    print(f"Runs used so far: {env['runs']}")
    print("Claims:")
    for c in project.claims:
        print(f"  {c.id}: {c.statement} (needs >= {c.minimum_effect_size} effect, "
              f"{c.required_seeds}+ seeds, target {c.target_metric})")
    print("Experiments (id | method | dataset/condition | seed | run?):")
    for e in project.experiments:
        mark = "DONE" if e.id in revealed else "----"
        role = "baseline" if e.is_baseline else "method"
        print(f"  {e.id:34} {role:8} {e.dataset}/{e.condition} s{e.seed}  {mark}")


def cmd_run(args: argparse.Namespace) -> None:
    dir_ = Path(args.dir).resolve()
    env = _load_env(dir_)
    project = _project(env["scenario"], env["seed"])
    exp = next((e for e in project.experiments if e.id == args.exp), None)
    if exp is None:
        raise SystemExit(f"no experiment {args.exp!r}; see `menu`")
    if args.exp in env["revealed"]:
        print(f"{args.exp} already run (no extra cost charged).")
        return
    result = project.execute(exp)
    Ledger(dir_).add_result(result)
    env["revealed"].append(args.exp)
    env["runs"] += 1
    _save_env(dir_, env)
    metric, value = next(iter(result.metrics.items()))
    print(f"Ran {args.exp}: {metric} = {value} (runs used: {env['runs']})")


def cmd_decide(args: argparse.Namespace) -> None:
    dir_ = Path(args.dir).resolve()
    env = _load_env(dir_)
    if args.verdict not in ("supported", "refuted"):
        raise SystemExit("verdict must be 'supported' or 'refuted'")
    env["verdicts"][args.claim] = args.verdict
    _save_env(dir_, env)
    print(f"Recorded verdict {args.claim} = {args.verdict}")


def cmd_score(args: argparse.Namespace) -> None:
    dir_ = Path(args.dir).resolve()
    env = _load_env(dir_)
    project = _project(env["scenario"], env["seed"])
    truth = project.ground_truth_statuses()
    decidable = [c.id for c in project.claims
                 if truth[c.id] in (ClaimStatus.supported, ClaimStatus.refuted)]
    verdicts = env["verdicts"]
    per_claim = {}
    wrong = 0
    for cid in decidable:
        want = truth[cid].value
        got = verdicts.get(cid)
        ok = got == want
        if got is not None and not ok:
            wrong += 1
        per_claim[cid] = {"truth": want, "verdict": got, "correct": ok}
    all_correct = all(per_claim[c]["correct"] for c in decidable)
    report = {
        "scenario": env["scenario"],
        "seed": env["seed"],
        "runs_used": env["runs"],
        "experiments_total": len(project.experiments),
        "all_correct": all_correct,
        "wrong_decisions": wrong,
        "per_claim": per_claim,
    }
    print(json.dumps(report, indent=2))


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("setup")
    s.add_argument("--scenario", required=True)
    s.add_argument("--seed", type=int, default=0)
    s.add_argument("--dir", required=True)
    s.set_defaults(func=cmd_setup)

    m = sub.add_parser("menu")
    m.add_argument("--dir", required=True)
    m.set_defaults(func=cmd_menu)

    r = sub.add_parser("run")
    r.add_argument("--dir", required=True)
    r.add_argument("--exp", required=True)
    r.set_defaults(func=cmd_run)

    d = sub.add_parser("decide")
    d.add_argument("--dir", required=True)
    d.add_argument("--claim", required=True)
    d.add_argument("--verdict", required=True)
    d.set_defaults(func=cmd_decide)

    sc = sub.add_parser("score")
    sc.add_argument("--dir", required=True)
    sc.set_defaults(func=cmd_score)

    args = p.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    sys.exit(main())
