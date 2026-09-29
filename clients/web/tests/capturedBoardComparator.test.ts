/**
 * The offline captured-board comparator must refuse what it cannot substantiate, and must never
 * echo the capture it read.
 *
 * The comparator (`scripts/uat/compareCapturedBoard.mjs`) is the safe first slice of populated
 * comparison: an operator supplies the exact market-context projection response, the collected hub
 * board (`collectQuotedBoard` shape), the displayed hub scope and their own commit/deployment
 * labels, and the tool compares board against response offline, reusing the browser sweep's own
 * `marketBoardRows`/`evaluateQuotedBoard`. These cases hold both halves to the opposite answer on
 * every way the capture can fail to substantiate a comparison: an unsupported or malformed capture,
 * absent or mixed as-of/context evidence, a non-200 answer, a price slice the cards depend on that
 * is unavailable/stale/missing/unknown/truncated, simulated rows (all-simulated vs mixed), cards
 * with no comparable prices, cards that cannot be tied to the captured rows, and a board captured
 * at another instant than the response. A pass is a bounded captured-board comparison only; the
 * summary prints counts and reason codes, never the capture's own values.
 */

import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import {
  CAPTURE_SCHEMA_VERSION,
  compareCapturedBoard,
} from "../../../scripts/uat/compareCapturedBoard.mjs";

const CLI = fileURLToPath(
  new URL("../../../scripts/uat/compareCapturedBoard.mjs", import.meta.url),
);

/** Synthetic values only: this suite never needs a customer payload. */
const CANARY = "CANARY-captured-board-7f31";
const AS_OF = "2026-09-27T04:51:52.988900+00:00";
const AS_OF_LABEL = "2026-09-27 04:51:52 UTC";
const HUB_SCOPE = ["TTF", "NBP", "THE", "PEG", "ZTP", "PSV"];

test("non-object required capture structures are invalid", () => {
  for (const key of ["source", "projection", "board"]) {
    for (const value of [null, [], "invalid", 42]) {
      const input = { ...capture(), [key]: value };
      assert.equal(compareCapturedBoard(input).verdict, "invalid", key);
    }
  }
});

/** One L1 quote, as the projection's `quotes` slice returns it. */
const QUOTE = {
  quote_id: "synthetic-quote-ttf-day-ahead",
  source_system: "EEX",
  venue: "EEX",
  hub: "TTF",
  product: "day-ahead",
  bid_price: 42.1,
  ask_price: 42.3,
  currency: "EUR",
  unit: "MWh",
  observed_at_utc: "2026-09-27T04:00:00+00:00",
  source_reference: "synthetic",
  simulated: false,
  metadata_json: {},
};

/** One normalized observation, as the projection's `normalized_quotes` slice returns it. */
const OBSERVATION = {
  observation_id: "synthetic-observation-psv-day-ahead",
  hub: "PSV",
  tenor: "day-ahead",
  is_gas_price: true,
  price: 32.4,
  currency: "EUR",
  unit: "EUR/MWh",
  source_system: "Trayport",
  market_venue: "Trayport",
  observed_at_utc: "2026-09-27T04:00:00+00:00",
  metadata_json: {},
};

function freshness(state: string) {
  return {
    state,
    basis: "observed_at_utc",
    evaluated_at_utc: AS_OF,
    last_observed_at_utc: state === "MISSING" ? null : "2026-09-27T04:00:00+00:00",
    expected_within_minutes: 60,
    expectation_source: "source_registry",
    measured: state !== "MISSING",
    derived_from: null,
  };
}

function slice(
  rows: Array<Record<string, unknown>>,
  options: { available?: boolean; state?: string; limits?: unknown } = {},
) {
  const available = options.available ?? true;
  return {
    available,
    source_references: available ? ["runtime-postgresql"] : ["runtime-db-not-configured"],
    row_count: rows.length,
    rows,
    payload: null,
    freshness: freshness(options.state ?? "FRESH"),
    entitlement: { row_filter_applied: true, filtered_out: 0, reason: "source_family" },
    context_filter: { applied: ["hub"], rule: "exact hub match" },
    limits: options.limits !== undefined ? options.limits : { row_limit: 500, truncated: false },
    warnings: [],
    notes: [],
  };
}

