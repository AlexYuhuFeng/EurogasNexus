import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test, { after } from "node:test";
import React from "react";
import ReactDOMServer from "react-dom/server";

import {
  lngEconomicsReadiness,
  type LngEconomicsDraft,
} from "../src/app/model/lngEconomicsModel.ts";
import type { LngEconomicsController } from "../src/app/model/useLngEconomicsOnly.ts";
import { closeApiStoreHarness, loadApiStore } from "./support/apiStoreHarness.ts";
import {
  goldenDraft,
  goldenMeta,
  goldenResult,
} from "./support/lngEconomicsFixtures.ts";

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

function controller(patch: Partial<LngEconomicsController> = {}): LngEconomicsController {
  const draft = patch.draft ?? goldenDraft();
  return {
    draft,
    updateDraft: () => undefined,
    readiness: lngEconomicsReadiness(draft),
    busy: false,
    result: null,
    meta: null,
    refusal: null,
    error: null,
    run: async () => undefined,
    ...patch,
  };
}

interface PanelModule {
  LngEconomicsPanel: (props: Record<string, unknown>) => unknown;
}

let panelModulePromise: Promise<PanelModule> | null = null;

function panelModule(): Promise<PanelModule> {
  panelModulePromise ??= loadApiStore().then((harness) =>
    harness.load<PanelModule>("/src/components/LngEconomicsPanel.tsx"),
  );
  return panelModulePromise;
}

async function renderPanel(
  panelController: LngEconomicsController,
  context: { id?: string | null; name?: string | null } = {},
): Promise<string> {
  const module = await panelModule();
  return ReactDOMServer.renderToStaticMarkup(
    React.createElement(module.LngEconomicsPanel as never, {
      t,
      lngEconomics: panelController,
      selectedContractId:
        context.id === undefined ? "contract-synthetic-lng-1" : context.id,
      selectedContractName:
        context.name === undefined ? "Synthetic LNG Term" : context.name,
    } as never),
  );
}

test("the mounted panel is a labelled explicit form with the sandbox/readiness boundary", async () => {
  const blank: LngEconomicsDraft = {
    ...goldenDraft(),
    contractId: "",
    cargoId: "",
    terminalId: "",
    resourceId: "",
    valuationDate: "",
    reportingCurrency: "",
    energyBasisReference: "",
    energyUnit: "",
    purchasedEnergyMwh: "",
    deliveredEnergyMwh: "",
    purchaseUnitPriceEurPerMwh: "",
    saleUnitPriceEurPerMwh: "",
    purchasePriceSourceReference: "",
    salePriceSourceReference: "",
    purchaseBasis: "",
    costScopeStatement: "",
    purchasePaymentDate: "",
    salePaymentDate: "",
    downstreamCosts: [],
    energyStages: [],
    discountFactors: [],
  };
  const markup = await renderPanel(controller({ draft: blank }));

  for (const label of [
    "contracts.lng_economics.title",
    "contracts.lng_economics.contract_id",
    "contracts.lng_economics.cargo_id",
    "contracts.lng_economics.terminal_id",
    "contracts.lng_economics.resource_id",
    "contracts.lng_economics.valuation_date",
    "contracts.lng_economics.purchase_payment_date",
    "contracts.lng_economics.sale_payment_date",
    "contracts.lng_economics.purchased_energy",
    "contracts.lng_economics.delivered_energy",
    "contracts.lng_economics.purchase_unit_price",
    "contracts.lng_economics.sale_unit_price",
    "contracts.lng_economics.purchase_basis",
    "contracts.lng_economics.purchase_included_cost_items",
    "contracts.lng_economics.cost_scope_statement",
    "contracts.lng_economics.energy_basis_reference",
    "contracts.lng_economics.energy_unit",
    "contracts.lng_economics.reporting_currency",
    "contracts.lng_economics.add_stage",
    "contracts.lng_economics.add_cost",
    "contracts.lng_economics.add_discount",
    "contracts.lng_economics.sandbox_notice",
    "contracts.lng_economics.no_readiness_claim",
    "contracts.lng_economics.context_only",
    "contracts.lng_economics.required_fields",
    "contracts.lng_economics.shortcut_help",
  ]) {
    assert.ok(markup.includes(label), `missing accessible label/help: ${label}`);
  }
  assert.match(markup, /aria-required="true"/);
  assert.match(markup, /aria-keyshortcuts="Control\+Enter"/);
  assert.match(markup, /disabled(?:="")?/, "an incomplete form cannot submit");
  assert.equal(markup.includes("contracts.lng_economics.result"), false);
  assert.ok(markup.includes("SANDBOX") === false, "the request surface does not claim a context");
  assert.ok(markup.includes("contract-synthetic-lng-1"), "selection is shown as context");
});

