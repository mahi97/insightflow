"""InsightFlow command-line interface.

The CLI is the source of truth's front door: every command reads or writes the
ledger and configs, never an in-memory guess. Human-readable Markdown is the
default output; ``--format json`` is available for agents and scripts.

Project location resolves in this order: ``--project-dir`` > ``$INSIGHTFLOW_HOME``
> current working directory. There are no hardcoded absolute paths.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import typer

from . import __version__
from .config import (
    load_claims,
    load_experiments,
    validate_configs,
    write_default_configs,
)
from .demo import setup_demo
from .errors import InsightFlowError
from .ledger import Ledger
from .reports import (
    render_benchmark_md,
    render_claim_confidence_md,
    render_plan_md,
    render_scenarios_md,
    render_state_md,
    write_report,
)
from .scheduler import build_plan
from .schemas import RunResult, RunSource, RunStatus
from .scoring import compute_claim_confidence
from .utils import now_iso, stable_hash

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="InsightFlow - adaptive experiment scheduler for ML research (time-to-insight).",
)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _project_dir(project_dir: str | None) -> Path:
    if project_dir:
        return Path(project_dir).resolve()
    env = os.environ.get("INSIGHTFLOW_HOME")
    if env:
        return Path(env).resolve()
    return Path.cwd()


def _ledger(project_dir: str | None, require_init: bool = True) -> Ledger:
    ledger = Ledger(_project_dir(project_dir))
    if require_init and not ledger.is_initialized():
        raise InsightFlowError(
            f"No InsightFlow project in '{ledger.project_dir}'. "
            "Run `uv run insightflow init` or `uv run insightflow demo --force` first."
        )
    return ledger


def _fail(message: str) -> None:
    typer.secho(message, fg=typer.colors.RED, err=True)
    raise typer.Exit(code=1)


def _echo_json(obj: object) -> None:
    typer.echo(json.dumps(obj, indent=2, default=str))


ProjectDirOpt = typer.Option(None, "--project-dir", "-C", help="Project directory.")
FormatOpt = typer.Option("md", "--format", "-f", help="Output format: md or json.")


# --------------------------------------------------------------------------- #
# Commands
# --------------------------------------------------------------------------- #
def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"insightflow {__version__}")
        raise typer.Exit()


@app.callback()
def _main(
    version: bool = typer.Option(
        False,
        "--version",
        callback=_version_callback,
        is_eager=True,
        help="Show version and exit.",
    ),
) -> None:
    """InsightFlow CLI."""


@app.command()
def init(
    project_dir: str | None = ProjectDirOpt,
    force: bool = typer.Option(False, "--force", help="Reinitialize the ledger if it exists."),
) -> None:
    """Initialize a project: write starter configs and create the ledger."""
    try:
        pdir = _project_dir(project_dir)
        written = write_default_configs(pdir, overwrite=force)
        ledger = Ledger(pdir)
        ledger.initialize(force=force)
        ledger.log_decision({"event": "init", "force": force})
    except InsightFlowError as exc:
        _fail(str(exc))
        return
    typer.secho(f"Initialized InsightFlow project at {pdir}", fg=typer.colors.GREEN)
    if written:
        typer.echo("Wrote configs:")
        for p in written:
            typer.echo(f"  - {p.relative_to(pdir)}")
    typer.echo("Next: edit configs/ then run `uv run insightflow validate` and `uv run insightflow plan`.")


@app.command()
def validate(
    project_dir: str | None = ProjectDirOpt,
    format: str = FormatOpt,
) -> None:
    """Validate configs (missing IDs, bad claim links, impossible costs, duplicates)."""
    try:
        pdir = _project_dir(project_dir)
        claims = load_claims(pdir)
        experiments = load_experiments(pdir)
        issues = validate_configs(claims, experiments)
    except InsightFlowError as exc:
        _fail(str(exc))
        return
    if format == "json":
        _echo_json(
            {
                "valid": not issues,
                "issues": issues,
                "claims": len(claims),
                "experiments": len(experiments),
            }
        )
        return
    if issues:
        typer.secho(f"Found {len(issues)} issue(s):", fg=typer.colors.RED)
        for i in issues:
            typer.echo(f"  - {i}")
        raise typer.Exit(code=1)
    typer.secho(
        f"OK: {len(claims)} claim(s), {len(experiments)} experiment(s), no issues.",
        fg=typer.colors.GREEN,
    )


@app.command()
def state(
    project_dir: str | None = ProjectDirOpt,
    format: str = FormatOpt,
) -> None:
    """Show current state: completed, pending, running, and claim summaries."""
    try:
        ledger = _ledger(project_dir)
        st = ledger.load_state()
        claim_conf = list(compute_claim_confidence(st).values())
    except InsightFlowError as exc:
        _fail(str(exc))
        return

    md = render_state_md(st, claim_conf)
    write_report(ledger.project_dir, "state.md", md)
    if format == "json":
        _echo_json(
            {
                "experiments": [
                    {"id": e.id, "status": e.status.value, "method": e.method, "dataset": e.dataset}
                    for e in st.experiments
                ],
                "results": len(st.results),
                "claim_confidence": [c.model_dump() for c in claim_conf],
            }
        )
        return
    typer.echo(md)


@app.command()
def plan(
    project_dir: str | None = ProjectDirOpt,
    format: str = FormatOpt,
) -> None:
    """Produce a ranked plan, save it, and write Markdown reports."""
    try:
        ledger = _ledger(project_dir)
        st = ledger.load_state()
        the_plan = build_plan(st)
        ledger.save_plan(the_plan)
        ledger.log_decision(
            {
                "event": "plan",
                "plan_id": the_plan.id,
                "state_hash": the_plan.state_hash,
                "queue": [a.experiment_id for a in the_plan.actions],
            }
        )
        write_report(ledger.project_dir, "plan_latest.md", render_plan_md(the_plan))
        write_report(
            ledger.project_dir,
            "claim_confidence.md",
            render_claim_confidence_md(the_plan.claim_confidence),
        )
    except InsightFlowError as exc:
        _fail(str(exc))
        return

    if format == "json":
        _echo_json(the_plan.model_dump())
        return
    typer.echo(render_plan_md(the_plan))


@app.command()
def explain(
    plan_id: str | None = typer.Option(None, "--plan", help="Plan id (default: latest)."),
    project_dir: str | None = ProjectDirOpt,
) -> None:
    """Explain a plan's scoring and the trade-offs it weighed."""
    from .explain import explain_plan

    try:
        ledger = _ledger(project_dir)
        the_plan = ledger.get_plan(plan_id) if plan_id else ledger.latest_plan()
        if the_plan is None:
            _fail(
                f"No plan found{f' with id {plan_id}' if plan_id else ''}. "
                "Run `uv run insightflow plan` first."
            )
            return
    except InsightFlowError as exc:
        _fail(str(exc))
        return
    typer.echo(explain_plan(the_plan))


