/**
 * The scoped read-to-render check must measure rows, not the page's copy.
 *
 * The whole-page heuristic it replaces (`n/a` / `unavailable` / `no data` anywhere in the first
 * 400 characters) failed the contracts and orders surfaces on CI run 35996627042 while they were
 * rendering what their reads returned: the portfolio context strip's own "stale, missing or
 * unavailable" sentence, an unmeasured portfolio total and a table's literal `n/a` empty-state
 * cells all matched. The first replacement still had to be repaired before it could be called
 * evidence: it searched every collected element across all groups, identity was display-text
 * substring matching (`contract-1` matched `contract-11`), overlapping selectors collected the
 * same element twice, its empty-state selector matched any row in the table, and a returned row
 * with no identity at all was only observed. These cases hold the scoped comparison to the
 * opposite answers on each of those.
 */

import assert from "node:assert/strict";
import test from "node:test";

import {
  collectCapacityOperatingBoard,
  collectVisibleElements,
  collectQuotedBoard,
  contrastRatio,
  displayPriceUnit,
  evaluateCapacityBoardJoin,
  evaluateCapacityBoardRecovery,
  evaluateRefusedCapacityBoard,
  evaluateRefusedRegistry,
  evaluateRegistryRecovery,
  evaluateRouteBadgeContrast,
  evaluateReadToRender,
  evaluateQuotedBoard,
  marketBoardRows,
  mountRouteBadgeFixture,
  QUOTED_PRICE_TOLERANCE,
  readGroupRows,
  removeRouteBadgeFixture,
  ROUTE_BADGE_FIXTURE_ATTRIBUTE,
  ROUTE_BADGE_MIN_CONTRAST,
  rowRecordId,
  utcInstantLabel,
} from "../../../scripts/uat/readToRender.mjs";

/** One upstream resource term, as `GET /api/route-cost/upstream-contracts` returns it. */
const CONTRACT = {
  contract_id: "preview-portfolio-contract-ttf-pool-2025",
  contract_name: "Preview TTF portfolio supply 2025",
  delivery_point_name: "TTF",
  delivery_quantity_mwh_per_day: 1_200_000,
  contract_price_gbp_mwh: 25,
};

/** One screen order, as the portfolio projection's `screen_orders` slice returns it. */
const ORDER = {
  order_observation_id: "uat-screen-order-1",
  venue: "ICE OCM",
  side: "BUY",
  hub: "NBP",
  status: "WORKING",
  remaining_quantity_mwh: 15_000,
};

/** One PnL snapshot, as the projection's `pnl_snapshots` slice returns it. */
const SNAPSHOT = {
  pnl_snapshot_id: "uat-pnl-1",
  portfolio_id: "preview-portfolio",
  valuation_basis: "MARK_TO_MARKET",
  quantity_mwh: 10_000,
};

const CONTRACTS_GROUP = {
  label: "upstream contracts",
  rowsPath: "data",
  recordIdField: "contract_id",
  rowSelectors: ['[data-record="portfolio-resource"]', '[data-record="upstream-contract"]'],
  rowLimit: 25,
};

const ORDERS_GROUP = {
  label: "screen orders",
  rowsPath: "data.slices.screen_orders",
  recordIdField: "order_observation_id",
  rowSelectors: ['[data-record="screen-order"]'],
  emptySelector: '[data-empty-state="screen-orders"]',
};

const PNL_GROUP = {
  label: "pnl snapshots",
  rowsPath: "data.slices.pnl_snapshots",
  recordIdField: "pnl_snapshot_id",
  rowSelectors: ['[data-record="pnl-snapshot"]'],
  emptySelector: '[data-empty-state="pnl-snapshots"]',
  rowLimit: 8,
};

function contractsBody(rows: Array<Record<string, unknown>>) {
  return { data: rows, meta: { source_references: ["runtime-postgresql"] } };
}

/** One glossary term, as `GET /api/glossary` returns it. */
const GLOSSARY_TERM = {
  term_id: "hub-ttf",
  term: "TTF",
  category: "hub",
  definition_en: "Title Transfer Facility, the Dutch virtual gas trading hub.",
};

/**
 * The glossary term index's scoped read group, as `browser_workflow_smoke.mjs` declares it.
 *
 * The surface carried a declared exemption until this group replaced it: "glossary terms return
 * rows while the term index renders 'Loading workspace'" (measured 2026-09-19). The whole-page
 * heuristic could neither tell a rendered index from a stale one nor see the Chinese copy at all,
 * which is what a row comparison by the term's own id fixes.
 */
const GLOSSARY_GROUP = {
  label: "glossary term index",
  rowsPath: "data",
  recordIdField: "term_id",
  rowSelectors: ['[data-record="glossary-term"]'],
  emptySelector: '[data-empty-state="glossary-terms"]',
};

/**
 * The source catalog's scoped read group, as `browser_workflow_smoke.mjs` declares it.
 *
 * The surface carried a declared exemption ("sources return rows while the administration surface
 * reports Total sources 0"), produced by a whole-page match over the page's first 400 characters.
 * `GET /api/sources` answers the whole static registry - the catalog renders every row of it - so
 * the group declares `exactRows`, while the surface's opening task (the priority queue) is a
 * filtered subset of the same read and is compared in the catalog task instead.
 */
const SOURCES_GROUP = {
  label: "registered sources",
  rowsPath: "data",
  recordIdField: "source_id",
  rowSelectors: ['[data-record="source-row"]'],
  emptySelector: '[data-empty-state="source-rows"]',
  taskTab: "source-tab-catalog",
  exactRows: true,
};

/** One registered source, as `GET /api/sources` returns it. */
const SOURCE = {
  source_id: "src-entsog",
  source_system: "ENTSOG",
  category: "infrastructure",
  entitlement_scope: "public",
};

function portfolioSnapshot(slices: Record<string, unknown>) {
  return { data: { projection: "portfolio-snapshot", slices }, meta: {} };
}

function glossaryBody(rows: Array<Record<string, unknown>>) {
  return { data: rows, meta: { source_references: ["baseline-glossary"] } };
}

function sourcesBody(rows: Array<Record<string, unknown>>) {
  return { data: rows, meta: { source: "runtime-postgresql" } };
}

/** The collector's output for one group, built directly for the decision-logic cases. */
function groupEvidence(
  group: { rowSelectors: string[] },
  recordIds: Array<string | null>,
  emptyState = false,
) {
  return {
    rowSelectors: group.rowSelectors,
    recordIds: recordIds.filter((id): id is string => id !== null),
    missingRecordIds: recordIds.filter((id) => id === null).length,
    emptyState,
  };
}

function compareContracts(rows: Array<Record<string, unknown>>, evidence: unknown[]) {
  return evaluateReadToRender({
    status: 200,
    groups: [readGroupRows(contractsBody(rows), CONTRACTS_GROUP)],
    evidence,
  });
}

function compareGlossary(rows: Array<Record<string, unknown>>, evidence: unknown[]) {
  return evaluateReadToRender({
    status: 200,
    groups: [readGroupRows(glossaryBody(rows), GLOSSARY_GROUP)],
    evidence,
  });
}

function compareSources(rows: Array<Record<string, unknown>>, evidence: unknown[]) {
  return evaluateReadToRender({
    status: 200,
    groups: [readGroupRows(sourcesBody(rows), SOURCES_GROUP)],
    evidence,
  });
}

test("only the group's own rows decide the verdict, never the page's other copy", () => {
  // The page also renders another panel's empty-state row, which has no record id and is
  // literally "n/a"; the group's selectors do not match it, so it is not evidence either way.
  const evidence = collectWithStub(CONTRACTS_GROUP, {
    '[data-record="portfolio-resource"]': [stubRow(CONTRACT.contract_id)],
    '[data-record="upstream-contract"]': [stubRow(CONTRACT.contract_id)],
    ".data-table-row:not(.header)": [stubRow(null)],
  });
  // The "n/a" row exists on the page, but the group never asked for that selector: it is not
  // collected, and its missing id is not this group's problem.
  assert.deepEqual(evidence[0].recordIds, [CONTRACT.contract_id, CONTRACT.contract_id]);
  assert.equal(evidence[0].missingRecordIds, 0);
  const result = compareContracts([CONTRACT], evidence);

  assert.deepEqual(result.failures, []);
  assert.match(
    result.observations.join(" | "),
    /1 returned row\(s\) \(200\) matched 1 rendered row\(s\) by contract_id/,
  );
});

test("a returned row the surface did not render is a missing row, named", () => {
  const second = { ...CONTRACT, contract_id: "uat-operator-easington" };
  const evidence = [groupEvidence(CONTRACTS_GROUP, [CONTRACT.contract_id])];
  const result = compareContracts([CONTRACT, second], evidence);

  assert.equal(result.failures.length, 1);
  assert.match(result.failures[0], /the read returned 2 row\(s\) \(200\) and 1 have no rendered row/);
  assert.match(result.failures[0], /uat-operator-easington/);
  assert.doesNotMatch(result.failures[0], /preview-portfolio-contract/);
});

test("a rendered id that only shares a prefix with a returned id is not that row", () => {
  // Substring identity matching read `contract-1` as present on a page that rendered only
  // `contract-11` - the false green this keeps out of the gate.
  const short = { ...CONTRACT, contract_id: "contract-1" };
  const longer = { ...CONTRACT, contract_id: "contract-11" };
  const result = compareContracts([short], [groupEvidence(CONTRACTS_GROUP, [longer.contract_id])]);

  assert.equal(result.failures.length, 1);
  assert.match(result.failures[0], /no rendered row carries their id: contract-1$/);
});

test("one group's rendered rows are not evidence for another group", () => {
  // Two reads whose rows live under two selectors. The screen-order id is on the page, but the
  // element carrying it was collected for the PnL group: identity may not be borrowed across
  // groups, which is what searching every collected element did.
  const body = portfolioSnapshot({
    screen_orders: { available: true, rows: [ORDER] },
    pnl_snapshots: { available: true, rows: [SNAPSHOT] },
  });
  const groups = [readGroupRows(body, ORDERS_GROUP), readGroupRows(body, PNL_GROUP)];
  const evidence = [
    groupEvidence(ORDERS_GROUP, []),
    groupEvidence(PNL_GROUP, [ORDER.order_observation_id, SNAPSHOT.pnl_snapshot_id]),
  ];
  const result = evaluateReadToRender({ status: 200, groups, evidence });

  assert.equal(result.failures.length, 1);
  assert.match(result.failures[0], /screen orders: the read returned 1 row\(s\) \(200\)/);
  assert.match(result.failures[0], new RegExp(ORDER.order_observation_id));
  // The group whose own evidence carries the rows is unaffected: the failure is scoping, not the
  // comparison as a whole.
  assert.doesNotMatch(result.failures.join(" | "), /pnl snapshots:/);
});

test("duplicate rows need duplicate rendered rows, and one element is one row", () => {
  const body = portfolioSnapshot({ screen_orders: { available: true, rows: [ORDER, ORDER] } });
  const oneElement = evaluateReadToRender({
    status: 200,
    groups: [readGroupRows(body, ORDERS_GROUP)],
    evidence: [groupEvidence(ORDERS_GROUP, [ORDER.order_observation_id])],
  });
  assert.equal(oneElement.failures.length, 1);
  assert.match(oneElement.failures[0], /1 have no rendered row carrying their id/);

  const twoElements = evaluateReadToRender({
    status: 200,
    groups: [readGroupRows(body, ORDERS_GROUP)],
    evidence: [
      groupEvidence(ORDERS_GROUP, [ORDER.order_observation_id, ORDER.order_observation_id]),
    ],
  });
  assert.deepEqual(twoElements.failures, []);
});

