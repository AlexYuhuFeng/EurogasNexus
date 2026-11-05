import { useCallback, useEffect, useState, type RefObject } from "react";

/**
 * Full screen for one element, for a wall or second-monitor view of the live map.
 *
 * Uses the browser's element full screen where it exists (desktop browsers, the Tauri
 * webview, iPad Safari) so the operating system hides everything else and Escape leaves it.
 * Where it does not (iPhone Safari), the element is expanded over the page instead
 * (`expanded`, styled by the caller) and Escape leaves that too.
 */
export function useFullscreen(target: RefObject<HTMLElement | null>) {
  const [native, setNative] = useState(false);
  const [expanded, setExpanded] = useState(false);

  useEffect(() => {
    const sync = () => setNative(Boolean(target.current) && document.fullscreenElement === target.current);
    document.addEventListener("fullscreenchange", sync);
    return () => document.removeEventListener("fullscreenchange", sync);
  }, [target]);

  useEffect(() => {
    if (!expanded) return undefined;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setExpanded(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [expanded]);

  const toggle = useCallback(() => {
    const element = target.current;
    if (!element) return;
    if (document.fullscreenElement) {
      void document.exitFullscreen();
      return;
    }
    if (expanded) {
      setExpanded(false);
      return;
    }
    if (typeof element.requestFullscreen === "function" && document.fullscreenEnabled !== false) {
      element.requestFullscreen().catch(() => setExpanded(true));
    } else {
      setExpanded(true);
    }
  }, [expanded, target]);

  return { active: native || expanded, expanded, toggle };
}