function marketBody(
  slices: Record<string, unknown>,
  overrides: Record<string, unknown> = {},
) {
  const timeBasis = {
    basis: "as_of_instant",
    as_of_utc: AS_OF,
    gas_day: "2026-09-27",
    gas_day_calendar: "cam.v1",
    gas_day_start_utc: "2026-09-26T22:00:00+00:00",
    gas_day_end_utc: "2026-09-27T22:00:00+00:00",
    delivery_product: "day-ahead",
    hub: null,
  };
  const data = {
    projection: "market-context",
    projection_version: "market-context.v1",
    as_of_utc: AS_OF,
    time_basis: timeBasis,
    active_context: {
      gas_day: "2026-09-27",
      gas_day_calendar: "cam.v1",
      delivery_product: "day-ahead",
      hub: null,
      as_of_utc: AS_OF,
    },
    slices,
    warnings: [],
    research_only: true,
    human_review_required: true,
    ...overrides,
  };
  return {
    data,
    meta: {
      projection: "market-context",
      projection_version: "market-context.v1",
      as_of_utc: AS_OF,
      time_basis: data.time_basis,
      research_only: true,
      human_review_required: true,
      source_references: ["runtime-postgresql"],
      warnings: [],
      table_lineage: ["market_quotes"],
    },
  };
}

function healthyBody(overrides: Record<string, unknown> = {}) {
  return marketBody(
    {
      quotes: slice([QUOTE]),
      normalized_quotes: slice([OBSERVATION]),
      ...(overrides.slices as Record<string, unknown> | undefined),
    },
    overrides,
  );
}

/** One card's collected evidence, as `collectQuotedBoard` returns it. */
function card(options: Record<string, string>) {
  return {
    recordId: options.recordId ?? "",
    slice: options.slice ?? "",
    tenor: options.tenor ?? "day-ahead",
    hub: options.hub ?? "TTF",
    priceText: options.priceText ?? "",
    metaText: options.metaText ?? "",
    sourceText: options.sourceText ?? "",
  };
}

function board(cells: Array<Record<string, string>>, overrides: Record<string, unknown> = {}) {
  return {
    boardTenor: "day-ahead",
    activeTenorTab: "day-ahead",
    asOf: AS_OF,
    asOfText: `Market context · As of ${AS_OF_LABEL} · gas day 2026-09-27`,
    cells,
    ...overrides,
  };
}

const CARDS = [
  card({
    recordId: QUOTE.quote_id,
    slice: "quotes",
    hub: "TTF",
    priceText: "42.100 / 42.300",
    metaText: "Bid/ask · EUR/MWh · Quote age 3s",
    sourceText: "EEX",
  }),
  card({
    recordId: OBSERVATION.observation_id,
    slice: "normalized_quotes",
    hub: "PSV",
    priceText: "32.40 EUR/MWh",
    metaText: "Day ahead · Quote age n/a",
    sourceText: "Trayport",
  }),
];

function capture(
  options: {
    schemaVersion?: unknown;
    source?: unknown;
    hubScope?: unknown;
    projection?: unknown;
    board?: unknown;
    extra?: Record<string, unknown>;
  } = {},
) {
  return {
    schema_version: options.schemaVersion ?? CAPTURE_SCHEMA_VERSION,
    source:
      options.source
      ?? { commit: "0123456789abcdef0123456789abcdef01234567", deployment: "synthetic-pilot" },
    hub_scope: options.hubScope ?? HUB_SCOPE,
    projection: options.projection ?? { status: 200, body: healthyBody() },
    board: options.board ?? board(CARDS),
    ...(options.extra ?? {}),
  };
}

function codes(summary: { reasons: Array<{ code: string }> }) {
  return summary.reasons.map((entry) => entry.code);
}