test("a golden result renders margin, netback, NPV and separate energy totals exactly", async () => {
  const markup = await renderPanel(
    controller({ result: goldenResult(), meta: goldenMeta() }),
  );
  // React may separate adjacent text nodes with hydration comments; the displayed text is what the
  // operator sees, so the assertions read it without the markers.
  const text = markup.replace(/<!-- -->/g, "");

  assert.ok(text.includes("550.0000"));
  assert.ok(text.includes("25.5000"));
  assert.ok(text.includes("482.5000"));
  assert.ok(text.includes("2000.0000"));
  assert.ok(text.includes("2700.0000"));
  assert.ok(text.includes("150.0000"));
  assert.ok(text.includes("2632.5000"));
  assert.ok(text.includes("0.975"));
  assert.ok(text.includes(">100 MWh<"));
  assert.ok(text.includes(">90 MWh<"));
  assert.ok(text.includes(">7 MWh<"));
  assert.ok(text.includes(">3 MWh<"));
  assert.ok(text.includes(">10 MWh<"));
  assert.ok(text.includes("NOT_ASSESSED"));
  assert.ok(text.includes("false"));
  assert.ok(text.includes("lng-economics-only/v1"));
  assert.ok(text.includes("SANDBOX_SCENARIO"));
  assert.ok(text.includes("contracts.lng_economics.result_exact"));
  assert.ok(text.includes("contracts.lng_economics.cash_legs_caption"));
  assert.ok(text.includes("contracts.lng_economics.stage_chain_caption"));
  assert.ok(text.includes("contracts.lng_economics.provenance"));
  assert.ok(text.includes("PHYSICAL_READINESS_NOT_ASSESSED"));
  assert.ok(text.includes("PROFITABLE_ECONOMICS_IS_NOT_DELIVERY_FEASIBILITY"));
  assert.ok(text.includes("synthetic-test-input:invoiced-cost-1"));
  assert.ok(text.includes("cargo-purchase"));
  assert.ok(text.includes("downstream-cost:regas-1"));
  assert.ok(text.includes("shipping-1"));
  assert.ok(text.includes("regasification"));
  assert.ok(text.includes("contracts.lng_economics.boundary_note"));
});

test("unknown readiness is reported as unknown, never coerced into a readiness claim", async () => {
  const result = {
    ...goldenResult(),
    physical_readiness: "",
    readiness_assessed: undefined,
    warnings: [],
  };
  const meta = {
    ...goldenMeta(),
    physical_readiness: "",
    readiness_assessed: undefined,
    warnings: [],
  };
  const markup = await renderPanel(
    controller({ result, meta } as unknown as Partial<LngEconomicsController>),
  );

  assert.ok(markup.includes("contracts.lng_economics.unknown"));
  assert.equal(markup.includes("NOT_ASSESSED"), false);
});

