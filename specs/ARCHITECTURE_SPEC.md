# InsightFlow Architecture Spec

## Architecture principle

The AI agent is the interface. The CLI and ledger are the source of truth.

```text
Researcher
  -> Claude Code
    -> insightflow CLI
      -> local ledger + configs + scheduler
        -> reports + suggested queue
```

## V0.1 components

### Config layer

- YAML files describe claims, experiments, resources, and policy.
- Validation should catch missing IDs, bad claim links, impossible costs, and duplicate experiments.

### Ledger layer

- Stores imported results, simulated results, plans, and decision logs.
- SQLite preferred.
- Reports are regenerated from ledger state.

### Scheduler layer

- Takes current state.
- Scores available actions.
- Produces a plan.
- Explains each recommendation.

### Simulator layer

- Creates controlled fake projects.
- Lets us test scheduling behavior without a real project.

### Import layer

- W&B importer.
- Later MLflow/CSV can be added.

### Agent layer

- `CLAUDE.md` and prompts tell Claude to call the CLI, not invent state.

## Future architecture

V0.2:

- MCP server
- FastAPI server
- dashboard
- Slurm/Ray launchers
- better Bayesian scoring
- real partial-run monitoring

V0.3:

- multi-user lab mode
- live W&B monitoring
- notification hooks
- project templates
- plugin system for custom scorers
