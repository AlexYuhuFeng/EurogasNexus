/**
 * Architecture V2 Wave 9 - canonical Inspector detail resolution tests.
 *
 * The Inspector exists so object detail lives in one place instead of a new page per
 * object kind. These tests pin what makes that safe: detail is resolved only from
 * data the surface already received, values are shown as reported rather than
 * invented, a kind this build cannot resolve says so, and a page may only hand over
 * the subject kinds its composition declares.
 */

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import {
  inspectorDetailFor,
  inspectorSubjectFor,
  marketObservationSubject,
  resolvableInspectorKinds,
  type InspectorDetailSource,
} from "../src/app/model/inspectorDetail.ts";
import { canOpenInspector } from "../src/app/experience/inspectorContract.ts";

function readWebSource(relativePath: string): string {
  return readFileSync(new URL(`../src/${relativePath}`, import.meta.url), "utf8");
}

function source(overrides: Partial<InspectorDetailSource> = {}): InspectorDetailSource {
  return {
    nodes: [],
    marketQuotes: [],
    normalizedMarkets: [],
    monitoringAlerts: [],
    intradayOpportunities: [],
    upstreamContracts: [],
    routeCandidates: [],
    resourcePoolOptions: null,
    strategyRuns: [],
    ...overrides,
  };
}

const QUOTE = {
  quote_id: "quote-1",
  source_system: "EEX",
  source_reference: "EEX:TTF:DA:2026-09-16",
  venue: "EEX",
  instrument_id: "TTF-DA",
  hub: "TTF",
  product: "day-ahead",
  delivery_start_utc: "2026-09-16T04:00:00+00:00",
  delivery_end_utc: "2026-09-17T04:00:00+00:00",
  bid_price: 31.4,
  ask_price: 31.9,
  last_price: null,
  currency: "EUR",
  unit: "EUR/MWh",
  observed_at_utc: "2026-09-16T05:58:00+00:00",
  received_at_utc: "2026-09-16T05:59:00+00:00",
  freshness: "fresh",
  quality_score: 0.94,
  simulated: false,
};

test("a market observation resolves into facts and provenance, not a fetch", () => {
  const detail = inspectorDetailFor(
    source({ marketQuotes: [QUOTE] as never }),
    { kind: "market-observation", ref: "quote-1", label: "quote-1", originPage: "market" },
  );

  assert.equal(detail.resolved, true);
  assert.equal(detail.label, "TTF · day-ahead");

  const byKey = new Map(detail.facts.map((fact) => [fact.labelKey, fact.value]));
  assert.equal(byKey.get("experience.inspector.fact.hub"), "TTF");
  assert.equal(byKey.get("experience.inspector.fact.product"), "day-ahead");
  assert.equal(byKey.get("experience.inspector.fact.bid"), "31.4");
  assert.equal(byKey.get("experience.inspector.fact.unit"), "EUR/MWh");
  assert.equal(byKey.get("experience.inspector.fact.simulated"), "false");

  // Provenance stays with the value it explains.
  assert.deepEqual(detail.evidenceRefs, ["EEX:TTF:DA:2026-09-16", "EEX"]);
});

test("a field the record does not carry is absent, never a zero", () => {
  const detail = inspectorDetailFor(
    source({ marketQuotes: [QUOTE] as never }),
    { kind: "market-observation", ref: "quote-1", label: "quote-1", originPage: "market" },
  );
  const keys = detail.facts.map((fact) => fact.labelKey);

  // `last_price` is explicitly null in the record: no fact is invented for it, and
  // an unmeasured price never renders as 0.
  assert.equal(keys.includes("experience.inspector.fact.last"), false);
  assert.equal(detail.facts.some((fact) => fact.value === "0"), false);
  assert.equal(keys.includes("experience.inspector.fact.observed_at"), true);
});

test("a timestamp is rendered as a timestamp, not as a raw ISO string", () => {
  const detail = inspectorDetailFor(
    source({ marketQuotes: [QUOTE] as never }),
    { kind: "market-observation", ref: "quote-1", label: "quote-1", originPage: "market" },
  );
  const observed = detail.facts.find(
    (fact) => fact.labelKey === "experience.inspector.fact.observed_at",
  );

  assert.ok(observed);
  assert.notEqual(observed.value, "2026-09-16T05:58:00+00:00");
  assert.match(observed.value, /2026/);
});

