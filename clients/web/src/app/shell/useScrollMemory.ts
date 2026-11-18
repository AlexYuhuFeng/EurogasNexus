/**
 * Coming back to a page or task puts the reader where they were (docs/product/UX_REFERENCE.md,
 * rule 19): the window's scroll position is remembered per page and task for the session and
 * restored when the reader returns, after the page has had a few frames to draw its kept data.
 * Selections, tabs and filters already live in the URL or the stores, so only the scroll is kept
 * here.
 */
import { useEffect, useRef } from "react";

const positions = new Map<string, number>();

/** The page and its task or view: the part of the address that names where the reader is. */
export function scrollMemoryKey(search: string): string {
  const params = new URLSearchParams(search);
  return ["workspace", "task", "view", "panel"].map((name) => params.get(name) ?? "").join("|");
}

export function useScrollMemory(locationKey: string): void {
  const current = useRef(locationKey);
  useEffect(() => {
    const save = () => positions.set(current.current, window.scrollY);
    window.addEventListener("scroll", save, { passive: true });
    return () => window.removeEventListener("scroll", save);
  }, []);
  useEffect(() => {
    if (current.current === locationKey) return;
    current.current = locationKey;
    const target = positions.get(locationKey) ?? 0;
    let frames = 0;
    let handle = 0;
    // Kept data draws in the first frames; follow it until the page is tall enough or 20 frames pass.
    const restore = () => {
      window.scrollTo(0, target);
      frames += 1;
      if (Math.abs(window.scrollY - target) > 2 && frames < 20) handle = window.requestAnimationFrame(restore);
    };
    handle = window.requestAnimationFrame(restore);
    return () => window.cancelAnimationFrame(handle);
  }, [locationKey]);
}
