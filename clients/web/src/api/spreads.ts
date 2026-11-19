/**
 * Wire types of Research → Spreads (`POST /api/research/spreads/interpret` and `/evaluate`).
 * The spec is the one object the form and the "Describe it" box both edit; every figure in a
 * result comes from the server's engine.
 */

import type { FxForwardDTO } from "./comparablePrices";

export type SpecKind = "curve" | "history";
export type InputClass = "missing" | "simulated" | "assumption" | "indicative" | "derived" | "converted" | "reference" | "sourced";

export interface StrategySpecDTO {
  version: number;
  kind: SpecKind;
  legs: Array<{ hub: string; tenor: string | null; weight: number }>;
  unit: string | null;
  fx: "forward" | "spot";
  /** `through`: market areas the desk picked the route through (empty: the cheapest). */
  cost: { kind: "route_tariff"; from_hub: string; to_hub: string; through?: string[] } | null;
  rule: { kind: "zscore" | "threshold"; lookback: number; entry_z?: number; exit_z?: number; low?: number | null; high?: number | null } | null;
  lookback_days: number;
  volume_mwh_per_day: number | null;
}

export interface SpecIssueDTO {
  code: string;
  field: string;
  message: string;
  choices: string[];
}

export interface InterpretationDTO {
  spec: StrategySpecDTO;
  issues: SpecIssueDTO[];
  basis: "parser" | "model" | "none";
  ai: "off" | "used" | "failed";
  read_as_text: boolean;
  ready: boolean;
}

export interface RouteLegDTO {
  point_name: string;
  tso: string;
  direction: string;
  role: string;
  value: number | null;
  currency: string | null;
  gas_year: string | null;
  status: string | null;
  input_class: InputClass;
}

export interface RouteDTO {
  from_hub: string;
  to_hub: string;
  direction: string;
  proven: boolean;
  via: string[];
  legs: RouteLegDTO[];
  total: number | null;
  currency: string | null;
  complete: boolean;
  gas_years: string[];
  input_class: InputClass;
  missing: string[];
  load_factor: string;
  in_display_unit?: number | null;
  value?: number | null;
  /** Market areas in flow order (NBP, ZTP, PEG) and those between the two hubs. */
  hubs?: string[];
  through?: string[];
  /** The other complete routes, cheapest first, with their extra cost in the display unit. */
  alternatives?: (RouteDTO & { extra_cost: number | null })[];
  /** Routes that cannot be priced, each with the legs the register does not hold. */
  unavailable?: { hubs: string[]; via: string[]; missing: string[] }[];
  /** The desk's pick (market areas between), or null for the cheapest. */
  picked?: string[] | null;
}

export interface CurveLegDTO {
  hub: string;
  weight: number;
  native_value: number;
  native_unit: string;
  value: number;
  source_system: string;
  observed: string;
  input_class: InputClass;
  price_class: InputClass;
  fx: FxForwardDTO | null;
}

export interface CurveRowDTO {
  month: string;
  label: string;
  legs: CurveLegDTO[];
  gross: number | null;
  cost: number | null;
  net: number | null;
  refused: string | null;
  cost_class?: InputClass;
  route_gas_years?: string[];
  delivery_gas_year?: string;
  tariff_year_differs?: boolean;
  input_class: InputClass;
  simulated: boolean;
}

export interface CurveResultDTO {
  kind: "curve";
  unit: string;
  fx_mode: "forward" | "spot";
  fx_labels: string[];
  rows: CurveRowDTO[];
  route: RouteDTO | null;
  months: number;
  input_class: InputClass;
  simulated: boolean;
  empty: string | null;
  spread: string;
  /** Net of transport: priced to the last month a published tariff covers, the later months not. */
  coverage?: { priced_to: string; unpriced_from: string; months_priced: number; reason: string } | null;
}

export interface HistoryResultDTO {
  kind: "history";
  unit: string | null;
  analysis: {
    labels: string[];
    points: Array<{ date: string; spread: number; zscore: number | null }>;
    statistics: Record<string, number | null>;
    metrics: Record<string, number | null>;
    normalisation?: Array<{ leg: string; fx_labels: string[]; simulated: boolean }>;
  };
  route: { delivery: { label: string }; lines: Array<RouteDTO & { value: number | null }> } | null;
  simulated: boolean;
}

export interface EvaluationDTO {
  spec: StrategySpecDTO;
  issues: SpecIssueDTO[];
  result: CurveResultDTO | HistoryResultDTO | null;
}

/** One tenor of a locational row on the spread board (`GET /api/research/spreads/board`). */
export interface BoardTenorDTO {
  tenor: "MA" | "DA";
  available: boolean;
  reason?: string;
  close_day?: string;
  delivery?: string;
  legs?: { hub: string; native_value: number; native_unit: string; value: number }[];
  gross?: number;
  direction?: string;
  cost?: number | null;
  net?: number | null;
  route?: { hubs: string[]; through: string[]; complete: boolean; missing: string[]; product: string; gas_years: string[]; issues: string[] };
  percentile?: number | null;
  range?: { low: number; high: number; days: number } | null;
  spark?: { days: string[]; values: number[] };
  input_class?: InputClass;
  simulated?: boolean;
}

export interface BoardTimeRowDTO {
  key: string;
  label: string;
  available: boolean;
  value?: number;
  near?: number;
  far?: number;
  reason?: string;
  spec?: Partial<StrategySpecDTO> | null;
  carry?: { total: number | null; reason?: string; parts?: Record<string, number>; missing?: string[] };
  net_of_carry?: number;
  /** The value in the hub's quotation (NBP in p/th) and in the reporting unit (hover). */
  native_value?: number;
  native_net_of_carry?: number;
  reporting_value?: number | null;
  uninformative?: boolean;
}

export interface BoardCrossRowDTO {
  key: "hh_ttf" | "clean_spark" | string;
  label: string;
  available: boolean;
  reason?: string;
  arrival?: string;
  terminal?: string;
  hub?: string;
  currency?: string;
  hh?: number | null;
  hh_source?: string | null;
  hub_price?: number | null;
  delivered?: number | null;
  value?: number | null;
  netback_usd_mmbtu?: number | null;
  assumptions?: number;
  input_class?: string;
  simulated?: boolean;
}

/** Research → Spreads opens on this: computed from what is held, no typing (rule 19). */
export interface SpreadBoardDTO {
  as_of: string;
  unit: string;
  reference: string;
  hubs: string[];
  locational: { pair: string; hub: string; reference: string; tenors: BoardTenorDTO[]; spec: Partial<StrategySpecDTO> }[];
  time: { hub: string; unit: string; native_unit?: string; reporting_unit?: string; rows: BoardTimeRowDTO[]; simulated: boolean }[];
  cross: BoardCrossRowDTO[];
  simulated: boolean;
}
