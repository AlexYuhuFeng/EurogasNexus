/**
 * Wire types of the regas auction desk (`/api/desk/regas-auctions...`): cases, the live answer,
 * snapshots, the read-only what-if. Money, prices and energy arrive as exact decimal text; the
 * screen formats them and never adds them up itself.
 */

export type RegasState = "missing_inputs" | "illustration" | "no_level" | "room" | "at_limit" | "stop";
export type RegasCaseState = "open" | "won" | "lost" | "lapsed";

export interface RegasEntryDTO {
  value: string;
  by?: string;
  at?: string;
  link?: string | null;
}

export interface RegasCaseInputsDTO {
  schema: number;
  title: string;
  terminal: { terminal_id: string; name: string; hub: string; by_hand: boolean };
  slot: { first_day: string; last_day: string; quantity: string; unit: string; factor: string | null; factor_source: string | null; source?: string };
  auction: {
    format: string;
    opens_at: string | null;
    closes_at: string;
    time_zone: string;
    quotation: "per_mwh" | "per_slot";
    level: RegasEntryDTO | null;
    level_history: RegasEntryDTO[];
    notice_key: string | null;
    link: string | null;
  };
  owner: { counterparty_id: string | null; name: string; by_hand: boolean };
  offer: {
    kind: "fixed" | "formula";
    price?: string;
    price_unit?: string;
    index_hub?: string;
    pricing?: "send_out_days" | "month";
    pricing_month?: string;
    slope?: string;
    constant?: string;
    tolerance_pct: string;
    expires_at: string | null;
  };
  profile: { weights: string[] | null };
  delay_days: number;
  costs: Record<string, RegasEntryDTO>;
  prices: Record<string, { all?: RegasEntryDTO; days?: Record<string, RegasEntryDTO> }>;
  fx: RegasEntryDTO | null;
  rate_pct: RegasEntryDTO | null;
}

export interface RegasCaseDTO {
  case_id: string;
  book_id: string;
  title: string;
  terminal_id: string;
  terminal_name: string;
  hub: string;
  counterparty_id: string | null;
  counterparty_name: string;
  state: RegasCaseState;
  auction_opens_at_utc: string | null;
  auction_closes_at_utc: string;
  offer_expires_at_utc: string | null;
  notice_key: string | null;
  inputs?: RegasCaseInputsDTO;
  version: number;
  created_by: string;
  created_at_utc: string;
  updated_by: string;
  updated_at_utc: string;
  closed_by: string | null;
  closed_at_utc: string | null;
  close_note: string | null;
  position_seam: Record<string, unknown> | null;
}

export interface RegasCostLineDTO {
  key: string;
  label: string;
  basis: string;
  value: string | null;
  input_class: string;
  source: string;
  origin: "register" | "publication" | "computed" | "hand" | "default";
  entered_by: string | null;
  entered_at: string | null;
  link: string | null;
  held: boolean;
  total: string | null;
  per_mwh: string | null;
}

export interface RegasDayDTO {
  day: string;
  sent_out_mwh: string;
  price: string;
  revenue: string;
  native_value: string | null;
  native_unit: string | null;
  class: string | null;
  source: string | null;
  as_of_utc: string | null;
}

export interface RegasHedgeDTO {
  hub: string;
  month: string;
  side: "sell" | "buy";
  mwh: string;
  half_spread: string;
  half_spread_source: string;
  half_spread_class: string;
  cost: string;
  long_mwh: string;
  formula_mwh: string;
  covered_mwh: string;
  contract: string;
  desk_unit: string;
  desk_volume: string | null;
  instrument: string;
  last_trading_day: string;
  month_futures_stopped: boolean;
}

export interface RegasExposureDTO {
  hub: string;
  month: string;
  long_mwh: string;
  formula_mwh: string;
  covered_mwh: string;
  residual_mwh: string;
  per_unit_move: string;
}

export interface RegasReadDTO {
  key: string;
  value: string | null;
  class: string;
  source: string;
  as_of_utc: string | null;
  native_value: string | null;
  native_unit: string | null;
}

