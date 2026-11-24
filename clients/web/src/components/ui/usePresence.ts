/**
 * Keep an overlay's content rendered while it plays its exit (UX R10). `open` false starts the
 * close; the content stays for the element's exit duration (`--ds-duration-exit`, or the slower
 * one a sheet sets) and then unmounts. Under reduced motion, or where the duration cannot be
 * read, it unmounts at once, as before.
 */
import { useEffect, useState, type RefObject } from "react";

export function exitDurationMs(element: Element | null): number {
  if (!element || typeof window === "undefined" || typeof window.getComputedStyle !== "function") return 0;
  if (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) return 0;
  const style = window.getComputedStyle(element);
  // The CSS transition on the closed state is the truth; the token is the fallback.
  const fromTransition = style.transitionDuration?.split(",").map((part) => parseDuration(part)) ?? [];
  const longest = Math.max(0, ...fromTransition);
  return longest > 0 ? longest : parseDuration(style.getPropertyValue("--ds-duration-exit"));
}

export function parseDuration(value: string | null | undefined): number {
  const text = (value ?? "").trim();
  const match = text.match(/^(\d+(?:\.\d+)?)(ms|s)$/);
  if (!match) return 0;
  return match[2] === "s" ? Number(match[1]) * 1000 : Number(match[1]);
}

export function usePresence(open: boolean, ref: RefObject<Element | null>): boolean {
  const [present, setPresent] = useState(open);
  useEffect(() => {
    if (open) {
      setPresent(true);
      return undefined;
    }
    // Read after the close has switched the closed-state transition on.
    const ms = exitDurationMs(ref.current);
    if (ms <= 0) {
      setPresent(false);
      return undefined;
    }
    const timer = window.setTimeout(() => setPresent(false), ms);
    return () => window.clearTimeout(timer);
  }, [open, ref]);
  return open || present;
}
