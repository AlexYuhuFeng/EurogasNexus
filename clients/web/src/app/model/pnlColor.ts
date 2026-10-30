/**
 * Profit and loss colours. Desks in Europe and the Americas read green as profit; in China and
 * much of Asia red means up and profit. The convention is a personal (or organisation)
 * preference, applied as `data-pnl` on the document so every P&L figure and chart follows it
 * through two tokens, `--pnl-profit` and `--pnl-loss`.
 */

export type PnlColorConvention = "green_up" | "red_up";

export const PNL_COLOR_CONVENTIONS: PnlColorConvention[] = ["green_up", "red_up"];

/** Class for a signed P&L value; zero and unknown stay neutral. */
export function pnlClass(value: number | null | undefined): "pnl-profit" | "pnl-loss" | "" {
  if (value == null || !Number.isFinite(value) || value === 0) return "";
  return value > 0 ? "pnl-profit" : "pnl-loss";
}

export function applyPnlColorConvention(convention: string, root?: { dataset: DOMStringMap }): void {
  const target = root ?? (typeof document !== "undefined" ? document.documentElement : undefined);
  if (!target) return;
  target.dataset.pnl = convention === "red_up" ? "red_up" : "green_up";
}
