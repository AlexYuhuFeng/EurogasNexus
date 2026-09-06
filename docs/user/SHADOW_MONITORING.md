# Shadow Monitoring

Shadow monitoring repeatedly evaluates a frozen strategy against current
evidence. It produces candidates for human review, not orders.

- Start from a frozen version and an explicit baseline backtest.
- Check schedule, data prerequisites, and evaluation history.
- A normal evaluation may be COMPLETED, COMPLETED_WITH_WARNINGS, or BLOCKED.
- BLOCKED means required evidence is missing/stale; no candidate is invented.
- Restore the source and allow the next scheduled evaluation to recover.
- Inspect drift and alerts; acknowledge alerts that you have reviewed.
- Pause and resume are deliberate lifecycle actions.

No screen in this workflow is an execution screen.
