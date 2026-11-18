// Phone-width geometry: nothing makes the page wider than the screen (docs/product/UX_REFERENCE.md,
// "Phone rules"; clients/web/src/styles/frame.css).
//
// The document-level check (`scrollWidth > clientWidth`) missed what testers saw on a phone: the
// app root used to be a horizontal scroll container, so the document never overflowed while the
// whole page could be swiped sideways, and a box clipped by the frame hides content without any
// scrollbar. This measures what a reader sees instead:
//
// - `document`: the document scrolls sideways;
// - `frame`: a page-level box (body, the app root, main, the page) is wider than it is shown;
// - `element`: a visible element's right edge passes the screen and no scroll container between it
//   and the page frame contains it (the frame's own clipping does not count as containing).
//
// `PHONE_ROUTES` is every mode task, every administration and research sub-view and every utility
// page, so a page that only overflows on its third tab is still found.

export const PHONE_ROUTES = [
  ...["overview", "curves", "network", "capacity"].map((task) => `?workspace=market&task=${task}`),
  ...["overview", "resources", "exposure", "delivery"].map((task) => `?workspace=contracts&task=${task}`),
  ...["review", "nomination", "dispatch"].map((task) => `?workspace=scenario&task=${task}`),
  "?workspace=research&task=reports",
  "?workspace=research&task=spreads",
  "?workspace=research&task=fundamentals",
  ...["attention", "catalog", "access", "infrastructure"].map((view) => `?workspace=sources&view=${view}`),
  ...["delivery", "readiness", "governance", "support"].map((view) => `?workspace=runtime&view=${view}`),
  ...["users", "api_keys", "catalogue", "audit", "sso"].map((view) => `?workspace=access&view=${view}`),
  "?workspace=glossary",
  "?workspace=manual",
  "?workspace=settings",
];

export const PHONE_WIDTHS = [360, 390, 430];

/**
 * Runs in the page (Playwright `page.evaluate`): self-contained, no closure over module scope.
 * Returns `{ problems: string[] }`, each problem one line naming the element and its edges.
 */
