#!/usr/bin/env python3
"""PreToolUse guard: don't launch expensive training runs without a fresh plan.

InsightFlow is advisor-mode: the human (via the agent) should consult
`uv run insightflow plan` before spending real compute. This hook watches Bash
commands about to run; if a command looks like an expensive training launch
(``python train.py``, ``torchrun``, ``accelerate launch``, ``sbatch``, ...) and
there is no *recent* plan report, it asks the agent to run the planner first.

Install (in ``.claude/settings.json``):

    {
      "hooks": {
        "PreToolUse": [
          {
            "matcher": "Bash",
            "hooks": [
              {"type": "command",
               "command": "python3 .claude/hooks/guard_expensive_runs.py"}
            ]
          }
        ]
      }
    }

The hook fails open: if anything is malformed it allows the command. It is
advisory — set ``INSIGHTFLOW_GUARD=off`` to disable, ``=warn`` (default) to warn
without blocking, or ``=block`` to hard-block until a recent plan exists.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

LAUNCH_PATTERNS = (
    "python train",
    "python -m train",
    "train.py",
    "torchrun",
    "accelerate launch",
    "deepspeed",
    "sbatch",
    "srun",
    "ray submit",
    "ray job submit",
)

PLAN_REPORT = Path("reports/plan_latest.md")
PLAN_MAX_AGE_SECONDS = 30 * 60  # a plan older than this counts as stale


def _looks_expensive(command: str) -> bool:
    c = command.lower()
    return any(pat in c for pat in LAUNCH_PATTERNS)


def _recent_plan_exists() -> bool:
    if not PLAN_REPORT.exists():
        return False
    age = time.time() - PLAN_REPORT.stat().st_mtime
    return age <= PLAN_MAX_AGE_SECONDS


def main() -> int:
    mode = os.environ.get("INSIGHTFLOW_GUARD", "warn").lower()
    if mode == "off":
        return 0

    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0  # fail open

    if payload.get("tool_name") != "Bash":
        return 0
    command = (payload.get("tool_input") or {}).get("command", "")
    if not command or not _looks_expensive(command):
        return 0
    if _recent_plan_exists():
        return 0

    reason = (
        "This looks like an expensive training launch, but there is no recent "
        "InsightFlow plan (reports/plan_latest.md). Run `uv run insightflow plan` "
        "first, confirm this run is in the immediate queue (not 'postponed' or "
        "'avoided'), and show the rationale before launching. "
        "Optimize time-to-insight, not grid completion."
    )

    if mode == "block":
        # Deny via PreToolUse JSON contract; exit 2 also surfaces stderr to Claude.
        print(
            json.dumps(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "PreToolUse",
                        "permissionDecision": "deny",
                        "permissionDecisionReason": reason,
                    }
                }
            )
        )
        print(reason, file=sys.stderr)
        return 2

    # warn (default): allow, but remind the agent.
    print(reason, file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
