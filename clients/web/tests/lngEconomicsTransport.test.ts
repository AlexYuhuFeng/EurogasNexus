/**
 * The web transport for the LNG economics-only composition
 * (`POST /api/research/lng-economics-only`).
 *
 * The tests hold the exactness contract:
 *
 * - every price, quantity, cost, stage amount and discount factor is a string end to end. The
 *   request is asserted as raw JSON text so a value JavaScript cannot represent exactly is shown
 *   to cross the transport unrounded, and the response keeps the engine's exact fixed-point
 *   strings instead of parsing them;
 * - the request sends no `decision_context` and no `model_version` claim. The backend labels the
 *   run `SANDBOX_SCENARIO`, and the domain's actual implementation version is what the response
 *   carries;
 * - a refusal rejects with the backend's typed detail (`lng_economics_only_refused` plus the
 *   engine's stable codes), and a transport failure still rejects;
 * - the method is transport only: no arithmetic, no parsing and no browser storage.
 */

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test, { after } from "node:test";

import { lngEconomicsRequest } from "../src/app/model/lngEconomicsModel.ts";
import { closeApiStoreHarness, loadApiStore } from "./support/apiStoreHarness.ts";
import {
  GOLDEN_COST_SOURCE,
  GOLDEN_DF_CURVE,
  GOLDEN_DF_SOURCE,
  GOLDEN_PURCHASE_SOURCE,
  GOLDEN_SALE_SOURCE,
  GOLDEN_STAGE_1_SOURCE,
  GOLDEN_STAGE_2_SOURCE,
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

interface CapturedRequest {
  readonly url: URL;
  readonly init: { method?: string; body?: unknown } | undefined;
}

interface LngEconomicsResultLike {
  readonly data: Record<string, unknown>;
  readonly meta: Record<string, unknown>;
}

interface LngEconomicsClient {
  api: {
    lngEconomicsOnly(
      body: unknown,
      options?: { signal?: AbortSignal },
    ): Promise<LngEconomicsResultLike>;
  };
  ApiError: new (message: string, status: number, detail: unknown, body?: unknown) => Error & {
    readonly status: number;
    readonly detail: unknown;
    readonly body: unknown;
  };
}

function jsonResponse(payload: unknown, status = 200): Promise<Response> {
  return Promise.resolve(
    new Response(JSON.stringify(payload), {
      status,
      headers: { "content-type": "application/json" },
    }),
  );
}

async function callWithCapturedFetch<T>(
  answer: () => Promise<Response>,
  run: (client: LngEconomicsClient) => Promise<T>,
): Promise<{ result: T; requests: CapturedRequest[] }> {
  const harness = await loadApiStore();
  const client = await harness.load<LngEconomicsClient>("/src/api/client.ts");
  const requests: CapturedRequest[] = [];
  const globals = globalThis as { fetch?: unknown };
  const previousFetch = globals.fetch;
  globals.fetch = async (input: unknown, init?: unknown) => {
    requests.push({
      url: new URL(String(input)),
      init: init as CapturedRequest["init"],
    });
    return answer();
  };
  try {
    return { result: await run(client), requests };
  } finally {
    globals.fetch = previousFetch;
  }
}

function goldenBody() {
  const body = lngEconomicsRequest(goldenDraft());
  assert.ok(body);
  return body;
}

test("the documented golden request crosses the transport exactly and keeps no local claim", async () => {
  const { requests } = await callWithCapturedFetch(
    () => jsonResponse({ data: goldenResult(), meta: goldenMeta() }),
    (client) => client.api.lngEconomicsOnly(goldenBody()),
  );

  assert.equal(requests.length, 1);
  assert.equal(requests[0].url.pathname, "/api/research/lng-economics-only");
  assert.equal(requests[0].init?.method, "POST");

  const raw = String(requests[0].init?.body);
  assert.ok(raw.includes('"purchased_energy_mwh":"100"'), raw);
  assert.ok(raw.includes('"delivered_energy_mwh":"90"'), raw);
  assert.ok(raw.includes('"purchase_unit_price_eur_per_mwh":"20"'), raw);
  assert.ok(raw.includes('"sale_unit_price_eur_per_mwh":"30"'), raw);
  assert.ok(raw.includes('"amount_eur":"150"'), raw);
  assert.ok(raw.includes('"physical_loss_energy_mwh":"2"'), raw);
  assert.ok(raw.includes('"factor":"0.975"'), raw);
  assert.ok(raw.includes('"charge_basis":"invoiced_cash"'), raw);

  const sent = JSON.parse(raw) as Record<string, unknown>;
  assert.deepEqual(Object.keys(sent), [
    "contract_id",
    "cargo_id",
    "terminal_id",
    "resource_id",
    "valuation_date",
    "reporting_currency",
    "energy_basis_reference",
    "energy_unit",
    "purchased_energy_mwh",
    "delivered_energy_mwh",
    "purchase_unit_price_eur_per_mwh",
    "sale_unit_price_eur_per_mwh",
    "purchase_price_source_reference",
    "sale_price_source_reference",
    "purchase_basis",
    "purchase_included_cost_items",
    "cost_scope_statement",
    "purchase_payment_date",
    "sale_payment_date",
    "downstream_costs",
    "energy_stages",
    "discount_factors",
  ]);
  assert.equal(typeof sent.purchased_energy_mwh, "string");
  assert.equal("model_version" in sent, false);
  assert.equal("decision_context" in sent, false);
  assert.equal(raw.includes("RUNTIME_DECISION"), false);
  assert.equal(raw.includes("SANDBOX_SCENARIO"), false);
});

test("the result keeps the backend's exact strings, totals and NOT_ASSESSED readiness", async () => {
  const { result } = await callWithCapturedFetch(
    () => jsonResponse({ data: goldenResult(), meta: goldenMeta() }),
    (client) => client.api.lngEconomicsOnly(goldenBody()),
  );

  assert.equal(result.data.cargo_margin_eur, "550.0000");
  assert.equal(result.data.unit_netback_eur_per_purchased_mwh, "25.5000");
  assert.equal(result.data.net_present_value_eur, "482.5000");
  assert.equal(result.data.purchase_outlay_eur, "2000.0000");
  assert.equal(result.data.sale_proceeds_eur, "2700.0000");
  assert.equal(result.data.total_downstream_costs_eur, "150.0000");
  assert.equal(result.data.purchased_energy_mwh, "100");
  assert.equal(result.data.delivered_energy_mwh, "90");
  assert.equal(result.data.total_consumed_energy_mwh, "7");
  assert.equal(result.data.physical_loss_energy_mwh, "3");
  assert.equal(result.data.total_reduction_energy_mwh, "10");
  assert.equal(result.data.physical_readiness, "NOT_ASSESSED");
  assert.equal(result.data.readiness_assessed, false);
  assert.equal(result.data.model_version, "lng-economics-only/v1");

  const cash = result.data.cash_valuation as Record<string, unknown>;
  assert.equal(cash.net_present_value_reporting_ccy, "482.5000");
  assert.equal(cash.total_undiscounted_cash_reporting_ccy, "550.0000");
  const energy = result.data.energy_balance as Record<string, unknown>;
  assert.equal(energy.total_consumed_energy_mwh, "7");
  assert.equal(energy.physical_loss_energy_mwh, "3");
  assert.equal(energy.total_reduction_energy_mwh, "10");
  assert.equal((energy.stages as Array<Record<string, unknown>>).length, 2);

  assert.equal(result.meta.decision_context, "SANDBOX_SCENARIO");
  assert.equal(result.meta.caller_supplied, true);
  assert.equal(result.meta.references_verified, false);
  assert.equal(result.meta.physical_readiness, "NOT_ASSESSED");
  assert.equal(result.meta.readiness_assessed, false);
  assert.equal(result.meta.customer_approval, false);

  const sourceReferences = (cash.source_references as string[]).join(" ");
  for (const reference of [
    GOLDEN_PURCHASE_SOURCE,
    GOLDEN_SALE_SOURCE,
    GOLDEN_COST_SOURCE,
    GOLDEN_DF_SOURCE,
    GOLDEN_STAGE_1_SOURCE,
    GOLDEN_STAGE_2_SOURCE,
  ]) {
    assert.ok(sourceReferences.includes(reference));
  }
  assert.ok((cash.leg_valuations as Array<Record<string, unknown>>).some(
    (leg) => leg.discount_curve_reference === GOLDEN_DF_CURVE,
  ));
});

test("a typed backend refusal rejects with the backend detail and nothing is swallowed", async () => {
  const refusal = {
    detail: {
      code: "lng_economics_only_refused",
      message: "The shared LNG economics-only composition refused the supplied inputs.",
      codes: ["STAGE_NOT_CONSERVED", "DISCOUNT_FACTOR_MISSING"],
      violations: [
        { code: "STAGE_NOT_CONSERVED", detail: "stage 1 input != output + consumed + loss" },
        { code: "DISCOUNT_FACTOR_MISSING", detail: "2026-11-30 has no explicit factor" },
      ],
      research_only: true,
      human_review_required: true,
    },
  };

  await callWithCapturedFetch(
    () => jsonResponse(refusal, 422),
    async (client) => {
      await assert.rejects(
        () => client.api.lngEconomicsOnly(goldenBody()),
        (error: unknown) => {
          assert.ok(error instanceof client.ApiError);
          assert.equal(error.status, 422);
          assert.match(error.message, /^API 422: lng_economics_only_refused — /);
          const detail = error.detail as { codes: string[]; violations: unknown[] };
          assert.deepEqual(detail.codes, ["STAGE_NOT_CONSERVED", "DISCOUNT_FACTOR_MISSING"]);
          assert.equal(detail.violations.length, 2);
          return true;
        },
      );
    },
  );
});

test("a transport failure is not read as a server answer", async () => {
  await callWithCapturedFetch(
    () => Promise.reject(new Error("network down")),
    async (client) => {
      await assert.rejects(
        () => client.api.lngEconomicsOnly(goldenBody()),
        /network down/,
      );
    },
  );
});

test("the method is transport only and declares no authority fields", () => {
  const clientSource = readFileSync(new URL("../src/api/client.ts", import.meta.url), "utf8");
  const methodBody = clientSource.slice(
    clientSource.indexOf("lngEconomicsOnly:"),
    clientSource.indexOf("lngEconomicsOnly:") + 520,
  );
  for (const forbidden of ["localStorage", "sessionStorage", "Number(", "parseFloat", "toFixed"]) {
    assert.equal(methodBody.includes(forbidden), false, forbidden);
  }

  const requestBlock = clientSource.slice(
    clientSource.indexOf("export interface LngEconomicsOnlyRequestDTO"),
    clientSource.indexOf("export interface LngEconomicsEnergyBalanceDTO"),
  );
  assert.ok(requestBlock.includes("purchased_energy_mwh: string"));
  assert.ok(requestBlock.includes("discount_factors: LngEconomicsOnlyDiscountFactorDTO[]"));
  assert.ok(requestBlock.includes("downstream_costs: LngEconomicsOnlyDownstreamCostDTO[]"));
  for (const forbidden of [
    "decision_context",
    "work_mode",
    "persona",
    "research_only",
    "human_review_required",
    "customer_approval",
  ]) {
    assert.equal(requestBlock.includes(forbidden), false, forbidden);
  }
  assert.equal(
    (clientSource.match(/"\/research\/lng-economics-only"/g) ?? []).length,
    1,
    "one typed method for the one route",
  );
});