test("an alert, a route and a resource each resolve from their own record shape", () => {
  const alert = inspectorDetailFor(
    source({
      monitoringAlerts: [
        {
          alert_id: "alert-1",
          category: "market",
          alert_type: "stale_source",
          severity: "warning",
          status: "open",
          entity_type: "source_system",
          entity_id: "EEX",
          occurrence_count: 4,
          event_time_utc: "2026-09-16T05:00:00+00:00",
          detected_at_utc: "2026-09-16T05:01:00+00:00",
          llm_status: "skipped",
          source_refs: ["pipeline:market_quotes"],
        },
      ] as never,
    }),
    { kind: "market-observation", ref: "alert-1", label: "alert-1", originPage: "market" },
  );
  assert.equal(alert.resolved, true);
  assert.equal(alert.label, "market · stale_source");
  const alertKeys = new Map(alert.facts.map((fact) => [fact.labelKey, fact.value]));
  assert.equal(alertKeys.get("experience.inspector.fact.severity"), "warning");
  assert.equal(alertKeys.get("experience.inspector.fact.occurrences"), "4");
  assert.deepEqual(alert.evidenceRefs, ["pipeline:market_quotes"]);

  const route = inspectorDetailFor(
    source({
      routeCandidates: [
        {
          route_id: "route-1",
          route_name: "TTF to NCG",
          start_point_name: "TTF",
          target_point_name: "NCG",
          business_model: "transport",
          required_entry_point_name: "TTF",
          required_exit_point_name: "NCG",
          required_tso_access: ["GTS", "Fluxys"],
          source_systems: ["ENTSOG"],
        },
      ] as never,
    }),
    { kind: "route", ref: "route-1", label: "route-1", originPage: "network" },
  );
  assert.equal(route.resolved, true);
  assert.equal(route.label, "TTF to NCG");
  assert.deepEqual(route.evidenceRefs, ["ENTSOG", "GTS", "Fluxys"]);

  const resource = inspectorDetailFor(
    source({
      resourcePoolOptions: {
        portfolio_resources: [
          {
            resource_id: "resource-1",
            resource_name: "Gate LNG slot",
            resource_type: "LNG",
            delivery_mode: "ship",
            location_point_name: "Gate",
            available_quantity_mwh_per_day: 1200,
            contract_cost_gbp_mwh: 24.5,
            accessible_tsos: ["GTS"],
          },
        ],
      } as never,
    }),
    { kind: "resource", ref: "resource-1", label: "resource-1", originPage: "contracts" },
  );
  assert.equal(resource.resolved, true);
  assert.equal(resource.label, "Gate LNG slot");
  assert.equal(
    resource.facts.find(
      (fact) => fact.labelKey === "experience.inspector.fact.available_quantity",
    )?.value,
    "1200",
  );
});

test("a page may only hand over the subject kinds its composition declares", () => {
  // The market page declares market observations, not contracts.
  assert.equal(canOpenInspector("market-observation", "market"), true);
  assert.equal(canOpenInspector("contract", "market"), false);

  const refused = inspectorDetailFor(source(), {
    kind: "contract",
    ref: "contract-1",
    label: "contract-1",
    originPage: "market",
  });
  assert.deepEqual(refused, { resolved: false, label: null, facts: [], evidenceRefs: [] });
});

test("an unresolvable subject says so instead of looking empty", () => {
  const missingRef = inspectorDetailFor(source({ marketQuotes: [QUOTE] as never }), {
    kind: "market-observation",
    ref: "quote-does-not-exist",
    label: "quote-does-not-exist",
    originPage: "market",
  });
  assert.equal(missingRef.resolved, false);
  assert.deepEqual(missingRef.facts, []);

  // A kind with no resolver in this build is explicitly unresolved rather than
  // rendering as "this object has no detail".
  assert.equal(resolvableInspectorKinds().includes("data-product" as never), false);
  const noResolver = inspectorDetailFor(source(), {
    kind: "data-product",
    ref: "product-1",
    label: "product-1",
    originPage: "research",
  });
  assert.equal(noResolver.resolved, false);

  // No source and no subject are both safe.
  assert.equal(inspectorDetailFor(null, null).resolved, false);
  assert.equal(
    inspectorDetailFor(source(), null).resolved,
    false,
  );
});