test("a captured board matching its response for the displayed scope passes with counts only", () => {
  const result = compareCapturedBoard(capture());

  assert.equal(result.verdict, "pass");
  assert.deepEqual(result.reasons, []);
  assert.deepEqual(result.coverage, {
    kind: "displayed_hub_scope_and_tenor",
    hubs_declared: 6,
    board_cards: 2,
    priced_cards: 2,
    comparable_rows_in_scope: 2,
    board_eligible_rows_in_scope: 2,
    simulated_rows_in_scope: 0,
    unplaceable_rows: 0,
    rows_outside_displayed_scope: 0,
    price_slices_served: 2,
    evaluator_failures: 0,
  });
  // A pass is never acceptance: the statements the comparator never verified travel with it.
  for (const statement of [
    "capture_authenticity",
    "customer_acceptance",
    "live_capture_automation",
    "pagination_beyond_captured_slice",
    "portfolio_workflow",
  ]) {
    assert.ok(result.unverified.includes(statement), statement);
  }
});

test("rows outside the displayed scope and tenor are counted, never demanded of the board", () => {
  const weekend = { ...QUOTE, quote_id: "synthetic-quote-ttf-weekend", product: "weekend" };
  const result = compareCapturedBoard(
    capture({
      projection: {
        status: 200,
        body: marketBody({
          quotes: slice([QUOTE, weekend]),
          normalized_quotes: slice([OBSERVATION]),
        }),
      },
    }),
  );

  assert.equal(result.verdict, "pass");
  assert.equal(result.coverage.comparable_rows_in_scope, 2);
  assert.equal(result.coverage.rows_outside_displayed_scope, 1);
});

test("an unsupported or malformed capture envelope is invalid, never compared", () => {
  const withoutBoard = capture();
  delete (withoutBoard as Record<string, unknown>).board;
  const withoutSchemaVersion = capture();
  delete (withoutSchemaVersion as Record<string, unknown>).schema_version;
  const cases: Array<[string, unknown, string]> = [
    ["another schema version", capture({ schemaVersion: `${CAPTURE_SCHEMA_VERSION}-next` }), "schema_version_unsupported"],
    ["no schema version", withoutSchemaVersion, "schema_version_missing"],
    ["an unknown top-level field", capture({ extra: { note: CANARY } }), "capture_field_unknown"],
    ["no board", withoutBoard, "capture_field_missing"],
    ["no source label", capture({ source: { commit: "", deployment: "synthetic-pilot" } }), "source_reference_missing"],
    ["no hub scope", capture({ hubScope: [] }), "hub_scope_missing"],
    ["a blank hub in the scope", capture({ hubScope: ["TTF", " "] }), "hub_scope_missing"],
    ["no projection status", capture({ projection: { body: healthyBody() } }), "projection_status_missing"],
    ["no board cells", capture({ board: board(CARDS, { cells: null }) }), "board_cells_missing"],
    ["a malformed card", capture({ board: board([{ ...CARDS[0], priceText: undefined }]) }), "board_cell_malformed"],
    ["a card with an unknown field", capture({ board: board([{ ...CARDS[0], extra: CANARY }]) }), "capture_field_unknown"],
    ["no board tenor", capture({ board: board(CARDS, { boardTenor: "" }) }), "board_tenor_missing"],
    ["no board as-of", capture({ board: board(CARDS, { asOf: "" }) }), "board_as_of_missing"],
  ];

  for (const [label, subject, code] of cases) {
    const result = compareCapturedBoard(subject);
    assert.equal(result.verdict, "invalid", label);
    assert.equal(result.coverage, null, label);
    assert.ok(codes(result).includes(code), `${label}: ${codes(result).join(", ")}`);
  }
});

