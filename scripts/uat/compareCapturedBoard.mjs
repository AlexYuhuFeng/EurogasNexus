/**
 * Offline captured-board evidence comparator (WF-1, read-only, operator-supplied capture).
 *
 * This is the safe first slice of populated comparison. An operator who has already captured the
 * market cockpit's hub board and the exact `GET /api/projections/market-context` response their
 * session received can compare the two *offline*: no browser navigation, no network, no
 * credentials, no database, no seeding, no subprocess and no provider call. It reuses the harness's
 * own board evaluator (`readToRender.mjs`: `marketBoardRows` + `evaluateQuotedBoard`), so the
 * verdict is the same comparison the browser sweep performs - never a second implementation of the
 * rule.
 *
 * What it is: a capture validator and comparator. It checks that the capture carries the shape,
 * freshness, truncation and simulation evidence this comparison needs, then compares the displayed
 * cards with the rows the captured response served for the displayed hub scope and tenor.
 *
 * What it is not: proof of authenticity (the commit/deployment strings are operator labels, never
 * verified and never printed), a live capture mechanism, customer acceptance, or coverage of the
 * portfolio workflow, other hubs and tenors, later pages or non-price slices. A `pass` means *the
 * captured board matches the captured response for the displayed hub scope and tenor* - nothing
 * more (see the `unverified` list in every summary).
 *
 * Output policy: stdout carries a fixed-shape JSON summary of status, counts and reason *codes*
 * only. Raw row values, source strings, URLs, headers, cookies, ids and the evaluator's own
 * diagnostic strings are never printed - not even for a malformed capture or an internal error -
 * because a capture is sensitive local operator evidence whose detail stays with the operator.
 * Nothing is written anywhere: the tool only reads the file it is given.
 *
 * Usage: node scripts/uat/compareCapturedBoard.mjs <capture.json>
 * Exit codes: 0 = pass, 1 = refused (well-formed capture that does not support acceptance),
 * 2 = invalid (unreadable/malformed/unsupported capture, or invalid invocation).
 *
 * Captures must never be committed; keep them in access-controlled local evidence storage and
 * redact credentials before retention or sharing (pilot plan, WF-1 step 8).
 */

import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";

import { evaluateQuotedBoard, marketBoardRows } from "./readToRender.mjs";

/** The one capture schema this comparator accepts; any other value is refused. */
export const CAPTURE_SCHEMA_VERSION = "eurogas-nexus.captured-market-board/v1";

/** The projection this comparator is scoped to (the market cockpit's own read). */
const PROJECTION_ID = "market-context";

/** Largest capture this comparator will parse, in bytes; a larger file is refused unparsed. */
const MAX_CAPTURE_BYTES = 32 * 1024 * 1024;

/** The v1 capture declares exactly these keys; an unknown key is refused, never ignored. */
const CAPTURE_KEYS = ["schema_version", "source", "hub_scope", "projection", "board"];
const SOURCE_KEYS = ["commit", "deployment"];
const PROJECTION_KEYS = ["status", "body"];
const BOARD_KEYS = ["boardTenor", "activeTenorTab", "asOf", "asOfText", "cells"];
const CELL_KEYS = ["recordId", "slice", "tenor", "hub", "priceText", "metaText", "sourceText"];

/**
 * The slices the board prices from, and the board's own row marker as `collectQuotedBoard` reads
 * it.
 */
const PRICE_SLICE_KEYS = ["quotes", "normalized_quotes"];
const BOARD_ROW_SELECTORS = ['[data-record="market-hub-price"]'];

/** The projection slice contract's freshness vocabulary (`projections/freshness.py`). */
const FRESHNESS_STATES = ["FRESH", "STALE", "MISSING", "UNKNOWN"];

/**
 * Statements that hold for every verdict this tool prints. A `pass` is a bounded captured-board
 * comparison and none of these was verified by it.
 */
const UNVERIFIED = [
  "capture_authenticity",
  "customer_acceptance",
  "intended_context_selection",
  "live_capture_automation",
  "non_price_slices",
  "other_hubs_and_tenors",
  "pagination_beyond_captured_slice",
  "portfolio_workflow",
];

const USAGE = [
  "usage: node scripts/uat/compareCapturedBoard.mjs <capture.json>",
  "",
  "Offline, read-only comparison of one captured market board against the exact captured",
  `market-context projection response (capture schema ${CAPTURE_SCHEMA_VERSION}).`,
  "Reads only the given file, writes nothing, and prints one JSON summary to stdout.",
  "Exit codes: 0 = pass, 1 = refused, 2 = invalid capture or invalid invocation.",
  "A pass is a bounded captured-board comparison only, never customer acceptance.",
].join("\n");