test("a market hand-over builds a subject only when the page may inspect it", () => {
  const quote = { quote_id: "quote-1" };
  const observation = { observation_id: "obs-1" };

  assert.deepEqual(marketObservationSubject(quote, "market", "TTF"), {
    kind: "market-observation",
    ref: "quote-1",
    label: "TTF",
    originPage: "market",
  });
  assert.equal(marketObservationSubject(observation, "market", "TTF")?.ref, "obs-1");
  assert.equal(marketObservationSubject(null, "market", "TTF"), null);
  assert.equal(marketObservationSubject({}, "market", "TTF"), null);
  // The network page does not declare market observations as an inspectable subject.
  assert.equal(marketObservationSubject(quote, "network", "TTF"), null);
});

test("every hand-over goes through one composition-checked builder", () => {
  // The contracts page declares contracts and resources; the market page does not.
  assert.deepEqual(inspectorSubjectFor("contract", "contract-1", "Gate term", "contracts"), {
    kind: "contract",
    ref: "contract-1",
    label: "Gate term",
    originPage: "contracts",
  });
  assert.equal(inspectorSubjectFor("contract", "contract-1", "Gate term", "market"), null);
  assert.equal(inspectorSubjectFor("contract", "", "Gate term", "contracts"), null);
  assert.equal(inspectorSubjectFor("contract", null, "Gate term", "contracts"), null);
  assert.equal(inspectorSubjectFor("resource", "resource-1", "Gate slot", "contracts")?.kind, "resource");

  // The network page declares network-node, the market page does not.
  assert.equal(inspectorSubjectFor("network-node", "node-1", "Zeebrugge", "network")?.kind, "network-node");
  assert.equal(inspectorSubjectFor("network-node", "node-1", "Zeebrugge", "market"), null);

  // The strategy page declares strategy-version and strategy-run.
  assert.equal(
    inspectorSubjectFor("strategy-run", "run-1", "TTF carry", "strategy")?.kind,
    "strategy-run",
  );
  assert.equal(inspectorSubjectFor("strategy-run", "run-1", "TTF carry", "market"), null);

  // The contract workbench hands a saved contract over rather than growing a third
  // detail pane, and it resolves detail from data the surface already received.
  const workbench = readWebSource("components/ContractWorkbench.tsx");
  assert.match(workbench, /import \{ inspectorSubjectFor \} from "@\/app\/model\/inspectorDetail"/);
  assert.match(workbench, /const inspector = useInspectorStore\(\);/);
  assert.match(
    workbench,
    /const subject = inspectorSubjectFor\(\s*"contract",\s*saved\.contract_id,\s*saved\.contract_name,\s*"contracts",\s*\);/s,
  );
  assert.match(workbench, /if \(subject\) inspector\.open\(subject\);/);
  assert.equal(workbench.includes("fetch("), false);
});

test("the network map hands a clicked node over instead of only popup detail", () => {
  const map = readWebSource("components/GasNetworkMap.tsx");
  const workspace = readWebSource("components/NetworkWorkspace.tsx");

  // The map keeps its quick context and adds the hand-over, so it does not become a
  // second detail pane.
  assert.match(map, /onInspectNode\?: \(nodeId: string, label: string\) => void;/);
  assert.match(map, /if \(onInspectNode && nodeId\) \{/);
  assert.match(map, /inspect\.textContent = t\("map\.inspect_node"\);/);
  assert.match(map, /onInspectNode\(nodeId, nodeLabel\);/);
  // The handler is registered with the effect, so a new callback cannot be ignored.
  assert.match(map, /mapReady, onInspectNode, t, verifiedPipelineLines\]/);

  // The workspace owns the page identity, so the composition rule is applied there.
  assert.match(workspace, /import \{ inspectorSubjectFor \} from "@\/app\/model\/inspectorDetail"/);
  assert.match(workspace, /const inspector = useInspectorStore\(\);/);
  assert.match(
    workspace,
    /const subject = inspectorSubjectFor\("network-node", nodeId, label, "network"\);/,
  );
  assert.match(workspace, /onInspectNode=\{openNodeInspector\}/);

  // The map itself plans no fetch: the Inspector resolves from state already in hand.
  assert.equal(map.includes("fetch("), false);

  const en = JSON.parse(readWebSource("i18n/en.json")) as Record<string, string>;
  const zh = JSON.parse(readWebSource("i18n/zh.json")) as Record<string, string>;
  for (const key of ["map.inspect_node", "map.node_popup_source"]) {
    assert.ok(en[key]?.trim(), `en ${key}`);
    assert.ok(zh[key]?.trim(), `zh ${key}`);
    assert.notEqual(en[key], zh[key], key);
  }
});

