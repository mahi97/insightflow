#!/usr/bin/env python
"""Aggregate an agent-vs-ledger study into a guided-vs-naive comparison.

Protocol (see eval/AGENT_STUDY.md):
  1. For each (scenario, condition, seed) create a world with `agent_env.py setup`
     into  <base>/<scenario>_<condition>[_<seed>].
  2. Run a real LLM agent in each world. Guided agents may consult
     `insightflow plan/readiness`; naive agents may not. Both minimise runs while
     staying correct, then commit verdicts.
  3. Run this aggregator over <base>: it scores every world (`agent_env.py score`)
     and reports, per condition, the mean runs-to-correct-decision, the fraction
     of worlds decided correctly, and the wrong-decision rate.

Usage:  python eval/agent_study.py --dir /tmp/if_agents
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ENV = Path(__file__).resolve().parent / "agent_env.py"


def _score(world: Path) -> dict | None:
    if not (world / ".env_state.json").exists():
        return None
    out = subprocess.run(
        [sys.executable, str(ENV), "score", "--dir", str(world)],
        capture_output=True, text=True,
    )
    if out.returncode != 0:
        return None
    return json.loads(out.stdout)


def _condition(name: str) -> str | None:
    for cond in ("guided", "naive"):
        if f"_{cond}" in name:
            return cond
    return None


def aggregate(base: Path) -> dict:
    worlds = sorted(p for p in base.iterdir() if p.is_dir())
    per_world = []
    for w in worlds:
        rep = _score(w)
        if rep is None:
            continue
        rep["world"] = w.name
        rep["condition"] = _condition(w.name)
        per_world.append(rep)

    by_cond: dict[str, list[dict]] = {"guided": [], "naive": []}
    for r in per_world:
        if r["condition"] in by_cond:
            by_cond[r["condition"]].append(r)

    summary = {}
    for cond, rows in by_cond.items():
        decided = [r for r in rows if r["all_correct"]]
        runs_when_correct = [r["runs_used"] for r in decided]
        summary[cond] = {
            "n": len(rows),
            "correct": len(decided),
            "correct_rate": round(len(decided) / len(rows), 3) if rows else None,
            "mean_runs_when_correct": (
                round(sum(runs_when_correct) / len(runs_when_correct), 2)
                if runs_when_correct else None
            ),
            "wrong_decisions_total": sum(r["wrong_decisions"] for r in rows),
        }
    return {"per_world": per_world, "summary": summary}


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dir", required=True)
    p.add_argument("--json", action="store_true", help="emit raw JSON")
    args = p.parse_args(argv)
    result = aggregate(Path(args.dir).resolve())

    if args.json:
        print(json.dumps(result, indent=2))
        return

    print("Per-world results:")
    print(f"  {'world':28} {'cond':7} {'runs':>5} {'correct':>8} {'wrong':>6}")
    for r in result["per_world"]:
        print(f"  {r['world']:28} {r['condition'] or '?':7} {r['runs_used']:>5} "
              f"{str(r['all_correct']):>8} {r['wrong_decisions']:>6}")
    print("\nBy condition:")
    print(f"  {'cond':7} {'n':>3} {'correct':>8} {'rate':>6} {'mean_runs*':>11} {'wrong':>6}")
    for cond in ("naive", "guided"):
        s = result["summary"].get(cond, {})
        if not s:
            continue
        print(f"  {cond:7} {s['n']:>3} {s['correct']:>8} "
              f"{str(s['correct_rate']):>6} {str(s['mean_runs_when_correct']):>11} "
              f"{s['wrong_decisions_total']:>6}")
    print("\n  * mean_runs = mean runs-to-decision among worlds decided CORRECTLY (lower is better).")


if __name__ == "__main__":
    sys.exit(main())
