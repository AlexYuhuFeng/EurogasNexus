import { useCallback, useEffect, useState } from "react";

/**
 * The map expanded to fill the app window, by CSS: no browser or operating-system full screen.
 *
 * The Fullscreen API is not used anywhere in the client (owner, 2026-11-26): on macOS, Safari and
 * WebKit full screen (and the Tauri WebView in native full screen) blocks keyboard input, so the
 * map's finder could not be typed into, and dragging the map misbehaved. Expanded, the element is
 * positioned over the app (the caller's `is-expanded` class), the app chrome is covered and the
 * page does not scroll behind it; the finder, the Layers menu (drawn in the top layer) and the
 * side panel keep working because nothing leaves the document. A visible button and Escape (the
 * caller's handler, which lets an open card or drawer take Escape first) restore it.
 */
export function useExpandedView() {
  const [expanded, setExpanded] = useState(false);

  useEffect(() => {
    if (!expanded || typeof document === "undefined") return undefined;
    const root = document.documentElement;
    root.classList.add("has-expanded-view");
    return () => root.classList.remove("has-expanded-view");
  }, [expanded]);

  const toggle = useCallback(() => setExpanded((value) => !value), []);
  const exit = useCallback(() => setExpanded(false), []);

  return { expanded, toggle, exit };
}
