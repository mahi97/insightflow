"""Typed errors for InsightFlow.

Every error carries a human-readable message. The CLI catches
:class:`InsightFlowError` and prints the message without a traceback, so error
text is part of the user interface and should be actionable.
"""

from __future__ import annotations


class InsightFlowError(Exception):
    """Base class for all InsightFlow errors."""


class ConfigError(InsightFlowError):
    """A configuration file is missing, malformed, or semantically invalid."""


class ValidationError(InsightFlowError):
    """Validation of configs found one or more problems.

    Carries a list of individual issue strings so the CLI can render them.
    """

    def __init__(self, issues: list[str]):
        self.issues = issues
        joined = "\n  - ".join(issues)
        super().__init__(f"Configuration is invalid:\n  - {joined}")


class LedgerError(InsightFlowError):
    """The ledger could not be read or written."""


class NotInitializedError(InsightFlowError):
    """The project has not been initialized yet.

    Tells the user exactly which command to run.
    """

    def __init__(self, project_dir: str):
        super().__init__(
            f"No InsightFlow project found in '{project_dir}'.\n"
            "Run `uv run insightflow init` to create one, "
            "or `uv run insightflow demo --force` to generate a toy project."
        )


class WandbImportError(InsightFlowError):
    """Importing runs from Weights & Biases failed.

    Used for missing dependency, missing login, missing project, or missing
    metric. The message should tell the user how to fix it.
    """


class SchedulerError(InsightFlowError):
    """The scheduler could not produce a plan."""
