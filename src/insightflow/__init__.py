"""InsightFlow: an adaptive experiment scheduler for ML research.

InsightFlow optimizes *time-to-insight* - which experiment, seed, baseline, or
ablation to run or avoid to decide research claims fastest under cost and
uncertainty. It is CLI-first and agent-native; the CLI and ledger are the
source of truth, not the agent.

Public API (stable for v0.1):

    from insightflow import Ledger, build_plan, State
    from insightflow.simulator import generate_project, run_policy
    from insightflow.benchmark import run_benchmark
"""

from __future__ import annotations

from .errors import (
    ConfigError,
    InsightFlowError,
    LedgerError,
    NotInitializedError,
    ValidationError,
    WandbImportError,
)
from .ledger import Ledger
from .scheduler import Scheduler, build_plan, compute_state_hash
from .schemas import (
    Claim,
    ClaimConfidence,
    Experiment,
    Plan,
    PlanAction,
    Policy,
    Resources,
    RunResult,
    State,
)
from .scoring import compute_claim_confidence, compute_claim_evidence

__version__ = "0.1.0"

__all__ = [
    "__version__",
    # core
    "Ledger",
    "Scheduler",
    "build_plan",
    "compute_state_hash",
    "compute_claim_confidence",
    "compute_claim_evidence",
    # schemas
    "Claim",
    "ClaimConfidence",
    "Experiment",
    "Plan",
    "PlanAction",
    "Policy",
    "Resources",
    "RunResult",
    "State",
    # errors
    "InsightFlowError",
    "ConfigError",
    "ValidationError",
    "LedgerError",
    "NotInitializedError",
    "WandbImportError",
]
