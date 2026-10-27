# CI review regression acceptance (CI-REVIEW-REGRESSIONS)

CI run `40549644282` on `09e8ac9` failed three review-surface checks (4204 passed,
90 skipped). The causes below are test/contract gaps around correctly added runtime
behaviour, not product regressions.

## Causes and corrections

1. **Browser probe contract expected the pre-review surface set.**
   After `09e8ac9` the sweep correctly declares a review read-to-render group
   (`/api/projections/review-context`, `data.slices.decisions`, `decision_id`).
   `tests/contract/test_browser_probe_paths.py` still expected exactly contracts,
   glossary, orders and sources, and its workspace-component map had no `review`
   entry, so the record-id test raised `KeyError: 'review'`.
   The expected set is now the full six groups, review is in the component map,
   and dedicated assertions bind the probe to the actual ReviewWorkspace markup
   (`data-record="review-decision"`, `data-record-id={row.decision_id}`,
   `data-empty-state="review-decisions"`, `slice(0, 12)`) and to the
   `review_context.py` decisions slice fed by `list_review_decisions`. The
   portfolio slice check is scoped to orders; the review slice is checked against
   the review projection's declared slices. No exemption was added and no check
   was removed.

2. **Review-pack confirmation fixture used the wrong principal.**
   `/api/review/decisions` resolves the target through the authenticated principal
   (`can_read_review_target`), and `/api/agent/runs/{id}/replay` requires a named
   active identity. The test created the pack directly under `analyst-1` but let
   the TestClient resolve to the deployment-token compatibility principal
   (`service:public-api`), so the foreign target was correctly refused with 404.
   The fixture now seeds the same named active `analyst-1` identity and bearer key,
   presents the deployment token for the public-auth gate plus that identity key,
   and records the owner as actor while the body's `trader-a` claim is asserted to
   be ignored. The expected status remains 200; no route, role, grant or
   authorization rule was widened.

## Changed files

- `tests/contract/test_browser_probe_paths.py`
- `tests/integration/test_agent_orchestrator.py`
- `docs/engineering/CI_REVIEW_REGRESSION_ACCEPTANCE.md`

No agent/review application module required a change. The decision repository,
review pack, data platform, native workflow, economics scripts, permissions and
database state were not modified.

## Verification status

The implementing session could not run pytest: the known harness temporary-lock
ACL failure blocked shell/ripgrep execution before tests started. Results here are
therefore from static inspection, not a claimed pass. Root independently runs:

```text
python -m pytest tests/contract/test_browser_probe_paths.py -q
python -m pytest tests/integration/test_agent_orchestrator.py -q
python -m pytest -q
```

## Remaining limits

- The integration fixture uses its isolated SQLite database; it does not prove a
  live PostgreSQL or browser workflow.
- The contract checks the harness and component declarations, not a browser run.
- The browser harness's existing actual-projection review comparison is unchanged;
  it still needs the seeded browser/API stack for execution evidence.
- Full CI success is claimed only after root runs the focused and full checks.

## Independent root verification

2026-10-28: the focused browser probe contracts and agent orchestrator integration
selection passed **25 tests**; Ruff passed. Full-suite and fresh remote CI results
remain separate evidence and are not inferred from this selection.
