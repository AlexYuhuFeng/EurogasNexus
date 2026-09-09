# UI Debt Register

Status: **active work queue; not whole-product acceptance**

This register consolidates the actionable queue from the [post-CR15 UI
audit](POST_CR15_UI_AUDIT.md) and [component census](COMPONENT_CENSUS.md). It
does not duplicate their capture narrative or source inventory. The audit
contains evidence from multiple refs; the closure context is source-audit
baseline `9a84f5e`, latest functional ref `ba26fe2`, and the current candidate
checkpoint. No future commit SHA is implied. Functional closure does not close
separate layout, visual, or acceptance debt.

## Classification rules

- `P1 confirmed` requires a reproduced product behavior that violates an
  accepted in-scope requirement.
- `P1 candidate` means the observed behavior needs current interaction or
  result confirmation before severity is assigned. Wrong or confusing
  Scenario scope belongs here until confirmed.
- `P2` is triage priority, not user acceptance. No P2 item in this register is
  marked accepted.
- `Evidence gap` and `Required implementation` are not runtime severities.
  Missing fixtures, reruns, screenshots, or external gates MUST NOT be
  upgraded to P1 by themselves.
- CR14 and CR15 required UI workflows remain required implementation scope;
  they are not deferred or accepted as thin UI merely because backend routes
  exist.

## Closed functional fixes

| ID | Screen / workflow | Severity | Description | Reason deferred | Recommended solution |
| --- | --- | --- | --- | --- | --- |
| CLOSED-NAV-001 | Optimize -> Review; Decision Center; Strategy Backtest -> Decision -> Strategy | Closed functional; layout debt open | URL, tab, heading, content, Back/Forward, and gas-day handoffs were functionally corrected. | Functional closure is evidenced by the audit's 61 Web tests, build, and Edge assertions at `3dbee3a`; loading/empty captures do not close visual acceptance. | Preserve the route contract while completing whole-product shell, overflow, and populated-state review. |
| CLOSED-ROUTE-001 | Portfolio Overview, Routes, Scenario | Closed functional; warning presentation debt open | Route feasibility and resource-pool warning behavior were corrected, including explicit UNKNOWN and deduplicated option warnings. | Audit evidence records 58 Web tests, build, readiness, and fixed Portfolio captures at `192cb4a`; this does not certify live market data or all warning surfaces. | Keep server-derived feasibility and warning identity; converge warning placement, units, alignment, and cross-workspace aggregation separately. |
| CLOSED-RESOURCE-001 | Portfolio resource selection, Resources/Library, contract draft | Closed functional; layout debt open | Selected resource versus editable draft identity, persisted loading, unknown status, and save guarding were corrected. | `9a84f5e` evidence records 64 Web tests, build, paired EN/CN labels, and `ux01-resource-missing-1440.png`; visual density and clipped/layout issues remain separate. | Preserve the functional identity boundary and migrate the surrounding resource panels, controls, and empty states to the accepted layout contract. |

## Active product debt

