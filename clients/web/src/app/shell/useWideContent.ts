/**
 * Wide tables at phone width scroll inside their own box (docs/product/UX_REFERENCE.md, "Phone
 * rules"; styles/frame.css).
 *
 * CSS cannot ask "is this table wider than its box?", and a table made a scroll box always
 * (`display: block`) would stop filling its panel when it is narrow. So the shell measures, after
 * each change to the page, and marks only the tables that do not fit (`data-wide-table`); the
 * stylesheet turns those into scroll boxes with edge shadows. A box that scrolls is reachable by
 * keyboard: one with nothing focusable inside gets `tabindex="0"` (WCAG 2.1.1; the axe sweep's
 * `scrollable-region-focusable`). DataGrid tables are left alone: the grid folds its own columns.
 *
 * Attributes only: React does not own them, so a re-render neither drops nor fights them.
 */
import { useEffect } from "react";

const SCROLLING = new Set(["auto", "scroll"]);
const FOCUSABLE = "a[href], button, input, select, textarea, summary, [tabindex]";
export const WIDE_TABLE_ATTRIBUTE = "data-wide-table";
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

/** Mark the tables under `root` that are wider than their box (exported for the unit test). */
export function markWideTables(root: HTMLElement, compact: boolean): number {
  let marked = 0;
  for (const table of root.querySelectorAll<HTMLTableElement>("table")) {
    if (table.closest(".ds-grid-wrap")) continue;
    if (!compact) {
      if (table.hasAttribute(WIDE_TABLE_ATTRIBUTE)) table.removeAttribute(WIDE_TABLE_ATTRIBUTE);
      keyboardReachable(table, false);
      continue;
    }
    const box = scrollBox(table, root);
    if (box) {
      keyboardReachable(box, box.scrollWidth > box.clientWidth + 1);
      continue;
    }
    const wasWide = table.hasAttribute(WIDE_TABLE_ATTRIBUTE);
    const parentWidth = table.parentElement?.clientWidth ?? 0;
    const wide = wasWide
      ? table.scrollWidth > table.clientWidth + 1
      : table.getBoundingClientRect().width > parentWidth + 1;
    if (wide !== wasWide) {
      if (wide) table.setAttribute(WIDE_TABLE_ATTRIBUTE, "");
      else table.removeAttribute(WIDE_TABLE_ATTRIBUTE);
    }
    keyboardReachable(table, wide);
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
