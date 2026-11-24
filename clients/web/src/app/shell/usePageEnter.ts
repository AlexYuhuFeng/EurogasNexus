/**
 * One entrance per page change (UX R10): the page container fades in once, for
 * `--ds-duration-base` with the entry easing, when the reader moves to another page. Panels do
 * not animate on their own, so a tab switch no longer replays an entrance on every panel.
 * Opacity only, so nothing moves under the pointer and fixed-position content keeps its place.
 * Nothing runs on the first page, under reduced motion, or where the Web Animations API is absent.
 */
import { useEffect, useRef, type RefObject } from "react";
import { parseDuration } from "@/components/ui/usePresence";

export function usePageEnter(ref: RefObject<HTMLElement | null>, pageKey: string): void {
  const first = useRef(true);
  useEffect(() => {
    if (first.current) {
      first.current = false;
      return undefined;
    }
    const element = ref.current;
    if (!element || typeof element.animate !== "function") return undefined;
    if (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) return undefined;
    const style = window.getComputedStyle(element);
    const duration = parseDuration(style.getPropertyValue("--ds-duration-base"));
    if (duration <= 0) return undefined;
    const easing = style.getPropertyValue("--ds-ease-out").trim() || "ease-out";
    const animation = element.animate([{ opacity: 0 }, { opacity: 1 }], { duration, easing });
    return () => animation.cancel();
  }, [ref, pageKey]);
}
