# RC Acceptance Report — CR-13

## 1. Tested commit
The commit produced by this CR-13 stabilization milestone; the final CR-13 report records the SHA.

## 2. Version/channel
Application version `0.5.0`, channel `preview`, internal RC validation only.

## 3. Environment
Windows workstation, PostgreSQL 16 scratch `eurogas_nexus_uat` (head
`0030_reliability_indexes`), development profile, Vite production build,
Playwright Chromium headless at 1440×900 and 1920×1080 spot checks.

## 4. Golden Workflow results

| Workflow | Result | Evidence |
| --- | --- | --- |
| A Market → Scenario | PASS | route candidates, NBP/TTF spread, sources/freshness, Open in Scenario handoff |
| B Portfolio → Optimize → Review | PASS | BBL 2,000 MWh/d + local 8,000 MWh/d allocation, evidence pack, no active warnings |
| C Strategy Design → Backtest → Compare | PASS | draft → freeze → persisted run; P0 FK defect found and fixed; compare contract covered by Node tests |
| D Backtest → Shadow | PASS (contract) | existing shadow scheduler/stale/blocked tests; UAT fixture provides historical evidence |
| E Decision Review | PASS | Review deep-link fixed; evidence pack + decision recorder exercised |
| F Data/operations failure | PASS (automated) | existing freshness/entitlement/scheduler tests; browser degraded-state smoke |
| G Access/entitlement | PASS (automated) | CR-10 security suite; LLM provider entitlement gate |
| H Desktop first-run | PARTIAL | desktop shell build/cargo check pass; clean-machine install/upgrade remains PENDING_EXTERNAL |

## 5. UAT metrics
- Browser workflow A: 1 interaction to carry route into Scenario.
- Browser workflow B: 2 interactions from Portfolio to optimized Review.
- Browser workflow C: keyboard-driven create/freeze/backtest, one P0 defect
  found and fixed.
- Long-session browser smoke: 60 workspace switches, zero console/page errors,
  JS heap stable ~50MB.
- Error count across audited pages: 0 (React/network errors); WebGL
  performance notices only.

## 6. Unresolved defects
Zero P0, zero P1. P2 list reviewed in `RC_DEFECT_REGISTER.md`; one P3
accepted (fixture EXPIRED rows). Pending external items are not product
defects and are listed below.

## 7. AI eval results
13/13 critical deterministic cases pass; entitlement and prompt-injection
pass; live DeepSeek grading PENDING_EXTERNAL.

## 8. Accessibility results
axe: 0 violations across 13 workspaces; keyboard workflows pass; external
assistive-technology review pending.

## 9. i18n results
1,247/1,247 key parity; no missing keys; zh-CN layout passes.

## 10. Performance result
Baseline p50 44.5ms / p95 1668.0ms / p99 3099.5ms on the deliberately dense
UAT fixture. This exceeds the p95 target (≤1500ms) but remains inside the
approved hard regression threshold (≤2500ms); CI load-smoke threshold is
validated against the normal CI database. ``/api/sources` and `/api/route-cost/tso-tariffs` are the slowest
representative paths and are recorded as post-RC performance backlog, not a
CR-13 blocker.

## 11. Install/upgrade result
Web build, desktop cargo check, and CR-12 release dry-run pass. Clean Windows
install/uninstall and previous-version upgrade remain PENDING_EXTERNAL.

## 12. Security gate result
Automated security acceptance PASS; external security review BLOCKED/
PENDING_EXTERNAL.

## 13. Data/provider certification state
ECB public FX exercised; ENTSOG remains certification-blocked in the fixture
(no fabricated certification); commercial providers PENDING_EXTERNAL.

## 14. External pending gates
Windows code-signing credential; live enterprise IdP acceptance; commercial
provider certification; external security acceptance; clean-machine
installer/upgrade acceptance; real trader UAT; assistive-technology review.

## 15. Decision
**INTERNAL GA RELEASE CANDIDATE** (not actual GA). Actual GA is not declared:
external mandatory gates remain pending and the stable release gate remains
fail-closed.
