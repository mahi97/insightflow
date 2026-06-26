# Install InsightFlow and use it on a project

The goal: **install once, change no training code, and let your agent schedule
experiments.** You declare *claims* in YAML (not code); InsightFlow reads your
existing runs (W&B / logs) and tells the agent what to run next.

---

## 1. Install (pick one)

### A. The CLI as a global tool (no per-project setup)

```bash
# from PyPI (once published)
uv tool install insightflow
# or straight from git today
uv tool install "git+https://github.com/mahi97/insightflow"
# optional W&B import support
uv tool install "git+https://github.com/mahi97/insightflow" --with wandb
```

Now `insightflow` is on your PATH in any directory. (Plain `pip install
insightflow` / `pipx install insightflow` work too.)

### B. The Claude Code plugin (skills + guard hook + slash commands)

This is what makes it "just work" inside Claude Code — your agent gets the
scheduling skills, the expensive-run guard, and `/insightflow-*` commands
automatically, with **no prompts to paste**.

```bash
# add this repo as a plugin marketplace, then install
claude plugin marketplace add mahi97/insightflow
claude plugin install insightflow@insightflow
```

After install, in any repo the agent can use the `adaptive-experiment-scheduler`,
`define-claims`, `interpret-results`, and `writeup-from-ledger` skills, plus
`/insightflow-setup`, `/insightflow-next`, and `/insightflow-writeup`.

### Why no code changes are needed

InsightFlow never wraps or imports your training loop. It works from:
- **YAML claims/experiments** you (or the `define-claims` skill) write, and
- **results you already have** — imported from W&B, or recorded with one CLI call
  (`insightflow log-result ...`).

Your `train.py` stays exactly as it is.

---

## 2. A project you already have running

You have runs in flight or finished (say, in W&B) and want to know what to run
next without finishing the whole grid.

```bash
cd your-research-repo
insightflow init                       # creates configs/ + the ledger
```

1. **Let the agent draft your claims** (no code changes):
   in Claude Code, run `/insightflow-setup` — it reads your scripts/sweeps and
   drafts `configs/claims.yaml` + `configs/experiments.yaml`, then validates.
   (Or write them by hand — see [concepts.md](concepts.md).)

2. **Pull in the runs you already did:**
   ```bash
   uv run wandb login
   insightflow import-wandb --entity YOUR_ENTITY --project YOUR_PROJECT --metric accuracy
   ```
   Link the imported runs to your claims in `configs/experiments.yaml`, then
   `insightflow validate`.

3. **Ask what to run next:**
   ```bash
   insightflow state      # what you already know
   insightflow plan       # ranked queue + what to postpone/avoid + warnings
   ```
   or just run `/insightflow-next` in Claude Code. You get recommendations like
   "run the missing baseline on dataset X before more seeds of Y — it can decide
   claim C1," with the postponed/avoided runs and the compute they save.

4. **As runs land, replan:** record results (`insightflow log-result ...` or
   another `import-wandb`) and run `insightflow plan` again. The ledger persists
   across sessions, so the agent never loses track.

This is **advisor mode**: InsightFlow recommends, you (or your launcher) run. It
will not touch your jobs.

---

## 3. A brand-new project

Starting from an idea, before any runs exist.

```bash
mkdir my-paper && cd my-paper
insightflow init
```

1. **Turn the idea into claims** — `/insightflow-setup` (the `define-claims`
   skill) drafts `configs/claims.yaml` (what you'll assert) and
   `configs/experiments.yaml` (the runnable grid, with baselines and
   dependencies). Edit to taste; `insightflow validate`.

2. **Run the loop:**
   ```bash
   insightflow plan        # with no results yet: it points you at the most
                           # informative first runs (breadth + missing baselines)
   # ... run those experiments however you run experiments ...
   insightflow log-result --experiment-id <id> --metric accuracy=<v> --status completed
   insightflow plan        # replan; did a claim's status change?
   ```
   Stop when the claim-confidence table marks your claims `supported`/`refuted` —
   not when the grid is full.

3. **Fully autonomous?** If an agent is running the whole project end to end, see
   [agent_driven_project.md](agent_driven_project.md) and the
   `prompts/autonomous_research_loop.md` template — set `INSIGHTFLOW_GUARD=block`
   so no expensive run launches without a fresh plan.

4. **Write it up from the ledger** — `/insightflow-writeup` (the
   `writeup-from-ledger` skill) drafts the results/methods/figures using only the
   numbers in the ledger and `reports/`.

---

## 4. Try the demo first (2 minutes, no setup)

```bash
insightflow demo --force      # toy project with CIFAR-10 already run
insightflow plan              # see it recommend a new dataset over more seeds
insightflow benchmark --all-scenarios   # see the effectiveness numbers
```

See [QUICKSTART.md](../QUICKSTART.md) for the guided tour.
