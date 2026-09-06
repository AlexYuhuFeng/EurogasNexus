# Commercial UAT Plan — CR-13

Status: controlling test plan for the internal GA release-candidate decision.
Repository truth wins; this plan measures the product, it does not add
features.

## 1. Personas

| Persona | Primary concerns | Mapped surface |
| --- | --- | --- |
| A — Market trader | price, spread, infrastructure, capacity, route economics, opportunities, speed | Market / Network / Scenario |
| B — Portfolio/commercial analyst | resources, availability, terms, routes, scenarios, optimizer, attribution | Portfolio / Decision Center |
| C — Strategy/quant analyst | definition, reproducibility, backtest, assumptions, comparison, shadow | Strategy Lab |
| D — Reviewer/manager | evidence, alternatives, provenance, risk, assumptions, decision record | Review |
| E — Data/platform operator | sources, freshness, failures, certification, entitlement, runtime, release state | Sources / Runtime / Settings |

## 2. Test environment

- Backend: PostgreSQL 16 scratch `eurogas_nexus_uat`, head
  `0030_reliability_indexes`, development profile.
- Fixture: `scripts/uat/seed_uat_fixture.py` (60 days of clearly simulated
  market/FX observations, gated to development/test with explicit
  acknowledgement). Public ECB ingestion is used for current FX only.
- Frontend: Vite production build served through the normal `/api` boundary.
- Viewport: 1440×900 baseline; core screens re-checked at 1920×1080.
- Browser: Chromium headless for automated workflows; manual review remains
  required for final visual sign-off.

## 3. Approved UAT data

- `*_Sim` source systems are the only synthetic market evidence and remain
  clearly labelled in source/freshness columns.
- `preview-portfolio-contract-ttf-pool-2025` is the only portfolio resource;
  its name marks it as preview data.
- No real licensed prices, counterparty terms, credentials, or proprietary
  strategies are placed in fixtures.
- `seed_uat_fixture.py` refuses to run in trial/release and requires
  `EUROGAS_NEXUS_UAT_FIXTURE_ALLOWED=1`.

## 4. Golden Workflows

A. Market investigation → Scenario
B. Portfolio → Route → Optimize → Review
C. Strategy Design → Backtest → Compare
D. Backtest → Shadow
E. Decision review
F. Data/operations failure
G. Access/entitlement roles
H. Desktop first-run

## 5. Acceptance criteria per workflow

A professional user who did not build the product can complete the workflow
and answer: what, when (gas day/product), from which source, how current,
which assumptions, which constraints, which calculation, indicative or not,
what next, research vs current state, blocked vs unavailable, and what needs
human review. Anything requiring source code or developer assistance is a
defect.

## 6. Measurement methodology

For each automated/manual run record:

- TASK SUCCESS: PASS / PARTIAL / FAIL
- TIME TO COMPLETE
- USER INTERACTIONS (where meaningful)
- ERROR COUNT
- BACKTRACK COUNT
- CONTEXT-LOSS COUNT
- HELP REQUIRED
- TRUST/CONFIDENCE ISSUE (qualitative)

No arbitrary commercial threshold is imposed before the baseline. CR-13
baseline is the local automated run; deployment owner supplies real-user
metrics for formal sign-off.

## 7. Defect classification

- P0: cannot safely complete a critical workflow; data/correctness/security
  failure.
- P1: critical workflow materially confusing/broken; high risk of wrong
  interpretation.
- P2: significant friction, inconsistency, discoverability, or visual defect.
- P3: minor polish.

Internal GA RC requires zero P0, zero P1, and an explicit reviewed P2 list.

## 8. Accessibility validation

Axe-core automated audit across every workspace plus manual keyboard
inspection of Market, Strategy, and Review. Serious/critical findings are
P1/P0. Automated PASS alone is not sufficient.

## 9. Bilingual validation

EN/zh-CN key parity, no fallback to English, terminology consistency for the
professional dictionary, and layout at translated lengths.

## 10. AI/Copilot validation

Repository-native eval corpus in `tests/evals/` grades factual correctness,
numerical consistency, citation coverage, entitlement, uncertainty, prompt
injection, and the no-execution boundary. Critical numerical/entitlement cases
must be 100% correct. Live DeepSeek grading remains PENDING_EXTERNAL until a
credentialed test environment exists.

## 11. Release-candidate exit criteria

See `docs/uat/RC_ACCEPTANCE_REPORT.md`. Internal GA RC is not actual GA; all
external gates remain visible.