test("loading, refusal and transport failure all suppress the previous result", async () => {
  const loading = await renderPanel(
    controller({ busy: true, result: goldenResult(), meta: goldenMeta() }),
  );
  assert.ok(loading.includes("contracts.lng_economics.loading"));
  assert.equal(loading.includes("550.0000"), false);
  assert.equal(loading.includes("482.5000"), false);
  assert.ok(loading.includes('aria-busy="true"'));

  const refusal = await renderPanel(
    controller({
      result: goldenResult(),
      meta: goldenMeta(),
      refusal: {
        status: 422,
        code: "lng_economics_only_refused",
        message: "The shared LNG economics-only composition refused the supplied inputs.",
        violations: [
          { code: "STAGE_NOT_CONSERVED", detail: "stage 1 input != output + consumed + loss" },
          { code: "DISCOUNT_FACTOR_MISSING", detail: "2026-11-30 has no explicit factor" },
        ],
      },
    }),
  );
  assert.ok(refusal.includes("lng_economics_only_refused"));
  assert.ok(refusal.includes("STAGE_NOT_CONSERVED"));
  assert.ok(refusal.includes("DISCOUNT_FACTOR_MISSING"));
  assert.ok(refusal.includes("contracts.lng_economics.refusal_help"));
  assert.equal(refusal.includes("550.0000"), false);
  assert.equal(refusal.includes("482.5000"), false);
  assert.match(refusal, /role="alert"/);

  const failed = await renderPanel(
    controller({
      result: goldenResult(),
      meta: goldenMeta(),
      error: new Error("network down"),
    }),
  );
  assert.ok(failed.includes("contracts.lng_economics.transport_error_help"));
  assert.equal(failed.includes("550.0000"), false);
  assert.equal(failed.includes("482.5000"), false);
  assert.match(failed, /role="alert"/);
});

test("a blank context is stated honestly and no synthetic facts are filled", async () => {
  const blank: LngEconomicsDraft = {
    ...goldenDraft(),
    contractId: "",
    cargoId: "",
    terminalId: "",
    resourceId: "",
    downstreamCosts: [],
    energyStages: [],
    discountFactors: [],
  };
  const markup = await renderPanel(controller({ draft: blank }), { id: null, name: null });
  assert.ok(markup.includes("contracts.lng_economics.no_selection"));
  assert.ok(markup.includes("disabled"));
  assert.equal(markup.includes("0.975"), false);
  assert.equal(markup.includes("shipping-1"), false);
});

test("the panel is mounted in the existing Contracts workbench, not a new top-level page", () => {
  const workbench = readWebSource("components/ContractWorkbench.tsx");
  const portfolio = readWebSource("components/PortfolioWorkspace.tsx");
  const renderer = readWebSource("app/workspaces/WorkspaceRenderer.tsx");
  const panel = readWebSource("components/LngEconomicsPanel.tsx");

  assert.match(workbench, /import \{ LngEconomicsPanel \} from "@\/components\/LngEconomicsPanel"/);
  assert.match(workbench, /import \{ useLngEconomicsOnly \} from "@\/app\/model\/useLngEconomicsOnly"/);
  assert.match(workbench, /type ContractTaskView =[^;]*"lng_economics"/s);
  assert.match(workbench, /\["lng_economics", t\("contracts\.view\.lng_economics"\)\]/);
  const lngStart = workbench.indexOf('{taskView === "lng_economics" && (');
  assert.ok(lngStart >= 0, "the LNG task block is present");
  const lngBlock = workbench.slice(
    lngStart,
    workbench.indexOf('{taskView === "library" && (', lngStart),
  );
  assert.ok(lngBlock.includes("<LngEconomicsPanel"));
  assert.ok(lngBlock.includes("selectedContractId={selectedResourceId}"));
  assert.ok(workbench.includes("useLngEconomicsOnly(selectedResourceId ?? \"\")"));
  assert.match(portfolio, /import \{ ContractWorkbench, type ContractTaskView \} from "@\/components\/ContractWorkbench"/);
  assert.match(portfolio, /<ContractWorkbench/);
  assert.equal(renderer.includes("LngEconomicsPanel"), false, "no new top-level page/route");
  assert.equal(portfolio.includes("LngEconomicsPanel"), false, "the panel lives in the contracts workbench");

  // Scoped keyboard handling, focusable result, and a synchronous disabled state are structure,
  // not prose: the component really attaches them.
  assert.match(panel, /onKeyDown=\{handleKeyDown\}/);
  assert.match(panel, /lngEconomicsSubmitShortcut\(event, \{ canSubmit: readiness\.canSubmit, busy \}\)/);
  assert.match(panel, /resultRef\.current\?\.focus\(/);
  assert.match(panel, /tabIndex=\{-1\}/);
  assert.match(panel, /disabled=\{busy \|\| !readiness\.canSubmit\}/);

  for (const forbidden of ["Number(", "parseFloat(", "parseInt(", "toFixed(", "Math."]) {
    assert.equal(panel.includes(forbidden), false, forbidden);
  }
});
