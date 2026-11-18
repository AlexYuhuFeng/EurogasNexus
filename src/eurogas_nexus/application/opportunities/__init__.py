"""The opportunity engine's application service (commercial design basis 2, J.2).

- :mod:`.settings`: the organisation's thresholds (decision L5), audited.
- :mod:`.service`: one evaluation run: snapshot, every registered evaluator, controls, the
  store (dedupe, persistence, hysteresis, versions, expiry), the run record.
- :mod:`.listing`: what one caller may see: book scope, entitlement, own dismissals; lanes,
  ranking, groups, cursors and the readiness checklist.
- :mod:`.actions`: dismiss, restore, follow, open as a decision case, statistics.
- :mod:`.schedule`: on-demand evaluation now; the job-runner trigger and the outbox
  subscription seams as interfaces.
"""
