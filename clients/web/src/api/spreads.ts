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
  cost: { kind: "route_tariff"; from_hub: string; to_hub: string } | null;
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
