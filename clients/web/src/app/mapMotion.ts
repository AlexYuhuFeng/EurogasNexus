/**
 * The map's motion, from the design system's motion tokens (styles/tokens.css): the camera's
 * fly-to, a route drawing in once, and the one loop the map has (the pulse of a disruption
 * touching the book, in CSS). Nothing moves under prefers-reduced-motion.
 */

/** cubic-bezier(x1, y1, x2, y2) as an easing function of t in [0, 1]. */
export function cubicBezier(x1: number, y1: number, x2: number, y2: number): (t: number) => number {
  const cx = 3 * x1;
  const bx = 3 * (x2 - x1) - cx;
  const ax = 1 - cx - bx;
  const cy = 3 * y1;
  const by = 3 * (y2 - y1) - cy;
  const ay = 1 - cy - by;
  const x = (s: number) => ((ax * s + bx) * s + cx) * s;
  const y = (s: number) => ((ay * s + by) * s + cy) * s;
  const dx = (s: number) => (3 * ax * s + 2 * bx) * s + cx;
  return (t: number) => {
    if (t <= 0) return 0;
    if (t >= 1) return 1;
    // Newton steps, then bisection when the slope is too flat.
    let s = t;
    for (let i = 0; i < 8; i += 1) {
      const error = x(s) - t;
      if (Math.abs(error) < 1e-6) return y(s);
      const slope = dx(s);
      if (Math.abs(slope) < 1e-6) break;
      s -= error / slope;
    }
    let lo = 0;
    let hi = 1;
    s = t;
    for (let i = 0; i < 30; i += 1) {
      const value = x(s);
      if (Math.abs(value - t) < 1e-6) break;
      if (value < t) lo = s;
      else hi = s;
      s = (lo + hi) / 2;
    }
    return y(s);
  };
}

/** `--ds-ease-out`: cubic-bezier(0.2, 0, 0, 1). */
export const easeOut = cubicBezier(0.2, 0, 0, 1);

/** A duration token in milliseconds ("400ms", "0.4s"), or the fallback outside a browser. */
export function durationToken(name: string, fallback: number): number {
  if (typeof document === "undefined" || typeof getComputedStyle !== "function") return fallback;
  const raw = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  const value = Number.parseFloat(raw);
  if (!Number.isFinite(value)) return fallback;
  return raw.endsWith("ms") ? value : raw.endsWith("s") ? value * 1000 : value;
}

export function prefersReducedMotion(): boolean {
  return typeof window !== "undefined" && typeof window.matchMedia === "function"
    && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

/** The camera's moves: `--ds-duration-map` with `--ds-ease-out`; none under reduced motion. */
export function cameraMotion(): { duration: number; easing: (t: number) => number } {
  return { duration: prefersReducedMotion() ? 0 : durationToken("--ds-duration-map", 400), easing: easeOut };
}

/** A route draws in once over this long: 1.5 x `--ds-duration-map`, at most 600 ms. */
export function drawInDuration(): number {
  return prefersReducedMotion() ? 0 : Math.min(600, durationToken("--ds-duration-map", 400) * 1.5);
}
