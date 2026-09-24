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
  collectVisibleElements,
  evaluateReadToRender,
  readGroupRows,
  rowRecordId,
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

function portfolioSnapshot(slices: Record<string, unknown>) {
  return { data: { projection: "portfolio-snapshot", slices }, meta: {} };
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