test("absent or mixed as-of and context evidence is invalid", () => {
  const missingAsOf = healthyBody();
  delete (missingAsOf.data as Record<string, unknown>).as_of_utc;
  const mixedMeta = healthyBody();
  (mixedMeta.meta as Record<string, unknown>).as_of_utc = "2026-09-27T05:00:00Z";
  const missingBasis = healthyBody();
  delete (missingBasis.data as Record<string, unknown>).time_basis;
  const mixedContext = healthyBody();
  ((mixedContext.data as Record<string, unknown>).active_context as Record<string, unknown>)
    .as_of_utc = "2026-09-27T05:00:00Z";
  const otherGasDay = healthyBody();
  ((otherGasDay.data as Record<string, unknown>).time_basis as Record<string, unknown>)
    .gas_day = "2026-09-28";
  const otherProjection = healthyBody({
    projection: "portfolio-snapshot",
  });

  const cases: Array<[string, unknown, string]> = [
    ["no as-of", missingAsOf, "as_of_missing"],
    ["meta as-of disagreeing", mixedMeta, "as_of_mismatch"],
    ["no time basis", missingBasis, "context_missing"],
    ["an active-context as-of disagreeing", mixedContext, "as_of_mismatch"],
    ["another gas day than the time basis", otherGasDay, "context_mismatch"],
    ["another projection", otherProjection, "projection_identity_mismatch"],
  ];

  for (const [label, body, code] of cases) {
    const result = compareCapturedBoard(capture({ projection: { status: 200, body } }));
    assert.equal(result.verdict, "invalid", label);
    assert.ok(codes(result).includes(code), `${label}: ${codes(result).join(", ")}`);
  }
});

test("a non-200 answer is refused without demanding the projection body", () => {
  const result = compareCapturedBoard(
    capture({ projection: { status: 503, body: { detail: CANARY } } }),
  );

  assert.equal(result.verdict, "refused");
  assert.deepEqual(codes(result), ["projection_status_not_200"]);
  assert.equal(JSON.stringify(result).includes(CANARY), false);
});

test("a price slice the cards depend on that is unavailable is refused", () => {
  const quotesGone = compareCapturedBoard(
    capture({
      projection: {
        status: 200,
        body: marketBody({
          quotes: slice([], { available: false }),
          normalized_quotes: slice([]),
        }),
      },
      board: board([CARDS[0]]),
    }),
  );
  assert.equal(quotesGone.verdict, "refused");
  assert.ok(codes(quotesGone).includes("price_slice_unavailable"));
  assert.ok(codes(quotesGone).includes("evaluator_failure"));

  const nothingServed = compareCapturedBoard(
    capture({
      projection: {
        status: 200,
        body: marketBody({
          quotes: slice([], { available: false }),
          normalized_quotes: slice([], { available: false }),
        }),
      },
      board: board([card({ hub: "TTF", priceText: "n/a", metaText: "Day ahead" })]),
    }),
  );
  assert.equal(nothingServed.verdict, "refused");
  assert.ok(codes(nothingServed).includes("no_comparable_prices"));
  assert.ok(codes(nothingServed).includes("no_priced_cards"));
  assert.equal(nothingServed.coverage.price_slices_served, 0);
});

test("a relevant price slice that is not FRESH is refused, one code per state", () => {
  for (const state of ["STALE", "MISSING", "UNKNOWN"]) {
    const result = compareCapturedBoard(
      capture({
        projection: {
          status: 200,
          body: marketBody({
            quotes: slice([QUOTE], { state }),
            normalized_quotes: slice([OBSERVATION]),
          }),
        },
      }),
    );
    assert.equal(result.verdict, "refused", state);
    assert.deepEqual(codes(result), [`slice_freshness_${state.toLowerCase()}`], state);
  }
});

