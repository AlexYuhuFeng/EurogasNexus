# RC Defect Register

Status legend: OPEN / FIXED / ACCEPTED. Severity is P0/P1/P2/P3 as defined in
`COMMERCIAL_UAT_PLAN.md`. No defect is closed without verification.

| ID | Persona | Workflow | Severity | Description | Expected | Actual | Evidence | Owner/Area | Status | Fix commit | Verification |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| CR-13-DEF-001 | C | Golden C | P0 | PostgreSQL FK violation: backtest attribution rows inserted before decision events | backtest persists in PostgreSQL | POST /api/strategy-runs returned 503 `backtest_attribution_event_id_fkey` | UAT API trace, workflow-c3 | backtest persistence | FIXED | CR-13 stabilization commit | `tests/unit/test_backtest_persistence_fk.py` + UAT POST returns COMPLETED_WITH_WARNINGS |
| CR-13-DEF-002 | D | Golden E | P1 | `?workspace=review` deep link opened Scenario | review workspace | wrong task rendered | Playwright text capture | navigation model | FIXED | CR-13 stabilization commit | `goldenWorkflow.test.ts` + Playwright review capture |
| CR-13-DEF-003 | A/B/D | Golden A/B/E | P1 | Raw backend codes shown to users (`TSO_ACCESS_UNKNOWN:...`) | human-readable warning | machine code visible | Playwright text capture | shared warning labels | FIXED | CR-13 stabilization commit | Playwright Portfolio/Scenario/Review captures |
| CR-13-DEF-004 | B | Golden B | P1 | Active company TSO access was not propagated to optimizer resources | BBL route eligible | BBL route excluded with TSO_ACCESS_UNKNOWN | Playwright workflow B + API options trace | route-cost API | FIXED | CR-13 stabilization commit | Playwright workflow B allocates BBL + local |
| CR-13-DEF-005 | All | All | P1 | Heading order skipped h2; main role overridden; contrast failures across 50+ nodes | WCAG 2.2 AA-oriented structure | axe serious/critical violations on every workspace | axe-core run 1440×900 | shared UI/CSS | FIXED | CR-13 stabilization commit | axe rerun: 0 violations across 13 workspaces |
| CR-13-DEF-006 | All | All | P2 | Topbar horizontal overflow at 1440×900 | no clipped controls | `.app-header` scrollWidth > clientWidth | axe/DOM audit | topbar CSS | FIXED | CR-13 stabilization commit | axe/DOM rerun |
| CR-13-DEF-007 | All | All | P2 | Chinese UI retained English fragments for capacity and strategy labels | professional zh-CN | m
| CR-13-DEF-007 | All | All | P2 | Chinese UI retained English fragments for capacity and strategy labels | professional zh-CN | mixed-language labels | i18n audit | i18n | FIXED | CR-13 stabilization commit | i18n parity script + web tests |
| CR-13-DEF-008 | A | Golden A | P3 | Intraday feed labels three simulated opportunities as EXPIRED without current explanation | current/expired distinction visible | only EXPIRED rows in fixture | fixture/UAT data | ACCEPTED | — | fixture is current-tick-only; documented in UAT data notes |