@app.command()
def demo(
    project_dir: str | None = ProjectDirOpt,
    force: bool = typer.Option(False, "--force", help="Overwrite any existing demo state."),
) -> None:
    """Create a complete toy project (configs + seeded runs) ready to plan."""
    try:
        pdir = _project_dir(project_dir)
        ledger = Ledger(pdir)
        if ledger.is_initialized() and not force:
            _fail("A project already exists here. Re-run with --force to overwrite the demo.")
            return
        setup_demo(pdir, force=True)
    except InsightFlowError as exc:
        _fail(str(exc))
        return
    typer.secho(f"Demo project created at {pdir}", fg=typer.colors.GREEN)
    typer.echo("Try: `uv run insightflow state` then `uv run insightflow plan`.")


@app.command("simulate-step")
def simulate_step(
    project_dir: str | None = ProjectDirOpt,
) -> None:
    """Run the top recommended action against the simulator and record the result."""
    from .schemas import ActionType
    from .simulator import simulate_result_for

    try:
        ledger = _ledger(project_dir)
        st = ledger.load_state()
        the_plan = build_plan(st)
        runnable = next(
            (
                a
                for a in the_plan.actions
                if a.action_type in (ActionType.launch, ActionType.add_seed, ActionType.launch_baseline)
            ),
            None,
        )
        if runnable is None:
            typer.echo("No runnable action in the current plan; nothing to simulate.")
            return
        exp = st.experiment(runnable.experiment_id)
        if exp is None:
            _fail(f"Experiment '{runnable.experiment_id}' not found.")
            return
        result = simulate_result_for(exp, project_seed=len(st.results))
        ledger.add_result(result)
        ledger.log_decision(
            {"event": "simulate_step", "experiment_id": exp.id, "metrics": result.metrics}
        )
    except InsightFlowError as exc:
        _fail(str(exc))
        return
    typer.secho(f"Simulated {exp.id}: {result.metrics}", fg=typer.colors.GREEN)
    typer.echo("Re-run `uv run insightflow plan` to see the updated recommendation.")


