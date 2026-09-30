/**
 * The web transport for the shared dated cash valuation (`POST /api/research/cash-valuation`).
 *
 * This slice is the client *transport foundation* only: a typed request/result/envelope pair and
 * one API method over the existing `post` helper, auth headers, `ApiError` and research
 * conventions. There is deliberately no page, component, store slice or browser-stored cash input
 * yet - the authenticated UI is inspected before any visual change.
 *
 * The theme every test here holds is the exactness contract:
 *
 * - a financial value is a string end to end. The request is rendered from the composed body and
 *   asserted as raw text, so a value beyond JavaScript's safe integer range is shown to survive
 *   unrounded; the response keeps the engine's exact fixed-point strings instead of parsing them;
 * - the sandbox context is explicit. The request sends no `decision_context` claim at all - the
 *   backend refuses a `RUNTIME_DECISION` claim *and* forbids the field on this pydantic model
 *   (`extra_forbidden`), so the only correct claim is none; the answer's `meta` labels the run
 *   `SANDBOX_SCENARIO` and states caller-supplied / unverified / not-customer-approval;
 * - a refusal arrives with the backend's typed `detail` (`cash_valuation_refused` with the
 *   engine's stable codes), and transport failures still reject;
 * - no authority or persona field is ever composed, and the method keeps no cash inputs in
 *   browser storage.
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

/** Exact decimal strings beyond JavaScript's safe integer / float precision, one per field kind. */
const UNSAFE_SIGNED_AMOUNT = "9007199254740993.1234567890123456789012345678901234";
const UNSAFE_FX_RATE = "1.0000000000000000000000000000000000001";
const UNSAFE_DISCOUNT_FACTOR = "0.9999999999999999999999999999999999999";
const EXACT_EXPECTATION = "0.0000000000000000000000000000000000001";

interface CapturedRequest {
  readonly url: URL;
  readonly init: { method?: string; body?: unknown } | undefined;
}

interface CashValuationResultLike {
  readonly data: Record<string, unknown>;
  readonly meta: Record<string, unknown>;
}

