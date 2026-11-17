/**
 * Wire types of the comparable-price reads (design basis 2, CP-01/CP-02):
 * `GET /api/market/fx-forward`, `POST /api/market/normalise`, `GET /api/market/instruments`.
 *
 * The client never holds a conversion factor or computes a forward: it shows what these reads
 * return, with the method, rate and date they state.
 */

export type FxMethod = "derived: covered interest parity" | "licensed" | "spot: ECB reference rate" | "same currency";

export interface FxRateUsedDTO {
  benchmark: string;
  label: string;
  currency: string;
  rate_pct: number;
  fixing_date: string;
  day_count: string;
  days: number;
  year_fraction: number;
  source_system: string;
}

export interface FxForwardDTO {
  pair: string;
  /** The rate as a desk quotes the pair (EUR/GBP, EUR/USD, GBP/USD), from the server. */
  desk_quote: { pair: string; rate: number; spot_rate: number | null };
  base: string;
  quote: string;
  rate: number;
  quoted_as: string;
  method: FxMethod;
  label: string;
  input_class: "derived" | "sourced" | "reference" | "simulated";
  simulated: boolean;
  value_date: string | null;
  delivery: { label: string; kind: string; first_gas_day: string; last_gas_day: string } | null;
  spot: { pair: string; rate: number; value_date: string; crossed_via: string | null; simulated: boolean } | null;
  rates: FxRateUsedDTO[];
  days: number | null;
  compounding: "simple" | "annual" | null;
  licensed: { source_system: string; value_date: string; as_of: string } | null;
  tolerance: { relative_pct: number; absolute: number };
  horizon_months: number;
  limitations: string[];
  as_of?: string;
}

export interface NormalisationRecordDTO {
  from_unit: string;
  to_unit: string;
  unit_factor: number;
  factor: number;
  heating_value: { gcv_kwh_per_m3: number; reference_conditions: string; basis: "stated" | "assumption" } | null;
  fx: FxForwardDTO | null;
}

export interface NormalisedValueDTO {
  value: number | null;
  unit?: string;
  native: { value: number; unit: string };
  simulated: boolean;
  input_class?: string;
  as_of?: string;
  delivery?: FxForwardDTO["delivery"];
  normalisation?: NormalisationRecordDTO;
  tolerance?: { absolute: number; relative_pct: number; basis: string };
  refused?: { code: string; message: string };
  label?: string;
}

export interface NormaliseRequestDTO {
  to_unit: string;
  values: Array<{ value: number; unit: string; product?: string; value_date?: string; as_of?: string; simulated?: boolean; label?: string }>;
  gcv_kwh_per_m3?: number;
}

export interface NormaliseResponseDTO {
  values: NormalisedValueDTO[];
  series: unknown;
}

export type InstrumentSourceClass = "sourced" | "indicative" | "simulated";
export type InstrumentProductKind = "spot" | "rolling" | "month" | "quarter" | "season" | "year" | "other";

export interface InstrumentSourceDTO {
  source_system: string;
  source_class: InstrumentSourceClass;
  simulated: boolean;
  days: number;
  first: string;
  last: string;
  last_as_of: string | null;
  stored_unit: string;
}

export interface InstrumentDTO {
  id: string;
  hub: string;
  instrument_kind: "outright";
  product_kind: InstrumentProductKind;
  code: string;
  label: string;
  /** The stored tenor key a spread-analysis leg names. */
  tenor: string;
  native_unit: string;
  currency: string;
  stored_unit: string;
  source_class: InstrumentSourceClass;
  simulated: boolean;
  best_source: string;
  sources: InstrumentSourceDTO[];
  observations: number;
  thin: boolean;
  first: string;
  last: string;
  last_as_of: string | null;
  delivery: { first_gas_day: string; last_gas_day: string } | null;
  expired: boolean;
}

export interface InstrumentHubDTO {
  hub: string;
  name: string;
  country: string;
  native_unit: string;
  currency: string;
  instrument_count: number;
  source_class: InstrumentSourceClass | null;
  simulated: boolean;
  last_as_of: string | null;
  kinds: Array<{ kind: InstrumentProductKind; count: number; instruments: InstrumentDTO[] }>;
}

export interface InstrumentCatalogueDTO {
  levels: string[];
  product_kinds: InstrumentProductKind[];
  thin_series_days: number;
  as_of: string | null;
  hubs: InstrumentHubDTO[];
}