test("a truncated relevant slice is refused, and a malformed slice contract is invalid", () => {
  const truncated = compareCapturedBoard(
    capture({
      projection: {
        status: 200,
        body: marketBody({
          quotes: slice([QUOTE], { limits: { row_limit: 500, truncated: true } }),
          normalized_quotes: slice([OBSERVATION]),
        }),
      },
    }),
  );
  assert.equal(truncated.verdict, "refused");
  assert.deepEqual(codes(truncated), ["slice_truncated"]);

  const cases: Array<[string, unknown, string]> = [
    ["a price slice missing", marketBody({ normalized_quotes: slice([OBSERVATION]) }), "price_slice_missing"],
    [
      "an availability that is not a boolean",
      marketBody({ quotes: { ...slice([QUOTE]), available: "yes" }, normalized_quotes: slice([OBSERVATION]) }),
      "price_slice_malformed",
    ],
    [
      "an available slice without rows",
      marketBody({ quotes: { ...slice([QUOTE]), rows: null }, normalized_quotes: slice([OBSERVATION]) }),
      "price_slice_malformed",
    ],
    [
      "a slice without a freshness block",
      marketBody({
        quotes: { ...slice([QUOTE]), freshness: null },
        normalized_quotes: slice([OBSERVATION]),
      }),
      "slice_freshness_malformed",
    ],
    [
      "a freshness state outside the vocabulary",
      marketBody({
        quotes: slice([QUOTE], { state: "FRESHISH" }),
        normalized_quotes: slice([OBSERVATION]),
      }),
      "slice_freshness_unrecognized",
    ],
    [
      "a limits record without a boolean truncation",
      marketBody({
        quotes: slice([QUOTE], { limits: { row_limit: 500, truncated: "yes" } }),
        normalized_quotes: slice([OBSERVATION]),
      }),
      "slice_limits_malformed",
    ],
  ];

  for (const [label, body, code] of cases) {
    const result = compareCapturedBoard(capture({ projection: { status: 200, body } }));
    assert.equal(result.verdict, "invalid", label);
    assert.ok(codes(result).includes(code), `${label}: ${codes(result).join(", ")}`);
  }
});

test("simulated rows for the displayed scope are refused, all-simulated and mixed apart", () => {
  const simQuote = { ...QUOTE, source_system: "EEX_Sim", venue: "EEX_Sim" };
  const simOnly = compareCapturedBoard(
    capture({
      projection: {
        status: 200,
        body: marketBody({ quotes: slice([simQuote]), normalized_quotes: slice([]) }),
      },
      board: board([
        card({
          recordId: simQuote.quote_id,
          slice: "quotes",
          hub: "TTF",
          priceText: "42.100 / 42.300",
          metaText: "Bid/ask · EUR/MWh · Quote age 3s",
          sourceText: simQuote.source_system,
        }),
      ]),
    }),
  );
  assert.equal(simOnly.verdict, "refused");
  assert.deepEqual(codes(simOnly), ["simulated_rows"]);
  assert.equal(simOnly.coverage.simulated_rows_in_scope, 1);

  const mixed = compareCapturedBoard(
    capture({
      projection: {
        status: 200,
        body: marketBody({ quotes: slice([simQuote]), normalized_quotes: slice([OBSERVATION]) }),
      },
      board: board([{ ...CARDS[0], sourceText: simQuote.source_system }, CARDS[1]]),
    }),
  );
  assert.equal(mixed.verdict, "refused");
  assert.deepEqual(codes(mixed), ["mixed_simulated_rows"]);
  assert.equal(mixed.coverage.simulated_rows_in_scope, 1);
  assert.equal(mixed.coverage.comparable_rows_in_scope, 2);

  // The surface's own rule is a union: a `_sim` source system case-insensitively, simulated
  // metadata, or the quote payload's own flag - any of them is a simulated input.
  const metadataMarked = { ...QUOTE, metadata_json: { simulated: true } };
  const flagged = compareCapturedBoard(
    capture({
      projection: {
        status: 200,
        body: marketBody({ quotes: slice([metadataMarked]), normalized_quotes: slice([]) }),
      },
      board: board([{ ...CARDS[0] }]),
    }),
  );
  assert.equal(flagged.verdict, "refused");
  assert.deepEqual(codes(flagged), ["simulated_rows"]);

  const upperCase = { ...QUOTE, source_system: "EEX_SIM" };
  const caseInsensitive = compareCapturedBoard(
    capture({
      projection: {
        status: 200,
        body: marketBody({ quotes: slice([upperCase]), normalized_quotes: slice([]) }),
      },
      board: board([{ ...CARDS[0], sourceText: upperCase.source_system }]),
    }),
  );
  assert.equal(caseInsensitive.verdict, "refused");
  assert.deepEqual(codes(caseInsensitive), ["simulated_rows"]);
});