interface CashValuationClient {
  api: {
    cashValuation(body: unknown, options?: { signal?: AbortSignal }): Promise<CashValuationResultLike>;
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

function cashValuationRequestBody(): Record<string, unknown> {
  return {
    business_context: ["portfolio:portfolio-unverified-1"],
    valuation_date: "2026-09-29",
    reporting_currency: "EUR",
    legs: [
      {
        leg_id: "pv-cash-1",
        category: "other",
        payment_date: "2026-09-29",
        signed_amount: UNSAFE_SIGNED_AMOUNT,
        currency: "EUR",
        source_reference: "synthetic-test-input:cash-1",
        description: "  trailing and leading spaces stay the caller's  ",
      },
      {
        leg_id: "hub-sale-1",
        category: "cargo_sale",
        payment_date: "2026-11-30",
        signed_amount: "150",
        currency: "USD",
        source_reference: "synthetic-test-input:sale-1",
        fx: {
          rate_reporting_per_leg: UNSAFE_FX_RATE,
          source_reference: "synthetic-test-input:fx-1",
          as_of: "2026-09-28",
        },
      },
    ],
    discount_factors: [
      {
        payment_date: "2026-09-29",
        factor: "1",
        curve_reference: "synthetic-test-curve:eur-usd-flat",
        source_reference: "synthetic-test-input:df-1",
        as_of: "2026-09-29",
      },
      {
        payment_date: "2026-11-30",
        factor: UNSAFE_DISCOUNT_FACTOR,
        curve_reference: "synthetic-test-curve:eur-usd-flat",
        source_reference: "synthetic-test-input:df-1",
        as_of: "2026-09-29",
      },
    ],
  };
}

/** Synthetic precision stress payload, not a numerical reference result from the engine. */
function cashValuationResponse(): Record<string, unknown> {
  return {
    data: {
      research_only: true,
      human_review_required: true,
      model_version: "cash-valuation/v1",
      action: "compute_cash_flow",
      business_context: ["portfolio:portfolio-unverified-1"],
      valuation_date: "2026-09-29",
      reporting_currency: "EUR",
      leg_valuations: [
        {
          leg_id: "hub-sale-1",
          category: "cargo_sale",
          payment_date: "2026-11-30",
          currency: "USD",
          signed_amount: "150",
          cash_amount_reporting_ccy: "150.0000000000000000000000000000000000150",
          present_value_reporting_ccy: EXACT_EXPECTATION,
          discount_factor: UNSAFE_DISCOUNT_FACTOR,
          discount_curve_reference: "synthetic-test-curve:eur-usd-flat",
          discount_source_reference: "synthetic-test-input:df-1",
          discount_as_of: "2026-09-29",
          source_reference: "synthetic-test-input:sale-1",
          fx_rate_reporting_per_leg: UNSAFE_FX_RATE,
          fx_source_reference: "synthetic-test-input:fx-1",
          fx_as_of: "2026-09-28",
          description: "",
        },
      ],
      total_undiscounted_cash_reporting_ccy: EXACT_EXPECTATION,
      net_present_value_reporting_ccy: EXACT_EXPECTATION,
      assumptions: ["Caller-supplied schedule."],
      warnings: ["RESEARCH_ONLY_DECISION_SUPPORT_NOT_ACCOUNTING_CUSTODY_OR_SETTLEMENT"],
      source_references: ["synthetic-test-input:df-1", "synthetic-test-input:sale-1"],
      lineage: ["cash-valuation", "cash-valuation/v1"],
    },
    meta: {
      research_only: true,
      human_review_required: true,
      decision_context: "SANDBOX_SCENARIO",
      caller_supplied: true,
      references_verified: false,
      customer_approval: false,
      source_references: ["synthetic-test-input:df-1", "synthetic-test-input:sale-1"],
      warnings: ["RESEARCH_ONLY_DECISION_SUPPORT_NOT_ACCOUNTING_CUSTODY_OR_SETTLEMENT"],
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
  run: (client: CashValuationClient) => Promise<T>,
): Promise<CapturedCall<T>> {
  const harness = await loadApiStore();
  const client = await harness.load<CashValuationClient>("/src/api/client.ts");
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

test("the request crosses the transport exactly: no decimal is parsed, rewritten or dropped", async () => {
  const { result, requests } = await callWithCapturedFetch(
    () => jsonResponse(cashValuationResponse()),
    (client) => client.api.cashValuation(cashValuationRequestBody()),
  );

  assert.equal(requests.length, 1);
  assert.equal(requests[0].url.pathname, "/api/research/cash-valuation");
  assert.equal(requests[0].init?.method, "POST");

  // The body is asserted as raw text, not as a re-stringified object: a JSON number would have
  // already become a binary float, so the assertion has to see the sent bytes.
  const raw = String(requests[0].init?.body);
  assert.ok(raw.includes(`"${UNSAFE_SIGNED_AMOUNT}"`), raw);
  assert.ok(raw.includes(`"${UNSAFE_FX_RATE}"`), raw);
  assert.ok(raw.includes(`"${UNSAFE_DISCOUNT_FACTOR}"`), raw);

  const sent = JSON.parse(raw) as {
    business_context: unknown;
    valuation_date: unknown;
    reporting_currency: unknown;
    legs: Array<Record<string, unknown>>;
    discount_factors: Array<Record<string, unknown>>;
  };
  assert.deepEqual(Object.keys(sent), [
    "business_context",
    "valuation_date",
    "reporting_currency",
    "legs",
    "discount_factors",
  ]);
  assert.equal(typeof sent.legs[0].signed_amount, "string");
  assert.equal(sent.legs[0].signed_amount, UNSAFE_SIGNED_AMOUNT);
  const fx = sent.legs[1].fx as Record<string, unknown>;
  assert.equal(typeof fx.rate_reporting_per_leg, "string");
  assert.equal(fx.rate_reporting_per_leg, UNSAFE_FX_RATE);
  assert.equal(typeof sent.discount_factors[1].factor, "string");
  assert.equal(sent.discount_factors[1].factor, UNSAFE_DISCOUNT_FACTOR);
  // The caller's text is transported, not trimmed or normalised.
  assert.equal(sent.legs[0].description, "  trailing and leading spaces stay the caller's  ");
  assert.deepEqual(sent.business_context, ["portfolio:portfolio-unverified-1"]);

  // Response strings survive transport unchanged; numerical correctness is tested server-side.
  assert.equal(result.data.net_present_value_reporting_ccy, EXACT_EXPECTATION);
  const valuedLeg = (result.data.leg_valuations as Array<Record<string, unknown>>)[0];
  assert.equal(valuedLeg.fx_rate_reporting_per_leg, UNSAFE_FX_RATE);
  assert.equal(valuedLeg.discount_factor, UNSAFE_DISCOUNT_FACTOR);
});

test("the sandbox context is explicit in the contract: no client claim, labelled response", async () => {
  const { result, requests } = await callWithCapturedFetch(
    () => jsonResponse(cashValuationResponse()),
    (client) => client.api.cashValuation(cashValuationRequestBody()),
  );

  const raw = String(requests[0].init?.body);
  const sent = JSON.parse(raw) as Record<string, unknown>;

  // The backend refuses RUNTIME_DECISION in the raw body and forbids `decision_context` on this
  // model (`extra_forbidden`), so the only safe claim is none - and none is what is sent.
  assert.equal("decision_context" in sent, false);
  assert.equal(raw.includes("RUNTIME_DECISION"), false);
  assert.equal(raw.includes("SANDBOX_SCENARIO"), false);

  // The response is where the context is stated, with the route's boundary metadata.
  assert.equal(result.meta.decision_context, "SANDBOX_SCENARIO");
  assert.equal(result.meta.research_only, true);
  assert.equal(result.meta.human_review_required, true);
  assert.equal(result.meta.caller_supplied, true);
  assert.equal(result.meta.references_verified, false);
  assert.equal(result.meta.customer_approval, false);
  assert.equal(result.data.action, "compute_cash_flow");
});

test("a typed refusal rejects with the backend detail and nothing is swallowed", async () => {
  const refusal = {
    detail: {
      code: "cash_valuation_refused",
      message:
        "The shared cash valuation engine refused the supplied inputs; nothing was computed.",
      codes: ["MODEL_VERSION_UNSUPPORTED"],
      violations: [
        { code: "MODEL_VERSION_UNSUPPORTED", detail: "model_version='cash-valuation/v2'" },
      ],
      research_only: true,
      human_review_required: true,
    },
  };

  await callWithCapturedFetch(
    () => jsonResponse(refusal, 422),
    async (client) => {
      await assert.rejects(
        () => client.api.cashValuation(cashValuationRequestBody()),
        (error: unknown) => {
          assert.ok(error instanceof client.ApiError);
          assert.equal(error.status, 422);
          // The flattened message stays `API <status>: <code> — <message>`; the raw detail keeps
          // the engine's stable codes so a governed surface renders them without re-parsing.
          assert.match(error.message, /^API 422: cash_valuation_refused — /);
          const detail = error.detail as { codes: string[] };
          assert.deepEqual(detail.codes, ["MODEL_VERSION_UNSUPPORTED"]);
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
        () => client.api.cashValuation(cashValuationRequestBody()),
        /network down/,
      );
    },
  );
});

test("no authority or persona field is authored, and no cash input is stored", async () => {
  const { requests } = await callWithCapturedFetch(
    () => jsonResponse(cashValuationResponse()),
    (client) => client.api.cashValuation(cashValuationRequestBody()),
  );

  const sent = JSON.parse(String(requests[0].init?.body)) as Record<string, unknown>;
  for (const forbidden of [
    "decision_context",
    "work_mode",
    "persona",
    "research_only",
    "human_review_required",
    "customer_approval",
  ]) {
    assert.equal(forbidden in sent, false, forbidden);
  }

  const clientSource = readFileSync(new URL("../src/api/client.ts", import.meta.url), "utf8");
  const methodBody = clientSource.slice(
    clientSource.indexOf("cashValuation:"),
    clientSource.indexOf("cashValuation:") + 400,
  );
  // The method is transport only: no storage call and no numeric parse of a financial value.
  for (const forbidden of ["localStorage", "sessionStorage", "Number(", "parseFloat", "toFixed"]) {
    assert.equal(methodBody.includes(forbidden), false, forbidden);
  }

  // The DTO declares no authority fields. Runtime enforcement remains the backend's job.
  const requestBlock = clientSource.slice(
    clientSource.indexOf("export interface CashValuationRequestDTO"),
    clientSource.indexOf("export interface CashValuationLegValuationDTO"),
  );
  assert.ok(requestBlock.includes("legs: CashValuationLegInputDTO[]"), requestBlock);
  assert.ok(requestBlock.includes("discount_factors: CashValuationDiscountFactorInputDTO[]"));
  for (const forbidden of [
    "decision_context",
    "work_mode",
    "persona",
    "research_only",
    "customer_approval",
  ]) {
    assert.equal(requestBlock.includes(forbidden), false, forbidden);
  }
});

test("the leg vocabulary is the engine's declared list and the route has one typed method", () => {
  const clientSource = readFileSync(new URL("../src/api/client.ts", import.meta.url), "utf8");

  const blockStart = clientSource.indexOf("CASH_VALUATION_LEG_CATEGORIES = [");
  const vocabularyBlock = clientSource.slice(
    blockStart,
    clientSource.indexOf("] as const;", blockStart),
  );
  const declared = [...vocabularyBlock.matchAll(/"([a-z_]+)"/g)].map((match) => match[1]);
  assert.deepEqual(declared, [
    "cargo_purchase",
    "cargo_sale",
    "shipping",
    "transport",
    "regas",
    "storage",
    "fuel",
    "demurrage",
    "boil_off",
    "other",
  ]);

  // One request path, one typed method: the engine stays the only implementation and the client
  // cannot grow a second spelling of the same route.
  assert.equal((clientSource.match(/"\/research\/cash-valuation"/g) ?? []).length, 1);
});