| ID | Screen / workflow | Severity | Description | Reason deferred | Recommended solution |
| --- | --- | --- | --- | --- | --- |
| UX01-001 | Global shell, Network and all workspaces | Closed scoped shell overlap; broader UI debt open | Parent reviewed `ux01-shell-endpoint-banner-1440.png`, `ux01-shell-endpoint-banner-1920.png`, and `ux01-shell-endpoint-banner-1100.png`; shell rows and context-banner content do not overlap in those three required viewports. | Closure is limited to the structural overlap correction. UI/token, bilingual, native, populated-state, and whole-product acceptance remain open. | Preserve the normal-flow shell rows; separately review the broader Constitution/token migration, content density, i18n, native, and populated states. |
| UX01-TOKEN-001 | Shared shell/header; Market (`market`), Portfolio, Decision | Scoped foundation adopted; broader debt open | Parent reviewed `ux01-token-fresh-1440.png`, `ux01-token-fresh-cn-1440.png`, `ux01-marketcockpit-cn-1440.png`, `ux01-portfolio-cn-1440.png`, and `ux01-decision-optimize-cn-1440.png`. The single H1 correctly identifies the workspace/task. Reviewed values are 4px primary tabs/buttons/header select/status, 32px controls, and 6px banner. | Only the shell-token foundation is adopted. Broad panel styles were reverted; legacy tokens, headings, spacing, raw-code treatment, density, normal-runtime behavior, and full international QA remain open. Parent verified `npm --prefix clients/web test` (`90 passed, 0 failed`) and `npm --prefix clients/web run build` (exit 0; TypeScript + Vite, 135 modules, 1.29s; existing dynamic-import warning). | Preserve the shared H1/header and shell-token foundation; complete the remaining token migration and bounded EN/CN, populated-state, normal-runtime, keyboard/focus, and viewport review before broader acceptance. |
| UX01-002 | Network offline/degraded error state | P1 confirmed; content debt open | The revised banner is visible without overlap, but real degraded evidence included a 12-second market/spreads `503` and other market timeouts, listing five affected endpoints. Raw endpoint labels/codes and bounded retry/content treatment remain unresolved. | The three banner captures prove layout participation only; they do not accept error semantics, all endpoint classes, or recovery behavior. | Keep one bounded structured error surface with a useful summary, five-endpoint detail when applicable, safe codes, retry behavior, and normal layout participation. |
| UX01-SCENARIO-001 | Portfolio -> Optimize/Review -> Scenario | Closed functional - wrong-route association only; browser evidence open | Parent visually reviewed `output/playwright/ux01-scenario-second-route-1440.png` for `public-route-ttf-local`: source resource-pool allocation sale `27.05`, resource volume `8000`, cost `n/a`; Kant-matched response `gross_sale=27.0472`, `totalcost=25.0219`, `allocated=8000`, with no recommendation response. The candidate helper matches carried `route_id` and explicit pool `option_id`/resource fallback. | Closure is limited to the source association defect. The `routeRecommendation` browser fixture is absent; the parent independently reports `npm --prefix clients/web test`: `73 passed, 0 failed`, including explicit default and ambiguous-pool cases. No backend/full-acceptance suite, degraded-state, or broader Scenario/layout acceptance is claimed. | Preserve the helper and closed navigation contract. Add the browser fixture later and verify selected-route label/economics against the exact response; do not reopen this specific functional closure for unrelated layout debt. |
| UX01-EXPOSURE-001 | Portfolio -> Exposure | P1 candidate - confirm semantics | `GBP 0` summary metrics coexist with unavailable placeholder rows, which may read as measured zero rather than missing evidence. | The capture does not prove whether the zero is a valid result or a display defect. | Preserve explicit Unknown/Missing semantics and lineage; classify P1 only if a reproduced response is rendered as a false zero. |
| UX01-WARN-001 | Decision/Optimize/Portfolio warning surfaces | P2 candidate - confirm aggregation | Warning presence and scope differ between Overview, Routes, and Optimize/Review observations; affected route/option context may be lost. | Route warning logic was functionally corrected, but cross-workspace aggregation and current evidence are not complete. | Define one server-result-derived warning aggregation view with affected object, severity, source, freshness, and time basis; do not hide or duplicate warnings. |
| UX01-003 | Network candidate results | P2 | "Executable spread candidates" conflicts with the decision-support/no-execution boundary. | Confirmed audit wording issue; calculation semantics must remain unchanged. | Replace EN/CN labels with candidate/decision-support language and retain human-review boundaries. |
| UX01-004 | Network resource rail; Portfolio panels; shared surfaces | P2 | Repeated gas day/product context, deeply framed panels, oversized headings, and explanatory prose reduce analytical density. | Functional fixes are closed; layout migration and visual review are separate work. | Apply one global context owner, accepted type/spacing/radius tokens, compact panels, and evidence adjacent to the affected result. |
| STRATEGY-EMPTY-001 | Strategy Lab -> Compare | P2 | An empty registry reports `COMPARABLE`; no comparison result or chart can be accepted. | The audit confirms the misleading state, but no strategy run fixture may be invented. | Show an explicit empty/not-ready state with the required next action; render `COMPARABLE` only when comparable runs exist. |
| AGENT-STATE-001 | Agent Research -> Agent Runs -> Observable Replay | P2 | Raw blocker codes omit affected-series context; objective visibility, timestamp basis, clipped model text, and nested framing are inconsistent. | The captured run is a blocked-data path with zero tool invocations; successful findings/review-pack behavior remains unverified. | Map codes to human-readable affected-series messages, show objective and local/UTC basis, preserve lineage and human gates, and keep raw codes available as bounded technical detail. |
| DATA-EVIDENCE-001 | System Sources/Runtime; Market/Capacity; Glossary; Review/Strategy | P2 candidate - evidence-led | Freshness, time basis, provenance, verified/indicative status, and restricted-state presentation vary by surface; glossary date controls lack visible timezone basis. | Source/runtime captures include stale or blocked providers and do not establish live pricing or whole-product acceptance. | Use shared evidence/status contracts with visible source, freshness (`Fresh`/`Late`/`Stale`/`Missing`), time basis, lineage, rights, and simulation labels. |
| TABS-I18N-001 | System tabs; local workspace tabs; EN/CN workflows | P2 candidate - coverage-led | Native-looking System tabs differ from styled local tabs; census records local tab groups that may omit shared keyboard semantics; bilingual parity remains unverified. | Source census and partial captures identify drift but do not prove every tab or locale failure. | Migrate eligible groups to `WorkspaceTabs`, preserve specialist semantics, run keyboard/focus and EN/CN parity checks, and record exact failures rather than infer them. |

