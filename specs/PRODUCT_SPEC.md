# InsightFlow Product Spec

## One-sentence description

InsightFlow tells ML researchers what evidence to buy next: which experiments, seeds, baselines, and ablations to run or avoid to minimize time-to-insight under cost and uncertainty.

## What it is

- adaptive research experiment scheduler
- claim-centric experiment planner
- seed allocation advisor
- W&B-aware run importer
- CLI-first agent-native tool
- synthetic benchmark suite for research scheduling

## What it is not

- not an AutoML system
- not a hyperparameter optimizer
- not a W&B/MLflow replacement
- not a dashboard-first product
- not an LLM-only planner

## Primary user

A researcher with many completed/running/pending ML experiments who wants to make correct research decisions faster and cheaper.

## Core user stories

1. As a researcher, I can import existing W&B runs and ask what to run next.
2. As a researcher, I can define claims and see which experiments support or threaten them.
3. As a researcher, I can avoid running all seeds blindly.
4. As a researcher, I can identify expensive runs that should wait.
5. As a researcher, I can get a Markdown report explaining the next queue.
6. As a researcher, I can use Claude Code to operate the tool naturally.

## MVP workflow

```bash
uv sync
uv run insightflow init
uv run insightflow import-wandb --entity E --project P --metric accuracy
uv run insightflow state
uv run insightflow plan
```

## Demo workflow

```bash
uv run insightflow demo --force
uv run insightflow plan
uv run insightflow benchmark --steps 5
```