test("the strategy backtest hands the selected run over instead of duplicating it", () => {
  const backtest = readWebSource("components/strategy/StrategyBacktestWorkspace.tsx");

  assert.match(backtest, /import \{ inspectorSubjectFor \} from "@\/app\/model\/inspectorDetail"/);
  assert.match(backtest, /const inspector = useInspectorStore\(\);/);
  assert.match(
    backtest,
    /const subject = inspectorSubjectFor\(\s*"strategy-run",\s*run\.run_id,\s*run\.strategy_name \?\? run\.run_id,\s*"strategy",\s*\);/s,
  );
  assert.match(backtest, /if \(subject\) inspector\.open\(subject\);/);
  // The surface keeps its own analysis (KPIs, charts) and fetches nothing for the detail.
  assert.match(backtest, /strategy-kpi-strip/);
  assert.equal(backtest.includes("fetch("), false);

  const en = JSON.parse(readWebSource("i18n/en.json")) as Record<string, string>;
  const zh = JSON.parse(readWebSource("i18n/zh.json")) as Record<string, string>;
  assert.ok(en["strategy_lab.inspect_run"]?.trim());
  assert.ok(zh["strategy_lab.inspect_run"]?.trim());
  assert.notEqual(en["strategy_lab.inspect_run"], zh["strategy_lab.inspect_run"]);
});

test("review evidence resolves from the review projection, including what it could not get", () => {
  const projection = {
    projection: "review-context",
    projection_version: "review-context/v1",
    as_of_utc: "2026-09-16T06:00:00+00:00",
    time_basis: { basis_id: "EU-CAM-UTC-2025" },
    active_context: {},
    review_target: {},
    slices: {
      decisions: { available: true, row_count: 1, rows: [], payload: null, freshness: { state: "FRESH" } },
      evidence: {
        available: true,
        row_count: 2,
        rows: [
          {
            entity_type: "strategy_run",
            entity_id: "run-1",
            available: true,
            resolver: "strategy_run",
            artifact: {
              run_id: "run-1",
              status: "SUCCEEDED",
              net_indicative_pnl_gbp: 12500,
              source_systems: ["ENTSOG"],
            },
            unavailable_reason: null,
            warnings: [],
          },
          {
            entity_type: "generated_report",
            entity_id: "report-1",
            available: false,
            resolver: "generated_report",
            artifact: null,
            unavailable_reason: "ENTITLEMENT_DENIED",
            warnings: ["ENTITLEMENT_DENIED"],
          },
        ],
        payload: null,
        freshness: { state: "FRESH" },
      },
      monitoring: { available: true, row_count: 0, rows: null, payload: null, freshness: { state: "FRESH" } },
    },
    warnings: [],
  } as never;

  const resolved = inspectorDetailFor(
    source({ reviewContext: projection }),
    { kind: "decision-evidence", ref: "strategy_run:run-1", label: "run-1", originPage: "review" },
  );

  assert.equal(resolved.resolved, true);
  assert.equal(resolved.label, "strategy_run: run-1");
  const byLabel = new Map(resolved.facts.map((fact) => [fact.label ?? fact.labelKey, fact.value]));
  assert.equal(byLabel.get("experience.inspector.fact.evidence_state"), "available");
  assert.equal(byLabel.get("experience.inspector.fact.evidence_resolver"), "strategy_run");
  // A resolver's artifact is presented under its own field names: inventing product copy
  // for data keys would misdescribe them.
  assert.equal(byLabel.get("status"), "SUCCEEDED");
  assert.equal(byLabel.get("net_indicative_pnl_gbp"), "12500");
  assert.equal(resolved.evidenceRefs.includes("strategy_run"), true);
  assert.equal(resolved.evidenceRefs.includes("ENTSOG"), true);

  // Evidence the backend could not resolve is still inspectable, and says why.
  const withheld = inspectorDetailFor(
    source({ reviewContext: projection }),
    {
      kind: "decision-evidence",
      ref: "generated_report:report-1",
      label: "report-1",
      originPage: "review",
    },
  );
  assert.equal(withheld.resolved, true);
  assert.equal(
    withheld.facts.find(
      (fact) => (fact.label ?? fact.labelKey) === "experience.inspector.fact.evidence_state",
    )?.value,
    "ENTITLEMENT_DENIED",
  );

  // An entity the projection does not carry is explicitly unresolved, and the ref format
  // is checked rather than guessed.
  assert.equal(
    inspectorDetailFor(source({ reviewContext: projection }), {
      kind: "decision-evidence",
      ref: "strategy_run:run-absent",
      label: "run-absent",
      originPage: "review",
    }).resolved,
    false,
  );
  assert.equal(
    inspectorDetailFor(source({ reviewContext: projection }), {
      kind: "decision-evidence",
      ref: "no-separator",
      label: "no-separator",
      originPage: "review",
    }).resolved,
    false,
  );
  assert.equal(
    inspectorDetailFor(source({ reviewContext: null }), {
      kind: "decision-evidence",
      ref: "strategy_run:run-1",
      label: "run-1",
      originPage: "review",
    }).resolved,
    false,
  );
});