## Required implementation scope

| ID | Screen / workflow | Severity | Description | Reason deferred | Recommended solution |
| --- | --- | --- | --- | --- | --- |
| CR14-UI-001 | Research Data -> datasets/features/targets -> dataset/artifact detail | Required implementation | The observed catalog does not expose required dataset detail, build/validate, quality, or export interactions. | Backend routes exist, but the UX01 contract requires the endpoint-to-screen workflow; no accepted thin catalog is permitted. | Expose existing catalog selection, snapshot detail, artifact operations, lineage, rights, freshness, calendar/version, and exact export result without adding domain models. |
| CR15-UI-001 | Agent Research -> governed research -> Review Pack -> Replay | Required implementation | The observed surface does not establish the complete plan -> findings -> StrategyIR -> validation -> challenge -> review-pack -> confirmation/replay path. | Blocked-data evidence and replay summary are not the required successful governed artifact workflow; backend capability does not waive the UI requirement. | Render existing artifacts and human gates with operation IDs, fixture IDs, lineage, rights, replay identity, and no hidden chain-of-thought or execution semantics. |

## Acceptance evidence gaps

| ID | Screen / workflow | Severity | Description | Reason deferred | Recommended solution |
| --- | --- | --- | --- | --- | --- |
| EVID-DESKTOP-001 | Native WebView/Tauri desktop | Evidence gap | A native build at clean `9a84f5e` exists: 9,142,272 bytes with parent-reverified SHA-256 `124A148C6954F7536159F7DFBE413216C7E83F4A37EA203FBF831CCA6EDF41BC`. Startup/render evidence exists, but it is a baseline only and does not prove native interaction. | The older executable was correctly rejected as stale; rebuilding is not the next action. Native launch interaction, accessibility, and full page walkthrough against the 9a84f5e build remain pending. | Inspect the existing 9a84f5e artifact and record native screenshots, accessibility tree, navigation, stale/degraded states, and package identity; do not infer behavior from compilation or startup alone. |
| EVID-SUITE-001 | Whole-product Web and desktop acceptance | Evidence gap | Pending coverage includes browser/visual 1440x900, 1920x1080 and narrow desktop, axe/accessibility, EN/CN, keyboard/focus, long-session, populated research/agent workflows, rights negatives, and current-ref desktop checks. Parent verified `npm --prefix clients/web test` (`90 passed, 0 failed`) and `npm --prefix clients/web run build` (exit 0; TypeScript + Vite, 135 modules, 1.29s; existing dynamic-import warning). | These verified commands still do not constitute a full-suite, full-auth, entitlement, or whole-product acceptance pass. | Parent acceptance run records exact commands, SHA, environment, fixture/operation IDs, screenshots, skips, and failures. Do not convert missing evidence into P1 or PASS. |
| EVID-FIXTURE-001 | Research, Agent, Market, Portfolio, Review/export | Evidence gap | Required fixtures for Unknown/Missing/zero-exposure, stale/fresh sources, restricted rights, simulation, MCP denial, replay, and export leakage are not all identified or rerun here. | No fixtures or pass claims are invented by this register. | Use existing labelled fixtures where available; record actual fixture IDs and exact results, and fail closed on missing rights/evidence. |
| RELIABILITY-READ-001 | Startup, retry, identity and user-triggered follow-up reads | Coverage gap | Parent verified `npm --prefix clients/web test` (`90 passed, 0 failed`) and `npm --prefix clients/web run build` (exit 0; TypeScript + Vite, 135 modules, 1.29s; existing dynamic-import warning). Revised startup/retry `/me` generation, auth-denial, bounded lane, sign-in, source-failure, and cross-lane paths are recorded as implementation evidence; user-triggered follow-up read guards remain incomplete. | Verified tests/build do not establish full-auth or entitlement acceptance; full-suite and user-triggered follow-up coverage remain open. | Guard remaining follow-up readbacks with the same identity/generation contract, then record exact rerun results. |

## References and ownership

- [Post-CR15 UI Audit](POST_CR15_UI_AUDIT.md) owns capture narrative and
  runtime evidence; this file owns prioritization and disposition.
- [Component Census](COMPONENT_CENSUS.md) owns source counts and primitive
  inventory; this file turns repeated gaps into work items.
- [CR1-15 Regression Matrix](CR1_15_REGRESSION_MATRIX.md) owns capability-level
  implementation/verification status.
- This register contains no source edits, fixture definitions, test results,
  visual pass claims, or P2 acceptance decisions. The PostgreSQL ordering-index
  proposal remains read-only and unapplied.