test("cards that cannot be tied to the captured rows are refused", () => {
  const noCards = compareCapturedBoard(capture({ board: board([]) }));
  assert.equal(noCards.verdict, "refused");
  assert.deepEqual(codes(noCards), ["evaluator_failure", "no_board_cards", "no_priced_cards"]);
  assert.equal(noCards.coverage.priced_cards, 0);

  const foreignRow = compareCapturedBoard(
    capture({ board: board([{ ...CARDS[0], recordId: "quote-from-another-read" }, CARDS[1]]) }),
  );
  assert.equal(foreignRow.verdict, "refused");
  assert.deepEqual(codes(foreignRow), ["evaluator_failure"]);
  assert.equal(foreignRow.coverage.evaluator_failures, 1);

  const missingCard = compareCapturedBoard(capture({ board: board([CARDS[0]]) }));
  assert.equal(missingCard.verdict, "refused");
  assert.deepEqual(codes(missingCard), ["evaluator_failure"]);

  const wrongPrice = compareCapturedBoard(
    capture({ board: board([{ ...CARDS[0], priceText: "44.100 / 44.300" }, CARDS[1]]) }),
  );
  assert.equal(wrongPrice.verdict, "refused");
  assert.deepEqual(codes(wrongPrice), ["evaluator_failure"]);

  const wrongSource = compareCapturedBoard(
    capture({ board: board([{ ...CARDS[0], sourceText: "ICIS" }, CARDS[1]]) }),
  );
  assert.equal(wrongSource.verdict, "refused");
  assert.deepEqual(codes(wrongSource), ["evaluator_failure"]);
});

test("a board captured at another instant than the response is refused as mixed", () => {
  const result = compareCapturedBoard(
    capture({
      board: board(CARDS, {
        asOf: "2026-09-26T09:00:00Z",
        asOfText: "Market context · As of 2026-09-26 09:00:00 UTC",
      }),
    }),
  );

  assert.equal(result.verdict, "refused");
  assert.deepEqual(codes(result), ["board_as_of_mismatch"]);
});

test("the summary prints counts and fixed codes, never the capture's own values", () => {
  const markedQuote = {
    ...QUOTE,
    quote_id: `${CANARY}-quote`,
    source_system: `${CANARY}_Sim`,
    venue: CANARY,
  };
  const markedBody = marketBody({
    quotes: slice([markedQuote]),
    normalized_quotes: slice([]),
  });
  const markedCard = card({
    recordId: `${CANARY}-quote`,
    slice: "quotes",
    hub: "TTF",
    priceText: `${CANARY} 42.100 / 42.300`,
    metaText: CANARY,
    sourceText: CANARY,
  });
  const markedCapture = capture({
    source: { commit: CANARY, deployment: CANARY },
    projection: { status: 200, body: markedBody },
    board: board([markedCard], { asOfText: CANARY }),
  });

  // Every path a value could leak through: the refusal verdict, the pass verdict (the canary is
  // also where a passing value would sit) and the invalid verdict.
  const summaries = [
    compareCapturedBoard(markedCapture),
    compareCapturedBoard(capture({ projection: { status: 503, body: markedBody } })),
    compareCapturedBoard({ ...capture(), extra: { note: CANARY } }),
  ];
  for (const summary of summaries) {
    const rendered = JSON.stringify(summary);
    assert.equal(rendered.includes(CANARY), false, rendered);
  }
  assert.equal(summaries[0].verdict, "refused");
  assert.deepEqual(codes(summaries[0]), ["evaluator_failure", "simulated_rows"]);
  for (const reason of summaries[0].reasons) {
    assert.deepEqual(Object.keys(reason).sort(), ["code", "count"]);
  }
});

