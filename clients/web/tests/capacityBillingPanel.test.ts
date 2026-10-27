import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test, { after } from "node:test";
import React from "react";
import ReactDOMServer from "react-dom/server";

import {
  capacityBillingReadiness,
  emptyCapacityBillingDraft,
  type CapacityBillingDraft,
} from "../src/app/model/capacityBillingModel.ts";
import { closeApiStoreHarness, loadApiStore } from "./support/apiStoreHarness.ts";

const originalWindow = (globalThis as { window?: unknown }).window;
(globalThis as { window?: unknown }).window = { location: { origin: "http://localhost:3000" } };

after(closeApiStoreHarness);
after(() => {
  (globalThis as { window?: unknown }).window = originalWindow;
});

function readWebSource(relativePath: string): string {
  return readFileSync(new URL(`../src/${relativePath}`, import.meta.url), "utf8");
}

const t = (key: string) => key;

interface PanelController {
  draft: CapacityBillingDraft;
  updateDraft: (updater: (current: CapacityBillingDraft) => CapacityBillingDraft) => void;
  readiness: ReturnType<typeof capacityBillingReadiness>;
  busy: boolean;
  result: Record<string, unknown> | null;
  meta: Record<string, unknown> | null;
  refusal: Record<string, unknown> | null;
  error: unknown;
  run: () => Promise<void>;
}

function controller(patch: Partial<PanelController> = {}): PanelController {
  const draft = patch.draft ?? {
    ...emptyCapacityBillingDraft(),
    scenarioId: "sandbox-scenario-1",
    tariffId: "tariff-1",
    tariffRate: "001.2300",
    currency: "GBP",
    tariffUnit: "p/(kWh/h)/h",
    bookedCapacityMwhPerHour: "100.000",
    deliveredEnergyMwh: "000123.4500",
    billedCapacityEnergyMwh: "2500.000000000000000000000000000000",
    billingStart: "2026-10-25T00:00:00+02:00",
    billingEnd: "2026-10-26T01:00:00+02:00",
    sourceReferences: "tariff-sheet:uat-1\noperator-input:capacity-1",
  };
  return {
    draft,
    updateDraft: () => undefined,
    readiness: capacityBillingReadiness(draft),
    busy: false,
    result: null,
    meta: null,
    refusal: null,
    error: null,
    run: async () => undefined,
    ...patch,
  };
}

function successResult(): Record<string, unknown> {
  return {
    research_only: true,
    human_review_required: true,
    model_version: "capacity-billing/v1",
    scenario_id: "sandbox-scenario-1",
    tariff_id: "tariff-1",
    currency: "GBP",
    tariff_unit: "p/(kWh/h)/h",
    tariff_rate: "1.2300",
    booked_capacity_mwh_per_h: "100.000",
    billed_capacity_energy_mwh: "2500.000000000000000000000000000000",
    delivered_energy_mwh: "123.4500",
    billing_start: "2026-10-24T22:00:00+00:00",
    billing_end: "2026-10-25T23:00:00+00:00",
    duration_microseconds: 90_000_000_000,
    duration_hours: "25",
    total_cost: "3075.000000000000000000000000000000",
    cost_per_delivered_mwh: "24.909090909090909090909090909091",
    basis: {},
    provenance: ["operator-input:capacity-1", "tariff-sheet:uat-1"],
    source_references: ["operator-input:capacity-1", "tariff-sheet:uat-1"],
    assumptions: ["Caller-supplied tariff."],
    warnings: ["RESEARCH_ONLY_DECISION_SUPPORT_NOT_INVOICE_OR_SETTLEMENT"],
    lineage: ["capacity-billing", "capacity-billing/v1"],
    physical_readiness: "NOT_ASSESSED",
  };
}

function successMeta(): Record<string, unknown> {
  return {
    research_only: true,
    human_review_required: true,
    decision_context: "SANDBOX_SCENARIO",
    caller_supplied: true,
    references_verified: false,
    booked_rights_established: false,
    physical_readiness: "NOT_ASSESSED",
    customer_approval: false,
    source_references: ["operator-input:capacity-1", "tariff-sheet:uat-1"],
    warnings: ["RESEARCH_ONLY_DECISION_SUPPORT_NOT_INVOICE_OR_SETTLEMENT"],
  };
}

interface PanelModule {
  CapacityBillingPanel: (props: Record<string, unknown>) => unknown;
  isCapacityBillingShortcut: (event: {
    key: string;
    ctrlKey: boolean;
    metaKey: boolean;
    altKey: boolean;
    isComposing?: boolean;
  }) => boolean;
}

