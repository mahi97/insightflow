# Prompt: Review a generated plan

Use this to critically review an InsightFlow plan before approving compute.

---

Review the current InsightFlow plan as a skeptical senior researcher. Do not
trust it blindly — check that it actually optimizes time-to-insight.

1. Run `uv run insightflow plan` and `uv run insightflow explain --plan <id>`.
2. For each item in the **immediate queue**, check:
   - Does it point to a real claim and a real decision? What would the result
     change?
   - Is it the cheapest way to get that decision value (proxy vs full run)?
   - Is it breadth where breadth is needed, or premature replication?
   - If it's a baseline, would it genuinely de-risk a reviewer attack?
3. Sanity-check the trade-offs the scheduler claims:
   - Is a postponed extra seed really low-value, or is variance/borderline-ness
     being underweighted?
   - Is an avoided run truly redundant?
4. Stress-test the **claim-confidence table**: are any claims marked `supported`
   on thin breadth? Is "generality unverified" being surfaced where it should?
   (Remember: claim confidence is a heuristic, not a calibrated posterior.)
5. Flag anything missing: a dangerous baseline not scheduled, a dependency that
   should run first, a budget overrun in the warnings.

Output: a short verdict (approve / approve-with-changes / revise), the specific
changes you'd make (and which `policy.yaml` weights or `claims.yaml` fields to
adjust), and any run you would NOT spend compute on yet.