/** Run the CLI as the operator would, against one file the suite owns. */
function runCli(args: string[]) {
  const result = spawnSync(process.execPath, [CLI, ...args], {
    encoding: "utf8",
    windowsHide: true,
  });
  return {
    status: result.status ?? -1,
    stdout: result.stdout ?? "",
    stderr: result.stderr ?? "",
  };
}

function withCaptureFile(contents: string, run: (file: string) => void) {
  const directory = mkdtempSync(path.join(tmpdir(), "eurogas-captured-board-"));
  try {
    const file = path.join(directory, "capture.json");
    writeFileSync(file, contents);
    run(file);
  } finally {
    rmSync(directory, { recursive: true, force: true });
  }
}

test("the CLI exits 0 on a pass and prints no capture value", () => {
  const marked = capture({
    source: { commit: CANARY, deployment: "synthetic-pilot" },
    extra: {},
  });
  withCaptureFile(JSON.stringify(marked), (file) => {
    const result = runCli([file]);

    assert.equal(result.status, 0);
    const summary = JSON.parse(result.stdout);
    assert.equal(summary.verdict, "pass");
    assert.deepEqual(summary.reasons, []);
    assert.equal(result.stderr, "");
    assert.equal(`${result.stdout}${result.stderr}`.includes(CANARY), false);
    assert.equal(result.stdout.includes(QUOTE.quote_id), false);
    assert.equal(result.stdout.includes(AS_OF), false);
  });
});

test("the CLI exits 1 on a refusal and prints no evaluator diagnostic detail", () => {
  const marked = capture({ board: board([{ ...CARDS[0], priceText: CANARY }, CARDS[1]]) });
  withCaptureFile(JSON.stringify(marked), (file) => {
    const result = runCli([file]);

    assert.equal(result.status, 1);
    const summary = JSON.parse(result.stdout);
    assert.equal(summary.verdict, "refused");
    assert.deepEqual(summary.reasons, [{ code: "evaluator_failure", count: 1 }]);
    assert.equal(`${result.stdout}${result.stderr}`.includes(CANARY), false);
  });
});

test("the CLI exits 2 on a malformed or unknown capture without echoing it", () => {
  withCaptureFile(`{"schema_version": "${CANARY}",`, (file) => {
    const result = runCli([file]);

    assert.equal(result.status, 2);
    assert.deepEqual(JSON.parse(result.stdout).reasons, [{ code: "capture_not_json", count: 1 }]);
    assert.equal(`${result.stdout}${result.stderr}`.includes(CANARY), false);
  });

  withCaptureFile(JSON.stringify({ ...capture(), extra: { note: CANARY } }), (file) => {
    const result = runCli([file]);

    assert.equal(result.status, 2);
    const summary = JSON.parse(result.stdout);
    assert.equal(summary.verdict, "invalid");
    assert.deepEqual(summary.reasons, [{ code: "capture_field_unknown", count: 1 }]);
    assert.equal(`${result.stdout}${result.stderr}`.includes(CANARY), false);
  });
});

test("the CLI refuses an invalid invocation and explains itself without a capture", () => {
  const missing = runCli([]);
  assert.equal(missing.status, 2);
  assert.deepEqual(JSON.parse(missing.stdout).reasons, [{ code: "invocation_invalid", count: 1 }]);
  assert.match(missing.stderr, /usage: node scripts\/uat\/compareCapturedBoard\.mjs/);

  const unreadable = runCli([path.join(tmpdir(), "eurogas-captured-board-absent.json")]);
  assert.equal(unreadable.status, 2);
  assert.deepEqual(JSON.parse(unreadable.stdout).reasons, [{ code: "capture_unreadable", count: 1 }]);

  const help = runCli(["--help"]);
  assert.equal(help.status, 0);
  assert.match(help.stdout, /usage: node scripts\/uat\/compareCapturedBoard\.mjs/);
  assert.match(help.stdout, new RegExp(CAPTURE_SCHEMA_VERSION.replace(/[/.]/g, "\\$&")));
  assert.equal(help.stderr, "");
});