export interface RegasAnswerDTO {
  computed: boolean;
  state: RegasState;
  missing: string[];
  missing_labels: { key: string; kind: string; what: string }[];
  simulated: boolean;
  illustration: string | null;
  hand_entered: string[];
  defaults: string[];
  grade: string;
  currency: string;
  quotation: "per_mwh" | "per_slot";
  as_of_utc: string;
  max_bid_total?: string;
  max_bid_quoted?: string;
  max_bid_per_mwh?: string;
  quoted_low?: string | null;
  quoted_high?: string | null;
  level?: string | null;
  headroom?: string | null;
  energy_unloaded_mwh?: string;
  energy_sent_out_mwh?: string;
  revenue?: string;
  gross?: string;
  average_hub_price?: string;
  cargo_price_per_mwh?: string;
  cargo_cost?: string;
  index_value?: string | null;
  waterfall?: { key: string; label: string; total: string; per_mwh: string }[];
  sensitivities?: { key: string; label: string; per: string; max_bid_total: string | null; max_bid_quoted: string | null }[];
  break_even_hub_price?: string | null;
  break_even_note?: string;
  hedges?: RegasHedgeDTO[];
  exposure?: RegasExposureDTO[];
  days?: RegasDayDTO[];
  cost_lines: RegasCostLineDTO[];
  reads: RegasReadDTO[];
  slot: { energy_mwh: string | null; source: string; days: number; first_day: string; last_day: string };
  assumptions: { key: string; text: string }[];
  prepare_hedge_orders: { enabled: false; note: string };
  auction_closes_in_seconds?: number;
  offer_expires_in_seconds?: number;
  offer_lapses_before_close?: boolean;
}

export interface RegasChoicesDTO {
  terminals: { terminal_id: string; name: string; hub: string; operator: string | null; country: string | null; link_only: boolean; firm_terms: boolean }[];
  owners: { counterparty_id: string; name: string; currency: string }[];
  books: { book_id: string; name: string }[];
  notices: { notice_key: string; title: string; facility_name: string | null; opens_at_utc: string; closes_at_utc: string | null; offers_from: string | null; offers_to: string | null; quantity: number | null; quantity_unit: string | null; source_url: string }[];
  definition: {
    quotation: "per_mwh" | "per_slot";
    formats: string[];
    default_format: string;
    at_limit_within_pct: string;
    default_time_zone: string;
    offer_kinds: string[];
    pricing_periods: string[];
    default_pricing: string;
    default_tolerance_pct: string;
    price_units: string[];
    costs: { key: string; label: string; basis: string; from: string; default: string | null }[];
  };
  hedge_orders: { enabled: false; note: string };
}

export interface RegasCasesDTO {
  cases: RegasCaseDTO[];
  choices: RegasChoicesDTO;
}

export interface RegasCaseAnswerDTO {
  case: RegasCaseDTO;
  answer: RegasAnswerDTO;
}

export interface RegasSnapshotDTO {
  snapshot_id: string;
  case_id: string;
  case_version: number;
  saved_by: string;
  saved_at_utc: string;
  note: string;
  state: RegasState;
  max_bid_quoted: string | null;
  max_bid_total: string | null;
  level: string | null;
  headroom: string | null;
  quotation: string | null;
  currency: string | null;
  simulated: boolean | null;
  hand_entered: string[];
}

export interface RegasWhatIfRowDTO {
  mandate_id: string;
  name: string;
  before: Record<string, unknown>;
  after: Record<string, unknown>;
}

export interface RegasWhatIfDTO {
  computed: boolean;
  booked: false;
  note?: string;
  missing?: string[];
  added?: { hub: string; month: string; net_mwh: string }[];
  mandates?: RegasWhatIfRowDTO[];
  credit?: { counterparty_id: string; before: Record<string, unknown>; after: Record<string, unknown>; marks_as_of: string | null } | null;
  options_allowed?: false;
  instruments?: string[];
}

/** The body a case is opened or changed with (the server checks every value). */
export interface RegasCaseBody {
  book_id?: string;
  version?: number;
  title?: string;
  terminal: { terminal_id?: string; name: string; hub: string };
  slot: { first_day: string; last_day: string; quantity: string; unit: string; factor?: string | null; source?: string };
  auction: { format: string; opens_at?: string | null; closes_at: string; time_zone: string; quotation: string; level?: string | null; notice_key?: string | null; link?: string | null };
  owner: { counterparty_id?: string | null; name: string };
  offer: { kind: string; price?: string; price_unit?: string; index_hub?: string; pricing?: string; pricing_month?: string; slope?: string; constant?: string; tolerance_pct?: string; expires_at?: string | null };
  profile?: { weights: string[] | null };
  delay_days?: number;
  costs?: Record<string, { value: string; link?: string }>;
  prices?: Record<string, { all?: string; days?: Record<string, string> }>;
  fx?: string;
  rate_pct?: string;
}
