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
  ...["overview", "resources", "routes", "exposure", "delivery"].map((task) => `?workspace=contracts&task=${task}`),
  ...["scenario", "optimize", "review", "nomination", "dispatch"].map((task) => `?workspace=scenario&task=${task}`),
  ...["spread", "design", "backtest", "experiments"].map((task) => `?workspace=strategy&task=${task}`),
  "?workspace=research&task=reports",
  ...["datasets", "products", "features", "targets"].map((view) => `?workspace=research&view=${view}`),
  ...["capabilities", "research", "runs"].map((view) => `?workspace=agents&view=${view}`),
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