@app.command()
def benchmark(
    steps: int = typer.Option(20, "--steps", help="Max steps per policy."),
    projects: int = typer.Option(3, "--projects", help="Number of synthetic projects."),
    all_scenarios: bool = typer.Option(
        False, "--all-scenarios", help="Run all task scenarios and quantify effectiveness gains."
    ),
    project_dir: str | None = ProjectDirOpt,
    format: str = FormatOpt,
) -> None:
    """Benchmark InsightFlow against baseline policies on synthetic projects.

    With --all-scenarios, runs every task type (breadth, expensive-branch,
    dependency-unlock, reviewer-baseline, noisy-seeds) and reports the % of runs
    and compute saved, plus a robustness summary vs the oracle.
    """
    from .benchmark import run_benchmark, run_scenarios

    try:
        pdir = _project_dir(project_dir)
        if all_scenarios:
            result = run_scenarios(steps=max(steps, 40), n_projects=projects)
            md = render_scenarios_md(result)
            write_report(pdir, "benchmark_scenarios.md", md)
        else:
            result = run_benchmark(steps=steps, n_projects=projects)
            md = render_benchmark_md(result)
            write_report(pdir, "benchmark.md", md)
    except InsightFlowError as exc:
        _fail(str(exc))
        return
    if format == "json":
        _echo_json(result)
        return
    typer.echo(md)


@app.command("import-wandb")
def import_wandb_cmd(
    entity: str = typer.Option(..., "--entity", help="W&B entity (team/user)."),
    project: str = typer.Option(..., "--project", help="W&B project name."),
    metric: str = typer.Option(..., "--metric", help="Metric to import (e.g. accuracy)."),
    limit: int = typer.Option(200, "--limit", help="Max runs to import."),
    project_dir: str | None = ProjectDirOpt,
) -> None:
    """Import runs from Weights & Biases into the ledger (degrades gracefully)."""
    from .wandb_importer import import_wandb

    try:
        ledger = _ledger(project_dir)
        experiments, results = import_wandb(entity, project, metric, limit=limit)
        n_exp, n_res = ledger.merge_imported_runs(experiments, results)
    except InsightFlowError as exc:
        _fail(str(exc))
        return
    typer.secho(
        f"Imported {n_res} run(s) and {n_exp} experiment definition(s) from {entity}/{project}.",
        fg=typer.colors.GREEN,
    )
    typer.echo("Link them to claims in configs/experiments.yaml, then run `uv run insightflow plan`.")


@app.command("log-result")
def log_result(
    experiment_id: str = typer.Option(..., "--experiment-id", help="Experiment id."),
    metric: list[str] = typer.Option(
        ..., "--metric", help="metric=value (repeatable), e.g. --metric accuracy=0.72."
    ),
    status: str = typer.Option("completed", "--status", help="Run status."),
    seed: int = typer.Option(0, "--seed", help="Seed."),
    cost: float = typer.Option(0.0, "--cost", help="Compute cost."),
    wall_time: float = typer.Option(0.0, "--wall-time", help="Wall-clock time."),
    project_dir: str | None = ProjectDirOpt,
) -> None:
    """Record a run result manually."""
    try:
        ledger = _ledger(project_dir)
        metrics: dict[str, float] = {}
        for item in metric:
            if "=" not in item:
                _fail(f"Bad --metric '{item}'. Use metric=value, e.g. accuracy=0.72.")
                return
            key, val = item.split("=", 1)
            try:
                metrics[key.strip()] = float(val)
            except ValueError:
                _fail(f"Metric value for '{key}' is not a number: '{val}'.")
                return
        try:
            run_status = RunStatus(status)
        except ValueError:
            _fail(f"Invalid status '{status}'. Use one of: {[s.value for s in RunStatus]}.")
            return
        result = RunResult(
            run_id=f"manual-{experiment_id}-{stable_hash((experiment_id, now_iso(), tuple(metric)), 8)}",
            experiment_id=experiment_id,
            seed=seed,
            metrics=metrics,
            cost=cost,
            wall_time=wall_time,
            status=run_status,
            source=RunSource.manual,
            finished_at=now_iso(),
        )
        ledger.add_result(result)
        ledger.log_decision({"event": "log_result", "experiment_id": experiment_id, "metrics": metrics})
    except InsightFlowError as exc:
        _fail(str(exc))
        return
    typer.secho(f"Recorded result for {experiment_id}: {metrics}", fg=typer.colors.GREEN)


if __name__ == "__main__":  # pragma: no cover
    app()
