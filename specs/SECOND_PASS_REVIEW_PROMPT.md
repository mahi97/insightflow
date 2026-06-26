# Second-Pass Review Prompt for Claude Code

You have built InsightFlow. Now act as a strict maintainer and reviewer.

Review the repository for:

1. Stub implementations.
2. Oversold README claims.
3. CLI commands that do not really work.
4. Scheduler logic that is too shallow.
5. Tests that pass without checking meaningful behavior.
6. W&B importer that cannot be used or tested.
7. Broken uv workflows.
8. Missing error messages.
9. Missing documentation.
10. Agent instructions that let Claude hallucinate scheduler state.

Then improve the project until it satisfies these standards:

- A user can run the demo and get a meaningful plan.
- The scheduler clearly distinguishes broad exploration from extra seeds.
- The tests would fail if the scheduler became a trivial cost sorter.
- W&B importer has mocked tests.
- README honestly separates built features from future roadmap.
- The project is ready for a public v0.1 GitHub release.

Run the full acceptance suite again and report results.
