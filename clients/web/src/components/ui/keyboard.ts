/**
 * Keyboard movement shared by the roving-focus primitives (Tabs, Segmented, Toolbar, DataGrid
 * rows). Pure functions, so the behaviour is tested without a browser.
 */
export type Orientation = "horizontal" | "vertical";

/**
 * The index a key moves to in a list of `count` items, or null when the key does not move.
 * Horizontal lists use Left/Right, vertical lists Up/Down; Home and End go to either end.
 * `wrap` loops past the ends (tabs, segmented controls); without it the ends hold (grid rows).
 */
export function rovingIndex(
  current: number,
  count: number,
  key: string,
  { orientation = "horizontal", wrap = true }: { orientation?: Orientation; wrap?: boolean } = {},
): number | null {
  if (!Number.isInteger(current) || count <= 0) return null;
  const start = Math.min(Math.max(current, 0), count - 1);
  const next = orientation === "horizontal" ? "ArrowRight" : "ArrowDown";
  const previous = orientation === "horizontal" ? "ArrowLeft" : "ArrowUp";
  if (key === "Home") return 0;
  if (key === "End") return count - 1;
  if (key === next) return wrap ? (start + 1) % count : Math.min(start + 1, count - 1);
  if (key === previous) return wrap ? (start - 1 + count) % count : Math.max(start - 1, 0);
  return null;
}

/** Rows a PageUp/PageDown moves in a grid: a screenful of dense rows. */
export const GRID_PAGE_ROWS = 10;

/** The row index a key moves to in a grid of `count` rows (no wrap; PageUp/PageDown by a page). */
export function gridRowIndex(current: number, count: number, key: string): number | null {
  if (count <= 0) return null;
  if (key === "PageDown") return Math.min(Math.max(current, 0) + GRID_PAGE_ROWS, count - 1);
  if (key === "PageUp") return Math.max(Math.max(current, 0) - GRID_PAGE_ROWS, 0);
  return rovingIndex(current, count, key, { orientation: "vertical", wrap: false });
}