test("an empty successful response must show its declared empty state", () => {
  const emptyRead = portfolioSnapshot({ screen_orders: { available: true, rows: [] } });
  const withEmptyState = evaluateReadToRender({
    status: 200,
    groups: [readGroupRows(emptyRead, ORDERS_GROUP)],
    evidence: [groupEvidence(ORDERS_GROUP, [], true)],
  });
  assert.deepEqual(withEmptyState.failures, []);
  assert.match(
    withEmptyState.observations.join(" | "),
    /the read returned no rows \(200\) and the surface renders its declared empty state/,
  );

  const withoutEmptyState = evaluateReadToRender({
    status: 200,
    groups: [readGroupRows(emptyRead, ORDERS_GROUP)],
    evidence: [groupEvidence(ORDERS_GROUP, [])],
  });
  assert.equal(withoutEmptyState.failures.length, 1);
  assert.match(withoutEmptyState.failures[0], /shows neither rows nor its declared empty state/);
});

test("an empty read rejects stale populated rows in its own group's selector", () => {
  // The orders empty state used to be selected as "any row in the table", so a populated table
  // left over from an earlier read passed an empty check. A populated row now fails it.
  const emptyRead = portfolioSnapshot({ screen_orders: { available: true, rows: [] } });
  const stale = evaluateReadToRender({
    status: 200,
    groups: [readGroupRows(emptyRead, ORDERS_GROUP)],
    evidence: [groupEvidence(ORDERS_GROUP, [ORDER.order_observation_id], true)],
  });

  assert.equal(stale.failures.length, 1);
  assert.match(
    stale.failures[0],
    /the read returned no rows \(200\) and the surface still renders 1 populated row/,
  );
  assert.match(stale.failures[0], /stale rows are not a measured zero/);
});

test("a slice the backend did not serve is unmeasured, not a missing-row defect", () => {
  const body = portfolioSnapshot({ screen_orders: { available: false, rows: [] } });
  const result = evaluateReadToRender({
    status: 200,
    groups: [readGroupRows(body, ORDERS_GROUP)],
    evidence: [groupEvidence(ORDERS_GROUP, [])],
  });

  assert.deepEqual(result.failures, []);
  assert.match(result.observations.join(" | "), /the backend did not serve this slice/);
});

test("an empty answer says which read produced it instead of claiming a measured zero", () => {
  // A deployment with no runtime database answers 200 with no rows and names its own
  // provenance; that is not the same statement as "the deployment holds no contracts".
  const degraded = evaluateReadToRender({
    status: 200,
    groups: [
      readGroupRows({ data: [], meta: { source: "runtime-db-not-configured" } }, CONTRACTS_GROUP),
    ],
    evidence: [groupEvidence(CONTRACTS_GROUP, [])],
    source: "runtime-db-not-configured",
  });
  assert.deepEqual(degraded.failures, []);
  assert.match(
    degraded.observations.join(" | "),
    /the read returned no rows \(200, runtime-db-not-configured\) - no row was available to compare/,
  );
});

test("an aggregate payload is not a row set", () => {
  // The probe used to count any non-array body as "1 row", which is how an aggregate summary
  // became evidence of a missing row set. Declaring that path as rows must fail loudly.
  const body = portfolioSnapshot({ summary: { available: true, payload: { open_order_count: 0 } } });
  const result = evaluateReadToRender({
    status: 200,
    groups: [readGroupRows(body, { ...ORDERS_GROUP, rowsPath: "data.slices.summary" })],
    evidence: [groupEvidence(ORDERS_GROUP, [])],
  });

  assert.equal(result.failures.length, 1);
  assert.match(result.failures[0], /carries no row set at 'data\.slices\.summary'/);
});

test("a slice that serves rows without declaring availability is malformed", () => {
  const body = portfolioSnapshot({ screen_orders: { rows: [ORDER] } });
  const result = evaluateReadToRender({
    status: 200,
    groups: [readGroupRows(body, ORDERS_GROUP)],
    evidence: [groupEvidence(ORDERS_GROUP, [ORDER.order_observation_id])],
  });

  assert.equal(result.failures.length, 1);
  assert.match(result.failures[0], /carries rows without declaring whether it is available/);
});

test("a returned row with no record id fails instead of passing quietly", () => {
  // `delivery_point_name` is not this read's record id; a row that carries none used to be
  // recorded as an observation, which let a read pass with nothing compared.
  const unattributable = { delivery_point_name: "TTF" };
  const result = compareContracts([unattributable], [groupEvidence(CONTRACTS_GROUP, ["TTF"])]);

  assert.equal(result.failures.length, 1);
  assert.match(result.failures[0], /1 returned row\(s\) carry no 'contract_id'/);
  assert.equal(rowRecordId({ contract_id: "  " }, "contract_id"), null);
  assert.equal(rowRecordId({ contract_id: " contract-1 " }, "contract_id"), "contract-1");
  assert.equal(rowRecordId({ contract_id: 12 }, "contract_id"), "12");
});

test("a rendered row that carries no record id fails instead of passing quietly", () => {
  const result = compareContracts(
    [CONTRACT],
    [groupEvidence(CONTRACTS_GROUP, [null, CONTRACT.contract_id])],
  );

  assert.equal(result.failures.length, 1);
  assert.match(result.failures[0], /1 visible row\(s\) matching .* carry no data-record-id/);
});

test("a group that names no record id field, rows path or selector fails", () => {
  const groups = [
    readGroupRows(contractsBody([CONTRACT]), {
      label: "no selector",
      rowsPath: "data",
      recordIdField: "contract_id",
    }),
    readGroupRows(contractsBody([CONTRACT]), {
      label: "no id field",
      rowsPath: "data",
      rowSelectors: ['[data-record="x"]'],
    }),
  ];
  const result = evaluateReadToRender({
    status: 200,
    groups,
    evidence: [groupEvidence(CONTRACTS_GROUP, []), groupEvidence(CONTRACTS_GROUP, [])],
  });

  assert.equal(result.failures.length, 2);
  assert.match(result.failures[0], /no selector: the group declares no selector for its own rendered rows/);
  assert.match(
    result.failures[1],
    /no id field: the group declares no payload field carrying each row's record id/,
  );
});

test("evidence and groups must describe the same row groups", () => {
  const result = evaluateReadToRender({
    status: 200,
    groups: [readGroupRows(contractsBody([CONTRACT]), CONTRACTS_GROUP)],
    evidence: [],
  });

  assert.equal(result.failures.length, 1);
  assert.match(
    result.failures[0],
    /collected rendered-row evidence for 0 group\(s\) and the surface declares 1/,
  );
});

test("a read that did not answer 200 is a measurement failure, not a silent pass", () => {
  for (const status of [0, 404, 500]) {
    const result = evaluateReadToRender({ status, groups: [], evidence: [] });
    assert.equal(result.failures.length, 1);
    assert.match(result.failures[0], /read-to-render could not be measured/);
  }
});

test("a hidden row is not rendered evidence", () => {
  const hiddenByStyle = collectWithStub(ORDERS_GROUP, {
    '[data-record="screen-order"]': [stubRow(ORDER.order_observation_id, { display: "none" })],
  });
  assert.deepEqual(hiddenByStyle[0].recordIds, []);
  const hiddenBySize = collectWithStub(ORDERS_GROUP, {
    '[data-record="screen-order"]': [
      stubRow(ORDER.order_observation_id, { width: 0, height: 0 }),
    ],
  });
  assert.deepEqual(hiddenBySize[0].recordIds, []);

  const visible = collectWithStub(ORDERS_GROUP, {
    '[data-record="screen-order"]': [stubRow(ORDER.order_observation_id)],
  });
  assert.deepEqual(visible[0].recordIds, [ORDER.order_observation_id]);

  const result = evaluateReadToRender({
    status: 200,
    groups: [
      readGroupRows(
        { data: { slices: { screen_orders: { available: true, rows: [ORDER] } } } },
        ORDERS_GROUP,
      ),
    ],
    evidence: hiddenByStyle,
  });
  assert.equal(result.failures.length, 1);
  assert.match(result.failures[0], /no rendered row carries their id/);
});

test("overlapping selectors collect one element once", () => {
  // One element matched by two of a group's selectors is one row: it used to be pushed twice, so
  // a single rendered row could satisfy two returned rows.
  const element = stubRow(CONTRACT.contract_id);
  const evidence = collectWithStub(CONTRACTS_GROUP, {
    '[data-record="portfolio-resource"]': [element],
    '[data-record="upstream-contract"]': [element],
  });
  assert.deepEqual(evidence[0].recordIds, [CONTRACT.contract_id]);

  const result = compareContracts([CONTRACT, CONTRACT], evidence);
  assert.equal(result.failures.length, 1);
  assert.match(result.failures[0], /1 have no rendered row carrying their id/);
});

test("the in-page collector survives serialisation, as page.evaluate performs it", () => {
  // Playwright sends the function's own source into the page, so anything it referenced from the
  // module scope would throw there while passing in-process. The serialised copy must collect the
  // same evidence as the imported one.
  const serialised = new Function(`return (${String(collectVisibleElements)})`)() as typeof collectVisibleElements;
  const rows = collectWithStub(
    CONTRACTS_GROUP,
    { '[data-record="portfolio-resource"]': [stubRow(CONTRACT.contract_id)] },
    serialised,
  );
  assert.deepEqual(rows, [{
    rowSelectors: CONTRACTS_GROUP.rowSelectors,
    recordIds: [CONTRACT.contract_id],
    missingRecordIds: 0,
    emptyState: false,
  }]);
});

test("the glossary term index must render the terms its own read returned", () => {
  const second = { ...GLOSSARY_TERM, term_id: "hub-nbp", term: "NBP" };
  const rendered = compareGlossary(
    [GLOSSARY_TERM, second],
    [groupEvidence(GLOSSARY_GROUP, [GLOSSARY_TERM.term_id, second.term_id])],
  );
  assert.deepEqual(rendered.failures, []);
  assert.match(
    rendered.observations.join(" | "),
    /2 returned row\(s\) \(200\) matched 2 rendered row\(s\) by term_id/,
  );

  // A term the read returned that the index never rendered is the surface's defect, named by the
  // term's own id rather than by the page's copy.
  const missing = compareGlossary(
    [GLOSSARY_TERM, second],
    [groupEvidence(GLOSSARY_GROUP, [GLOSSARY_TERM.term_id])],
  );
  assert.equal(missing.failures.length, 1);
  assert.match(
    missing.failures[0],
    /glossary term index: the read returned 2 row\(s\) \(200\) and 1 have no rendered row carrying their id: hub-nbp/,
  );
});

test("a glossary card carrying another term's id does not answer the term that was read", () => {
  // The index rendering *a* term is not evidence it rendered *this* term, and an id that merely
  // shares a prefix with the returned one is a different record.
  const wrongTerm = compareGlossary(
    [GLOSSARY_TERM],
    [groupEvidence(GLOSSARY_GROUP, ["hub-nbp"])],
  );
  assert.equal(wrongTerm.failures.length, 1);
  assert.match(wrongTerm.failures[0], /no rendered row carries their id: hub-ttf$/);

  const longerId = compareGlossary(
    [{ ...GLOSSARY_TERM, term_id: "hub-ttf" }],
    [groupEvidence(GLOSSARY_GROUP, ["hub-ttf-day-ahead"])],
  );
  assert.equal(longerId.failures.length, 1);
  assert.match(longerId.failures[0], /no rendered row carries their id: hub-ttf$/);
});

