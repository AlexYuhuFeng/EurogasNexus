/**
 * The web transport for the shared capacity-billing primitive
 * (`POST /api/research/capacity-billing`).
 *
 * The tests hold the exactness contract:
 *
 * - a financial or physical value is a string end to end. The request is asserted as raw JSON text
 *   so a value that JavaScript cannot represent exactly is shown to cross the transport unrounded,
 *   and the response keeps the engine's exact fixed-point strings instead of parsing them;
 * - the request sends no `decision_context` claim at all. The backend refuses a `RUNTIME_DECISION`
 *   claim and forbids the field on this model, so the only correct claim is none; the response
 *   labels the run `SANDBOX_SCENARIO` and states caller-supplied / unverified / no booked rights /
 *   NOT_ASSESSED physical readiness;
 * - a refusal rejects with the backend's typed detail (`capacity_billing_refused` plus the engine's
 *   stable codes), and a transport failure still rejects;
 * - the method is transport only: no arithmetic, no parsing and no browser storage.
 */

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test, { after } from "node:test";

import { closeApiStoreHarness, loadApiStore } from "./support/apiStoreHarness.ts";

const originalWindow = (globalThis as { window?: unknown }).window;
(globalThis as { window?: unknown }).window = { location: { origin: "http://localhost:3000" } };

after(closeApiStoreHarness);
after(() => {
  (globalThis as { window?: unknown }).window = originalWindow;
});

const EXACT_TOTAL_COST = "3075.000000000000000000000000000000";
const EXACT_COST_PER_DELIVERED = "24.909090909090909090909090909091";
const EXACT_DURATION_MICROSECONDS = 90_000_000_000; // 25 h, resolved by the backend, not here.

interface CapturedRequest {
  readonly url: URL;
  readonly init: { method?: string; body?: unknown } | undefined;
}

interface CapacityBillingResultLike {
  readonly data: Record<string, unknown>;
  readonly meta: Record<string, unknown>;
}

interface CapacityBillingClient {
  api: {
    capacityBilling(
      body: unknown,
      options?: { signal?: AbortSignal },
    ): Promise<CapacityBillingResultLike>;
  };
  ApiError: new (message: string, status: number, detail: unknown, body?: unknown) => Error & {
    readonly status: number;
    readonly detail: unknown;
    readonly body: unknown;
  };
}

interface CapturedCall<T> {
  readonly result: T;
  readonly requests: CapturedRequest[];
}

function capacityBillingRequestBody(): Record<string, unknown> {
  return {
    scenario_id: "sandbox-scenario-1",
    tariff_id: "tariff-1",
    tariff_rate: "0.000000000000000000000000001234",
    currency: "GBP",
    tariff_unit: "p/(kWh/h)/h",
    booked_capacity_mwh_per_h: "100.000000000000000000000000000001",
    delivered_energy_mwh: "000123.4500",
    billed_capacity_energy_mwh: "2500.000000000000000000000000000000",
    billing_start: "2026-10-25T00:00:00+02:00",
    billing_end: "2026-10-26T01:00:00+02:00",
    source_references: ["tariff-sheet:uat-1", "operator-input:capacity-1"],
  };
}

