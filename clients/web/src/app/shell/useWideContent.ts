/**
 * Wide tables at phone width scroll inside their own box (docs/product/UX_REFERENCE.md, "Phone
 * rules"; styles/frame.css).
 *
 * CSS cannot ask "is this table wider than its box?", and turning every table into a scroll box
 * (`display: block`) squeezes its columns to the screen. So the shell measures, after each change
 * to the page, and marks the box that holds a table that does not fit (`data-wide-box`); the
 * stylesheet makes that box scroll sideways with edge shadows, and the table keeps its width. A box that scrolls is reachable by
 * keyboard: one with nothing focusable inside gets `tabindex="0"` (WCAG 2.1.1; the axe sweep's
 * `scrollable-region-focusable`). DataGrid tables are left alone: the grid folds its own columns.
 *
 * Attributes only: React does not own them, so a re-render neither drops nor fights them.
 */
import { useEffect } from "react";

const SCROLLING = new Set(["auto", "scroll"]);
const FOCUSABLE = "a[href], button, input, select, textarea, summary, [tabindex]";
export const WIDE_BOX_ATTRIBUTE = "data-wide-box";
const OWN_TABINDEX = "data-shell-tabindex";

function scrollBox(element: HTMLElement, limit: HTMLElement): HTMLElement | null {
  let current = element.parentElement;
  for (let depth = 0; current && current !== limit && depth < 3; depth += 1) {
    if (SCROLLING.has(getComputedStyle(current).overflowX)) return current;
    current = current.parentElement;
  }
  return null;
}

function keyboardReachable(box: HTMLElement, overflowing: boolean): void {
  const own = box.hasAttribute(OWN_TABINDEX);
  if (overflowing && !box.hasAttribute("tabindex") && !box.querySelector(FOCUSABLE)) {
    box.setAttribute("tabindex", "0");
    box.setAttribute(OWN_TABINDEX, "");
  } else if (!overflowing && own) {
    box.removeAttribute("tabindex");
    box.removeAttribute(OWN_TABINDEX);
  }
}

/** Mark the boxes under `root` whose table is wider than they are (exported for the unit test). */
export function markWideTables(root: HTMLElement, compact: boolean): number {
  let marked = 0;
  for (const table of root.querySelectorAll<HTMLTableElement>("table")) {
    if (table.closest(".ds-grid-wrap")) continue;
    const parent = table.parentElement;
    if (!parent || parent === root) continue;
    const wasWide = parent.hasAttribute(WIDE_BOX_ATTRIBUTE);
    if (!compact) {
      if (wasWide) parent.removeAttribute(WIDE_BOX_ATTRIBUTE);
      keyboardReachable(parent, false);
      continue;
    }
    if (!wasWide) {
      const box = scrollBox(table, root);
      if (box) {
        keyboardReachable(box, box.scrollWidth > box.clientWidth + 1);
        continue;
      }
    }
    const wide = wasWide
      ? parent.scrollWidth > parent.clientWidth + 1
      : table.getBoundingClientRect().width > parent.clientWidth + 1;
    if (wide !== wasWide) {
      if (wide) parent.setAttribute(WIDE_BOX_ATTRIBUTE, "");
      else parent.removeAttribute(WIDE_BOX_ATTRIBUTE);
    }
    keyboardReachable(parent, wide);
    if (wide) marked += 1;
  }
  return marked;
}

/** Keep the marks current while `compact` holds: after every change below the main region. */
export function useWideContent(compact: boolean, rootId = "workspace-primary-content"): void {
  useEffect(() => {
    const root = document.getElementById(rootId);
    if (!root || typeof MutationObserver === "undefined") return undefined;
    let timer = 0;
    const run = () => {
      timer = 0;
      markWideTables(root, compact);
    };
    const schedule = () => {
      if (timer) return;
      timer = window.setTimeout(() => window.requestAnimationFrame(run), 120);
    };
    run();
    const observer = new MutationObserver(schedule);
    observer.observe(root, { childList: true, subtree: true, characterData: true });
    window.addEventListener("resize", schedule);
    return () => {
      observer.disconnect();
      window.removeEventListener("resize", schedule);
      if (timer) window.clearTimeout(timer);
    };
  }, [compact, rootId]);
}
