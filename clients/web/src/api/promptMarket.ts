/**
 * Wire types of the prompt desk read (`GET /api/market/prompt`).
 *
 * Nothing here is an order: every figure comes from the server.
 */

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
  };
  simulated: boolean;
  warnings: string[];
}