test("the review surface hands its evidence over only when it was resolved", () => {
  const workspace = readWebSource("components/ReviewWorkspace.tsx");
  const decision = readWebSource("components/DecisionWorkspace.tsx");

  assert.match(workspace, /const resolved = reviewEvidenceFor\(reviewProjection, row\.entity_type, row\.entity_id\);/);
  assert.match(workspace, /\{resolved \? \(/);
  assert.match(workspace, /onInspectEvidence\(entityRef, /);
  // An unresolved entity says so rather than offering an action that would do nothing.
  assert.match(workspace, /t\("review\.evidence_unavailable"\)/);

  assert.match(decision, /reviewProjection=\{api\.reviewContext\}/);
  assert.match(
    decision,
    /const subject = inspectorSubjectFor\("decision-evidence", ref, label, "review"\);/,
  );
  assert.match(decision, /if \(subject\) inspector\.open\(subject\);/);

  const en = JSON.parse(readWebSource("i18n/en.json")) as Record<string, string>;
  const zh = JSON.parse(readWebSource("i18n/zh.json")) as Record<string, string>;
  for (const key of [
    "review.evidence",
    "review.inspect_evidence",
    "review.evidence_unavailable",
    "experience.inspector.fact.evidence_state",
    "experience.inspector.fact.evidence_resolver",
  ]) {
    assert.ok(en[key]?.trim(), `en ${key}`);
    assert.ok(zh[key]?.trim(), `zh ${key}`);
    assert.notEqual(en[key], zh[key], key);
  }
});

test("the panel renders resolved facts and never resolves detail itself", () => {
  const panel = readWebSource("components/InspectorPanel.tsx");
  const shell = readWebSource("app/shell/AppShell.tsx");
  const cockpit = readWebSource("components/MarketCockpit.tsx");

  // The panel is told the detail; it does not look it up or fetch it.
  assert.match(panel, /detail: InspectorDetail;/);
  assert.match(panel, /\{detail\.facts\.map\(\(fact\) => \(/);
  assert.match(panel, /\{detail\.resolved\s*\n?\s*\? t\("experience\.inspector\.note"\)/);
  for (const banned of ["useEffect", "api.", "fetch(", "inspectorDetailFor"]) {
    assert.equal(panel.includes(banned), false, banned);
  }

  // The shell resolves detail from state the identity already received.
  assert.match(shell, /detail=\{inspectorDetailFor\(api, inspector\.subject\)\}/);

  // The market cockpit hands its focused observation over through the contract.
  assert.match(cockpit, /import \{ marketObservationSubject \} from "@\/app\/model\/inspectorDetail"/);
  assert.match(cockpit, /const inspector = useInspectorStore\(\);/);
  assert.match(cockpit, /const subject = marketObservationSubject\(/);
  assert.match(cockpit, /if \(subject\) inspector\.open\(subject\);/);
});