export function measurePhoneOverflow() {
  const width = document.documentElement.clientWidth;
  const problems = [];
  const describe = (element) => {
    const parts = [];
    for (let node = element, depth = 0; node && node !== document.body && depth < 3; node = node.parentElement, depth += 1) {
      const classes = typeof node.className === "string" ? node.className.trim().split(/\s+/).slice(0, 2).join(".") : "";
      parts.unshift(`${node.tagName.toLowerCase()}${node.id ? `#${node.id}` : ""}${classes ? `.${classes}` : ""}`);
    }
    return parts.join(" > ");
  };
  if (document.documentElement.scrollWidth > width + 1) {
    problems.push(`document scrolls sideways (${document.documentElement.scrollWidth}px > ${width}px)`);
  }
  const frame = [document.body, document.querySelector(".cockpit-app"), document.querySelector("main"),
    ...document.querySelectorAll(".workspace-page")].filter(Boolean);
  for (const box of frame) {
    const style = getComputedStyle(box);
    if (style.display === "none") continue;
    if (box.scrollWidth > box.clientWidth + 1) {
      problems.push(`frame ${describe(box)} holds ${box.scrollWidth}px in ${box.clientWidth}px`);
    }
  }
  const frameSet = new Set(frame);
  const contained = (element) => {
    for (let node = element.parentElement; node && node !== document.documentElement; node = node.parentElement) {
      if (frameSet.has(node)) continue;
      const style = getComputedStyle(node);
      if (style.position === "fixed") return true;
      if (["auto", "scroll", "hidden", "clip"].includes(style.overflowX)) {
        const rect = node.getBoundingClientRect();
        if (rect.right <= width + 1 && rect.left >= -1) return true;
      }
    }
    return false;
  };
  const over = new Set();
  for (const element of document.querySelectorAll("header *, main *, .app > *")) {
    const rect = element.getBoundingClientRect();
    if (rect.width === 0 || rect.height === 0) continue;
    const style = getComputedStyle(element);
    if (style.visibility === "hidden" || style.position === "fixed") continue;
    // The body of a closed <details> keeps a box but is not drawn (content-visibility: hidden).
    if (typeof element.checkVisibility === "function" && !element.checkVisibility({ contentVisibilityAuto: true, visibilityProperty: true })) continue;
    const closed = element.closest("details:not([open])");
    if (closed && !element.closest("summary")) continue;
    // MapLibre draws its own canvas and controls; the map owns their geometry.
    if (element.closest(".maplibregl-map")) continue;
    if ((rect.right > width + 1 || rect.left < -1) && !contained(element)) over.add(element);
  }
  for (const element of over) {
    if (element.parentElement && over.has(element.parentElement)) continue;
    const rect = element.getBoundingClientRect();
    problems.push(
      `element ${describe(element)} spans ${Math.round(rect.left)}..${Math.round(rect.right)}px on a ${width}px screen`
      + ` ("${(element.textContent || "").trim().slice(0, 40)}")`,
    );
  }
  return { problems: problems.slice(0, 12) };
}

/**
 * Pages being deleted under COMMERCIAL_PRODUCT_DESIGN_2 (Deals -> Evaluate/Optimise/Routes,
 * Research -> Strategies/Data/Assistant): not polished, so not held to the enum rule. The list may
 * only shrink.
 */
export const ENUM_RULE_EXEMPT_ROUTES = new Set([
  "?workspace=scenario&task=scenario",
  "?workspace=scenario&task=optimize",
  "?workspace=contracts&task=routes",
  ...["spread", "design", "backtest", "experiments"].map((task) => `?workspace=strategy&task=${task}`),
  ...["datasets", "products", "features", "targets"].map((view) => `?workspace=research&view=${view}`),
  ...["capabilities", "research", "runs"].map((view) => `?workspace=agents&view=${view}`),
]);

/**
 * Runs in the page: visible text that is a bare enum code (`SUCCEEDED_WITH_WARNINGS`), which the
 * screen must say in words (UX_REFERENCE rule 21). Code and preformatted text, closed disclosures
 * and hidden text are not read; an element's `title` is where a code may stay.
 */
export function findVisibleEnums() {
  const found = new Map();
  const root = document.querySelector("main") ?? document.body;
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  for (let node = walker.nextNode(); node; node = walker.nextNode()) {
    const element = node.parentElement;
    if (!element || element.closest("code, pre, kbd, samp, script, style, [hidden], .ds-visually-hidden")) continue;
    if (typeof element.checkVisibility === "function" && !element.checkVisibility({ contentVisibilityAuto: true, visibilityProperty: true })) continue;
    const rect = element.getBoundingClientRect();
    if (!rect.width || !rect.height) continue;
    for (const match of String(node.textContent).matchAll(/\b[A-Z][A-Z0-9]+(?:_[A-Z0-9]+)+\b/g)) {
      found.set(match[0], element.tagName.toLowerCase());
    }
  }
  return [...found.keys()].slice(0, 8);
}

/** Routes of commercial tasks (design basis H.2): each shows a purpose line. */
/**
 * Pages that still offer a JSON upload, removed by their own package (design basis H.3): the
 * contract import (to PDF, form and CSV). Any other page with a JSON file input fails the page
 * contract.
 */
export const JSON_UPLOAD_PENDING_REMOVAL = new Set(["?workspace=contracts&task=resources"]);

export const PURPOSE_ROUTES = new Set([
  ...["overview", "curves", "network"].map((task) => `?workspace=market&task=${task}`),
  ...["overview", "resources", "exposure", "delivery"].map((task) => `?workspace=contracts&task=${task}`),
  ...["review", "nomination", "dispatch"].map((task) => `?workspace=scenario&task=${task}`),
  "?workspace=research&task=reports",
  "?workspace=research&task=spreads",
  "?workspace=research&task=fundamentals",
]);

/**
 * Runs in the page: the page contract (design basis H.1; ROLE_FIRST_REDESIGN I5). Returns one
 * line per breach: no purpose line (when `needsPurpose`), a purpose over 110 characters, an
 * empty state without a reason, or a file input that accepts JSON.
 */
export function checkPageContract({ needsPurpose, jsonUploadAllowed }) {
  const problems = [];
  const visible = (element) => {
    const box = element.getBoundingClientRect();
    return box.width > 0 && box.height > 0;
  };
  const purposes = [...document.querySelectorAll("[data-purpose]")].filter(visible);
  if (needsPurpose && purposes.length === 0) problems.push("no purpose line ([data-purpose])");
  for (const purpose of purposes) {
    const text = (purpose.textContent || "").trim();
    if (text.length > 110) problems.push(`purpose line is ${text.length} characters: ${text.slice(0, 60)}...`);
  }
  for (const empty of document.querySelectorAll("[data-empty-state]")) {
    if (!visible(empty)) continue;
    // The reason is the EmptyState's <strong>, or the marked line's own text.
    if (!((empty.querySelector("strong") ?? empty).textContent || "").trim()) {
      problems.push(`empty state without a reason: ${empty.getAttribute("data-empty-state") || "(unnamed)"}`);
    }
  }
  for (const input of jsonUploadAllowed ? [] : document.querySelectorAll('input[type="file"]')) {
    if (/json/i.test(input.getAttribute("accept") || "")) {
      problems.push(`file input accepts JSON: ${input.id || input.name || "(unnamed)"}`);
    }
  }
  return { problems };
}
