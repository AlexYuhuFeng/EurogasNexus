/**
 * Wire types of tracked strategies (paper shadow run) and the prompt desk.
 * `GET/POST /api/research/strategy-tracks`, `GET /api/market/prompt`. Nothing here is an
 * order: fills are paper fills, every figure comes from the server.
 */

import type { StrategySpecDTO } from "./spreads";

export interface TrackAdviceDTO {
  signal: "long" | "short" | "flat";
  reason?: string | null;
  entry_level: number | null;
  spread_bid?: number | null;
  spread_offer?: number | null;
  edge_net_per_mwh?: number | null;
  computed_at?: string;
  at: string;
  expires_at: string | null;
  cutoff_at?: string | null;
  quote_age_seconds?: Record<string, number> | null;
  currency?: string | null;
  unit?: string | null;
  simulated?: boolean;
}

export interface TrackSnapshotDTO {
  at?: string;
  signal?: string;
  reason?: string;
  gated?: string[];
  mid?: number | null;
  z?: number | null;
  spread_bid?: number | null;
  spread_offer?: number | null;
  position?: number;
  qty_mwh_per_day?: number;
  entry_price?: number | null;
  realised?: number;
  unrealised?: number;
  equity?: number;
  max_drawdown?: number;
  closed_trades?: number;
  winning_trades?: number;
  worst_trade?: number | null;
  currency?: string | null;
  simulated?: boolean;
  latency_ms?: number | null;
  advice?: TrackAdviceDTO | null;
  withdrawn?: { at: string; reason: string } | null;
  // daily
  close_date?: string | null;
  spread?: number | null;
  unit?: string | null;
  paper_pnl_since_start?: number;
}

export interface TrackBlotterEntryDTO {
  kind: "fill" | "no_fill";
  at: string;
  action?: "open" | "close";
  side?: string;
  price?: number | null;
  qty_mwh_per_day?: number;
  pnl?: number | null;
  pnl_per_mwh?: number | null;
  reason?: string | null;
  crossed_per_mwh?: number | null;
}

export interface StrategyTrackDTO {
  track_id: string;
  name: string;
  mode: "daily" | "intraday";
  state: "active" | "stopped" | "paused";
  paper: true;
  spec: StrategySpecDTO;
  rule: Record<string, unknown>;
  created_at_utc: string;
  last_evaluated_at_utc: string | null;
  evaluations: number;
  snapshot: TrackSnapshotDTO;
  assumptions: string;
  blotter?: TrackBlotterEntryDTO[];
  signals?: Array<Record<string, unknown> & { kind: string; at: string }>;
  equity?: Array<{ at: string; equity: number | null }>;
}

export interface PromptQuoteDTO {
  bid: number | null;
  ask: number | null;
  mid: number | null;
  bid_mwh_per_day: number | null;
  ask_mwh_per_day: number | null;
  last: number | null;
  vwap: number | null;
  volume_mwh: number | null;
  trade_count: number | null;
  prior_settlement: number | null;
  observed_at_utc: string;
  age_seconds: number;
  source_system: string;
  simulated: boolean;
  currency: string;
  last_trade?: { price: number; mwh_per_day: number; aggressor: string | null; at_utc: string };
}

export interface PromptMarketDTO {
  hub: string;
  as_of_utc: string;
  market: Record<"within_day" | "day_ahead", { gas_day: string; quote: PromptQuoteDTO | null }>;
  spread_wd_da: { mid: number; buy: number; sell: number; unit: string } | null;
  performance: {
    trades: Array<{ id: string; product: string; side: string; price: number; mwh: number; traded_at_utc: string; vs_vwap: number | null; vs_settlement: number | null; vs_decision_mid: number | null; slippage_vs_touch: number | null; pnl: number | null; simulated: boolean }>;
    day_pnl: number;
    currency: string | null;
    simulated: boolean;
    missed_signals?: Array<{ track: string; at: string; reason: string; advice: TrackAdviceDTO | null }>;
  };
  simulated: boolean;
  warnings: string[];
}
