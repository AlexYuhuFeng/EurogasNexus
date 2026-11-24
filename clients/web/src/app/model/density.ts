/**
 * Row density (UX R11): how tall a table or list row is, the one thing a trader on a laptop
 * wants to trade for more prices above the fold. `comfortable` keeps rows at 32 px (header
 * 28); `compact` sets `data-density="compact"` on the document, and tokens.css re-points
 * `--ds-row` to 28 and `--ds-row-header` to 24. Controls (28/32, 44 on touch), type and
 * spacing do not change: rows are not controls, so the geometry budgets and the touch-target
 * rule hold in both densities.
 */

export type Density = "comfortable" | "compact";

export const DENSITIES: Density[] = ["comfortable", "compact"];

export const DENSITY_STORAGE_KEY = "eurogas.density";

export function isDensity(value: unknown): value is Density {
  return typeof value === "string" && (DENSITIES as string[]).includes(value);
}

export function applyDensity(density: string, root?: { dataset: DOMStringMap }): Density {
  const target = root ?? (typeof document !== "undefined" ? document.documentElement : undefined);
  const value: Density = isDensity(density) ? density : "comfortable";
  if (target) target.dataset.density = value;
  return value;
}

export function readStoredDensity(): Density {
  try {
    const stored = window.localStorage.getItem(DENSITY_STORAGE_KEY);
    return isDensity(stored) ? stored : "comfortable";
  } catch {
    return "comfortable";
  }
}

export function writeStoredDensity(density: Density): void {
  try {
    window.localStorage.setItem(DENSITY_STORAGE_KEY, density);
  } catch {
    // The server copy still holds it.
  }
}
