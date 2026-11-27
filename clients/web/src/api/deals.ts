/**
 * Wire types of deal capture (`/api/desk/deals...`): the blotter, imports, manual deals, the
 * end-of-day check and close, the daily pack. Money and volume arrive as exact decimal text
 * ("31.25", "-1860"); the screen formats them and never sums them itself.
 */

export interface DealSourceDTO {
  kind: "file" | "manual";
  file_name?: string | null;
  line?: number | null;
  entered_by?: string;
  fields?: string[];
}

export interface DealRowDTO {
  deal_key: string;
  version: number;
  versions: number;
  status: "live" | "cancelled";
  venue: string;
  venue_trade_id: string;
  leg_id: string | null;
  trade_date: string;
  trade_time_utc: string | null;
  trader: string;
  counterparty: string | null;
  cleared: boolean;
  hub: string;
  product: string;
  delivery_start: string;
  delivery_end: string;
  side: "buy" | "sell";
  volume: string;
  volume_unit: string;
  total_mwh: string;
  price: string;
  price_unit: string;
  price_currency: string;
  physical: boolean;
  instrument: string;
  fees: string | null;
  fee_currency: string | null;
  book_id: string | null;
  origin: "file" | "manual";
  source: DealSourceDTO;
  recorded_at_utc: string;
  change_reason: string | null;
  superseded_at_utc?: string | null;
  entered_by?: string;
}

export interface DealProblemDTO {
  problem_id: string;
  file_name: string;
  line: number;
  code: string;
  message: string;
  field: string | null;
  value: string | null;
  raw: string;
  book_id: string | null;
  recorded_at_utc: string;
}

export interface DealTotalDTO {
  hub: string;
  product: string;
  delivery_start: string;
  delivery_end: string;
  deals: number;
  buy_mwh: string;
  sell_mwh: string;
  net_mwh: string;
  avg_buy_price: string | null;
  avg_sell_price: string | null;
  price_unit: string | null;
}

export interface DayCloseDTO {
  book_id: string | null;
  closed_by: string;
  closed_at_utc: string;
  differences: number;
  etrm_file_name: string;
  note: string | null;
}

export interface DayStatusDTO {
  business_date: string;
  closed: boolean;
  open_books: string[];
  closes: DayCloseDTO[];
  label: string | null;
}

export interface DealBlotterDTO {
  business_date: string;
  deals: DealRowDTO[];
  unreadable: DealProblemDTO[];
  totals: DealTotalDTO[];
  counts: { deals: number; live: number; cancelled: number; manual: number; unreadable: number };
  choices: { traders: string[]; hubs: string[]; venues: string[]; books: string[] };
  status: DayStatusDTO;
  books: { book_id: string; name: string; legal_entity: string }[];
}

export interface DealBlotterFilters {
  day: string;
  trader?: string;
  hub?: string;
  venue?: string;
}

export interface DealFormatDTO {
  name: string;
  title: string;
  venue: string;
  provenance: string;
  verified: boolean;
  source_path: string;
  notes: string[];
}

export interface DealFormatsDTO {
  formats: DealFormatDTO[];
  sheet_layout: { title: string; headers: string[]; source_path: string } | null;
  errors: string[];
}

export interface DealImportDTO {
  file_id: string;
  format: string;
  format_title: string;
  provenance: string;
  verified: boolean;
  counts: { rows: number; new: number; amended: number; cancelled: number; duplicate: number; unreadable: number };
  problems: { line: number; code: string; message: string }[];
}

export interface ManualDealInput {
  book: string;
  deal_key?: string;
  venue?: string;
  venue_trade_id?: string;
  trade_date?: string;
  trader?: string;
  counterparty?: string;
  hub?: string;
  product?: string;
  delivery_start?: string;
  delivery_end?: string;
  side?: "buy" | "sell";
  volume?: string;
  volume_unit?: string;
  price?: string;
  price_unit?: string;
  physical?: boolean;
  instrument?: string;
  status?: "live" | "cancelled";
}

export interface ManualDealResultDTO {
  deal_key: string;
  outcome: string;
  origin: "manual";
  entered_by_hand: string[];
}

export interface EodDifferenceDTO {
  id: string;
  kind: string;
  deal_key: string | null;
  etrm_trade_id: string | null;
  hub: string | null;
  product: string | null;
  matched_by: "reference" | "terms" | null;
  captured: Record<string, unknown> | null;
  etrm: Record<string, unknown> | null;
  detail: Record<string, unknown>;
}

export interface EodCheckDTO {
  business_date: string;
  matched: number;
  matched_by_terms: number;
  differences: EodDifferenceDTO[];
  counts: Record<string, number>;
  captured_deals: number;
  etrm_trades: number;
  etrm_cancelled: number;
  etrm_rows_outside_your_books: number;
  etrm_file_name: string;
  reference_column: string | null;
  tolerances: { volume_mwh: string; price_per_mwh: string };
  status: DayStatusDTO;
}

export interface CloseDayInput {
  day: string;
  etrm_file_name: string;
  etrm_csv: string;
  acknowledgements: Record<string, string>;
  note?: string;
}

export interface CloseDayResultDTO {
  business_date: string;
  closed_by: string;
  closed_at_utc: string;
  differences: number;
}

export interface DealPnlRowDTO {
  book_id: string;
  trader: string;
  hub: string;
  currency: string;
  day: string;
  mtd: string;
  ytd: string;
  fees: string;
}

export interface DealPnlDTO {
  business_date: string;
  by_trader_hub: DealPnlRowDTO[];
  totals: { currency: string; day: string; mtd: string; ytd: string }[];
  not_valued: { deal_key: string; hub: string; product: string; reason: string | null }[];
  simulated_marks: boolean;
  method: string;
  status: DayStatusDTO;
}

export interface PackScheduleInput {
  enabled: boolean;
  at_local: string;
  timezone: string;
  weekdays: number[];
  kinds: string[];
  languages: string[];
}

export interface PackScheduleDTO extends PackScheduleInput {
  last_slot?: string | null;
  updated_by?: string | null;
  recipients?: Record<string, number>;
}