/** Synthetic precision-stress payload, not a numerical reference result from the engine. */
function capacityBillingResponse(): Record<string, unknown> {
  return {
    data: {
      research_only: true,
      human_review_required: true,
      model_version: "capacity-billing/v1",
      scenario_id: "sandbox-scenario-1",
      tariff_id: "tariff-1",
      currency: "GBP",
      tariff_unit: "p/(kWh/h)/h",
      tariff_rate: "0.000000000000000000000000001234",
      booked_capacity_mwh_per_h: "100.000000000000000000000000000001",
      billed_capacity_energy_mwh: "2500.000000000000000000000000000000",
      delivered_energy_mwh: "000123.4500",
      billing_start: "2026-10-24T22:00:00+00:00",
      billing_end: "2026-10-25T23:00:00+00:00",
      duration_microseconds: EXACT_DURATION_MICROSECONDS,
      duration_hours: "25",
      total_cost: EXACT_TOTAL_COST,
      cost_per_delivered_mwh: EXACT_COST_PER_DELIVERED,
      basis: {
        tariff_rate: "0.000000000000000000000000001234",
        tariff_unit: "p/(kWh/h)/h",
        booked_capacity_mwh_per_h: "100.000000000000000000000000000001",
        billed_capacity_energy_mwh: "2500.000000000000000000000000000000",
        delivered_energy_mwh: "000123.4500",
        billing_start_utc: "2026-10-24T22:00:00+00:00",
        billing_end_utc: "2026-10-25T23:00:00+00:00",
        duration_microseconds: EXACT_DURATION_MICROSECONDS,
      },
      provenance: ["operator-input:capacity-1", "tariff-sheet:uat-1"],
      source_references: ["operator-input:capacity-1", "tariff-sheet:uat-1"],
      assumptions: ["Caller-supplied tariff."],
      warnings: ["RESEARCH_ONLY_DECISION_SUPPORT_NOT_INVOICE_OR_SETTLEMENT"],
      lineage: ["capacity-billing", "capacity-billing/v1"],
      physical_readiness: "NOT_ASSESSED",
    },
    meta: {
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
    },
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

/** Run one call against a stubbed `fetch` and return the answer with what crossed the transport. */
async function callWithCapturedFetch<T>(
  answer: () => Promise<Response>,
  run: (client: CapacityBillingClient) => Promise<T>,
): Promise<CapturedCall<T>> {
  const harness = await loadApiStore();
  const client = await harness.load<CapacityBillingClient>("/src/api/client.ts");
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

test("the request crosses the transport exactly and the result keeps exact strings", async () => {
  const { result, requests } = await callWithCapturedFetch(
    () => jsonResponse(capacityBillingResponse()),
    (client) => client.api.capacityBilling(capacityBillingRequestBody()),
  );

  assert.equal(requests.length, 1);
  assert.equal(requests[0].url.pathname, "/api/research/capacity-billing");
  assert.equal(requests[0].init?.method, "POST");

  // Assert the sent bytes, not a re-stringified object: a JSON number would already have become a
  // binary float, which is exactly what this contract refuses.
  const raw = String(requests[0].init?.body);
  assert.ok(raw.includes('"0.000000000000000000000000001234"'), raw);
  assert.ok(raw.includes('"100.000000000000000000000000000001"'), raw);
  assert.ok(raw.includes('"2500.000000000000000000000000000000"'), raw);
  assert.ok(raw.includes('"000123.4500"'), raw);
  assert.ok(raw.includes('"2026-10-25T00:00:00+02:00"'), raw);

  const sent = JSON.parse(raw) as Record<string, unknown>;
  assert.deepEqual(Object.keys(sent), [
    "scenario_id",
    "tariff_id",
    "tariff_rate",
    "currency",
    "tariff_unit",
    "booked_capacity_mwh_per_h",
    "delivered_energy_mwh",
    "billed_capacity_energy_mwh",
    "billing_start",
    "billing_end",
    "source_references",
  ]);
  assert.equal(typeof sent.tariff_rate, "string");
  assert.equal(typeof sent.booked_capacity_mwh_per_h, "string");
  assert.equal(typeof sent.billed_capacity_energy_mwh, "string");
  assert.deepEqual(sent.source_references, ["tariff-sheet:uat-1", "operator-input:capacity-1"]);

  assert.equal(result.data.total_cost, EXACT_TOTAL_COST);
  assert.equal(result.data.cost_per_delivered_mwh, EXACT_COST_PER_DELIVERED);
  assert.equal(result.data.duration_microseconds, EXACT_DURATION_MICROSECONDS);
  assert.equal(result.data.duration_hours, "25");
  assert.equal(result.data.physical_readiness, "NOT_ASSESSED");
  assert.equal(result.data.billed_capacity_energy_mwh, "2500.000000000000000000000000000000");
});

test("the sandbox context is explicit: no client claim, labelled response", async () => {
  const { result, requests } = await callWithCapturedFetch(
    () => jsonResponse(capacityBillingResponse()),
    (client) => client.api.capacityBilling(capacityBillingRequestBody()),
  );

  const raw = String(requests[0].init?.body);
  const sent = JSON.parse(raw) as Record<string, unknown>;
  assert.equal("decision_context" in sent, false);
  assert.equal(raw.includes("RUNTIME_DECISION"), false);
  assert.equal(raw.includes("SANDBOX_SCENARIO"), false);

  assert.equal(result.meta.decision_context, "SANDBOX_SCENARIO");
  assert.equal(result.meta.research_only, true);
  assert.equal(result.meta.human_review_required, true);
  assert.equal(result.meta.caller_supplied, true);
  assert.equal(result.meta.references_verified, false);
  assert.equal(result.meta.booked_rights_established, false);
  assert.equal(result.meta.physical_readiness, "NOT_ASSESSED");
  assert.equal(result.meta.customer_approval, false);
});

test("a typed refusal rejects with the backend detail and nothing is swallowed", async () => {
  const refusal = {
    detail: {
      code: "capacity_billing_refused",
      message: "The shared capacity-billing engine refused the supplied inputs; nothing was computed.",
      codes: ["BILLED_CAPACITY_ENERGY_INCONSISTENT"],
      violations: [
        {
          code: "BILLED_CAPACITY_ENERGY_INCONSISTENT",
          detail: "billed_capacity_energy_mwh must equal booked capacity × actual duration",
        },
      ],
      research_only: true,
      human_review_required: true,
    },
  };

  await callWithCapturedFetch(
    () => jsonResponse(refusal, 422),
    async (client) => {
      await assert.rejects(
        () => client.api.capacityBilling(capacityBillingRequestBody()),
        (error: unknown) => {
          assert.ok(error instanceof client.ApiError);
          assert.equal(error.status, 422);
          assert.match(error.message, /^API 422: capacity_billing_refused — /);
          const detail = error.detail as { codes: string[]; violations: unknown[] };
          assert.deepEqual(detail.codes, ["BILLED_CAPACITY_ENERGY_INCONSISTENT"]);
          assert.equal(detail.violations.length, 1);
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
        () => client.api.capacityBilling(capacityBillingRequestBody()),
        /network down/,
      );
    },
  );
});

test("the method is transport only and the request type declares no authority fields", () => {
  const clientSource = readFileSync(new URL("../src/api/client.ts", import.meta.url), "utf8");
  const methodBody = clientSource.slice(
    clientSource.indexOf("capacityBilling:"),
    clientSource.indexOf("capacityBilling:") + 420,
  );
  for (const forbidden of ["localStorage", "sessionStorage", "Number(", "parseFloat", "toFixed"]) {
    assert.equal(methodBody.includes(forbidden), false, forbidden);
  }

  const requestBlock = clientSource.slice(
    clientSource.indexOf("export interface CapacityBillingRequestDTO"),
    clientSource.indexOf("export interface CapacityBillingBasisDTO"),
  );
  assert.ok(requestBlock.includes("billed_capacity_energy_mwh: string"));
  assert.ok(requestBlock.includes("billing_start: string"));
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
    (clientSource.match(/"\/research\/capacity-billing"/g) ?? []).length,
    1,
    "one typed method for the one route",
  );

  const hookSource = readFileSync(
    new URL("../src/app/model/useCapacityBilling.ts", import.meta.url),
    "utf8",
  );
  assert.match(hookSource, /api\.capacityBilling\(body, \{ signal: controller\.signal \}\)/);
  assert.match(hookSource, /capacityBillingRefusal\(error\)/);
  assert.equal(hookSource.includes("decision_context"), false);
  assert.match(hookSource, /abortRef\.current\?\.abort\(\)/, "an edit or rerun aborts the old request");
  assert.match(hookSource, /if \(sequence !== runSequence\.current\) return;/, "stale responses are ignored");
});

test("the harness keeps store modules fresh and the real client unmocked", async () => {
  const first = await loadApiStore();
  const second = await loadApiStore();

  assert.notEqual(first.store, second.store, "each load executes a fresh store module");
  assert.equal(typeof first.store.getState, "function");
  assert.equal(typeof second.store.getState, "function");

  // The store above is loaded with the mock boundary swapped in; this load is the real module.
  const client = await second.load<CapacityBillingClient>("/src/api/client.ts");
  assert.equal(typeof client.api.capacityBilling, "function");
  assert.equal(typeof client.ApiError, "function");
});