let panelModulePromise: Promise<PanelModule> | null = null;

function panelModule(): Promise<PanelModule> {
  panelModulePromise ??= loadApiStore().then((harness) =>
    harness.load<PanelModule>("/src/components/CapacityBillingPanel.tsx"),
  );
  return panelModulePromise;
}

async function renderPanel(panelController: PanelController): Promise<string> {
  const module = await panelModule();
  return ReactDOMServer.renderToStaticMarkup(
    React.createElement(module.CapacityBillingPanel as never, {
      t,
      capacityBilling: panelController,
    } as never),
  );
}

test("Ctrl+Enter is advertised and only activates on the panel's own ready shortcut", async () => {
  const module = await panelModule();
  const chord = {
    key: "Enter",
    ctrlKey: true,
    metaKey: false,
    altKey: false,
    isComposing: false,
  };

  assert.equal(module.isCapacityBillingShortcut(chord), true);
  assert.equal(module.isCapacityBillingShortcut({ ...chord, isComposing: undefined }), true);
  assert.equal(module.isCapacityBillingShortcut({ ...chord, key: "Enter", ctrlKey: false }), false);
  assert.equal(module.isCapacityBillingShortcut({ ...chord, key: " " }), false);
  assert.equal(module.isCapacityBillingShortcut({ ...chord, key: "Enter", metaKey: true }), false);
  assert.equal(module.isCapacityBillingShortcut({ ...chord, key: "Enter", altKey: true }), false);
  assert.equal(module.isCapacityBillingShortcut({ ...chord, isComposing: true }), false);

  const incomplete = await renderPanel(controller({ draft: emptyCapacityBillingDraft() }));
  assert.match(incomplete, /aria-keyshortcuts="Control\+Enter"/);
  assert.match(incomplete, /title="[^"]*Ctrl\+Enter\)"/);
  assert.match(incomplete, /<button[^>]*disabled/);

  const ready = await renderPanel(controller());
  assert.match(ready, /aria-keyshortcuts="Control\+Enter"/);
  assert.match(ready, /title="[^"]*Ctrl\+Enter\)"/);
  assert.doesNotMatch(ready, /<button[^>]*disabled/);
});

test("the mounted capacity-billing panel is a labelled form with the sandbox boundary", async () => {
  const markup = await renderPanel(controller({ draft: emptyCapacityBillingDraft() }));

  for (const label of [
    "portfolio.capacity_billing.title",
    "portfolio.capacity_billing.scenario_id",
    "portfolio.capacity_billing.tariff_id",
    "portfolio.capacity_billing.tariff_rate",
    "portfolio.capacity_billing.currency",
    "portfolio.capacity_billing.tariff_unit",
    "portfolio.capacity_billing.booked_capacity",
    "portfolio.capacity_billing.delivered_energy",
    "portfolio.capacity_billing.billed_capacity",
    "portfolio.capacity_billing.billing_start",
    "portfolio.capacity_billing.billing_end",
    "portfolio.capacity_billing.source_references",
    "portfolio.capacity_billing.sandbox_notice",
    "portfolio.capacity_billing.billed_help",
  ]) {
    assert.ok(markup.includes(label), `missing accessible label/help: ${label}`);
  }
  for (const fieldId of [
    "capacity-billing-scenario-id",
    "capacity-billing-tariff-id",
    "capacity-billing-tariff-rate",
    "capacity-billing-tariff-unit",
    "capacity-billing-currency",
    "capacity-billing-booked",
    "capacity-billing-delivered",
    "capacity-billing-billed",
    "capacity-billing-start",
    "capacity-billing-end",
    "capacity-billing-source-references",
  ]) {
    assert.ok(markup.includes(`for="${fieldId}"`), `label is not associated with ${fieldId}`);
    assert.ok(markup.includes(`id="${fieldId}"`), `control is missing ${fieldId}`);
  }
  assert.match(markup, /class="capacity-billing-form-grid"/);
  assert.match(markup, /aria-required="true"/);
  assert.match(markup, /aria-describedby="capacity-billing-billed-help"/);
  assert.match(markup, /aria-describedby="capacity-billing-utc-help"/);
  assert.match(markup, /disabled(?:="")?/, "an incomplete form cannot submit");
  assert.ok(markup.includes('value="GBP"'));
  assert.ok(markup.includes('value="p/(kWh/h)/h"'));
});