test("a glossary card hidden behind a filter is not rendered evidence", () => {
  const hidden = collectWithStub(GLOSSARY_GROUP, {
    '[data-record="glossary-term"]': [stubRow(GLOSSARY_TERM.term_id, { display: "none" })],
  });
  assert.deepEqual(hidden[0].recordIds, []);
  const result = compareGlossary([GLOSSARY_TERM], hidden);
  assert.equal(result.failures.length, 1);
  assert.match(result.failures[0], /no rendered row carries their id: hub-ttf$/);

  const visible = collectWithStub(GLOSSARY_GROUP, {
    '[data-record="glossary-term"]': [stubRow(GLOSSARY_TERM.term_id)],
  });
  assert.deepEqual(visible[0].recordIds, [GLOSSARY_TERM.term_id]);
  assert.deepEqual(compareGlossary([GLOSSARY_TERM], visible).failures, []);
});

test("a glossary row the read served without its term id cannot be compared", () => {
  const result = compareGlossary(
    [{ term: "TTF", category: "hub" }],
    [groupEvidence(GLOSSARY_GROUP, [GLOSSARY_TERM.term_id])],
  );
  assert.equal(result.failures.length, 1);
  assert.match(result.failures[0], /1 returned row\(s\) carry no 'term_id'/);
});

test("the source catalog must render every row its own read returned", () => {
  const second = { ...SOURCE, source_id: "src-gie", source_system: "GIE" };
  const rendered = compareSources(
    [SOURCE, second],
    [groupEvidence(SOURCES_GROUP, [SOURCE.source_id, second.source_id])],
  );
  assert.deepEqual(rendered.failures, []);
  assert.match(
    rendered.observations.join(" | "),
    /2 returned row\(s\) \(200\) matched 2 rendered row\(s\) by source_id/,
  );

  // The surface opens on its priority queue, which filters the read down to the sources needing
  // attention. Those rows answering an unfiltered registry read is exactly the mistake the group's
  // declared task exists to prevent: the row the queue filtered out is named by its own id.
  const filteredTask = compareSources(
    [SOURCE, second],
    [groupEvidence(SOURCES_GROUP, [SOURCE.source_id])],
  );
  assert.equal(filteredTask.failures.length, 1);
  assert.match(
    filteredTask.failures[0],
    /registered sources: the read returned 2 row\(s\) \(200\) and 1 have no rendered row carrying their id: src-gie/,
  );
});

test("a row the registry read did not return fails in a group that claims the whole set", () => {
  // `exactRows` is the direction the other groups do not declare: the orders and contracts reads
  // are bounded over larger sets, so a rendered row they did not return cannot be attributed to
  // them. The source catalog claims the whole registry, so a foreign row is a failure - and it is
  // named, rather than being carried as an observation.
  const foreign = compareSources(
    [SOURCE],
    [groupEvidence(SOURCES_GROUP, [SOURCE.source_id, "src-not-registered"])],
  );
  assert.equal(foreign.failures.length, 1);
  assert.match(
    foreign.failures[0],
    /registered sources: the surface renders 1 row\(s\) its own read did not return \(200\): src-not-registered/,
  );
  // The read's own row was rendered, so this is not reported as a missing row as well.
  assert.doesNotMatch(foreign.failures[0], /no rendered row carries their id/);
});

test("a source row hidden on the page is not evidence that the catalog rendered it", () => {
  const hidden = collectWithStub(SOURCES_GROUP, {
    '[data-record="source-row"]': [stubRow(SOURCE.source_id, { display: "none" })],
  });
  assert.deepEqual(hidden[0].recordIds, []);
  const result = compareSources([SOURCE], hidden);
  assert.equal(result.failures.length, 1);
  assert.match(result.failures[0], /no rendered row carries their id: src-entsog/);

  const visible = collectWithStub(SOURCES_GROUP, {
    '[data-record="source-row"]': [stubRow(SOURCE.source_id), stubRow("src-gie")],
  });
  // The catalog rendered a second row the read did not return: both directions are measured.
  const mixed = compareSources([SOURCE], visible);
  assert.equal(mixed.failures.length, 1);
  assert.match(mixed.failures[0], /src-gie/);
});

test("the source catalog's empty state is a declared marker, not any row in the table", () => {
  const emptyRead = compareSources([], [groupEvidence(SOURCES_GROUP, [], true)]);
  assert.deepEqual(emptyRead.failures, []);
  assert.match(
    emptyRead.observations.join(" | "),
    /the read returned no rows \(200\) and the surface renders its declared empty state/,
  );

  const staleRows = compareSources(
    [],
    [groupEvidence(SOURCES_GROUP, [SOURCE.source_id], true)],
  );
  assert.equal(staleRows.failures.length, 1);
  assert.match(staleRows.failures[0], /stale rows are not a measured zero/);
});

test("a group that bounds its rows is not held to the whole row set", () => {
  // The catalog's read is unbounded; a group that mirrors a surface's own bound must not report the
  // rows beyond it as rows its read did not return.
  const bounded = { ...SOURCES_GROUP, rowLimit: 1 };
  const second = { ...SOURCE, source_id: "src-gie" };
  const result = evaluateReadToRender({
    status: 200,
    groups: [readGroupRows(sourcesBody([SOURCE, second]), bounded)],
    evidence: [groupEvidence(bounded, [SOURCE.source_id, second.source_id])],
  });
  assert.deepEqual(result.failures, []);
});

/**
 * The market hub board's quoted-value evidence.
 *
 * The market workspace carried a declared gap until this comparison replaced it: "market
 * observations return rows while every hub card renders n/a". The probe read
 * `/api/market/observations`, an endpoint the market lane does not read at all, and the verdict was
 * a whole-page match on the page's own `n/a` copy - so it could not say which hub was unpriced, and
 * it compared nothing with the market-context projection the board actually prices from. These
 * cases hold the replacement to the opposite answer on each way a board can lie about a price: a
 * wrong number, another tenor or hub, a row the read did not return, a served pair no card prices,
 * a hidden card, a missing source or unit, an as-of that is not the read's, and an unread
 * projection that must not be read as a measured zero.
 */

/** One L1 quote, as the projection's `quotes` slice returns it. */
const MARKET_QUOTE = {
  quote_id: "sim-eex-ttf-dayahead-20260927T040000",
  source_system: "EEX_Sim",
  venue: "EEX",
  instrument_id: "TTF-DA",
  hub: "TTF",
  product: "day-ahead",
  bid_price: 42.1,
  ask_price: 42.3,
  currency: "EUR",
  unit: "MWh",
  observed_at_utc: "2026-09-27T04:00:00+00:00",
};

/** One normalized observation, as the projection's `normalized_quotes` slice returns it. */
const MARKET_OBSERVATION = {
  observation_id: "sim-trayport-psv-dayahead-20260927T040000",
  hub: "PSV",
  tenor: "day-ahead",
  is_gas_price: true,
  price: 32.4,
  currency: "EUR",
  unit: "EUR/MWh",
  source_system: "Trayport_Sim",
  market_venue: "Trayport",
  observed_at_utc: "2026-09-27T04:00:00+00:00",
};

const MARKET_AS_OF = "2026-09-27T04:51:52.988900+00:00";
const MARKET_AS_OF_LABEL = "2026-09-27 04:51:52 UTC";

/** The hub scope the sweep declares, which `MAJOR_MARKET_HUBS` owns in the client. */
const MARKET_HUB_SCOPE = ["TTF", "NBP", "THE", "PEG", "ZTP", "PSV"];

function marketProjection(slices: Record<string, unknown>) {
  return { data: { as_of_utc: MARKET_AS_OF, slices }, meta: { source: "runtime-postgresql" } };
}

