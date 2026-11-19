/**
 * The bundled examples behind "See an example" (design basis H.1): a few made-up records per
 * page, shaped as the server sends them, so the page's own components draw them. They are
 * never sent anywhere and never stored; every name says it is an example.
 */
import type { OpportunityListDTO, OpportunityRowDTO, PositionLadderDTO, PositionLadderRowDTO, ReportSummaryDTO, UpstreamContractDTO } from "../../api/client.ts";

const contract = (fields: Partial<UpstreamContractDTO> & Pick<UpstreamContractDTO, "contract_id" | "contract_name">): UpstreamContractDTO => ({
  resource_type: "pipeline_supply",
  delivery_point_name: "NBP",
  gas_year: "2026/27",
  delivery_quantity_mwh_per_day: 0,
  contract_price_gbp_mwh: 0,
  contract_price_currency: "GBP",
  settlement_frequency: "monthly",
  upstream_payment_lag_days: 20,
  screen_sale_cash_lag_days: 2,
  delivery_tolerance_pct: 5,
  nomination_tolerance_pct: 5,
  annual_financing_rate_pct: 5,
  allowed_exit_points: [],
  eligible_sale_modes: [],
  contract_kind_reviewed: true,
  ...fields,
});

/** Deals -> Contracts: a supply agreement, a tender, a master and one cargo under it. */
export const EXAMPLE_CONTRACTS: readonly UpstreamContractDTO[] = [
  contract({
    contract_id: "example-gsa",
    contract_name: "Example North Sea supply",
    contract_kind: "SUPPLY_GSA",
    delivery_point_name: "Easington",
    delivery_quantity_mwh_per_day: 12000,
    contract_price_gbp_mwh: 31.5,
    notes: JSON.stringify({ counterparty: "Example Producer Ltd" }),
  }),
  contract({
    contract_id: "example-tender",
    contract_name: "Example field tender",
    contract_kind: "UPSTREAM_TENDER",
    delivery_point_name: "St Fergus",
    delivery_quantity_mwh_per_day: 8000,
    headline: { key: "swing", value: 8000, min: 6000, max: 10000, unit: "MWh/d" },
    notes: JSON.stringify({ counterparty: "Example Upstream AS" }),
  }),
  contract({
    contract_id: "example-mspa",
    contract_name: "Example LNG master agreement",
    contract_kind: "LNG_MSPA",
    delivery_point_name: "",
    kind_terms: { delivery_terms: ["FOB", "DES"], term_start: "2026-01-01" },
    notes: JSON.stringify({ counterparty: "Example LNG Trading" }),
  }),
  contract({
    contract_id: "example-cargo",
    contract_name: "Example cargo, Gate",
    contract_kind: "LNG_CARGO",
    master_contract_id: "example-mspa",
    delivery_point_name: "Gate",
    gas_year: "2027-01..2027-01",
    kind_terms: { delivery_term: "DES", discharge_terminal: "Gate", terminal_hub: "TTF" },
    headline: { key: "cargo", value: 3.4, unit: "TBtu", term: "DES", window: ["2027-01-10", "2027-01-14"] },
    notes: JSON.stringify({ counterparty: "Example LNG Trading" }),
  }),
];

const DAY_MS = 86_400_000;

function exampleOpportunity(now: Date, fields: Partial<OpportunityRowDTO> & Pick<OpportunityRowDTO, "opportunity_id" | "type" | "lane" | "subject" | "period">): OpportunityRowDTO {
  const at = (days: number) => new Date(now.getTime() + days * DAY_MS).toISOString();
  return {
    key: fields.opportunity_id,
    type_code: fields.type,
    state: "actionable",
    claim: fields.subject,
    headline: { value: null, unit: "EUR/MWh" },
    value: null,
    volume: null,
    quality: { class: "derived", label: "Derived" },
    simulated: false,
    book_ids: [],
    expires_at_utc: at(6),
    deadline_utc: null,
    version: 1,
    first_seen_utc: at(-1),
    last_evaluated_utc: at(0),
    reasons: [],
    blocked: null,
    rank: null,
    user_state: null,
    period_start: null,
    period_end: null,
    ...fields,
  };
}