test("a backend result shows full billed cost beside per-delivered cost and the exact basis", async () => {
  const result = successResult();
  const markup = await renderPanel(
    controller({ result, meta: successMeta() }),
  );

  assert.ok(markup.includes("3075.000000000000000000000000000000"));
  assert.ok(markup.includes("24.909090909090909090909090909091"));
  assert.ok(markup.includes("GBP/MWh"));
  assert.match(markup, /role="region"/);
  assert.match(markup, /tabindex="-1"/);
  assert.ok(markup.includes('class="capacity-billing-metric-amount"'));
  assert.ok(markup.includes("90,000,000,000") || markup.includes("90000000000"));
  assert.ok(markup.includes("25 h"), "the backend's 25-hour duration is displayed, not recomputed");
  assert.ok(markup.includes("NOT_ASSESSED"));
  assert.ok(markup.includes("SANDBOX_SCENARIO"));
  assert.ok(markup.includes("portfolio.capacity_billing.total_cost"));
  assert.ok(markup.includes("portfolio.capacity_billing.cost_per_delivered"));
  assert.ok(markup.includes("portfolio.capacity_billing.result_exact"));
  assert.ok(markup.includes("2026-10-24T22:00:00+00:00"));
  assert.ok(markup.includes("2026-10-25T23:00:00+00:00"));
  assert.ok(markup.includes("2500.000000000000000000000000000000 MWh"));
  assert.ok(markup.includes("123.4500 MWh"));
  assert.ok(markup.includes("100.000 MWh/h"));
});

test("loading clears the previous result instead of showing it beside the spinner", async () => {
  const markup = await renderPanel(
    controller({ busy: true, result: successResult(), meta: successMeta() }),
  );

  assert.ok(markup.includes("portfolio.capacity_billing.loading"));
  assert.equal(markup.includes("3075.000000000000000000000000000000"), false);
  assert.equal(markup.includes("24.909090909090909090909090909091"), false);
  assert.ok(markup.includes("aria-busy=\"true\""));
});

test("a backend refusal shows the stable code and field details with no synthetic result", async () => {
  const markup = await renderPanel(
    controller({
      result: successResult(),
      meta: successMeta(),
      refusal: {
        status: 422,
        code: "capacity_billing_refused",
        message: "The shared capacity-billing engine refused the supplied inputs; nothing was computed.",
        violations: [
          {
            code: "BILLED_CAPACITY_ENERGY_INCONSISTENT",
            detail: "billed_capacity_energy_mwh must equal booked capacity × actual duration",
          },
          {
            code: "DELIVERED_ENERGY_EXCEEDS_BILLED_CAPACITY",
            detail: "delivered_energy_mwh exceeds billed_capacity_energy_mwh",
          },
        ],
      },
    }),
  );

  assert.ok(markup.includes("capacity_billing_refused"));
  assert.ok(markup.includes("BILLED_CAPACITY_ENERGY_INCONSISTENT"));
  assert.ok(markup.includes("DELIVERED_ENERGY_EXCEEDS_BILLED_CAPACITY"));
  assert.ok(markup.includes("portfolio.capacity_billing.refusal_help"));
  assert.equal(markup.includes("3075.000000000000000000000000000000"), false);
  assert.equal(markup.includes("24.909090909090909090909090909091"), false);
  assert.match(markup, /role="alert"/);
});

test("the panel is mounted in the actual Routes task, not a new top-level page", () => {
  const portfolio = readWebSource("components/PortfolioWorkspace.tsx");
  const renderer = readWebSource("app/workspaces/WorkspaceRenderer.tsx");

  assert.match(portfolio, /import \{ CapacityBillingPanel \} from "@\/components\/CapacityBillingPanel"/);
  assert.match(portfolio, /useCapacityBilling/);
  const routesStart = portfolio.indexOf('{task === "routes" && (');
  assert.ok(routesStart >= 0, "the Routes task block is present");
  const routesBlock = portfolio.slice(
    routesStart,
    portfolio.indexOf('{task === "exposure" && (', routesStart),
  );
  assert.ok(routesBlock.includes("<CapacityBillingPanel"));
  assert.ok(routesBlock.includes("<RouteCostWhatIfPanel"), "the existing route-cost workflow is preserved");
  assert.match(renderer, /activePrimaryWorkspace\.id === "portfolio"/);
  assert.match(renderer, /<PortfolioWorkspace/);
  // The panel displays the backend's sandbox context; it never composes a runtime claim.
  const panel = readWebSource("components/CapacityBillingPanel.tsx");
  assert.equal(panel.includes("RUNTIME_DECISION"), false);
  assert.equal(panel.includes("Number("), false);
  assert.equal(panel.includes("parseFloat"), false);
  assert.equal(panel.includes("toFixed"), false);
});
