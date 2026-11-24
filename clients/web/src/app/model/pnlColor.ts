/**
 * Profit and loss colours. Desks in Europe and the Americas read green as profit; in China and
 * much of Asia red means up and profit. The convention is a personal (or organisation)
 * preference, applied as `data-pnl` on the document so every P&L figure and chart follows it
 * through two tokens, `--pnl-profit` and `--pnl-loss`.
 *
 * `blue_orange` is the colour-vision friendly scheme (UX R1): blue profit, orange loss, and the
 * "ok" status blue, so a red-green colour-blind reader never has to tell green from red. It is a
 * choice for anyone, not a diagnosis, and it sits beside the regional conventions.
 */

export type PnlColorConvention = "green_up" | "red_up" | "blue_orange";

export const PNL_COLOR_CONVENTIONS: PnlColorConvention[] = ["green_up", "red_up", "blue_orange"];

export function isPnlColorConvention(value: unknown): value is PnlColorConvention {
  return typeof value === "string" && (PNL_COLOR_CONVENTIONS as string[]).includes(value);
}

/** Class for a signed P&L value; zero and unknown stay neutral. */
export function pnlClass(value: number | null | undefined): "pnl-profit" | "pnl-loss" | "" {
  if (value == null || !Number.isFinite(value) || value === 0) return "";
  return value > 0 ? "pnl-profit" : "pnl-loss";
}

export function applyPnlColorConvention(convention: string, root?: { dataset: DOMStringMap }): void {
  const target = root ?? (typeof document !== "undefined" ? document.documentElement : undefined);
  if (!target) return;
  target.dataset.pnl = isPnlColorConvention(convention) ? convention : "green_up";
}