/** Zeroed coverage: every entry counts capture structure, never a captured value. */
function emptyCounts() {
  return {
    hubs_declared: 0,
    board_cards: 0,
    priced_cards: 0,
    comparable_rows_in_scope: 0,
    board_eligible_rows_in_scope: 0,
    simulated_rows_in_scope: 0,
    unplaceable_rows: 0,
    rows_outside_displayed_scope: 0,
    price_slices_served: 0,
    evaluator_failures: 0,
  };
}

function isPlainObject(value) {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isNonEmptyString(value) {
  return typeof value === "string" && value.trim() !== "";
}

/** Epoch milliseconds of an ISO instant, or `null` when the value is absent or unusable. */
function instantMs(value) {
  if (!isNonEmptyString(value)) return null;
  const parsed = Date.parse(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function note(notes, code, count = 1) {
  notes.set(code, (notes.get(code) ?? 0) + count);
}

function noteUnknownKeys(notes, value, allowed) {
  if (!isPlainObject(value)) return;
  for (const key of Object.keys(value)) {
    if (!allowed.includes(key)) note(notes, "capture_field_unknown");
  }
}

function summarize(verdict, counts, invalid, refused) {
  const codes = new Map(invalid);
  for (const [code, count] of refused) codes.set(code, (codes.get(code) ?? 0) + count);
  return {
    comparator: "captured-market-board",
    schema_version: CAPTURE_SCHEMA_VERSION,
    verdict,
    coverage: verdict === "invalid" ? null : { kind: "displayed_hub_scope_and_tenor", ...counts },
    reasons: [...codes.entries()]
      .sort(([left], [right]) => (left < right ? -1 : left > right ? 1 : 0))
      .map(([code, count]) => ({ code, count })),
    unverified: [...UNVERIFIED],
  };
}

/**
 * Validate one parsed capture and compare its board with its response, returning the whitelisted
 * summary. Pure: no filesystem, network or process interaction.
 *
 * A capture is `invalid` when it does not declare the shape this comparator reads (unsupported or
 * missing schema version, unknown or absent critical fields, malformed slice/as-of/context
 * evidence, an unusable board). It is `refused` when the capture is well-formed but cannot support
 * the comparison: a non-200 response; a price slice the cards depend on that is unavailable,
 * truncated or not `FRESH`; simulated rows for the displayed scope; no comparable in-scope prices
 * or no card pricing one; a board captured at another instant than the response; or any failure
 * from the shared board evaluator. Only a capture with none of those is a `pass`.
 */
export function compareCapturedBoard(capture) {
  const invalid = new Map();
  const refused = new Map();
  const counts = emptyCounts();

  if (!isPlainObject(capture)) {
    note(invalid, "capture_not_object");
    return summarize("invalid", counts, invalid, refused);
  }

  // Phase one: the capture envelope itself. Everything is refused rather than guessed, so a
  // capture that does not declare the shape this comparator reads measures nothing.
  noteUnknownKeys(invalid, capture, CAPTURE_KEYS);
  if (capture.schema_version === undefined) note(invalid, "schema_version_missing");
  else if (capture.schema_version !== CAPTURE_SCHEMA_VERSION) {
    note(invalid, "schema_version_unsupported");
  }
  for (const key of CAPTURE_KEYS) {
    if (key !== "schema_version" && capture[key] === undefined) note(invalid, "capture_field_missing");
  }
  for (const key of ["source", "projection", "board"]) {
    if (!isPlainObject(capture[key])) note(invalid, "capture_structure_invalid");
  }

  const source = capture.source;
  if (isPlainObject(source)) {
    noteUnknownKeys(invalid, source, SOURCE_KEYS);
    if (!isNonEmptyString(source.commit) || !isNonEmptyString(source.deployment)) {
      note(invalid, "source_reference_missing");
    }
  }

  const hubScope = Array.isArray(capture.hub_scope)
    ? capture.hub_scope.map((hub) => (typeof hub === "string" ? hub.trim() : ""))
    : null;
  if (!hubScope || hubScope.length === 0 || hubScope.some((hub) => hub === "")) {
    note(invalid, "hub_scope_missing");
  } else {
    counts.hubs_declared = hubScope.length;
  }

  let status = null;
  if (isPlainObject(capture.projection)) {
    noteUnknownKeys(invalid, capture.projection, PROJECTION_KEYS);
    if (
      typeof capture.projection.status !== "number"
      || !Number.isInteger(capture.projection.status)
    ) {
      note(invalid, "projection_status_missing");
    } else {
      status = capture.projection.status;
    }
    if (!isPlainObject(capture.projection.body)) note(invalid, "projection_body_missing");
  }

  const board = capture.board;
  if (isPlainObject(board)) {
    noteUnknownKeys(invalid, board, BOARD_KEYS);
    if (!isNonEmptyString(board.boardTenor)) note(invalid, "board_tenor_missing");
    if (instantMs(board.asOf) === null) note(invalid, "board_as_of_missing");
    if (typeof board.activeTenorTab !== "string" || typeof board.asOfText !== "string") {
      note(invalid, "board_malformed");
    }
    if (!Array.isArray(board.cells)) {
      note(invalid, "board_cells_missing");
    } else {
      counts.board_cards = board.cells.length;
      counts.priced_cards = board.cells.filter(
        (cell) => isPlainObject(cell) && isNonEmptyString(cell.recordId),
      ).length;
      for (const cell of board.cells) {
        if (!isPlainObject(cell)) {
          note(invalid, "board_cell_malformed");
          continue;
        }
        noteUnknownKeys(invalid, cell, CELL_KEYS);
        if (CELL_KEYS.some((key) => typeof cell[key] !== "string")) {
          note(invalid, "board_cell_malformed");
        }
      }
    }
  }

  if (invalid.size > 0) return summarize("invalid", counts, invalid, refused);

  // Phase two: a non-200 answer is well-formed evidence of a refusal, not a comparable capture.
  if (status !== 200) {
    note(refused, "projection_status_not_200");
    return summarize("refused", counts, invalid, refused);
  }

  const body = capture.projection.body;
  const data = body.data;
  const meta = body.meta;
  if (!isPlainObject(data) || !isPlainObject(meta)) {
    note(invalid, "projection_body_missing");
    return summarize("invalid", counts, invalid, refused);
  }

  // The projection identity, the single as-of instant and the echoed Active Context: a capture
  // that mixes or omits these cannot state what its own rows are as of.
  if (
    !isNonEmptyString(data.projection)
    || !isNonEmptyString(meta.projection)
    || data.projection !== meta.projection
    || data.projection !== PROJECTION_ID
  ) {
    note(invalid, "projection_identity_mismatch");
  }
  const dataAsOf = instantMs(data.as_of_utc);
  const metaAsOf = instantMs(meta.as_of_utc);
  if (dataAsOf === null || metaAsOf === null) note(invalid, "as_of_missing");
  else if (dataAsOf !== metaAsOf) note(invalid, "as_of_mismatch");

  const timeBasis = data.time_basis;
  const activeContext = data.active_context;
  if (!isPlainObject(timeBasis) || !isPlainObject(activeContext)) {
    note(invalid, "context_missing");
  } else {
    if (
      !isNonEmptyString(timeBasis.basis)
      || !isNonEmptyString(timeBasis.gas_day)
      || !isNonEmptyString(activeContext.gas_day)
    ) {
      note(invalid, "context_missing");
    }
    const basisAsOf = instantMs(timeBasis.as_of_utc);
    const contextAsOf = instantMs(activeContext.as_of_utc);
    if (basisAsOf === null || contextAsOf === null) note(invalid, "context_missing");
    else if (dataAsOf !== null && (basisAsOf !== dataAsOf || contextAsOf !== dataAsOf)) {
      note(invalid, "as_of_mismatch");
    }
    if (
      isNonEmptyString(timeBasis.gas_day)
      && isNonEmptyString(activeContext.gas_day)
      && timeBasis.gas_day !== activeContext.gas_day
    ) {
      note(invalid, "context_mismatch");
    }
  }

  const slices = data.slices;
  if (!isPlainObject(slices)) {
    note(invalid, "projection_body_missing");
    return summarize("invalid", counts, invalid, refused);
  }
  const sliceStates = new Map();
  for (const key of PRICE_SLICE_KEYS) {
    const slice = slices[key];
    if (!isPlainObject(slice)) {
      note(invalid, "price_slice_missing");
      continue;
    }
    if (typeof slice.available !== "boolean") {
      note(invalid, "price_slice_malformed");
      continue;
    }
    if (slice.available && !Array.isArray(slice.rows)) {
      note(invalid, "price_slice_malformed");
      continue;
    }
    if (!isPlainObject(slice.freshness) || !isNonEmptyString(slice.freshness.state)) {
      note(invalid, "slice_freshness_malformed");
      continue;
    }
    if (!FRESHNESS_STATES.includes(slice.freshness.state)) {
      note(invalid, "slice_freshness_unrecognized");
      continue;
    }
    const limits = slice.limits;
    if (
      limits !== null
      && !(
        isPlainObject(limits)
        && typeof limits.row_limit === "number"
        && typeof limits.truncated === "boolean"
      )
    ) {
      note(invalid, "slice_limits_malformed");
      continue;
    }
    sliceStates.set(key, {
      available: slice.available,
      state: slice.freshness.state,
      truncated: isPlainObject(limits) && limits.truncated === true,
    });
  }

  if (invalid.size > 0) return summarize("invalid", counts, invalid, refused);

  // Phase three: the board must be the capture of the same instant as the response. The live sweep
  // may legitimately hold an earlier poll; a single-instant offline capture may not.
  if (instantMs(board.asOf) !== dataAsOf) {
    note(refused, "board_as_of_mismatch");
    return summarize("refused", counts, invalid, refused);
  }

  // Phase four: the comparison itself, through the harness's own board evaluator.
  const scope = new Set(hubScope.map((hub) => hub.toUpperCase()));
  const boardTenor = board.boardTenor.trim().toLowerCase();
  const market = marketBoardRows(body, { rowSelectors: BOARD_ROW_SELECTORS });
  counts.price_slices_served = market.slices.filter((slice) => slice.available).length;

  const inScope = market.rows.filter(
    (row) => row.comparable && scope.has(row.hub) && row.tenor === boardTenor,
  );
  counts.comparable_rows_in_scope = inScope.length;
  counts.board_eligible_rows_in_scope = inScope.filter((row) => row.boardEligible !== false).length;
  counts.simulated_rows_in_scope = inScope.filter((row) => row.simulated === true).length;
  counts.unplaceable_rows = market.rows.filter((row) => !row.comparable).length;
  counts.rows_outside_displayed_scope = market.rows.filter(
    (row) => row.comparable && !(scope.has(row.hub) && row.tenor === boardTenor),
  ).length;

  const namedSlices = new Set(
    board.cells
      .filter((cell) => isNonEmptyString(cell.recordId))
      .map((cell) => cell.slice.trim()),
  );
  for (const key of PRICE_SLICE_KEYS) {
    const state = sliceStates.get(key);
    if (!state) continue;
    const relevant = namedSlices.has(key)
      || (state.available && inScope.some((row) => row.slice === key));
    if (!relevant) continue;
    if (!state.available) {
      note(refused, "price_slice_unavailable");
      continue;
    }
    if (state.state !== "FRESH") note(refused, `slice_freshness_${state.state.toLowerCase()}`);
    if (state.truncated) note(refused, "slice_truncated");
  }

  if (counts.comparable_rows_in_scope === 0) note(refused, "no_comparable_prices");
  if (counts.board_cards === 0) note(refused, "no_board_cards");
  if (counts.simulated_rows_in_scope > 0) {
    note(
      refused,
      counts.simulated_rows_in_scope === counts.comparable_rows_in_scope
        ? "simulated_rows"
        : "mixed_simulated_rows",
    );
  }
  if (counts.priced_cards === 0) note(refused, "no_priced_cards");

  const compared = evaluateQuotedBoard({
    status,
    hubScope,
    board,
    slices: market.slices,
    rows: market.rows,
    problems: market.problems,
    asOf: data.as_of_utc,
    source: null,
  });
  counts.evaluator_failures = compared.failures.length;
  if (counts.evaluator_failures > 0) note(refused, "evaluator_failure");

  return summarize(refused.size > 0 ? "refused" : "pass", counts, invalid, refused);
}

function writeSummary(summary) {
  process.stdout.write(`${JSON.stringify(summary, null, 2)}\n`);
}

function invalidSummary(code) {
  return summarize("invalid", emptyCounts(), new Map([[code, 1]]), new Map());
}

function main(argv) {
  const args = argv.slice(2);
  if (args.length === 1 && (args[0] === "--help" || args[0] === "-h")) {
    process.stdout.write(`${USAGE}\n`);
    return 0;
  }
  if (args.length !== 1 || args[0].startsWith("-")) {
    process.stderr.write(`${USAGE}\n`);
    writeSummary(invalidSummary("invocation_invalid"));
    return 2;
  }

  let text;
  try {
    const raw = readFileSync(args[0]);
    if (raw.byteLength > MAX_CAPTURE_BYTES) {
      writeSummary(invalidSummary("capture_too_large"));
      return 2;
    }
    text = raw.toString("utf8");
  } catch {
    writeSummary(invalidSummary("capture_unreadable"));
    return 2;
  }

  let capture;
  try {
    capture = JSON.parse(text);
  } catch {
    writeSummary(invalidSummary("capture_not_json"));
    return 2;
  }

  let summary;
  try {
    summary = compareCapturedBoard(capture);
  } catch {
    // The summary never echoes payload detail, not even for an internal failure.
    summary = invalidSummary("comparator_error");
  }
  writeSummary(summary);
  if (summary.verdict === "pass") return 0;
  return summary.verdict === "refused" ? 1 : 2;
}

const invokedDirectly = Boolean(process.argv[1])
  && pathToFileURL(resolve(process.argv[1])).href === import.meta.url;
if (invokedDirectly) process.exitCode = main(process.argv);