/** One card's collected evidence, as `collectQuotedBoard` returns it. */
function marketCard(options: Record<string, string>) {
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

function marketBoard(cells: Array<Record<string, string>>, overrides: Record<string, unknown> = {}) {
  return {
    boardTenor: "day-ahead",
    activeTenorTab: "day-ahead",
    asOf: MARKET_AS_OF,
    asOfText: `Market context · As of ${MARKET_AS_OF_LABEL} · gas day 2026-09-27`,
    cells,
    ...overrides,
  };
}

function compareMarket(
  body: unknown,
  board: unknown,
  options: { status?: number; hubScope?: string[] } = {},
) {
  const market = marketBoardRows(body, {
    rowSelectors: ['[data-record="market-hub-price"]'],
  });
  return evaluateQuotedBoard({
    status: options.status ?? 200,
    hubScope: options.hubScope ?? MARKET_HUB_SCOPE,
    board,
    slices: market.slices,
    rows: market.rows,
    problems: market.problems,
    asOf: MARKET_AS_OF,
    source: "runtime-postgresql",
  });
}

/** The quote card and the normalized card the board renders for the two served pairs. */
const MARKET_CARDS = [
  marketCard({
    recordId: MARKET_QUOTE.quote_id,
    slice: "quotes",
    hub: "TTF",
    priceText: "42.100 / 42.300",
    metaText: "Bid/ask · EUR/MWh · Quote age 3s",
    sourceText: "EEX_Sim",
  }),
  marketCard({
    recordId: MARKET_OBSERVATION.observation_id,
    slice: "normalized_quotes",
    hub: "PSV",
    priceText: "32.40 EUR/MWh",
    metaText: "Day ahead · Quote age n/a",
    sourceText: "Trayport_Sim",
  }),
];

const MARKET_BODY = marketProjection({
  quotes: { available: true, rows: [MARKET_QUOTE] },
  normalized_quotes: { available: true, rows: [MARKET_OBSERVATION] },
});

test("the hub board is held to the rows it priced, one card per declared hub", () => {
  const result = compareMarket(MARKET_BODY, marketBoard(MARKET_CARDS));

  assert.deepEqual(result.failures, []);
  assert.match(result.observations.join(" | "), /the board priced 2 of its 6 declared hub\(s\)/);
  assert.match(result.observations.join(" | "), /the surface states the projection's as-of/);
});

test("a card that shows another number than the row it names fails, naming both", () => {
  const wrongPrice = [
    { ...MARKET_CARDS[0], priceText: "44.100 / 44.300" },
    MARKET_CARDS[1],
  ];
  const result = compareMarket(MARKET_BODY, marketBoard(wrongPrice));

  assert.equal(result.failures.length, 1);
  assert.match(result.failures[0], /hub card TTF shows 44\.1, 44\.3/);
  assert.match(result.failures[0], new RegExp(`row '${MARKET_QUOTE.quote_id}' carries 42\\.1, 42\\.3`));
});

test("a card that prices another tenor, hub or row than it declares fails", () => {
  // Another tenor than the board displays: the card would be a price for a chart the operator is
  // not looking at.
  const otherTenor = compareMarket(
    MARKET_BODY,
    marketBoard([{ ...MARKET_CARDS[0], tenor: "weekend" }, MARKET_CARDS[1]]),
  );
  assert.match(
    otherTenor.failures.join(" | "),
    /hub card TTF declares the tenor 'weekend' while the board prices 'day-ahead'/,
  );

  // A row that belongs to another hub: the id is real, the pair it is shown under is not.
  const otherHub = compareMarket(
    MARKET_BODY,
    marketBoard([{ ...MARKET_CARDS[0], hub: "NBP" }, MARKET_CARDS[1]]),
  );
  assert.match(
    otherHub.failures.join(" | "),
    new RegExp(`hub card NBP prices NBP day-ahead from row '${MARKET_QUOTE.quote_id}'`),
  );
  assert.match(otherHub.failures.join(" | "), /places on TTF day-ahead/);

  // A row this read did not return: a stale, other-context or foreign price.
  const foreignRow = compareMarket(
    MARKET_BODY,
    marketBoard([
      { ...MARKET_CARDS[0], recordId: "quote-from-another-read" },
      MARKET_CARDS[1],
    ]),
  );
  assert.match(foreignRow.failures.join(" | "), /this read did not return/);
  assert.match(foreignRow.failures.join(" | "), /quote-from-another-read/);
});

test("a served pair the board does not price is a missing row, and an unpriced pair is honest", () => {
  // The read served TTF day-ahead and PSV day-ahead; the board prices only TTF.
  const missing = compareMarket(MARKET_BODY, marketBoard([MARKET_CARDS[0]]));
  assert.equal(missing.failures.length, 1);
  assert.match(
    missing.failures[0],
    /the read served 1 row\(s\) for PSV day-ahead \(200\) and the price board renders no card/,
  );

  // The board renders the card but prices nothing on it, while the read served that pair a row.
  const unpriced = compareMarket(
    MARKET_BODY,
    marketBoard([MARKET_CARDS[0], { ...MARKET_CARDS[1], recordId: "", slice: "" }]),
  );
  assert.equal(unpriced.failures.length, 1);
  assert.match(unpriced.failures[0], /hub card PSV: the read served 1 row\(s\) for PSV day-ahead/);
  assert.match(unpriced.failures[0], /the card prices none of them/);

  // A hub the read did not serve has nothing to price: "not served" is not a measured zero and the
  // card that states it is not a failure.
  const unserved = compareMarket(
    MARKET_BODY,
    marketBoard([
      MARKET_CARDS[0],
      MARKET_CARDS[1],
      { ...marketCard({ hub: "NBP", priceText: "n/a", metaText: "Day ahead · Quote age n/a" }) },
    ]),
  );
  assert.deepEqual(unserved.failures, []);
  assert.match(unserved.observations.join(" | "), /the read served no row for NBP day-ahead/);
});

test("an unread projection is not a measured zero", () => {
  const unread = compareMarket(MARKET_BODY, marketBoard(MARKET_CARDS), { status: 503 });
  assert.equal(unread.failures.length, 1);
  assert.match(unread.failures[0], /answered 503; the quoted-value comparison could not be measured/);

  // Neither price slice served: an unmeasured market, reported as such - not as a board of zeros.
  const unserved = compareMarket(
    marketProjection({
      quotes: { available: false, rows: [] },
      normalized_quotes: { available: false, rows: [] },
    }),
    marketBoard([]),
  );
  assert.deepEqual(unserved.failures, []);
  assert.match(unserved.observations.join(" | "), /neither the quote nor the normalized price slice/);
});

test("the board is not held to rows its own price rule excludes", () => {
  // A non-gas row on a declared hub and the displayed tenor - a pence-per-therm NBP observation,
  // for instance: the terminal prices gas prices only (`is_gas_price`, the backend's own flag), so
  // the board owes that pair no card, and a card that prices it anyway fails.
  const therm = {
    ...MARKET_OBSERVATION,
    observation_id: "sim-trayport-nbp-therm-20260927T040000",
    hub: "NBP",
    is_gas_price: false,
    price: 48.1,
    currency: "GBp",
    unit: "GBp/therm",
  };
  const body = marketProjection({
    quotes: { available: true, rows: [] },
    normalized_quotes: { available: true, rows: [therm] },
  });

  const cardless = compareMarket(
    body,
    marketBoard([marketCard({ hub: "NBP", priceText: "n/a" })]),
  );
  assert.deepEqual(cardless.failures, []);
  assert.match(
    cardless.observations.join(" | "),
    /excluded by the board's own price rule \(is_gas_price\)/,
  );

  const priced = compareMarket(
    body,
    marketBoard([
      marketCard({
        hub: "NBP",
        recordId: therm.observation_id,
        slice: "normalized_quotes",
        priceText: "48.10 GBp/therm",
        metaText: "Day ahead · Quote age n/a",
        sourceText: therm.source_system,
      }),
    ]),
  );
  assert.equal(priced.failures.length, 1);
  assert.match(priced.failures[0], /which the board's own gas-price rule excludes/);
});

test("a card's source, unit and the surface's as-of are held to the read", () => {
  const wrongSource = compareMarket(
    MARKET_BODY,
    marketBoard([{ ...MARKET_CARDS[0], sourceText: "ICIS_Sim" }, MARKET_CARDS[1]]),
  );
  assert.equal(wrongSource.failures.length, 1);
  assert.match(wrongSource.failures[0], /attributes the price to 'ICIS_Sim'/);
  assert.match(wrongSource.failures[0], /carries 'EEX_Sim'/);

  const withoutUnit = compareMarket(
    MARKET_BODY,
    marketBoard([
      {
        ...MARKET_CARDS[0],
        metaText: "Bid/ask · Quote age 3s",
      },
      MARKET_CARDS[1],
    ]),
  );
  assert.equal(withoutUnit.failures.length, 1);
  assert.match(withoutUnit.failures[0], /without displaying its unit 'EUR\/MWh'/);

  const staleAsOf = compareMarket(
    MARKET_BODY,
    marketBoard(MARKET_CARDS, { asOfText: "Market context · As of 2026-09-26 09:00:00 UTC" }),
  );
  assert.equal(staleAsOf.failures.length, 1);
  assert.match(staleAsOf.failures[0], /the surface states as-of 'Market context · As of 2026-09-26/);
  assert.match(staleAsOf.failures[0], new RegExp(MARKET_AS_OF_LABEL));

  const noAsOf = compareMarket(
    MARKET_BODY,
    marketBoard(MARKET_CARDS, { asOf: "", asOfText: "" }),
  );
  assert.equal(noAsOf.failures.length, 1);
  assert.match(noAsOf.failures[0], /the surface states no as-of instant/);

  const earlierReading = compareMarket(
    MARKET_BODY,
    marketBoard(MARKET_CARDS, {
      asOf: "2026-09-26T09:00:00Z",
      asOfText: "Market context · As of 2026-09-26 09:00:00 UTC",
    }),
  );
  assert.deepEqual(earlierReading.failures, [], "polling reads need not have identical as-of instants");
});

test("a hidden card is not evidence, and its pair is then unpriced", () => {
  const evidence = collectQuotedBoardWithStub({
    cards: [
      stubMarketCard({
        recordId: MARKET_QUOTE.quote_id,
        slice: "quotes",
        hub: "TTF",
        priceText: "42.100 / 42.300",
        metaText: "Bid/ask · EUR/MWh · Quote age 3s",
        sourceText: "EEX_Sim",
      }),
      stubMarketCard({
        recordId: MARKET_OBSERVATION.observation_id,
        slice: "normalized_quotes",
        hub: "PSV",
        hidden: true,
      }),
    ],
  });
  assert.equal(evidence.cells.length, 1);
  assert.equal(evidence.boardTenor, "day-ahead");
  assert.equal(evidence.activeTenorTab, "day-ahead");
  assert.equal(evidence.asOf, MARKET_AS_OF);

  const result = compareMarket(MARKET_BODY, evidence);
  assert.equal(result.failures.length, 1);
  assert.match(result.failures[0], /the read served 1 row\(s\) for PSV day-ahead/);
});

test("the quoted-value mirrors follow the client's own unit and instant rules", () => {
  // The component composes the unit it prints and the instant it displays; these two mirrors are
  // what lets the sweep hold the *visible* text to the row's currency/unit and the read's as-of.
  // `tests/contract/test_browser_probe_paths.py` holds them to the component.
  assert.equal(displayPriceUnit("EUR", "MWh"), "EUR/MWh");
  assert.equal(displayPriceUnit("eur", "EUR/MWh"), "EUR/MWh");
  assert.equal(displayPriceUnit("", ""), null);
  assert.equal(utcInstantLabel(MARKET_AS_OF), MARKET_AS_OF_LABEL);
  assert.equal(utcInstantLabel("not-a-time"), null);
  // The price tolerance is the surface's own display precision (two decimals), not a roundness
  // allowance: half of the last displayed digit.
  assert.equal(QUOTED_PRICE_TOLERANCE, 0.005);
});

/** Minimal element/document stubs: `collectVisibleElements` runs in the page and in here. */
interface StubElement {
  textContent: string;
  recordId: string | null;
  ownerDocument: { defaultView: { getComputedStyle: () => { display: string; visibility: string } } };
  getBoundingClientRect: () => { width: number; height: number };
  getAttribute: (name: string) => string | null;
}

function stubRow(
  recordId: string | null,
  options: { display?: string; visibility?: string; width?: number; height?: number } = {},
): StubElement {
  const style = {
    display: options.display ?? "block",
    visibility: options.visibility ?? "visible",
  };
  return {
    textContent: recordId ?? "",
    recordId,
    ownerDocument: { defaultView: { getComputedStyle: () => style } },
    getBoundingClientRect: () => ({ width: options.width ?? 240, height: options.height ?? 20 }),
    getAttribute: (name: string) => (name === "data-record-id" ? recordId : null),
  };
}

function collectWithStub(
  group: { rowSelectors: string[]; emptySelector?: string },
  matches: Record<string, StubElement[]>,
  collector: typeof collectVisibleElements = collectVisibleElements,
) {
  const page = {
    ...stubRow(null, { width: 1440, height: 900 }),
    querySelectorAll: (selector: string) => matches[selector] ?? [],
  };
  const previous = (globalThis as { document?: unknown }).document;
  (globalThis as { document?: unknown }).document = {
    querySelectorAll: (selector: string) => (selector === ".workspace-page" ? [page] : []),
  };
  try {
    return collector({
      groups: [
        {
          rowSelectors: group.rowSelectors,
          emptySelector: group.emptySelector ?? null,
        },
      ],
    });
  } finally {
    (globalThis as { document?: unknown }).document = previous;
  }
}

/** One hub card stub for `collectQuotedBoard`: declarations, copy and visibility. */
function stubMarketCard(options: {
  recordId?: string;
  slice?: string;
  tenor?: string;
  hub?: string;
  priceText?: string;
  metaText?: string;
  sourceText?: string;
  hidden?: boolean;
}) {
  const style = { display: options.hidden ? "none" : "block", visibility: "visible" };
  const parts: Record<string, { textContent: string }> = {
    "[data-price-hub-label]": { textContent: options.hub ?? "" },
    "[data-price-value]": { textContent: options.priceText ?? "" },
    "[data-price-meta]": { textContent: options.metaText ?? "" },
    "[data-price-source]": { textContent: options.sourceText ?? "" },
  };
  return {
    textContent: "",
    ownerDocument: { defaultView: { getComputedStyle: () => style } },
    getBoundingClientRect: () => ({
      width: options.hidden ? 0 : 240,
      height: options.hidden ? 0 : 96,
    }),
    getAttribute: (name: string) => {
      if (name === "data-record-id") return options.recordId ?? null;
      if (name === "data-record-slice") return options.slice ?? null;
      if (name === "data-price-tenor") return options.tenor ?? "day-ahead";
      return null;
    },
    querySelector: (selector: string) => parts[selector] ?? null,
  };
}

/**
 * Run `collectQuotedBoard` against a stub displayed page, the way `collectWithStub` exercises the
 * group collector: the market board's evidence is collected in the page too, so its own hidden-card
 * and declaration rules are tested here rather than only in a browser.
 */
function collectQuotedBoardWithStub(spec: {
  cards: Array<ReturnType<typeof stubMarketCard>>;
  boardTenor?: string;
  activeTenorTab?: string;
  asOf?: string;
  asOfText?: string;
}) {
  const board = {
    textContent: "",
    getAttribute: (name: string) => (name === "data-board-tenor" ? spec.boardTenor ?? "day-ahead" : null),
  };
  const tab = {
    textContent: "",
    getAttribute: (name: string) => (name === "data-tenor" ? spec.activeTenorTab ?? "day-ahead" : null),
  };
  const asOf = {
    textContent: spec.asOfText ?? `As of ${MARKET_AS_OF_LABEL}`,
    getAttribute: (name: string) => (name === "data-projection-as-of" ? spec.asOf ?? MARKET_AS_OF : null),
  };
  const page = {
    ...stubRow(null, { width: 1440, height: 900 }),
    querySelector: (selector: string) => {
      if (selector === '[data-market-board="hub-prices"]') return board;
      if (selector === '.market-tenor-tab[aria-pressed="true"]') return tab;
      if (selector === "[data-projection-as-of]") return asOf;
      return null;
    },
    querySelectorAll: (selector: string) =>
      selector === '[data-record="market-hub-price"]' ? spec.cards : [],
  };
  const previous = (globalThis as { document?: unknown }).document;
  (globalThis as { document?: unknown }).document = {
    querySelectorAll: (selector: string) => (selector === ".workspace-page" ? [page] : []),
  };
  try {
    return collectQuotedBoard();
  } finally {
    (globalThis as { document?: unknown }).document = previous;
  }
}

/** What the surface reported while the harness refused its registry read. */
const REFUSED_REGISTRY_OK = {
  state: "failed",
  failedNotice: true,
  rows: 0,
  measuredEmpty: 0,
  kpiStrips: 0,
  retryControls: 1,
  retryDisabled: false,
};

test("a refused registry read passes only when the surface states it and measures nothing", () => {
  // The state the surface owes for a read that did not answer: its own failure, its own retry,
  // and nothing that reads as a count.
  assert.deepEqual(evaluateRefusedRegistry(REFUSED_REGISTRY_OK), []);

  // The recorded defect: a measured zero for a read that never answered. A surface that reports
  // any other state fails by name, including "ready" and the states that mean "no reading".
  for (const state of ["ready", "empty", "pending", "unread", ""]) {
    const failures = evaluateRefusedRegistry({ ...REFUSED_REGISTRY_OK, state });
    assert.equal(failures.length, 1, state);
    assert.match(failures[0], /reports '(ready|empty|pending|unread|\(no state\))'/);
  }
  assert.match(
    evaluateRefusedRegistry({}).join(" | "),
    /reports '\(no state\)'/,
    "a surface that reports nothing is a failure, not a pass",
  );

  // Each measurement a surface could still present is its own failure.
  assert.match(
    evaluateRefusedRegistry({ ...REFUSED_REGISTRY_OK, failedNotice: false }).join(" | "),
    /no failure notice/,
  );
  assert.match(
    evaluateRefusedRegistry({ ...REFUSED_REGISTRY_OK, kpiStrips: 1 }).join(" | "),
    /1 KPI strip/,
  );
  assert.match(
    evaluateRefusedRegistry({ ...REFUSED_REGISTRY_OK, rows: 3 }).join(" | "),
    /3 source row/,
  );
  assert.match(
    evaluateRefusedRegistry({ ...REFUSED_REGISTRY_OK, measuredEmpty: 1 }).join(" | "),
    /measured-empty marker/,
  );

  // The retry is the surface's own control, offered and enabled while no attempt is in flight.
  assert.match(
    evaluateRefusedRegistry({ ...REFUSED_REGISTRY_OK, retryControls: 0 }).join(" | "),
    /offers no retry/,
  );
  assert.match(
    evaluateRefusedRegistry({ ...REFUSED_REGISTRY_OK, retryDisabled: true }).join(" | "),
    /disabled while no retry is in flight/,
  );
  // Every defect is reported at once: one repair must not hide the next.
  assert.equal(
    evaluateRefusedRegistry({
      state: "empty",
      failedNotice: false,
      rows: 2,
      measuredEmpty: 1,
      kpiStrips: 1,
      retryControls: 0,
      retryDisabled: null,
    }).length,
    6,
  );
});

test("a recovered registry renders exactly its own read, with the failed notice gone", () => {
  const wanted = ["ENTSOG", "GIE", "ICE"];
  assert.deepEqual(
    evaluateRegistryRecovery({ failedNotice: false, recordIds: ["GIE", "ICE", "ENTSOG"] }, wanted),
    [],
    "order is the surface's business; identity is the check's",
  );
  assert.match(
    evaluateRegistryRecovery({ failedNotice: true, recordIds: wanted }, wanted).join(" | "),
    /notice survives/,
  );
  assert.match(
    evaluateRegistryRecovery({ failedNotice: false, recordIds: ["ENTSOG"] }, wanted).join(" | "),
    /does not render 2 source\(s\) its own read returned/,
  );
  assert.match(
    evaluateRegistryRecovery({ failedNotice: false, recordIds: [...wanted, "EEX"] }, wanted)
      .join(" | "),
    /renders 1 source\(s\) its read did not return/,
  );
  // One element is one row: a duplicated rendering is not a match for a single returned row.
  assert.match(
    evaluateRegistryRecovery({ failedNotice: false, recordIds: ["ENTSOG", "ENTSOG"] }, ["ENTSOG"])
      .join(" | "),
    /read did not return/,
  );
  // A surface that never recovered is named for what it does not render.
  assert.match(
    evaluateRegistryRecovery({ failedNotice: false, recordIds: [] }, wanted).join(" | "),
    /does not render 3 source\(s\)/,
  );
});

/** What the operating board reported while the harness refused its capacity read. */
const REFUSED_CAPACITY_OK = {
  state: "failed",
  noticePresent: true,
  noticeState: "failed",
  noticeText: "Operating board read The board's flow and capacity reads did not answer",
  vocabulary: "Capacity observations · Backend rejected the read",
  rows: 0,
  measuredEmpty: 0,
  filterNoMatch: 0,
  kpiStrips: 0,
  retryControls: 1,
  retryDisabled: false,
};

test("a refused capacity read passes only when the board states it and measures nothing", () => {
  // The board's two honest answers: no rows held (failed), or the answered read's rows with the
  // incompleteness stated (partial).
  assert.deepEqual(evaluateRefusedCapacityBoard(REFUSED_CAPACITY_OK), []);
  assert.deepEqual(
    evaluateRefusedCapacityBoard({
      ...REFUSED_CAPACITY_OK,
      state: "partial",
      noticeState: "partial",
      rows: 3,
    }),
    [],
    "a joined board may keep the answered read's rows, explicitly incomplete",
  );

  // The recorded defect: a board that reads as a measured zero for a read that never answered. A
  // board reporting any other state fails by name, including the states that mean "no reading".
  for (const state of ["ready", "empty", "pending", "unread", ""]) {
    const failures = evaluateRefusedCapacityBoard({ ...REFUSED_CAPACITY_OK, state, noticeState: state });
    assert.equal(failures.length, 1, state);
    assert.match(failures[0], /reports '(ready|empty|pending|unread|\(no state\))'/);
  }
  assert.match(
    evaluateRefusedCapacityBoard({}).join(" | "),
    /reports '\(no state\)'/,
    "a board that reports nothing is a failure, not a pass",
  );

  // A board that states the failure through another element, or states nothing at all, fails.
  assert.match(
    evaluateRefusedCapacityBoard({
      ...REFUSED_CAPACITY_OK,
      noticePresent: false,
      noticeState: "",
    }).join(" | "),
    /declares '\(none\)'/,
  );
  assert.match(
    evaluateRefusedCapacityBoard({ ...REFUSED_CAPACITY_OK, noticeText: "   " }).join(" | "),
    /no failure notice/,
  );
  assert.match(
    evaluateRefusedCapacityBoard({ ...REFUSED_CAPACITY_OK, vocabulary: "" }).join(" | "),
    /names no endpoint/,
  );

  // Every claim a refused board could still present is its own failure.
  assert.match(
    evaluateRefusedCapacityBoard({ ...REFUSED_CAPACITY_OK, rows: 2 }).join(" | "),
    /2 operating row\(s\) for a read that did not answer/,
  );
  assert.match(
    evaluateRefusedCapacityBoard({ ...REFUSED_CAPACITY_OK, measuredEmpty: 1 }).join(" | "),
    /measured-empty marker/,
  );
  assert.match(
    evaluateRefusedCapacityBoard({ ...REFUSED_CAPACITY_OK, filterNoMatch: 1 }).join(" | "),
    /filter result/,
  );
  assert.match(
    evaluateRefusedCapacityBoard({ ...REFUSED_CAPACITY_OK, kpiStrips: 1 }).join(" | "),
    /1 KPI strip/,
  );
  assert.match(
    evaluateRefusedCapacityBoard({ ...REFUSED_CAPACITY_OK, retryControls: 0 }).join(" | "),
    /offers no retry/,
  );
  assert.match(
    evaluateRefusedCapacityBoard({ ...REFUSED_CAPACITY_OK, retryDisabled: true }).join(" | "),
    /disabled while no retry is in flight/,
  );

  // Every defect is reported at once: one repair must not hide the next.
  assert.equal(
    evaluateRefusedCapacityBoard({
      state: "ready",
      noticePresent: false,
      noticeState: "",
      noticeText: "",
      vocabulary: "",
      rows: 2,
      measuredEmpty: 1,
      filterNoMatch: 1,
      kpiStrips: 1,
      retryControls: 0,
      retryDisabled: null,
    }).length,
    8,
  );
});

test("a recovered capacity board states the reading its two reads support", () => {
  const measuredEmpty = {
    state: "empty",
    noticePresent: false,
    noticeState: "",
    noticeText: "",
    vocabulary: "",
    rows: 0,
    measuredEmpty: 1,
    filterNoMatch: 0,
    kpiStrips: 1,
    retryControls: 0,
    retryDisabled: null,
  };
  assert.deepEqual(
    evaluateCapacityBoardRecovery(measuredEmpty, { capacityRows: 0, flowsRows: 0 }),
    [],
    "both reads answered with no row: the board declares a measured empty result",
  );
  assert.deepEqual(
    evaluateCapacityBoardRecovery(
      { ...measuredEmpty, state: "ready", rows: 2, measuredEmpty: 0 },
      { capacityRows: 1, flowsRows: 2 },
    ),
    [],
    "either read's rows make the joined board ready",
  );

  // A state the reads do not support fails, naming both counts.
  const wrongState = evaluateCapacityBoardRecovery(
    { ...measuredEmpty, measuredEmpty: 0, rows: 1 },
    { capacityRows: 3, flowsRows: 0 },
  );
  assert.equal(wrongState.length, 1);
  assert.match(wrongState[0], /answered 3 capacity and 0 flow row\(s\).*'empty' instead of 'ready'/);
  assert.match(
    evaluateCapacityBoardRecovery(
      { ...measuredEmpty, state: "ready", rows: 1, measuredEmpty: 0 },
      { capacityRows: 0, flowsRows: 0 },
    ).join(" | "),
    /'ready' instead of 'empty'/,
  );
  // The two reads could not be read at all: the comparison fails rather than passing quietly.
  assert.match(
    evaluateCapacityBoardRecovery(measuredEmpty, { capacityRows: null, flowsRows: 0 }).join(" | "),
    /could not be read/,
  );

  // The failed state's own furniture must be gone.
  assert.match(
    evaluateCapacityBoardRecovery({ ...measuredEmpty, noticePresent: true }, { capacityRows: 0, flowsRows: 0 }).join(" | "),
    /notice survives/,
  );
  assert.match(
    evaluateCapacityBoardRecovery({ ...measuredEmpty, retryControls: 1 }, { capacityRows: 0, flowsRows: 0 }).join(" | "),
    /retry control survives/,
  );
  // A measured zero and a filter result are separate answers, in both directions.
  assert.match(
    evaluateCapacityBoardRecovery(
      { ...measuredEmpty, state: "ready", rows: 1, measuredEmpty: 1 },
      { capacityRows: 1, flowsRows: 0 },
    ).join(" | "),
    /measured-empty marker while its reads served rows/,
  );
  assert.match(
    evaluateCapacityBoardRecovery({ ...measuredEmpty, measuredEmpty: 0 }, { capacityRows: 0, flowsRows: 0 }).join(" | "),
    /does not declare its measured empty state/,
  );
  assert.match(
    evaluateCapacityBoardRecovery({ ...measuredEmpty, filterNoMatch: 1 }, { capacityRows: 0, flowsRows: 0 }).join(" | "),
    /filter result/,
  );
  // A measured board states its counts again, and a board with rows renders them.
  assert.match(
    evaluateCapacityBoardRecovery({ ...measuredEmpty, kpiStrips: 0 }, { capacityRows: 0, flowsRows: 0 }).join(" | "),
    /states no measurement/,
  );
  assert.match(
    evaluateCapacityBoardRecovery(
      { ...measuredEmpty, state: "ready", rows: 0, measuredEmpty: 0 },
      { capacityRows: 2, flowsRows: 0 },
    ).join(" | "),
    /renders none of them/,
  );
});

/** One element stub carrying only what the board collector reads from the page. */
function stubBoardElement(options: { attributes?: Record<string, string>; text?: string } = {}) {
  return {
    textContent: options.text ?? "",
    getAttribute: (name: string) => options.attributes?.[name] ?? null,
  };
}

/**
 * Run `collectCapacityOperatingBoard` against a stub displayed page, the way the collectors above
 * are exercised: the board's evidence is collected in the page, so the markers it reads must be
 * the surface's declared ones rather than any row or copy the page happens to carry.
 */
function collectCapacityBoardWithStub(spec: {
  state?: string;
  notice?: { state: string; text: string } | null;
  rows?: number;
  rowIds?: string[];
  hiddenRowIds?: string[];
  count?: string;
  pageStart?: string;
  filters?: string;
  sort?: string;
  measuredEmpty?: number;
  filterNoMatch?: number;
  kpiStrips?: number;
  retryDisabled?: boolean | null;
  visible?: boolean;
}) {
  const element = (attributes: Record<string, string>, text = "", hidden = false) => ({
    ...stubBoardElement({ attributes, text }),
    ownerDocument: {
      defaultView: {
        getComputedStyle: () => ({ display: hidden ? "none" : "block", visibility: "visible" }),
      },
    },
    getBoundingClientRect: () => (hidden ? { width: 0, height: 0 } : { width: 120, height: 24 }),
  });
  const noticeElement = spec.notice
    ? element({ "data-capacity-notice": spec.notice.state }, spec.notice.text)
    : null;
  const retryElement = spec.retryDisabled === undefined
    ? null
    : { ...element({ "data-capacity-board-retry": "true" }), disabled: spec.retryDisabled ?? false };
  const spread = (count: number) => Array.from({ length: count }, () => element({}));
  const page = {
    ...element({}),
    getBoundingClientRect: () => ({
      width: spec.visible === false ? 0 : 1440,
      height: spec.visible === false ? 0 : 900,
    }),
    querySelector: (selector: string) => {
      if (selector === "[data-capacity-read-state]") {
        return element({ "data-capacity-read-state": spec.state ?? "" });
      }
      if (selector === "[data-capacity-notice]") return noticeElement;
      if (selector === ".capacity-board-vocabulary") {
        return spec.notice ? element({}, spec.notice.text) : null;
      }
      if (selector === "[data-capacity-board-retry]") return retryElement;
      if (selector === "[data-capacity-board-count]") {
        return spec.count === undefined
          ? null
          : element({ "data-capacity-board-count": "999/999" }, spec.count);
      }
      if (selector === "[data-capacity-page-start]") {
        return spec.pageStart === undefined
          ? null
          : element({ "data-capacity-page-start": spec.pageStart });
      }
      if (selector === "[data-capacity-board-filters]") {
        return spec.filters === undefined
          ? null
          : element({ "data-capacity-board-filters": spec.filters });
      }
      if (selector === "[data-capacity-board-sort]") {
        return spec.sort === undefined
          ? null
          : element({ "data-capacity-board-sort": spec.sort });
      }
      return null;
    },
    querySelectorAll: (selector: string) => {
      if (selector === '[data-record="capacity-point"]') {
        return [
          ...(spec.rowIds ?? []).map((id) => element({ "data-record-id": id })),
          ...(spec.hiddenRowIds ?? []).map((id) => element({ "data-record-id": id }, "", true)),
          ...spread(spec.rows ?? 0),
        ];
      }
      if (selector === '[data-empty-state="capacity-operating-points"]') return spread(spec.measuredEmpty ?? 0);
      if (selector === '[data-empty-state="capacity-filter-no-match"]') return spread(spec.filterNoMatch ?? 0);
      if (selector === ".capacity-kpi-strip") return spread(spec.kpiStrips ?? 0);
      if (selector === "[data-capacity-board-retry]") return retryElement ? [retryElement] : [];
      return [];
    },
  };
  const previous = (globalThis as { document?: unknown }).document;
  (globalThis as { document?: unknown }).document = {
    querySelectorAll: (selector: string) => (selector === ".workspace-page" ? [page] : []),
  };
  try {
    return collectCapacityOperatingBoard();
  } finally {
    (globalThis as { document?: unknown }).document = previous;
  }
}

test("the operating board's own markers are what the sweep reads", () => {
  const collected = collectCapacityBoardWithStub({
    state: "partial",
    notice: { state: "partial", text: "One of the board's two reads did not answer." },
    rows: 4,
    kpiStrips: 0,
    retryDisabled: false,
  });
  assert.equal(collected?.state, "partial");
  assert.equal(collected?.noticePresent, true);
  assert.equal(collected?.noticeState, "partial");
  assert.match(collected?.noticeText ?? "", /did not answer/);
  assert.equal(collected?.rows, 4);
  assert.equal(collected?.kpiStrips, 0);
  assert.equal(collected?.retryDisabled, false);
  assert.deepEqual(evaluateRefusedCapacityBoard(collected), []);

  // The measured-empty and filter markers are collected separately, and a board without them
  // reports no marker rather than the page's copy.
  const measured = collectCapacityBoardWithStub({
    state: "empty",
    notice: null,
    measuredEmpty: 1,
    kpiStrips: 1,
  });
  assert.equal(measured?.measuredEmpty, 1);
  assert.equal(measured?.filterNoMatch, 0);
  assert.equal(measured?.noticePresent, false);
  assert.deepEqual(evaluateCapacityBoardRecovery(measured, { capacityRows: 0, flowsRows: 0 }), []);

  // A hidden page is not evidence at all.
  assert.equal(collectCapacityBoardWithStub({ state: "ready", visible: false }), null);

  // The joined comparison's evidence is the board's own declared markers: the count it states,
  // its filter and sort context, and the visible rows that carry their own record id. A hidden
  // row, or a row element with no id, is not evidence for a joined key.
  const joined = collectCapacityBoardWithStub({
    state: "ready",
    notice: null,
    rowIds: ["de-nl-obbicht:entry"],
    hiddenRowIds: ["be-de-zeebrugge:exit"],
    rows: 2,
    count: "3/3",
    pageStart: "0",
    filters: "none",
    sort: "attention",
    kpiStrips: 1,
  });
  assert.deepEqual(joined?.recordIds, ["de-nl-obbicht:entry"]);
  assert.equal(joined?.missingRecordIds, 2);
  assert.equal(joined?.count, "3/3");
  assert.equal(joined?.pageStart, "0");
  assert.equal(joined?.filters, "none");
  assert.equal(joined?.sort, "attention");
});

/**
 * The capacity operating board's joined-row evidence.
 *
 * The board is a union of the flow and capacity reads keyed `point_id:direction`
 * (`CapacityWorkspace.buildOperatingRows`), so comparing it with either read alone would judge a
 * correctly rendered board by the wrong row list - which is why its whole-page exemption outlived
 * the row-comparison milestones. `evaluateCapacityBoardJoin` holds the board to the union's keys,
 * the total it declares and the visible page it renders, without re-deriving the component's
 * utilization, posture or sort arithmetic. These are the negative cases: a missing, foreign,
 * hidden, duplicated or unidentifiable row, a read the runtime did not answer, a count that is not
 * the joined total, and a page the reads cannot account for all fail by name.
 */

/** One physical flow observation, as `GET /api/physical/flows` answers with it. */
const FLOW_OBS = {
  observation_id: "uat-flow-1",
  point_id: "de-nl-obbicht",
  point_name: "Obbicht",
  direction: "entry",
  flow_mcm_d: 12.5,
};

/** One capacity observation, as `GET /api/physical/capacity` answers with it. */
const CAPACITY_OBS = {
  observation_id: "uat-capacity-1",
  point_id: "de-nl-obbicht",
  point_name: "Obbicht",
  direction: "entry",
  capacity_type: "Firm Technical",
  capacity_mcm_d: 20,
};

/** The envelope both physical reads answer with; the fallback names a source of its own. */
function physicalBody(rows: Array<Record<string, unknown>>, source = "runtime-postgresql") {
  return {
    data: rows,
    meta: { source_references: [source], warnings: [] },
  };
}

/** The board's own evidence, as `collectCapacityOperatingBoard` collects it. */
function capacityBoard(
  options: {
    state?: string;
    recordIds?: string[];
    count?: string | null;
    pageStart?: string;
    filters?: string;
    sort?: string;
    notice?: boolean;
    retryControls?: number;
    measuredEmpty?: number;
    filterNoMatch?: number;
    kpiStrips?: number;
  } = {},
) {
  return {
    state: options.state ?? "ready",
    noticePresent: options.notice ?? false,
    noticeState: options.notice ? options.state ?? "ready" : "",
    noticeText: "",
    vocabulary: "",
    rows: options.recordIds?.length ?? 0,
    recordIds: options.recordIds ?? [],
    missingRecordIds: 0,
    count: options.count === undefined ? "0/0" : options.count,
    pageStart: options.pageStart ?? "0",
    filters: options.filters ?? "none",
    sort: options.sort ?? "attention",
    measuredEmpty: options.measuredEmpty ?? 0,
    filterNoMatch: options.filterNoMatch ?? 0,
    kpiStrips: options.kpiStrips ?? 1,
    retryControls: options.retryControls ?? 0,
    retryDisabled: null,
  };
}

/** The two reads the board joins, each with its own status and source. */
function capacityReads(
  flows: Array<Record<string, unknown>>,
  capacity: Array<Record<string, unknown>>,
  options: { flowsSource?: string; flowsStatus?: number } = {},
) {
  return [
    {
      lane: "flows",
      label: "flows",
      path: "/api/physical/flows",
      status: options.flowsStatus ?? 200,
      body: physicalBody(flows, options.flowsSource),
    },
    {
      lane: "capacity",
      label: "capacity",
      path: "/api/physical/capacity",
      status: 200,
      body: physicalBody(capacity),
    },
  ];
}

const JOIN_PAGE_SIZE = 50;

test("the operating board is held to the union of its two reads, not to either row list", () => {
  const flows = [
    FLOW_OBS,
    { ...FLOW_OBS, observation_id: "uat-flow-2", point_id: "be-de-zeebrugge", direction: "exit" },
  ];
  const capacity = [
    CAPACITY_OBS,
    { ...CAPACITY_OBS, observation_id: "uat-capacity-2", point_id: "nl-uk-bbl", direction: "entry" },
  ];
  const compared = evaluateCapacityBoardJoin({
    reads: capacityReads(flows, capacity),
    pageSize: JOIN_PAGE_SIZE,
    board: capacityBoard({
      recordIds: ["de-nl-obbicht:entry", "be-de-zeebrugge:exit", "nl-uk-bbl:entry"],
      count: "3/3",
    }),
  });
  assert.deepEqual(compared.failures, []);
  assert.match(compared.observations.join(" | "), /joined 3 key\(s\)/);
  // The summary says which it measured: a populated union is not an empty fixture.
  assert.match(compared.observations.join(" | "), /populated union/);

  // A key only one read served is the board's to render in either direction: the capacity-only
  // key is not missing because the capacity read is not the board's row list.
  const flowOnly = evaluateCapacityBoardJoin({
    reads: capacityReads(flows, []),
    pageSize: JOIN_PAGE_SIZE,
    board: capacityBoard({
      recordIds: ["de-nl-obbicht:entry", "be-de-zeebrugge:exit"],
      count: "2/2",
    }),
  });
  assert.deepEqual(flowOnly.failures, []);
  assert.match(flowOnly.observations.join(" | "), /joined 2 key\(s\)/);
});

test("a joined key the board does not render is a missing row, and a key neither read joined is foreign", () => {
  const missing = evaluateCapacityBoardJoin({
    reads: capacityReads(
      [FLOW_OBS, { ...FLOW_OBS, observation_id: "uat-flow-2", direction: "exit" }],
      [],
    ),
    pageSize: JOIN_PAGE_SIZE,
    board: capacityBoard({ recordIds: ["de-nl-obbicht:entry"], count: "2/2" }),
  }).failures.join(" | ");
  assert.match(missing, /does not render 1 joined key\(s\)/);
  assert.match(missing, /de-nl-obbicht:exit/);

  const foreign = evaluateCapacityBoardJoin({
    reads: capacityReads([FLOW_OBS], []),
    pageSize: JOIN_PAGE_SIZE,
    board: capacityBoard({ recordIds: ["de-nl-obbicht:entry", "fr-es-foreign:exit"], count: "2/2" }),
  }).failures.join(" | ");
  assert.match(foreign, /renders 1 row\(s\) neither read joined/);
  assert.match(foreign, /fr-es-foreign:exit/);
});

test("an empty runtime answer is a measured empty only when the board states it", () => {
  const empty = evaluateCapacityBoardJoin({
    reads: capacityReads([], []),
    pageSize: JOIN_PAGE_SIZE,
    board: capacityBoard({ state: "empty", count: "0/0", measuredEmpty: 1 }),
  });
  assert.deepEqual(empty.failures, []);
  assert.match(empty.observations.join(" | "), /both reads answered 0 row\(s\)/);
  assert.match(empty.observations.join(" | "), /not populated acceptance/);

  const stateOf = (overrides: Parameters<typeof capacityBoard>[0]) =>
    evaluateCapacityBoardJoin({
      reads: capacityReads([], []),
      pageSize: JOIN_PAGE_SIZE,
      board: capacityBoard({ state: "empty", count: "0/0", measuredEmpty: 1, ...overrides }),
    }).failures.join(" | ");
  assert.match(stateOf({ state: "ready" }), /reports 'ready' instead of 'empty'/);
  assert.match(stateOf({ measuredEmpty: 0 }), /does not declare its measured empty state/);
  assert.match(stateOf({ filterNoMatch: 1 }), /filter result/);
  assert.match(stateOf({ kpiStrips: 0 }), /states no measurement/);
  assert.match(stateOf({ recordIds: ["de-nl-obbicht:entry"] }), /renders 1 visible row\(s\)/);
});

test("a read the runtime database did not answer cannot pass as a measured board", () => {
  const fallback = evaluateCapacityBoardJoin({
    reads: capacityReads([], [], { flowsSource: "runtime-db-not-configured" }),
    pageSize: JOIN_PAGE_SIZE,
    board: capacityBoard({ state: "empty", count: "0/0", measuredEmpty: 1 }),
  }).failures.join(" | ");
  assert.match(fallback, /runtime-db-not-configured/);
  assert.match(fallback, /rather than the runtime database/);

  const refused = evaluateCapacityBoardJoin({
    reads: capacityReads([FLOW_OBS], [], { flowsStatus: 503 }),
    pageSize: JOIN_PAGE_SIZE,
    board: capacityBoard({ recordIds: ["de-nl-obbicht:entry"], count: "1/1" }),
  }).failures.join(" | ");
  assert.match(refused, /flows: the read answered 503/);

  const noRowSet = evaluateCapacityBoardJoin({
    reads: [{ lane: "flows", label: "flows", status: 200, body: { meta: {} } }],
    pageSize: JOIN_PAGE_SIZE,
    board: capacityBoard(),
  }).failures.join(" | ");
  assert.match(noRowSet, /carries no row set 'data'/);

  const unkeyed = evaluateCapacityBoardJoin({
    reads: capacityReads([{ ...FLOW_OBS, direction: "" }], []),
    pageSize: JOIN_PAGE_SIZE,
    board: capacityBoard(),
  }).failures.join(" | ");
  assert.match(unkeyed, /no point_id\/direction/);
});

test("the board's stated total is the joined key count, and a page is verified as the bounded slice it is", () => {
  for (const reads of [[], capacityReads([], []).slice(0, 1), [capacityReads([], [])[0], capacityReads([], [])[0]]]) {
    const result = evaluateCapacityBoardJoin({
      reads,
      pageSize: 50,
      board: capacityBoard({ state: "empty", measuredEmpty: 1 }),
    });
    assert.match(result.failures.join(" | "), /exactly one flows and one capacity read/);
  }
  const unionRows = Array.from({ length: 60 }, (_, index) => ({
    ...FLOW_OBS,
    observation_id: `uat-flow-${index}`,
    point_id: `point-${index}`,
  }));
  const firstPage = unionRows.slice(0, 50).map((row) => `${row.point_id}:entry`);
  const bounded = evaluateCapacityBoardJoin({
    reads: capacityReads(unionRows, []),
    pageSize: JOIN_PAGE_SIZE,
    board: capacityBoard({ recordIds: firstPage, count: "60/60" }),
  });
  assert.deepEqual(bounded.failures, []);
  assert.match(bounded.observations.join(" | "), /joined 60 key\(s\)/);
  assert.match(bounded.observations.join(" | "), /first declared page of 50/);

  const shortPage = evaluateCapacityBoardJoin({
    reads: capacityReads(unionRows, []),
    pageSize: JOIN_PAGE_SIZE,
    board: capacityBoard({ recordIds: firstPage.slice(0, 49), count: "60/60" }),
  }).failures.join(" | ");
  assert.match(shortPage, /holds 50 of 60 joined key\(s\) and it renders 49 visible row\(s\)/);

  const wrongTotal = evaluateCapacityBoardJoin({
    reads: capacityReads([FLOW_OBS], []),
    pageSize: JOIN_PAGE_SIZE,
    board: capacityBoard({ recordIds: ["de-nl-obbicht:entry"], count: "2/2" }),
  }).failures.join(" | ");
  assert.match(wrongTotal, /joined 1 key\(s\) and the board states 2 operating point\(s\)/);

  const duplicates = evaluateCapacityBoardJoin({
    reads: capacityReads([FLOW_OBS], []),
    pageSize: JOIN_PAGE_SIZE,
    board: capacityBoard({
      recordIds: ["de-nl-obbicht:entry", "de-nl-obbicht:entry"],
      count: "1/1",
    }),
  }).failures.join(" | ");
  assert.match(duplicates, /renders 1 duplicate operating row identity\(ies\)/);

  const narrowed = evaluateCapacityBoardJoin({
    reads: capacityReads(
      [FLOW_OBS, { ...FLOW_OBS, observation_id: "uat-flow-2", direction: "exit" }],
      [],
    ),
    pageSize: JOIN_PAGE_SIZE,
    board: capacityBoard({ recordIds: ["de-nl-obbicht:entry"], count: "1/2" }),
  }).failures.join(" | ");
  assert.match(narrowed, /states 1 of 2 operating point\(s\) while it declares no filter applied/);

  const undeclared = evaluateCapacityBoardJoin({
    reads: capacityReads([FLOW_OBS], []),
    pageSize: JOIN_PAGE_SIZE,
    board: capacityBoard({ recordIds: ["de-nl-obbicht:entry"], count: null }),
  }).failures.join(" | ");
  assert.match(undeclared, /states no joined count/);

  // The compared slice is declared, not assumed: an undeclared page start fails, and a page the
  // reads cannot place first is not accepted as the first page.
  const unplaced = evaluateCapacityBoardJoin({
    reads: capacityReads([FLOW_OBS], []),
    pageSize: JOIN_PAGE_SIZE,
    board: capacityBoard({ recordIds: ["de-nl-obbicht:entry"], count: "1/1", pageStart: "" }),
  }).failures.join(" | ");
  assert.match(unplaced, /does not declare the page of joined keys it rendered/);
  const laterPage = evaluateCapacityBoardJoin({
    reads: capacityReads(unionRows, []),
    pageSize: JOIN_PAGE_SIZE,
    board: capacityBoard({ recordIds: firstPage, count: "60/60", pageStart: "50" }),
  }).failures.join(" | ");
  assert.match(laterPage, /renders the page starting at row 50/);
});

test("the board's filter and sort context is captured, and a board that failed while its reads answered fails", () => {
  const base = { reads: capacityReads([FLOW_OBS], []), pageSize: JOIN_PAGE_SIZE };
  const stateOf = (overrides: Parameters<typeof capacityBoard>[0]) =>
    evaluateCapacityBoardJoin({
      ...base,
      board: capacityBoard({ recordIds: ["de-nl-obbicht:entry"], count: "1/1", ...overrides }),
    }).failures.join(" | ");
  assert.match(stateOf({ filters: "" }), /does not declare its filter context/);
  assert.match(stateOf({ filters: "applied" }), /filters were applied/);
  assert.match(stateOf({ sort: "" }), /does not declare the sort/);
  for (const state of ["failed", "partial", "pending", "unread"]) {
    assert.match(stateOf({ state }), new RegExp(`reports '${state}'`), state);
  }
  assert.match(stateOf({ notice: true }), /states a read failure while both of its reads answered/);
  assert.match(stateOf({ retryControls: 1 }), /offers its retry control/);

  const unbound = evaluateCapacityBoardJoin({
    reads: capacityReads([FLOW_OBS], []),
    pageSize: 0,
    board: capacityBoard(),
  }).failures.join(" | ");
  assert.match(unbound, /declares no page size/);

  const unboarded = evaluateCapacityBoardJoin({
    reads: capacityReads([FLOW_OBS], []),
    pageSize: JOIN_PAGE_SIZE,
    board: null,
  }).failures.join(" | ");
  assert.match(unboarded, /no displayed workspace page carried the operating board/);
});

/**
 * The route-state badge fixture: the pill markup the map overlay renders, mounted with the
 * app's own labels and measured (CI 36428725740: the Chinese candidate pill was white on
 * `#0ea5e9`, 2.77 against the required 4.5). The verdict below is what the sweep records, so
 * each way a badge can hide - no fixture, no state, no text, wrong text, a translucent or
 * failing background, an overlapping or clipped or off-screen pill, two states sharing a
 * background - gets the failing answer rather than a pass.
 */

const BADGE_LABELS: Record<string, string> = {
  allocated: "Allocated",
  candidate: "Candidate",
  blocked: "Blocked",
};

const BADGE_BACKGROUNDS: Record<string, string> = {
  allocated: "rgb(15, 118, 110)",
  candidate: "rgb(3, 105, 161)",
  blocked: "rgb(146, 64, 14)",
};

interface BadgePillMeasurement {
  state: string;
  text: string;
  color: string;
  backgroundColor: string;
  fontSize: string;
  fontWeight: string;
  display: string;
  visibility: string;
  opacity: string;
  clientWidth: number;
  clientHeight: number;
  scrollWidth: number;
  scrollHeight: number;
  box: { x: number; y: number; width: number; height: number };
}

/** One pill measurement, shaped like `mountRouteBadgeFixture`'s, before an override. */
function badgePill(
  state: keyof typeof BADGE_LABELS,
  overrides: Partial<BadgePillMeasurement> = {},
): BadgePillMeasurement {
  const index = ["allocated", "candidate", "blocked"].indexOf(state);
  return {
    state,
    text: BADGE_LABELS[state],
    color: "rgb(255, 255, 255)",
    backgroundColor: BADGE_BACKGROUNDS[state],
    fontSize: "10px",
    fontWeight: "800",
    display: "block",
    visibility: "visible",
    opacity: "1",
    clientWidth: 60,
    clientHeight: 16,
    scrollWidth: 60,
    scrollHeight: 16,
    box: { x: 10 + index * 70, y: 10, width: 60, height: 16 },
    ...overrides,
  };
}

function badgeFixture(states: BadgePillMeasurement[] = [
  badgePill("allocated"),
  badgePill("candidate"),
  badgePill("blocked"),
]) {
  return {
    mounted: true,
    container: { box: { x: 8, y: 8, width: 220, height: 28 } },
    viewport: { width: 1440, height: 900 },
    states,
  };
}

test("the badge verdict passes the product's own colours and reports what it measured", () => {
  const verdict = evaluateRouteBadgeContrast({ fixture: badgeFixture(), labels: BADGE_LABELS });
  assert.deepEqual(verdict.failures, []);
  assert.equal(verdict.observations.length, 3);
  assert.match(
    verdict.observations.join(" | "),
    /the candidate pill renders 'Candidate' at rgb\(255, 255, 255\) on rgb\(3, 105, 161\)/,
  );
  // The verdict's own minimum is the product's, not a number a caller can lower.
  assert.equal(ROUTE_BADGE_MIN_CONTRAST, 4.5);
});

test("the badge verdict fails the CI defect and every way a badge can hide", () => {
  const failureOf = (states: BadgePillMeasurement[]) =>
    evaluateRouteBadgeContrast({ fixture: badgeFixture(states), labels: BADGE_LABELS })
      .failures.join(" | ");

  // White on `#0ea5e9` is the measured 2.77 from CI 36428725740; the same contrast function
  // answers it, so a green verdict cannot be a verdict that cannot see the defect.
  assert.ok(Math.abs((contrastRatio("#ffffff", "#0ea5e9") as number) - 2.77) < 0.01);
  assert.match(
    failureOf([
      badgePill("allocated"),
      badgePill("candidate", { backgroundColor: "rgb(14, 165, 233)" }),
      badgePill("blocked"),
    ]),
    /the candidate pill's text is 2\.77:1/,
  );

  // Data variation cannot hide the candidate: a missing state is a failure by name, not a pass.
  assert.match(
    failureOf([badgePill("allocated"), badgePill("blocked")]),
    /rendered no candidate pill/,
  );
  // A translucent background would make the ratio unmeasurable; it is refused, not approximated.
  assert.match(
    failureOf([
      badgePill("allocated", { backgroundColor: "rgba(3, 105, 161, 0.4)" }),
      badgePill("candidate"),
      badgePill("blocked"),
    ]),
    /allocated pill's colours are not opaque/,
  );
  assert.match(
    failureOf([
      badgePill("allocated"),
      badgePill("candidate", { text: "" }),
      badgePill("blocked"),
    ]),
    /candidate pill rendered no label text/,
  );
  // The label is the app's own translation, not any text the fixture chose.
  assert.match(
    failureOf([
      badgePill("allocated"),
      badgePill("candidate", { text: "候选" }),
      badgePill("blocked"),
    ]),
    /candidate pill rendered '候选' while the app's own label is 'Candidate'/,
  );
  // Two pills that overlap, a label clipped by its own box, and a pill off the viewport each
  // fail by name.
  assert.match(
    failureOf([
      badgePill("allocated"),
      badgePill("candidate", { box: { x: 20, y: 10, width: 60, height: 16 } }),
      badgePill("blocked"),
    ]),
    /allocated and candidate pills overlap/,
  );
  assert.match(
    failureOf([
      badgePill("allocated"),
      badgePill("candidate", { scrollWidth: 90 }),
      badgePill("blocked"),
    ]),
    /candidate pill's label overflows its box/,
  );
  assert.match(
    failureOf([
      badgePill("allocated"),
      badgePill("candidate"),
      badgePill("blocked", { box: { x: 1400, y: 10, width: 60, height: 16 } }),
    ]),
    /blocked pill sits outside the 1440x900 viewport/,
  );
  // States that share one colour are not three states.
  assert.match(
    failureOf([
      badgePill("allocated"),
      badgePill("candidate", { backgroundColor: BADGE_BACKGROUNDS.allocated }),
      badgePill("blocked"),
    ]),
    /share a background colour/,
  );
  // And a fixture that was never rendered or never mounted fails rather than passing vacuously.
  assert.match(
    evaluateRouteBadgeContrast({ fixture: null }).failures.join(" | "),
    /not measured: the check collected nothing/,
  );
  assert.match(
    evaluateRouteBadgeContrast({
      fixture: { mounted: false, reason: "no displayed .workspace-page", states: [] },
    }).failures.join(" | "),
    /could not be mounted: no displayed \.workspace-page/,
  );
});

/** Minimal element/document stubs: `mountRouteBadgeFixture` runs in the page and in here. */
interface StubBadgeNode {
  tagName: string;
  className: string;
  textContent: string;
  attributes: Record<string, string>;
  style: Record<string, string>;
  children: StubBadgeNode[];
  parentNode: StubBadgeNode | null;
  removed: boolean;
  clientWidth: number;
  clientHeight: number;
  scrollWidth: number;
  scrollHeight: number;
  setAttribute: (name: string, value: string) => void;
  getAttribute: (name: string) => string | null;
  append: (child: StubBadgeNode) => void;
  remove: () => void;
  getBoundingClientRect: () => { x: number; y: number; width: number; height: number };
  querySelectorAll: (selector: string) => StubBadgeNode[];
}

function stubBadgeNode(tagName: string): StubBadgeNode {
  const node: StubBadgeNode = {
    tagName,
    className: "",
    textContent: "",
    attributes: {},
    style: {},
    children: [],
    parentNode: null,
    removed: false,
    clientWidth: tagName === "em" ? 68 : 220,
    clientHeight: tagName === "em" ? 16 : 28,
    scrollWidth: tagName === "em" ? 68 : 220,
    scrollHeight: tagName === "em" ? 16 : 28,
    setAttribute: (name, value) => {
      node.attributes[name] = String(value);
    },
    getAttribute: (name) => node.attributes[name] ?? null,
    append: (child) => {
      child.parentNode = node;
      node.children.push(child);
    },
    remove: () => {
      if (node.parentNode) {
        node.parentNode.children = node.parentNode.children.filter((child) => child !== node);
      }
      node.parentNode = null;
      node.removed = true;
    },
    getBoundingClientRect: () => {
      if (tagName !== "em") return { x: 8, y: 8, width: 220, height: 28 };
      const order = ["allocated", "candidate", "blocked"];
      const index = Math.max(0, order.indexOf(node.getAttribute("data-route-state") ?? ""));
      return { x: 10 + index * 70, y: 10, width: 68, height: 16 };
    },
    querySelectorAll: (selector) =>
      selector === "[data-route-state]"
        ? node.children.filter((child) => child.getAttribute("data-route-state") !== null)
        : [],
  };
  return node;
}

/** Run the mounting pair against a stub page, the way the sweep runs them in the browser. */
function mountBadgesWithStub(labels: Record<string, string>, { pageVisible = true } = {}) {
  const host = stubBadgeNode("div");
  if (!pageVisible) host.getBoundingClientRect = () => ({ x: 0, y: 0, width: 0, height: 0 });
  let fixtureNode: StubBadgeNode | null = null;
  const computedStyle = (node: StubBadgeNode) => {
    const state = node.getAttribute("data-route-state");
    return {
      color: "rgb(255, 255, 255)",
      backgroundColor: state ? BADGE_BACKGROUNDS[state] : "rgba(0, 0, 0, 0)",
      fontSize: "10px",
      fontWeight: "800",
      display: "block",
      visibility: "visible",
      opacity: "1",
    };
  };
  const previousWindow = (globalThis as { window?: unknown }).window;
  const previousDocument = (globalThis as { document?: unknown }).document;
  (globalThis as { window?: unknown }).window = {
    getComputedStyle: computedStyle,
    innerWidth: 1440,
    innerHeight: 900,
  };
  (globalThis as { document?: unknown }).document = {
    querySelector: (selector: string) =>
      selector === `[${ROUTE_BADGE_FIXTURE_ATTRIBUTE}]`
      && fixtureNode !== null
      && !fixtureNode.removed
        ? fixtureNode
        : null,
    querySelectorAll: (selector: string) => (selector === ".workspace-page" ? [host] : []),
    createElement: (tagName: string) => {
      const node = stubBadgeNode(tagName);
      if (tagName === "div") fixtureNode = node;
      return node;
    },
  };
  try {
    const fixture = mountRouteBadgeFixture({ labels });
    const container = fixtureNode;
    const removed = removeRouteBadgeFixture();
    return { fixture, removed, host, container };
  } finally {
    (globalThis as { window?: unknown }).window = previousWindow;
    (globalThis as { document?: unknown }).document = previousDocument;
  }
}

test("the badge fixture mounts the overlay's own pill markup and measures it", () => {
  const { fixture, removed, host, container } = mountBadgesWithStub(BADGE_LABELS);
  assert.equal(fixture.mounted, true);
  assert.equal(host.children.length, 0, "the fixture leaves the page as it found it");
  assert.equal(removed.removed, true);
  assert.deepEqual(
    fixture.states.map((state) => [state.state, state.text, state.color, state.backgroundColor]),
    [
      ["allocated", "Allocated", "rgb(255, 255, 255)", BADGE_BACKGROUNDS.allocated],
      ["candidate", "Candidate", "rgb(255, 255, 255)", BADGE_BACKGROUNDS.candidate],
      ["blocked", "Blocked", "rgb(255, 255, 255)", BADGE_BACKGROUNDS.blocked],
    ],
  );
  // The mounted markup carries the classes `ResourcePoolPathOverlay` renders.
  assert.equal(
    (container?.children ?? []).map((pill) => pill.className).join(" | "),
    "resource-route-state-pill allocated | resource-route-state-pill candidate"
    + " | resource-route-state-pill blocked",
  );
  // And the measurements pass the same verdict the sweep records.
  assert.deepEqual(
    evaluateRouteBadgeContrast({ fixture, labels: BADGE_LABELS }).failures,
    [],
  );
});

test("a page that never displayed cannot pass the badge check for lack of a fixture", () => {
  const { fixture } = mountBadgesWithStub(BADGE_LABELS, { pageVisible: false });
  assert.equal(fixture.mounted, false);
  assert.match(
    evaluateRouteBadgeContrast({ fixture, labels: BADGE_LABELS }).failures.join(" | "),
    /no displayed \.workspace-page to render the route-state badge fixture inside/,
  );
});
