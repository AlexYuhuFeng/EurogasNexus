/**
 * The web transport for captured contract revisions (`GET /api/route-cost/...`).
 *
 * This slice is transport only: two typed read methods over the existing `get` helper, the shared
 * auth headers and the standard envelope. There is deliberately no page, component or store slice -
 * the reads exist so a governed surface can cite stored evidence, not to add visual UI.
 *
 * The theme every test here holds:
 *
 * - the contract and revision ids are URL-encoded path segments, so an id can never change which
 *   contract scopes the read;
 * - the read is a bounded GET: no request body, and the page parameters travel as query values;
 * - the response is passed through unmodified. Exact decimal strings inside `snapshot` and the
 *   capture/provenance metadata stay as stored; no client arithmetic, parsing or persistence.
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

const CONTRACT_ID = "ttf supply/2025";
const REVISION_ID = "contract-revision:1";

interface CapturedRequest {
  readonly url: URL;
  readonly init: { method?: string; body?: unknown } | undefined;
}

interface ContractRevisionReadClient {
  api: {
    upstreamContractRevisions(
      contractId: string,
      params?: { limit?: number; offset?: number },
      options?: { signal?: AbortSignal },
    ): Promise<{ data: Record<string, unknown>; meta: Record<string, unknown> }>;
    upstreamContractRevision(
      contractId: string,
      contractRevisionId: string,
      options?: { signal?: AbortSignal },
    ): Promise<{ data: Record<string, unknown>; meta: Record<string, unknown> }>;
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

/** Exact decimal strings, as the stored canonical snapshot carries them. */
const REVISION = {
  contract_revision_id: REVISION_ID,
  contract_id: "ttf supply/2025",
  revision_number: 2,
  schema_version: "upstream-contract-revision/v1",
  capture_origin: "legacy_capture",
  content_hash: "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  recorded_at_utc: "2026-10-01T12:00:00+00:00",
  recorded_by: "trader-a",
  display_metadata: { contract_name: "TTF supply 2025", operator_notes: null },
  snapshot: {
    contract_price_gbp_mwh: "29.7500000000000000000000000000000000001",
    payment_terms: null,
  },
};

function historyResponse(): Record<string, unknown> {
  return {
    data: {
      scope: "UPSTREAM_CONTRACT_REVISIONS",
      data_source: "runtime-postgresql",
      contract_id: "ttf supply/2025",
      revision_count: 3,
      returned_count: 1,
      has_more: true,
      limit: 1,
      offset: 1,
      revisions: [REVISION],
    },
    meta: {
      research_only: true,
      human_review_required: true,
      source_references: ["runtime-postgresql"],
      warnings: [
        "Captured revisions are explicit capture-time evidence, not a complete history of past contract writes.",
        "Captured economics carry no payment terms or effective dates; nothing here asserts when the terms applied or when payment falls due.",
      ],
    },
  };
}

async function callWithCapturedFetch<T>(
  answer: () => Promise<Response>,
  run: (client: ContractRevisionReadClient) => Promise<T>,
): Promise<{ result: T; requests: CapturedRequest[] }> {
  const harness = await loadApiStore();
  const client = await harness.load<ContractRevisionReadClient>("/src/api/client.ts");
  const requests: CapturedRequest[] = [];
  const globals = globalThis as { fetch?: unknown };
  const previousFetch = globals.fetch;
  globals.fetch = async (input: unknown, init?: unknown) => {
    requests.push({ url: new URL(String(input)), init: init as CapturedRequest["init"] });
    return answer();
  };
  try {
    return { result: await run(client), requests };
  } finally {
    globals.fetch = previousFetch;
  }
}

test("the history read is a bounded GET with encoded contract scoping", async () => {
  const { result, requests } = await callWithCapturedFetch(
    () => jsonResponse(historyResponse()),
    (client) => client.api.upstreamContractRevisions(CONTRACT_ID, { limit: 1, offset: 1 }),
  );

  assert.equal(requests.length, 1);
  assert.equal(
    requests[0].url.pathname,
    "/api/route-cost/upstream-contracts/ttf%20supply%2F2025/revisions",
  );
  assert.equal(requests[0].url.searchParams.get("limit"), "1");
  assert.equal(requests[0].url.searchParams.get("offset"), "1");
  // A read: no method override and no request body.
  assert.equal(requests[0].init?.method, undefined);
  assert.equal(requests[0].init?.body, undefined);

  // The page passes through unmodified, including the exact stored decimal string.
  const data = result.data;
  assert.equal(data.revision_count, 3);
  assert.equal(data.has_more, true);
  const revision = (data.revisions as Array<Record<string, unknown>>)[0];
  assert.equal(revision.recorded_by, "trader-a");
  assert.equal(revision.capture_origin, "legacy_capture");
  assert.equal(revision.content_hash, REVISION.content_hash);
  const snapshot = revision.snapshot as Record<string, unknown>;
  assert.equal(snapshot.contract_price_gbp_mwh, REVISION.snapshot.contract_price_gbp_mwh);
  assert.equal(snapshot.payment_terms, null);
});

test("the single-revision read scopes both ids as encoded path segments", async () => {
  const { result, requests } = await callWithCapturedFetch(
    () =>
      jsonResponse({
        data: { ...REVISION, scope: "UPSTREAM_CONTRACT_REVISION", data_source: "runtime-postgresql" },
        meta: historyResponse().meta,
      }),
    (client) => client.api.upstreamContractRevision(CONTRACT_ID, REVISION_ID),
  );

  assert.equal(requests.length, 1);
  assert.equal(
    requests[0].url.pathname,
    "/api/route-cost/upstream-contracts/ttf%20supply%2F2025/revisions/contract-revision%3A1",
  );
  assert.equal(requests[0].url.search, "");
  assert.equal(requests[0].init?.method, undefined);
  assert.equal(requests[0].init?.body, undefined);

  assert.equal(result.data.contract_id, REVISION.contract_id);
  assert.equal(result.data.contract_revision_id, REVISION_ID);
  assert.equal(result.data.schema_version, "upstream-contract-revision/v1");
});

test("the transport is declared once, read-only and arithmetic-free", () => {
  const clientSource = readFileSync(new URL("../src/api/client.ts", import.meta.url), "utf8");

  // One spelling of each route path: no second reader can drift from the type.
  assert.equal(
    (clientSource.match(/upstream-contracts\/\$\{encodeURIComponent\(contractId\)\}\/revisions/g) ?? [])
      .length,
    2,
  );

  for (const methodName of ["upstreamContractRevisions:", "upstreamContractRevision:"]) {
    const start = clientSource.indexOf(methodName);
    assert.ok(start > 0, methodName);
    const methodBody = clientSource.slice(start, start + 700);
    for (const forbidden of ["localStorage", "sessionStorage", "Number(", "parseFloat", "toFixed"]) {
      assert.ok(!methodBody.includes(forbidden), `${methodName} must not use ${forbidden}`);
    }
  }

  // The DTOs declare the provenance fields a citation needs, and the snapshot stays opaque:
  // the stored canonical document is not re-typed (or re-computed) by the client.
  const dtoBlock = clientSource.slice(
    clientSource.indexOf("export interface UpstreamContractRevisionDTO"),
    clientSource.indexOf("export interface RouteRecommendationRequestDTO"),
  );
  for (const field of [
    "contract_revision_id: string",
    "schema_version: string",
    "capture_origin: string",
    "content_hash: string",
    "recorded_at_utc: string",
    "recorded_by: string",
    "snapshot: Record<string, unknown>",
  ]) {
    assert.ok(dtoBlock.includes(field), field);
  }
});