/** Deals -> Opportunities: one item in each lane, as an evaluation of a small book would list. */
export function exampleOpportunityList(now: Date = new Date()): OpportunityListDTO {
  const bucket = (items: OpportunityRowDTO[]) => ({ total: items.length, offset: 0, items, next_cursor: null });
  return {
    as_of_utc: now.toISOString(),
    evaluation: null,
    lanes: {
      must_act: bucket([
        exampleOpportunity(now, {
          opportunity_id: "example-hedge-gap",
          type: "hedge_gap",
          lane: "must_act",
          subject: "Example North Sea supply",
          period: "2027-02",
          volume: { value: "62000", unit: "MWh" },
          deadline_utc: new Date(now.getTime() + 2 * DAY_MS).toISOString(),
        }),
      ]),
      could_act: bucket([
        exampleOpportunity(now, {
          opportunity_id: "example-locational",
          type: "locational",
          lane: "could_act",
          subject: "NBP → TTF",
          period: "2027-01",
          headline: { value: "0.84", unit: "EUR/MWh" },
          value: { amount: "41300", currency: "EUR" },
          rank: { position: 1, reason: "Largest value after transport" },
        }),
      ]),
      market: bucket([
        exampleOpportunity(now, {
          opportunity_id: "example-time-spread",
          type: "time_spread",
          lane: "market",
          state: "indicative",
          subject: "TTF Win-27 − Sum-27",
          period: "2027",
          headline: { value: "2.10", unit: "EUR/MWh" },
          rank: { position: 1, reason: "Wider than the storage carry" },
        }),
      ]),
    },
    groups: {},
    confirming: 0,
    hidden_by_you: 0,
    per_lane_shown: 5,
    simulated: false,
    banner: null,
    readiness: {
      book: { ready: true, contracts: 4, approved_hedge_bands: 1, missing: null },
      prices: { ready: true, licensed_quote_sources: [], settlement_sources: [], firm_marks: 0, missing: null },
      published_costs: { ready: true, transport_tariffs: 12, terminal_terms: 2, missing: null },
      assumptions: { ready: true, approved_versions: 1, missing: null },
      types_now: ["hedge_gap", "locational", "time_spread"],
    },
  };
}

/** Book -> Position: a supply contract against two hubs' screen hedges over three months. */
export function examplePositionLadder(now: Date = new Date()): PositionLadderDTO {
  const month = (offset: number) => {
    const date = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth() + offset, 1));
    return date.toISOString().slice(0, 7);
  };
  const row = (offset: number, hub: string, physical: number, financial: number, mark: number, unit: string): PositionLadderRowDTO => ({
    hub,
    month: month(offset),
    physical_mwh: physical,
    financial_mwh: financial,
    net_mwh: physical + financial,
    hedge_ratio: physical === 0 ? null : Math.min(1, Math.abs(financial) / Math.abs(physical)),
    mark,
    mark_method: "quoted",
    mark_unit: unit,
  });
  const rows = [
    row(1, "NBP", 372000, -300000, 31.2, "GBP/MWh"),
    row(1, "TTF", -155000, 120000, 32.4, "EUR/MWh"),
    row(2, "NBP", 336000, -240000, 31.9, "GBP/MWh"),
    row(2, "TTF", -140000, 140000, 33.1, "EUR/MWh"),
    row(3, "NBP", 372000, -150000, 31.4, "GBP/MWh"),
    row(3, "TTF", -155000, 60000, 32.0, "EUR/MWh"),
  ];
  const sum = (key: "physical_mwh" | "financial_mwh" | "net_mwh") => rows.reduce((total, item) => total + item[key], 0);
  return {
    rows,
    totals: { physical_mwh: sum("physical_mwh"), financial_mwh: sum("financial_mwh"), net_mwh: sum("net_mwh") },
    mark_to_market: null,
    unpriced_rows: 0,
    var_95_1d: null,
    var_observations: 0,
    horizon: { start: `${month(1)}-01`, end: `${month(3)}-28` },
    legs: { physical: 2, financial: 6 },
    reporting_currency: null,
    group_by: "hub",
    warnings: [],
  };
}

/** Research -> Reports: the stored reports a desk keeps after a week of use. */
export function exampleReports(now: Date = new Date()): ReportSummaryDTO[] {
  const day = (offset: number) => new Date(now.getTime() - offset * DAY_MS).toISOString();
  const date = (offset: number) => day(offset).slice(0, 10);
  const report = (id: string, kind: ReportSummaryDTO["kind"], title: string, offset: number, span = 0): ReportSummaryDTO => ({
    report_id: id,
    kind,
    variant: null,
    title,
    audience: "internal",
    headline: title,
    period_start: date(offset + span),
    period_end: date(offset),
    as_of: day(offset),
    created_at: day(offset),
    generated_by_type: "rule",
    simulated: false,
    licensed_families: [],
    model_use: {},
    generated_by: "Example Analyst",
    edited_by: "rule",
  });
  return [
    report("example-daily", "daily", "Example daily: NBP firmer on colder weather", 0),
    report("example-weekly", "weekly", "Example weekly: storage draws ahead of the 5-yr mean", 2, 6),
    report("example-situation", "situation", "Example situation: Norwegian field outage", 4),
  ];
}
