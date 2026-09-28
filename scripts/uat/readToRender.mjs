/**
 * Scoped read-to-render evidence for the whole-product browser sweep.
 *
 * The sweep used to judge a surface "after load" by searching the whole displayed page for
 * `n/a`, `unavailable`, `no data` or `not available`, and it counted any non-array read body as
 * one row. Both halves were wrong in the same direction: the portfolio context strip's own
 * honest sentence ("N slice(s) stale, missing or unavailable"), an unmeasured portfolio total
 * and a language-independent literal `n/a` in a table's empty state all read as "the surface
 * renders none of the rows this read returned" - and an aggregate summary object read as a row
 * set. The failures on the contracts and orders surfaces (CI run 35996627042) were that
 * inference, not missing rows.
 *
 * These helpers compare the rows a read returned with the rows a surface actually rendered. The
 * comparison is scoped rather than inferred:
 *
 * - a read group names the stable DOM selector its own rows live under, and only the elements
 *   that selector matches inside the *displayed* page are its evidence - never another panel's
 *   rows, and never the page's copy;
 * - identity is the record's own id: each row element carries the identifier verbatim
 *   (`data-record-id`), and a returned row matches only an element whose id is exactly equal -
 *   `contract-1` does not stand in for `contract-11`;
 * - one element is one piece of evidence (the collector de-duplicates overlapping selectors), so
 *   duplicate rows need duplicate rendered rows;
 * - an empty read is compared with the surface's declared empty-state marker
 *   (`data-empty-state`), so a populated table the read no longer returned is a stale-row
 *   failure rather than a pass;
 * - a returned row that carries no id, a slice that served rows without declaring availability,
 *   and a group whose evidence was not collected are failures rather than quiet observations;
 * - a group that declares `exactRows` is compared in both directions: a rendered row its own read
 *   did not return then fails by name, because that group claims the read is the surface's whole
 *   row set (the source catalog), not a bound over a larger set.
 *
 * The decision logic is pure so every negative case can be exercised without a browser
 * (`clients/web/tests/readToRender.test.ts`); `collectVisibleElements` is serialised into the
 * page by `page.evaluate` and exercised there against a stub document.
 *
 * The market hub board's quoted values are a second shape of the same rule: its cards name the row
 * each priced (id and slice) and are compared with that row's own numbers, source and unit, for the
 * tenor and hubs the board declares (`collectQuotedBoard`, `marketBoardRows`,
 * `evaluateQuotedBoard`, below).
 */

/** The attribute a rendered row carries its own record identifier in. */
export const RECORD_ID_ATTRIBUTE = "data-record-id";

/** Read one dotted path out of a payload without widening the payload type. */
function valueAtPath(root, path) {
  let node = root;
  for (const segment of String(path).split(".")) {
    if (node === null || node === undefined || typeof node !== "object") return undefined;
    node = node[segment];
  }
  return node;
}

/**
 * The record identifier a returned row carries, verbatim, or `null` when it carries none.
 *
 * Only an id a surface can render verbatim is usable: a number is stringified the way the DOM
 * attribute would carry it, and a missing or blank one proves nothing - the caller fails the row
 * as uncomparable rather than matching it optimistically.
 */
export function rowRecordId(row, field) {
  const value = row?.[field];
  if (typeof value === "string" && value.trim() !== "") return value.trim();
  if (typeof value === "number" && Number.isFinite(value)) return String(value);
  return null;
}

/**
 * The rows one declared read group returned, with every reason they cannot be compared.
 *
 * A path may name an array (a route envelope's `data`) or a projection slice, whose rows live
 * under `rows`. A slice the backend did not serve (`available: false`) is reported as
 * *unmeasured* rather than as an empty row set: "not served" and "measured zero" are different
 * answers, and only the second is a row count a surface could have rendered. A slice that
 * carries rows without declaring availability at all, or a group that names no rows path,
 * record id field or row selector, is a `problem` the caller reports as a failure - a
 * declaration that cannot be compared must not pass as one that was.
 */
export function readGroupRows(body, group) {
  const problems = [];
  for (const [field, description] of [
    ["rowsPath", "path for the rows its read returns"],
    ["recordIdField", "payload field carrying each row's record id"],
    ["rowSelectors", "selector for its own rendered rows"],
  ]) {
    const value = group?.[field];
    const declared = Array.isArray(value)
      ? value.length > 0 && value.every((item) => typeof item === "string" && item.trim() !== "")
      : typeof value === "string" && value.trim() !== "";
    if (!declared) problems.push(`the group declares no ${description}, so it cannot be compared`);
  }
  if (problems.length > 0) {
    return { ...group, readable: false, available: false, rows: [], problems };
  }

  const node = valueAtPath(body, group.rowsPath);
  const rows = Array.isArray(node)
    ? node
    : node && typeof node === "object" && Array.isArray(node.rows)
      ? node.rows
      : null;
  if (rows === null) {
    return {
      ...group,
      readable: false,
      available: false,
      rows: [],
      problems: [`the payload carries no row set at '${group.rowsPath}'`],
    };
  }
  if (!Array.isArray(node) && typeof node.available !== "boolean") {
    return {
      ...group,
      readable: false,
      available: false,
      rows: [],
      problems: [
        `the slice at '${group.rowsPath}' carries rows without declaring whether it is available`,
      ],
    };
  }
  return {
    ...group,
    readable: true,
    available: Array.isArray(node) ? true : node.available === true,
    rows,
    problems: [],
  };
}

/**
 * The read's own provenance label, when its envelope carries one.
 *
 * It keeps an empty answer honest: "no rows" from a read that could not reach the runtime
 * database is not the same statement as a measured zero, and the summary says which one it was.
 */
export function readSourceLabel(body) {
  const source = body?.meta?.source;
  return typeof source === "string" && source.trim() !== "" ? source.trim() : null;
}

/** The selector list a group's rows are collected by, named in every failure about them. */
function selectorLabel(group) {
  return Array.isArray(group.rowSelectors)
    ? group.rowSelectors.join(", ")
    : String(group.rowSelectors);
}

/**
 * Compare what a read returned with what the surface rendered, one read group at a time.
 *
 * `groups` are the outputs of `readGroupRows`; `evidence` is the collector's output for the same
 * groups, in the same order. A returned row counts as rendered when one visible element
 * *collected for that group* carries its exact record id, and each element stands for one row -
 * so duplicate rows are counted, a returned row no element carries is a failure, a returned row
 * with no id is a failure, an empty successful answer must not sit beside populated rows, and a
 * measurement the check could not perform is reported instead of passing silently.
 */
export function evaluateReadToRender({ status, groups, evidence = [], source = null }) {
  const failures = [];
  const observations = [];
  if (status !== 200) {
    failures.push(
      `the surface's own read answered ${status === null || status === undefined ? "nothing" : status}`
      + "; read-to-render could not be measured",
    );
    return { failures, observations };
  }
  if (evidence.length !== groups.length) {
    failures.push(
      `the sweep collected rendered-row evidence for ${evidence.length} group(s) and the surface`
      + ` declares ${groups.length}: the two could not be compared`,
    );
    return { failures, observations };
  }

  groups.forEach((group, index) => {
    const label = group.label ?? group.rowsPath ?? `group ${index + 1}`;
    if (group.problems?.length > 0) {
      for (const problem of group.problems) failures.push(`${label}: ${problem}`);
      return;
    }
    if (!group.available) {
      observations.push(
        `${label}: the backend did not serve this slice, so there were no rows to compare`,
      );
      return;
    }

    const rendered = evidence[index];
    if (rendered.missingRecordIds > 0) {
      failures.push(
        `${label}: ${rendered.missingRecordIds} visible row(s) matching '${selectorLabel(group)}'`
        + ` carry no ${RECORD_ID_ATTRIBUTE}, so they cannot be compared with a returned row`,
      );
    }

    const rows = group.rowLimit ? group.rows.slice(0, group.rowLimit) : group.rows;
    if (rows.length === 0) {
      if (rendered.recordIds.length > 0) {
        failures.push(
          `${label}: the read returned no rows (200${source ? `, ${source}` : ""}) and the surface`
          + ` still renders ${rendered.recordIds.length} populated row(s) matching`
          + ` '${selectorLabel(group)}': stale rows are not a measured zero`,
        );
      } else if (group.emptySelector) {
        if (rendered.emptyState) {
          observations.push(
            `${label}: the read returned no rows (200) and the surface renders its declared`
            + " empty state",
          );
        } else {
          failures.push(
            `${label}: the read returned no rows (200) and the surface shows neither rows nor its`
            + ` declared empty state (${group.emptySelector})`,
          );
        }
      } else {
        observations.push(
          `${label}: the read returned no rows (200${source ? `, ${source}` : ""}) - no row was`
          + " available to compare",
        );
      }
      return;
    }

    const remaining = [...rendered.recordIds];
    const unmatched = [];
    let unattributable = 0;
    for (const row of rows) {
      const id = rowRecordId(row, group.recordIdField);
      if (id === null) {
        unattributable += 1;
        continue;
      }
      const at = remaining.indexOf(id);
      if (at === -1) unmatched.push(id);
      else remaining.splice(at, 1);
    }
    if (unattributable > 0) {
      failures.push(
        `${label}: ${unattributable} returned row(s) carry no '${group.recordIdField}', so no`
        + " rendered row could be compared with them",
      );
    }
    if (unmatched.length > 0) {
      const detail = unmatched.slice(0, 4).join(" | ");
      failures.push(
        unmatched.length === rows.length
          ? `${label}: the read returned ${rows.length} row(s) (200) and no rendered row carries`
            + ` their id: ${detail}`
          : `${label}: the read returned ${rows.length} row(s) (200) and ${unmatched.length} have no`
            + ` rendered row carrying their id: ${detail}`,
      );
    } else if (rows.length > unattributable) {
      const matched = rows.length - unattributable;
      observations.push(
        `${label}: ${matched} returned row(s) (200) matched ${matched} rendered row(s)`
        + ` by ${group.recordIdField}`,
      );
    }

    // The rows the surface rendered that its own read did not return. Only a group declaring
    // `exactRows` is held to this direction, because only then is the read claimed to be the
    // surface's whole row set rather than a bound over a larger one; a `rowLimit` cuts the
    // returned rows, so the rows beyond it are not an answer about this read.
    if (group.exactRows === true && !group.rowLimit && remaining.length > 0) {
      failures.push(
        `${label}: the surface renders ${remaining.length} row(s) its own read did not return`
        + ` (200): ${remaining.slice(0, 4).join(" | ")}`,
      );
    }
  });
  return { failures, observations };
}

/**
 * The route-state badge fixture: the map overlay's status pills, rendered and measured in the
 * running page.
 *
 * CI 36428725740 measured the Chinese candidate pill as white on `#0ea5e9` - 2.77 against the
 * 4.5 the product requires for its 10px label - but only because that run's seeded data happened
 * to place a candidate path. The overlay's legend and pills are data-dependent, so a later run
 * without a candidate could pass while rendering nothing to measure. This fixture makes the three
 * states deterministic: `mountRouteBadgeFixture` renders exactly the pill markup
 * `ResourcePoolPathOverlay` renders (`<em class="resource-route-state-pill {state}">label</em>`)
 * with the labels the sweep read from the app's own `clients/web/src/i18n` files, inside the
 * displayed workspace page - so the production stylesheet and its theme tokens are the ones in
 * force - and `evaluateRouteBadgeContrast` holds the measured colours and boxes to the product's
 * own minimum.
 */

/** The attribute the mounted badge fixture carries; the sweep's handle for axe and screenshots. */
export const ROUTE_BADGE_FIXTURE_ATTRIBUTE = "data-uat-route-state-fixture";

/** The three route states the product declares (`ResourcePoolMapPath["routeState"]`). */
export const ROUTE_BADGE_STATES = ["allocated", "candidate", "blocked"];

/** WCAG 2.x AA minimum for the badge's 10px text; never lowered, only published. */
export const ROUTE_BADGE_MIN_CONTRAST = 4.5;

/** The channels of a hex or `rgb()`/`rgba()` colour; null when the value is not a colour. */
function colorChannels(color) {
  const text = String(color ?? "").trim();
  const hex = text.match(/^#([0-9a-f]{3}|[0-9a-f]{6})$/i);
  if (hex) {
    const digits = hex[1].length === 3
      ? hex[1].split("").map((digit) => digit + digit).join("")
      : hex[1];
    return [0, 2, 4].map((at) => parseInt(digits.slice(at, at + 2), 16));
  }
  const rgb = text.match(/^rgba?\(\s*([0-9.]+)[,\s]+([0-9.]+)[,\s]+([0-9.]+)/i);
  if (!rgb) return null;
  const channels = rgb.slice(1, 4).map(Number);
  if (!channels.every((value) => Number.isFinite(value) && value >= 0 && value <= 255)) return null;
  return channels;
}

/** WCAG 2.x relative luminance of a colour; null when the value is not a usable opaque colour. */
export function relativeLuminance(color) {
  const channels = colorChannels(color);
  if (!channels) return null;
  const linear = channels.map((value) => {
    const channel = value / 255;
    return channel <= 0.03928 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2];
}

/** WCAG 2.x contrast ratio between two colours; null when either cannot be read. */
export function contrastRatio(foreground, background) {
  const fg = relativeLuminance(foreground);
  const bg = relativeLuminance(background);
  if (fg === null || bg === null) return null;
  const lighter = Math.max(fg, bg);
  const darker = Math.min(fg, bg);
  return (lighter + 0.05) / (darker + 0.05);
}

/**
 * Whether a computed colour is fully opaque.
 *
 * A translucent badge background makes its text ratio unmeasurable (whatever is behind it would
 * be part of the contrast), so the verdict refuses it instead of measuring against a colour the
 * browser never painted.
 */
export function isOpaqueColor(color) {
  const text = String(color ?? "").trim();
  const rgba = text.match(/^rgba\(\s*[0-9.]+[,\s]+[0-9.]+[,\s]+[0-9.]+[,\s/]+([0-9.]+%?)\s*\)$/i);
  if (rgba) {
    const raw = rgba[1];
    const alpha = raw.endsWith("%") ? Number(raw.slice(0, -1)) / 100 : Number(raw);
    return Number.isFinite(alpha) && alpha >= 1;
  }
  return /^rgb\(/i.test(text) || /^#[0-9a-f]{3}([0-9a-f]{3})?$/i.test(text);
}

/**
 * Render the three route-state pills inside the displayed workspace page and measure them.
 *
 * Self-contained (the sweep serialises this function into the page), so every selector and
 * attribute name is a literal here. The fixture is fixed-positioned on purpose: it has to be
 * fully on screen at every viewport (390x844 included) so its screenshot and the box checks are
 * evidence, and it is removed again before the sweep screenshots the page itself. The markup is
 * the overlay's own: `<em class="resource-route-state-pill {state}">{label}</em>`.
 */
export function mountRouteBadgeFixture(spec) {
  const labels = (spec && spec.labels) || {};
  const existing = document.querySelector("[data-uat-route-state-fixture]");
  if (existing) existing.remove();
  const isVisible = (element) => {
    const style = window.getComputedStyle(element);
    const rect = element.getBoundingClientRect();
    return style.display !== "none" && style.visibility !== "hidden" && rect.width > 0 && rect.height > 0;
  };
  const host = [...document.querySelectorAll(".workspace-page")].find(isVisible);
  if (!host) {
    return {
      mounted: false,
      reason: "no displayed .workspace-page to render the route-state badge fixture inside",
      states: [],
    };
  }
  const container = document.createElement("div");
  container.setAttribute("data-uat-route-state-fixture", "mounted");
  container.setAttribute("role", "group");
  container.setAttribute("aria-label", "route-state badge fixture");
  Object.assign(container.style, {
    position: "fixed",
    top: "8px",
    left: "8px",
    zIndex: "2147483000",
    display: "flex",
    gap: "6px",
    padding: "6px",
    background: "transparent",
  });
  for (const state of ["allocated", "candidate", "blocked"]) {
    const pill = document.createElement("em");
    pill.className = "resource-route-state-pill " + state;
    pill.setAttribute("data-route-state", state);
    pill.textContent = String(labels[state] || "");
    container.append(pill);
  }
  host.append(container);
  const containerRect = container.getBoundingClientRect();
  const states = [];
  for (const pill of container.querySelectorAll("[data-route-state]")) {
    const style = window.getComputedStyle(pill);
    const rect = pill.getBoundingClientRect();
    states.push({
      state: pill.getAttribute("data-route-state"),
      text: String(pill.textContent || "").trim(),
      color: style.color,
      backgroundColor: style.backgroundColor,
      fontSize: style.fontSize,
      fontWeight: style.fontWeight,
      display: style.display,
      visibility: style.visibility,
      opacity: style.opacity,
      clientWidth: pill.clientWidth,
      clientHeight: pill.clientHeight,
      scrollWidth: pill.scrollWidth,
      scrollHeight: pill.scrollHeight,
      box: { x: rect.x, y: rect.y, width: rect.width, height: rect.height },
    });
  }
  return {
    mounted: true,
    container: {
      box: {
        x: containerRect.x,
        y: containerRect.y,
        width: containerRect.width,
        height: containerRect.height,
      },
    },
    viewport: { width: window.innerWidth, height: window.innerHeight },
    states,
  };
}

/** Remove the mounted fixture, so nothing the sweep screenshots afterwards contains it. */
export function removeRouteBadgeFixture() {
  const fixture = document.querySelector("[data-uat-route-state-fixture]");
  if (!fixture) return { removed: false };
  fixture.remove();
  return { removed: true };
}

/**
 * The verdict for the mounted badge fixture: are the three route-state pills rendered with the
 * product's own labels, readable at the required ratio, and laid out without overlap or clipping?
 *
 * `fixture` is `mountRouteBadgeFixture`'s measurement, `labels` the app's own translations the
 * fixture was asked to render. Every failure names the state it is about; the measured colours
 * and ratios travel as observations so a green run states what it measured. Pure, so the negative
 * cases run without a browser (`clients/web/tests/readToRender.test.ts`).
 */
export function evaluateRouteBadgeContrast({ fixture, labels = {} }) {
  const failures = [];
  const observations = [];
  if (!fixture) {
    failures.push("the route-state badge fixture was not measured: the check collected nothing");
    return { failures, observations };
  }
  if (fixture.mounted !== true) {
    failures.push(
      "the route-state badge fixture could not be mounted:"
      + ` ${fixture.reason || "no reason reported"}`,
    );
    return { failures, observations };
  }
  const viewport = fixture.viewport || { width: 0, height: 0 };
  const byState = new Map((fixture.states || []).map((entry) => [entry.state, entry]));
  const backgrounds = new Map();
  for (const state of ROUTE_BADGE_STATES) {
    const entry = byState.get(state);
    if (!entry) {
      failures.push(`the route-state badge fixture rendered no ${state} pill`);
      continue;
    }
    const expected = labels[state];
    if (entry.text === "") {
      failures.push(`the ${state} pill rendered no label text`);
    } else if (expected !== undefined && entry.text !== expected) {
      failures.push(
        `the ${state} pill rendered '${entry.text || "(no text)"}' while the app's own label is`
        + ` '${expected}'`,
      );
    }
    if (
      entry.display === "none"
      || entry.visibility === "hidden"
      || Number(entry.opacity) === 0
      || !(Number(entry.box?.width) > 0 && Number(entry.box?.height) > 0)
    ) {
      failures.push(`the ${state} pill is not visible on the page`);
    }
    const box = entry.box || { x: 0, y: 0, width: 0, height: 0 };
    const tolerance = 1;
    if (
      box.x < -tolerance
      || box.y < -tolerance
      || box.x + box.width > viewport.width + tolerance
      || box.y + box.height > viewport.height + tolerance
    ) {
      failures.push(
        `the ${state} pill sits outside the ${viewport.width}x${viewport.height} viewport at`
        + ` ${Math.round(box.x)},${Math.round(box.y)} (${Math.round(box.width)}x${Math.round(box.height)})`,
      );
    }
    if (!isOpaqueColor(entry.color) || !isOpaqueColor(entry.backgroundColor)) {
      failures.push(
        `the ${state} pill's colours are not opaque (text '${entry.color}', background`
        + ` '${entry.backgroundColor}'), so its contrast cannot be measured`,
      );
    } else {
      const ratio = contrastRatio(entry.color, entry.backgroundColor);
      if (ratio === null) {
        failures.push(
          `the ${state} pill's colours could not be read (text '${entry.color}', background`
          + ` '${entry.backgroundColor}')`,
        );
      } else {
        observations.push(
          `the ${state} pill renders '${entry.text}' at ${entry.color} on ${entry.backgroundColor}`
          + ` (${ratio.toFixed(2)}:1, ${entry.fontSize} weight ${entry.fontWeight})`,
        );
        if (ratio < ROUTE_BADGE_MIN_CONTRAST) {
          failures.push(
            `the ${state} pill's text is ${ratio.toFixed(2)}:1 (${entry.color} on`
            + ` ${entry.backgroundColor}); the product requires ${ROUTE_BADGE_MIN_CONTRAST}:1`,
          );
        }
      }
      backgrounds.set(state, entry.backgroundColor);
    }
    if (
      Number(entry.scrollWidth) > Number(entry.clientWidth) + tolerance
      || Number(entry.scrollHeight) > Number(entry.clientHeight) + tolerance
    ) {
      failures.push(
        `the ${state} pill's label overflows its box (${entry.scrollWidth}x${entry.scrollHeight}`
        + ` against ${entry.clientWidth}x${entry.clientHeight})`,
      );
    }
  }
  if (backgrounds.size === ROUTE_BADGE_STATES.length) {
    const distinct = new Set(backgrounds.values());
    if (distinct.size !== backgrounds.size) {
      failures.push(
        "the route-state pills share a background colour, so the states are not distinguishable:"
        + ` ${[...backgrounds.entries()].map(([state, color]) => `${state}=${color}`).join(", ")}`,
      );
    }
  }
  const measured = ROUTE_BADGE_STATES
    .map((state) => byState.get(state))
    .filter(Boolean);
  for (let first = 0; first < measured.length; first += 1) {
    for (let second = first + 1; second < measured.length; second += 1) {
      const a = measured[first].box || { x: 0, y: 0, width: 0, height: 0 };
      const b = measured[second].box || { x: 0, y: 0, width: 0, height: 0 };
      const overlapX = Math.min(a.x + a.width, b.x + b.width) - Math.max(a.x, b.x);
      const overlapY = Math.min(a.y + a.height, b.y + b.height) - Math.max(a.y, b.y);
      if (overlapX > 0.5 && overlapY > 0.5) {
        failures.push(
          `the ${measured[first].state} and ${measured[second].state} pills overlap by`
          + ` ${overlapX.toFixed(1)}x${overlapY.toFixed(1)}px`,
        );
      }
    }
  }
  const containerBox = fixture.container?.box;
  if (
    containerBox
    && (
      containerBox.x < -1
      || containerBox.y < -1
      || containerBox.x + containerBox.width > viewport.width + 1
      || containerBox.y + containerBox.height > viewport.height + 1
    )
  ) {
    failures.push(
      "the route-state badge fixture is not fully inside the viewport, so its screenshot is not"
      + " evidence of an on-screen render",
    );
  }
  return { failures, observations };
}

/**
 * Collect each read group's own visible row evidence from the displayed page.
 *
 * Self-contained on purpose: the sweep serialises this function into the page
 * (`page.evaluate`), and the negative tests call it against a stub document, so it may not
 * reference anything outside its own body - the attribute name included. Every element is
 * collected once even when two of a group's selectors both match it, one element is one row, and
 * only elements matching the group's own selectors are its evidence: a panel rendering some
 * other read's rows is not evidence for this one. Hidden evidence is not evidence - `display:
 * none`, `visibility: hidden` and zero-size elements are dropped (a `display: none` subtree
 * reports a zero rect), the same rule the sweep uses to decide a page is displayed.
 */
export function collectVisibleElements(spec) {
  const isVisible = (element) => {
    if (!element || typeof element.getBoundingClientRect !== "function") return false;
    const view = element.ownerDocument && element.ownerDocument.defaultView;
    const style = view && view.getComputedStyle ? view.getComputedStyle(element) : null;
    if (style && (style.display === "none" || style.visibility === "hidden")) return false;
    const rect = element.getBoundingClientRect();
    return rect.width > 0 && rect.height > 0;
  };
  const pages = [...document.querySelectorAll(".workspace-page")];
  const displayed = pages.find(isVisible);
  if (!displayed) return [];

  const evidence = [];
  for (const group of spec.groups) {
    const seen = new Set();
    const recordIds = [];
    let missingRecordIds = 0;
    for (const selector of group.rowSelectors ?? []) {
      for (const element of displayed.querySelectorAll(selector)) {
        if (seen.has(element)) continue;
        seen.add(element);
        if (!isVisible(element)) continue;
        const value = element.getAttribute("data-record-id");
        const recordId = value === null || value === undefined ? "" : String(value).trim();
        if (recordId === "") missingRecordIds += 1;
        else recordIds.push(recordId);
      }
    }
    const emptyState = group.emptySelector
      ? [...displayed.querySelectorAll(group.emptySelector)].some(isVisible)
      : false;
    evidence.push({
      rowSelectors: group.rowSelectors ?? [],
      recordIds,
      missingRecordIds,
      emptyState,
    });
  }
  return evidence;
}

/**
 * What the Source Center's surface reports about a registry read the harness itself refused.
 *
 * `GET /api/sources` failing used to leave the surface rendering `Total sources 0` beside `No
 * active warnings` - the copy of a measured zero, produced by a read that never answered
 * (`docs/release/FUNCTIONAL_ACCEPTANCE_REPORT.md`, 2026-09-25 limits). The rule this holds the
 * surface to is one-directional on purpose: while the read is refused, nothing that reads as a
 * measurement may be presented, so a KPI strip, a source row or the declared measured-empty marker
 * is a failure even when the value would look plausible. The failure must be stated in the surface
 * itself, with a retry that is offered and enabled while no attempt is in flight (the store owns
 * the one-attempt-at-a-time rule).
 *
 * Pure, so the negative cases run without a browser (`clients/web/tests/readToRender.test.ts`).
 */
export function evaluateRefusedRegistry(surface) {
  const failures = [];
  const state = surface?.state ?? "";
  if (state !== "failed") {
    failures.push(
      `the registry read was refused and the surface reports '${state || "(no state)"}'`,
    );
  }
  if (!surface?.failedNotice) {
    failures.push("the surface renders no failure notice for the refused registry read");
  }
  if (surface?.rows > 0) {
    failures.push(
      `the surface still renders ${surface.rows} source row(s) for a read that did not answer`,
    );
  }
  if (surface?.measuredEmpty > 0) {
    failures.push(
      "the surface still presents its measured-empty marker for a read that did not answer",
    );
  }
  if (surface?.kpiStrips > 0) {
    failures.push(
      `the surface still renders ${surface.kpiStrips} KPI strip(s) for a read that did not answer`,
    );
  }
  if (surface?.retryControls === 0) {
    failures.push("the surface offers no retry for the refused registry read");
  } else if (surface?.retryDisabled === true) {
    failures.push("the retry control is disabled while no retry is in flight");
  }
  return failures;
}

/**
 * The recovery half: once the refusal is removed, the surface's own retry must leave it rendering
 * exactly the registry its read serves - by each source's own id, in both directions - with the
 * failure notice gone. A surface that keeps the notice, drops a returned source or renders one the
 * read did not return is named by id rather than passed.
 *
 * Pure, so the negative cases run without a browser (`clients/web/tests/readToRender.test.ts`).
 */
export function evaluateRegistryRecovery(surface, wanted) {
  const failures = [];
  if (surface?.failedNotice) {
    failures.push("the failed-registry notice survives the retry that recovered the read");
  }
  const remaining = [...(wanted ?? [])];
  const foreign = [];
  for (const id of surface?.recordIds ?? []) {
    const at = remaining.indexOf(id);
    if (at === -1) foreign.push(id);
    else remaining.splice(at, 1);
  }
  if (remaining.length > 0) {
    failures.push(
      `the recovered catalog does not render ${remaining.length} source(s) its own read returned:`
      + ` ${remaining.slice(0, 4).join(" | ")}`,
    );
  }
  if (foreign.length > 0) {
    failures.push(
      `the recovered catalog renders ${foreign.length} source(s) its read did not return:`
      + ` ${foreign.slice(0, 4).join(" | ")}`,
    );
  }
  return failures;
}

/**
 * What the capacity operating board reports about a read the harness itself refused.
 *
 * The board's rows are a join of two reads (`flows` and `capacity`), so its refusal is not the
 * registry's case: when the other read answered with rows the board may keep them as an
 * explicitly incomplete reading (`partial`), and when it holds none the board is `failed`.
 * Neither state may present a measurement - no KPI strip, no measured-empty marker, no filter
 * result - and both must state that a required read did not answer and offer the store's own
 * bounded retry, enabled while no attempt is in flight. Rows are permitted only in the `partial`
 * state, where they are the reading that did answer.
 *
 * Pure, so the negative cases run without a browser (`clients/web/tests/readToRender.test.ts`).
 */
export function evaluateRefusedCapacityBoard(surface) {
  const failures = [];
  const state = surface?.state ?? "";
  if (state !== "failed" && state !== "partial") {
    failures.push(
      `the capacity read was refused and the operating board reports`
      + ` '${state || "(no state)"}'`,
    );
  }
  if (surface?.noticeState !== state || surface?.noticePresent !== true) {
    failures.push(
      `the board reports '${state || "(no state)"}' and its own notice declares`
      + ` '${surface?.noticeState || "(none)"}'`,
    );
  }
  if (!String(surface?.noticeText ?? "").trim()) {
    failures.push("the board renders no failure notice for the refused capacity read");
  }
  if (!String(surface?.vocabulary ?? "").trim()) {
    failures.push(
      "the board's failure notice names no endpoint for the read that did not answer",
    );
  }
  if (surface?.rows > 0 && state === "failed") {
    failures.push(
      `the board still renders ${surface.rows} operating row(s) for a read that did not answer`,
    );
  }
  if (surface?.measuredEmpty > 0) {
    failures.push(
      "the board still presents its measured-empty marker for a read that did not answer",
    );
  }
  if (surface?.filterNoMatch > 0) {
    failures.push(
      "the board still presents a filter result for a read that did not answer",
    );
  }
  if (surface?.kpiStrips > 0) {
    failures.push(
      `the board still renders ${surface.kpiStrips} KPI strip(s) for a read that did not answer`,
    );
  }
  if (surface?.retryControls === 0) {
    failures.push("the board offers no retry for the refused capacity read");
  } else if (surface?.retryDisabled === true) {
    failures.push("the retry control is disabled while no retry is in flight");
  }
  return failures;
}

/**
 * The recovery half: once the refusal is removed, the board's own retry must leave it state the
 * reading its two reads now support - `ready` when either read served a row, the measured `empty`
 * when both answered with none - with the failure notice and its retry gone.
 *
 * `served` names the rows the platform's two reads answer with after the refusal is removed
 * (`capacityRows`, `flowsRows`), read in the same session by the caller; when either could not be
 * read the comparison is a failure rather than a pass. The joined rows themselves are **not**
 * compared here - that is the scoped joined-row acceptance, a later milestone - so this rule makes
 * no claim about which rows the board rendered.
 *
 * Pure, so the negative cases run without a browser (`clients/web/tests/readToRender.test.ts`).
 */
export function evaluateCapacityBoardRecovery(surface, served) {
  const failures = [];
  const capacityRows = served?.capacityRows;
  const flowsRows = served?.flowsRows;
  if (!Number.isFinite(capacityRows) || !Number.isFinite(flowsRows)) {
    failures.push(
      "the platform's two reads could not be read once the refusal was removed, so the board's"
      + " recovery could not be measured",
    );
    return failures;
  }
  const state = surface?.state ?? "";
  const wanted = capacityRows + flowsRows > 0 ? "ready" : "empty";
  if (state !== wanted) {
    failures.push(
      `the board's reads answered ${capacityRows} capacity and ${flowsRows} flow row(s) and the`
      + ` board reports '${state || "(no state)"}' instead of '${wanted}'`,
    );
  }
  if (surface?.noticePresent === true) {
    failures.push("the failed-board notice survives the retry that recovered the reads");
  }
  if (surface?.retryControls > 0) {
    failures.push("the retry control survives the retry that recovered the reads");
  }
  if (surface?.measuredEmpty > 0 && wanted === "ready") {
    failures.push(
      "the board presents its measured-empty marker while its reads served rows",
    );
  }
  if (surface?.measuredEmpty === 0 && wanted === "empty") {
    failures.push(
      "both reads answered with no row and the board does not declare its measured empty state",
    );
  }
  if (surface?.filterNoMatch > 0) {
    failures.push(
      "the board presents a filter result for reads that answered with no row at all",
    );
  }
  if (surface?.kpiStrips === 0) {
    failures.push("the board states no measurement after its reads recovered");
  }
  if (wanted === "ready" && surface?.rows === 0) {
    failures.push(
      "the reads served rows and the operating board renders none of them",
    );
  }
  return failures;
}

/** The source a read served by the runtime database names in its envelope. */
const RUNTIME_DATABASE_SOURCE = "runtime-postgresql";

/**
 * The joined keys the operating board's two reads support, and every reason they cannot be joined.
 *
 * The board is not a list of capacity observations: its rows are a union of `flows` and `capacity`
 * keyed `point_id:direction` (`CapacityWorkspace.buildOperatingRows`), so comparing it with either
 * read alone would judge a correctly rendered board by the wrong row list - which is why its
 * whole-page exemption outlived the row-comparison milestones. Each read must be the runtime
 * database's own answer: the fallback envelope answers 200 with an empty row set and names another
 * source, and "the runtime served no operating point" is not the same statement as "no runtime
 * read happened". A row carrying no `point_id`/`direction` proves nothing, so it is a problem
 * rather than a key skipped quietly.
 */
export function capacityBoardJoinedKeys(reads) {
  const problems = [];
  if (!Array.isArray(reads) || reads.length !== 2
      || reads.filter((read) => read?.lane === "flows").length !== 1
      || reads.filter((read) => read?.lane === "capacity").length !== 1) {
    problems.push("the join requires exactly one flows and one capacity read");
  }
  const keys = [];
  const seen = new Set();
  const served = [];
  for (const read of Array.isArray(reads) ? reads : []) {
    const label = read?.label ?? read?.lane ?? "read";
    const status = read?.status ?? null;
    if (status !== 200) {
      problems.push(
        `${label}: the read answered ${status === null || status === 0 ? "nothing" : status}, so`
        + " the board's join could not be measured",
      );
      continue;
    }
    const rows = read?.body?.data;
    const references = read?.body?.meta?.source_references;
    const source =
      Array.isArray(references) && typeof references[0] === "string" ? references[0].trim() : "";
    if (!Array.isArray(rows)) {
      problems.push(`${label}: the read's payload carries no row set 'data'`);
      continue;
    }
    if (source !== RUNTIME_DATABASE_SOURCE) {
      problems.push(
        `${label}: the read was answered by '${source || "(no source)"}' rather than the runtime`
        + " database, so it is not a measurement",
      );
      continue;
    }
    served.push(`${label} ${rows.length}`);
    for (const row of rows) {
      const pointId = rowRecordId(row, "point_id");
      const direction = rowRecordId(row, "direction");
      if (pointId === null || direction === null) {
        problems.push(
          `${label}: a returned row carries no point_id/direction, so no joined key could be`
          + " compared with it",
        );
        continue;
      }
      const key = `${pointId}:${direction}`;
      if (!seen.has(key)) {
        seen.add(key);
        keys.push(key);
      }
    }
  }
  return { keys, problems, served };
}

/** The board's own declared joined count (`data-capacity-board-count`, ``<filtered>/<total>``). */
function boardDeclaredCount(raw) {
  const match = /^(\d+)\/(\d+)$/.exec(String(raw ?? "").trim());
  if (!match) return null;
  return { filtered: Number(match[1]), total: Number(match[2]) };
}

/**
 * Compare the operating board with the union of its two reads.
 *
 * `reads` are the harness's declared reads, each with its own `status` and `body`; `board` is
 * `collectCapacityOperatingBoard`'s output; `pageSize` is the surface's own declared page bound
 * (`CapacityWorkspace.PAGE_SIZE`), held to it by the contract tests rather than guessed here.
 *
 * The rules, one direction at a time:
 *
 * - the board's expected identities are the union's keys, deduplicated the way the board's own
 *   `Set` joins them; no utilization, posture or sort value is recomputed here;
 * - both reads must be the runtime database's answers, so an unavailable read can never pass as
 *   the board's measured empty state;
 * - the board must report the state its reads support (`ready`/`empty`), state its count, and
 *   present no failure notice, retry or filter result;
 * - its stated total is held to the joined key count, and a total it claims without the reads'
 *   rows is named;
 * - its visible keys are held to the bounded page the surface renders: a missing, foreign,
 *   hidden, duplicated or unidentifiable row fails by name, and a union larger than the declared
 *   page is reported as the bounded slice it is rather than claimed as fully compared.
 *
 * Pure, so the negative cases run without a browser (`clients/web/tests/readToRender.test.ts`).
 */
export function evaluateCapacityBoardJoin({ reads = [], pageSize = 0, board = null }) {
  const failures = [];
  const observations = [];
  const declaredPage = Number(pageSize) > 0 ? Math.floor(Number(pageSize)) : 0;
  if (declaredPage === 0) {
    failures.push(
      "the joined comparison declares no page size, so no bounded slice could be verified",
    );
    return { failures, observations };
  }
  const joined = capacityBoardJoinedKeys(reads);
  for (const problem of joined.problems) failures.push(problem);
  if (joined.problems.length > 0) return { failures, observations };
  if (!board) {
    failures.push(
      "no displayed workspace page carried the operating board, so its joined rows could not be"
      + " compared",
    );
    return { failures, observations };
  }

  const total = joined.keys.length;
  const served = joined.served.join(", ");
  const expectedState = total > 0 ? "ready" : "empty";
  if (board.state !== expectedState) {
    failures.push(
      `the board's two reads joined ${total} key(s) and the board reports`
      + ` '${board.state || "(no state)"}' instead of '${expectedState}'`,
    );
  }
  if (board.noticePresent === true) {
    failures.push("the board states a read failure while both of its reads answered");
  }
  if (board.retryControls > 0) {
    failures.push("the board offers its retry control while both of its reads answered");
  }
  if (board.kpiStrips === 0) {
    failures.push("the board states no measurement after both of its reads answered");
  }
  if (board.filterNoMatch > 0) {
    failures.push("the board presents a filter result while it declares no filter applied");
  }

  const filters = String(board.filters ?? "");
  if (filters !== "none" && filters !== "applied") {
    failures.push(
      "the board does not declare its filter context, so the comparison's filters are unknown",
    );
  } else if (filters === "applied") {
    failures.push(
      "the board's filters were applied, so the unfiltered joined comparison could not be"
      + " measured",
    );
    return { failures, observations };
  }
  const sort = String(board.sort ?? "").trim();
  if (sort === "") {
    failures.push("the board does not declare the sort its first page was drawn with");
  }

  const count = boardDeclaredCount(board.count);
  if (count === null) {
    failures.push(
      `the board states no joined count, so its total could not be compared with the ${total}`
      + " key(s) the two reads joined",
    );
  } else {
    if (count.total !== total) {
      failures.push(
        `the board's two reads joined ${total} key(s) and the board states ${count.total}`
        + " operating point(s)",
      );
    }
    if (count.filtered !== count.total) {
      failures.push(
        `the board states ${count.filtered} of ${count.total} operating point(s) while it declares`
        + " no filter applied",
      );
    }
  }
  // The compared slice is declared rather than assumed: the board states the first row of the page
  // it is rendering, so the sweep verifies the first declared page and never a later one by
  // accident. A missing declaration is a failure, not "page zero by default".
  const pageStartRaw = String(board.pageStart ?? "").trim();
  const pageStart = /^\d+$/.test(pageStartRaw) ? Number(pageStartRaw) : null;
  if (total > 0 && pageStart === null) {
    failures.push(
      "the board does not declare the page of joined keys it rendered, so no bounded slice could"
      + " be verified",
    );
  } else if (total > 0 && pageStart !== 0) {
    failures.push(
      `the board's first page is the compared slice and the board renders the page starting at`
      + ` row ${pageStart}`,
    );
  }

  const recordIds = Array.isArray(board.recordIds) ? board.recordIds.map(String) : [];
  const missingRecordIds = Number(board.missingRecordIds) > 0 ? Number(board.missingRecordIds) : 0;
  if (missingRecordIds > 0) {
    failures.push(
      `${missingRecordIds} visible row(s) under '[data-record="capacity-point"]' carry no`
      + " data-record-id, so no joined key could be compared with them",
    );
  }
  const duplicates = recordIds.length - new Set(recordIds).size;
  if (duplicates > 0) {
    failures.push(`the board renders ${duplicates} duplicate operating row identity(ies)`);
  }
  const expectedVisible = Math.min(total, declaredPage);
  if (recordIds.length !== expectedVisible) {
    failures.push(
      `the board's own page holds ${expectedVisible} of ${total} joined key(s) and it renders`
      + ` ${recordIds.length} visible row(s)`,
    );
  }
  const foreign = recordIds.filter((id) => !joined.keys.includes(id));
  if (foreign.length > 0) {
    failures.push(
      `the board renders ${foreign.length} row(s) neither read joined:`
      + ` ${foreign.slice(0, 4).join(" | ")}`,
    );
  }

  if (total === 0) {
    if (!(board.measuredEmpty > 0)) {
      failures.push(
        "both reads answered with an empty row set and the board does not declare its measured"
        + " empty state",
      );
    }
    observations.push(
      "both reads answered 0 row(s) from the runtime database: the board states the measured"
      + " empty reading (an empty fixture is not populated acceptance)",
    );
  } else {
    if (board.measuredEmpty > 0) {
      failures.push("the board presents its measured-empty marker while its reads joined rows");
    }
    if (total <= declaredPage) {
      const remaining = [...joined.keys];
      for (const id of recordIds) {
        const at = remaining.indexOf(id);
        if (at !== -1) remaining.splice(at, 1);
      }
      if (remaining.length > 0) {
        failures.push(
          `the board does not render ${remaining.length} joined key(s) its two reads served:`
          + ` ${remaining.slice(0, 4).join(" | ")}`,
        );
      }
      observations.push(
        `the two reads joined ${total} key(s) (${served}) - a populated union - and the board`
        + ` rendered every one of them under its own '${sort}' sort`,
      );
    } else {
      observations.push(
        `the two reads joined ${total} key(s) (${served}) - a populated union; the board's first`
        + ` declared page of ${declaredPage} was compared by identity and keys beyond that page`
        + " are not claimed",
      );
    }
  }
  return { failures, observations };
}

/**
 * Collect the operating board's own read state and its claims from the displayed page.
 *
 * Self-contained like the other collectors (the sweep serialises this function into the page),
 * so every selector and attribute name is a literal here. Only the displayed `.workspace-page` is
 * evidence; the notice's text is read from the element the operator sees, the row count only from
 * the board's own row marker, and the measured-empty and filter markers are the surface's
 * declared ones - never the page's copy and never another panel's rows.
 *
 * The joined comparison's own evidence is collected here too: the visible row identities the
 * board renders (`recordIds`), the count it states (`count`, the numbers it prints as `N / M`),
 * the page its rows begin at (`pageStart`), and the filter and sort context it was drawn under
 * (`filters`, `sort`). `rows` remains the row-element count the refusal rules use; `recordIds` is
 * the visibility-filtered evidence - a hidden row, or a row carrying no id, is not a joined key.
 */
export function collectCapacityOperatingBoard() {
  const isVisible = (element) => {
    if (!element || typeof element.getBoundingClientRect !== "function") return false;
    const view = element.ownerDocument && element.ownerDocument.defaultView;
    const style = view && view.getComputedStyle ? view.getComputedStyle(element) : null;
    if (style && (style.display === "none" || style.visibility === "hidden")) return false;
    const rect = element.getBoundingClientRect();
    return rect.width > 0 && rect.height > 0;
  };
  const attribute = (element, name) => {
    if (!element) return "";
    const value = element.getAttribute(name);
    return value === null || value === undefined ? "" : String(value).trim();
  };
  const text = (element) =>
    (element ? String(element.textContent || "") : "").trim().replace(/\s+/g, " ");
  const displayed = [...document.querySelectorAll(".workspace-page")].find(isVisible);
  if (!displayed) return null;

  const notice = displayed.querySelector("[data-capacity-notice]");
  const rowElements = [...displayed.querySelectorAll('[data-record="capacity-point"]')];
  const recordIds = [];
  let missingRecordIds = 0;
  for (const row of rowElements) {
    if (!isVisible(row)) continue;
    const value = attribute(row, "data-record-id");
    if (value === "") missingRecordIds += 1;
    else recordIds.push(value);
  }
  const countElement = displayed.querySelector("[data-capacity-board-count]");
  return {
    state: attribute(
      displayed.querySelector("[data-capacity-read-state]"),
      "data-capacity-read-state",
    ),
    noticePresent: notice !== null,
    noticeState: attribute(notice, "data-capacity-notice"),
    noticeText: text(notice),
    vocabulary: text(displayed.querySelector(".capacity-board-vocabulary")),
    rows: rowElements.length,
    recordIds,
    missingRecordIds,
    count: isVisible(countElement) ? text(countElement).replace(/\s+/g, "") : "",
    pageStart: attribute(
      displayed.querySelector("[data-capacity-page-start]"),
      "data-capacity-page-start",
    ),
    filters: attribute(
      displayed.querySelector("[data-capacity-board-filters]"),
      "data-capacity-board-filters",
    ),
    sort: attribute(
      displayed.querySelector("[data-capacity-board-sort]"),
      "data-capacity-board-sort",
    ),
    measuredEmpty: displayed.querySelectorAll(
      '[data-empty-state="capacity-operating-points"]',
    ).length,
    filterNoMatch: displayed.querySelectorAll(
      '[data-empty-state="capacity-filter-no-match"]',
    ).length,
    kpiStrips: displayed.querySelectorAll(".capacity-kpi-strip").length,
    retryControls: displayed.querySelectorAll("[data-capacity-board-retry]").length,
    retryDisabled: displayed.querySelector("[data-capacity-board-retry]")?.disabled ?? null,
  };
}

/**
 * Quoted-value evidence for the market hub board.
 *
 * The market workspace's numeric task (`curves`) prices one hub board from the authenticated
 * `GET /api/projections/market-context` read the market lane already performs: one card per major
 * hub, for the tenor the board is displaying, fed by the projection's `quotes` slice (L1 bid/ask)
 * or - when no quote is served for that hub - its `normalized_quotes` slice. The sweep used to
 * probe `/api/market/observations`, an endpoint this lane does not read, and judge the surface by
 * the page's copy - so the declared gap ("market observations return rows while every hub card
 * renders n/a", recorded by a visual review) could neither be confirmed nor retired by a row.
 *
 * What replaces it is scoped at both ends, because every market row set is filtered on purpose:
 *
 * - the probe reads the projection *for the displayed Active Context* (gas day, product, hub as the
 *   shell shows them), so a focused board is never compared with another context's payload;
 * - a card declares the tenor it prices (`data-price-tenor`) and the row it priced (its own id plus
 *   the slice that id belongs to) - never a rendered label, and never a value read back out of the
 *   payload it is supposed to prove;
 * - the comparison is held to the board's declared hub scope (`hubScope`, the model's
 *   `MAJOR_MARKET_HUBS`) and to the *displayed* tenor, which the board and its own active tenor tab
 *   must agree on; rows of other hubs or other tenors are reported as observations instead of
 *   failing a board that legitimately prices one tenor at a time;
 * - a hub whose pair the read served must be priced by a visible card: a card that shows no price
 *   for a served pair is the "missing rows" case, and a card whose own element is hidden is not
 *   evidence at all;
 * - a card that shows no row is only honest when the read served that pair no row: "not served" is
 *   not a measured zero, and `status`, slice availability and per-slice problems are all reported
 *   rather than collapsed into "no prices";
 * - the board is held only to rows its own price rule admits: the terminal prices gas prices
 *   (`is_gas_price`, the backend's own flag - a quotes row carries none and is admitted), so a
 *   non-gas row on a declared hub is an observation rather than a card the board owes;
 * - the visible price is compared with the row's own numbers (bid/ask, or the normalized price),
 *   the visible source with the row's source system, the visible unit with the row's currency and
 *   unit, and the surface's declared as-of with the instant it displays.
 *
 * Pure except for `collectQuotedBoard`, which the sweep serialises into the page.
 */

/**
 * The price slices of the market-context projection, and the fields that make a row comparable.
 *
 * `valueFields` is exactly what the board prints for that slice: a quote card shows the row's
 * bid/ask (with `n/a` for a side the payload does not carry), and a normalized card shows the row's
 * price. The unit is composed by the one rule the surface prints it with (`displayPriceUnit`).
 */
const MARKET_PRICE_SLICE_SPECS = [
  {
    key: "quotes",
    label: "quotes",
    rowsPath: "data.slices.quotes",
    recordIdField: "quote_id",
    hubField: "hub",
    tenorField: "product",
    valueFields: ["bid_price", "ask_price"],
    sourceField: "source_system",
    fallbackSourceField: "venue",
  },
  {
    key: "normalized_quotes",
    label: "normalized quotes",
    rowsPath: "data.slices.normalized_quotes",
    recordIdField: "observation_id",
    hubField: "hub",
    tenorField: "tenor",
    valueFields: ["price"],
    sourceField: "source_system",
    fallbackSourceField: "market_venue",
  },
];

/** The tolerance a displayed number may sit from the payload's, mirroring the board's own digits. */
export const QUOTED_PRICE_TOLERANCE = 0.005;

function textOf(value) {
  return typeof value === "string" ? value.trim() : "";
}

function finiteOrNull(value) {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

/**
 * The unit string the market surface prints a price with, for one payload row.
 *
 * The payload owns the currency and the unit; this mirror of the component's own rule (`a unit that
 * already names its currency is printed as it is, a bare quantity is qualified with the currency`)
 * exists so the sweep can require the *visible* text to carry the unit of the row the card priced.
 * A row whose currency and unit are both blank has no displayable unit and answers `null`.
 */
export function displayPriceUnit(currency, unit) {
  const currencyCode = typeof currency === "string" ? currency : "";
  const unitName = typeof unit === "string" ? unit : "";
  const composed = unitName.toUpperCase().includes(currencyCode.toUpperCase())
    ? unitName
    : `${currencyCode}/${unitName}`;
  return composed.trim() === "" || composed === "/" ? null : composed;
}

/**
 * The label the client's `formatUtcTimestamp` prints for an instant (`YYYY-MM-DD HH:MM:SS UTC`).
 *
 * The sweep needs the *displayed* as-of to be held to the read's own instant, and the only way to
 * do that without parsing localized copy is to mirror the one formatter the client renders it with.
 * `tests/contract/test_browser_probe_paths.py` holds the mirror to that formatter.
 */
export function utcInstantLabel(value) {
  const parsed = new Date(String(value));
  if (!Number.isFinite(parsed.getTime())) return null;
  return `${parsed.toISOString().slice(0, 19).replace("T", " ")} UTC`;
}

/**
 * The comparable price rows the market projection served, one entry per slice.
 *
 * A slice the backend did not serve is reported as unmeasured (`available: false`) rather than as
 * an empty row set; a slice that carries rows without declaring availability, or a payload that is
 * not this projection at all, is a `problem` the caller records as a failure. Rows that carry no
 * id, no hub or no tenor stay in the returned list marked `comparable: false`, so the verdict can
 * say how many served rows it could not place instead of dropping them silently.
 */
export function marketBoardRows(body, spec = {}) {
  const rowSelectors = spec.rowSelectors ?? ['[data-record="market-hub-price"]'];
  const slices = [];
  const rows = [];
  const problems = [];
  for (const sliceSpec of MARKET_PRICE_SLICE_SPECS) {
    const group = readGroupRows(body, {
      label: sliceSpec.label,
      rowsPath: sliceSpec.rowsPath,
      recordIdField: sliceSpec.recordIdField,
      rowSelectors,
    });
    slices.push({
      key: sliceSpec.key,
      label: sliceSpec.label,
      readable: group.readable,
      available: group.available,
      rowCount: group.rows.length,
      problems: group.problems,
    });
    for (const problem of group.problems) problems.push(`${sliceSpec.label}: ${problem}`);
    if (!group.available) continue;
    for (const row of group.rows) {
      const id = rowRecordId(row, sliceSpec.recordIdField);
      const hub = textOf(row?.[sliceSpec.hubField]).toUpperCase();
      const tenor = textOf(row?.[sliceSpec.tenorField]).toLowerCase();
      const source = textOf(row?.[sliceSpec.sourceField])
        || textOf(row?.[sliceSpec.fallbackSourceField]);
      rows.push({
        slice: sliceSpec.key,
        id,
        hub,
        tenor,
        values: sliceSpec.valueFields.map((field) => finiteOrNull(row?.[field])),
        currency: textOf(row?.currency),
        unit: textOf(row?.unit),
        source: source === "" ? null : source,
        // The board's own price rule: the terminal prices gas-price rows only (the backend's
        // `is_gas_price`); a quotes row carries no such field and is admitted.
        boardEligible: row?.is_gas_price !== false,
        comparable: Boolean(id) && hub !== "" && tenor !== "",
      });
    }
  }
  return { slices, rows, problems };
}

/**
 * Collect the hub board's own visible evidence from the displayed page.
 *
 * Self-contained like `collectVisibleElements` (the sweep serialises this function into the page),
 * so every selector and attribute name is a literal here. Only the displayed `.workspace-page` is
 * evidence; a card that is hidden (`display: none`, `visibility: hidden`, zero size) is dropped,
 * and each card's text is read from the elements the operator sees - the hub label, the price line,
 * the meta line and the source pill - never from an attribute the surface could set without
 * printing it. The declarations (`data-record-id`, `data-record-slice`, `data-price-tenor`) and the
 * board's own displayed tenor come back beside the page's copy so the pure verdict can hold the two
 * to each other.
 */
export function collectQuotedBoard() {
  const isVisible = (element) => {
    if (!element || typeof element.getBoundingClientRect !== "function") return false;
    const view = element.ownerDocument && element.ownerDocument.defaultView;
    const style = view && view.getComputedStyle ? view.getComputedStyle(element) : null;
    if (style && (style.display === "none" || style.visibility === "hidden")) return false;
    const rect = element.getBoundingClientRect();
    return rect.width > 0 && rect.height > 0;
  };
  const text = (element) =>
    (element ? String(element.textContent || "") : "").trim().replace(/\s+/g, " ");
  const attribute = (element, name) => {
    if (!element) return "";
    const value = element.getAttribute(name);
    return value === null || value === undefined ? "" : String(value).trim();
  };
  const pages = [...document.querySelectorAll(".workspace-page")];
  const displayed = pages.find(isVisible);
  if (!displayed) return null;

  const cells = [];
  for (const element of displayed.querySelectorAll('[data-record="market-hub-price"]')) {
    if (!isVisible(element)) continue;
    cells.push({
      recordId: attribute(element, "data-record-id"),
      slice: attribute(element, "data-record-slice"),
      tenor: attribute(element, "data-price-tenor").toLowerCase(),
      hub: text(element.querySelector("[data-price-hub-label]")).toUpperCase(),
      priceText: text(element.querySelector("[data-price-value]")),
      metaText: text(element.querySelector("[data-price-meta]")),
      sourceText: text(element.querySelector("[data-price-source]")),
    });
  }
  const asOfElement = displayed.querySelector("[data-projection-as-of]");
  return {
    boardTenor: attribute(
      displayed.querySelector('[data-market-board="hub-prices"]'),
      "data-board-tenor",
    ).toLowerCase(),
    activeTenorTab: attribute(
      displayed.querySelector('.market-tenor-tab[aria-pressed="true"]'),
      "data-tenor",
    ).toLowerCase(),
    asOf: attribute(asOfElement, "data-projection-as-of"),
    asOfText: text(asOfElement),
    cells,
  };
}

/** The numbers a price line prints, in order; a unit such as `EUR/MWh` carries none. */
function priceNumbers(text) {
  return (String(text ?? "").match(/-?\d+(?:\.\d+)?/g) ?? []).map(Number);
}

/**
 * The verdict for the hub board: does it price the payload's rows for the scope it displays?
 *
 * `board` is `collectQuotedBoard`'s evidence, `rows`/`slices`/`problems` are `marketBoardRows`'s,
 * `asOf` is the projection payload's own `data.as_of_utc`, and `hubScope` is the board's declared
 * hub set. Every failure names the hub, the row or the value it is about; anything the comparison
 * could not measure (a slice the backend did not serve, rows outside the displayed scope, the
 * distance between the surface's as-of and this read's) is an observation, never a pass.
 */
export function evaluateQuotedBoard({
  status,
  hubScope = [],
  board = null,
  slices = [],
  rows = [],
  problems = [],
  asOf = null,
  source = null,
}) {
  const failures = [];
  const observations = [];
  if (status !== 200) {
    failures.push(
      `the market projection answered ${status === null || status === undefined ? "nothing" : status}`
      + "; the quoted-value comparison could not be measured",
    );
    return { failures, observations };
  }
  for (const problem of problems) failures.push(`market projection: ${problem}`);
  if (!board) {
    failures.push("the hub board's rendered evidence was not collected: the comparison measured nothing");
    return { failures, observations };
  }
  const available = slices.filter((slice) => slice.available);
  if (available.length === 0) {
    observations.push(
      "the backend served neither the quote nor the normalized price slice, so no quoted value"
      + " could be compared (an unserved slice is not a measured zero)",
    );
    return { failures, observations };
  }

  const scope = hubScope.map((hub) => String(hub).trim().toUpperCase()).filter(Boolean);
  const boardTenor = String(board.boardTenor ?? "").trim().toLowerCase();
  const tabTenor = String(board.activeTenorTab ?? "").trim().toLowerCase();
  if (boardTenor === "") {
    failures.push(
      "the price board does not declare the tenor it prices (data-board-tenor), so a filtered board"
      + " could not be compared with the payload it was read from",
    );
  } else if (tabTenor !== boardTenor) {
    failures.push(
      `the price board prices '${boardTenor}' while its own active tenor tab declares`
      + ` '${tabTenor || "(none)"}'`,
    );
  }

  const comparable = rows.filter((row) => row.comparable);
  const unplaceable = rows.length - comparable.length;
  if (unplaceable > 0) {
    observations.push(
      `${unplaceable} served row(s) carry no record id, hub or tenor and could not be placed on the`
      + " board",
    );
  }
  const foreignHub = comparable.filter((row) => !scope.includes(row.hub));
  if (foreignHub.length > 0) {
    observations.push(
      `${foreignHub.length} served row(s) name a hub the board does not declare`
      + ` (${scope.join(", ")}) and were not compared`,
    );
  }
  const otherTenor = comparable.filter(
    (row) => scope.includes(row.hub) && row.tenor !== boardTenor,
  );
  if (otherTenor.length > 0) {
    observations.push(
      `${otherTenor.length} served row(s) for the declared hubs are another tenor than the`
      + ` displayed '${boardTenor}' and were not compared`,
    );
  }
  const inScope = comparable.filter(
    (row) => scope.includes(row.hub) && row.tenor === boardTenor,
  );
  const excluded = inScope.filter((row) => row.boardEligible === false);
  if (excluded.length > 0) {
    observations.push(
      `${excluded.length} served row(s) for the displayed pair(s) are excluded by the board's own`
      + " price rule (is_gas_price) and were not demanded of it",
    );
  }

  const rowsById = new Map();
  const rowsByPair = new Map();
  for (const row of inScope) {
    rowsById.set(`${row.slice}|${row.id}`, row);
    if (row.boardEligible === false) continue;
    const pair = `${row.hub}|${row.tenor}`;
    rowsByPair.set(pair, [...(rowsByPair.get(pair) ?? []), row]);
  }

  const cardsByHub = new Map();
  for (const [index, cell] of (board.cells ?? []).entries()) {
    const hub = String(cell.hub ?? "").trim().toUpperCase();
    const where = `hub card ${hub || `#${index + 1}`}`;
    const tenor = String(cell.tenor ?? "").trim().toLowerCase();
    if (!scope.includes(hub)) {
      failures.push(
        `${where} prices a hub the board does not declare (${scope.join(", ") || "none"})`,
      );
      continue;
    }
    if (tenor !== boardTenor) {
      failures.push(
        `${where} declares the tenor '${tenor || "(none)"}' while the board prices '${boardTenor}'`,
      );
      continue;
    }
    if (cardsByHub.has(hub)) {
      failures.push(`the price board renders more than one card for ${hub}`);
      continue;
    }
    cardsByHub.set(hub, cell);
    const served = rowsByPair.get(`${hub}|${tenor}`) ?? [];
    if (cell.recordId === "") {
      if (served.length > 0) {
        failures.push(
          `${where}: the read served ${served.length} row(s) for ${hub} ${tenor} (200) and the card`
          + " prices none of them",
        );
      } else {
        observations.push(
          `${where}: the read served no row for ${hub} ${tenor}, so the card states the absence`
          + " rather than a price",
        );
      }
      continue;
    }
    if (!cell.slice) {
      failures.push(`${where} names row '${cell.recordId}' without declaring which slice it came from`);
      continue;
    }
    const row = rowsById.get(`${cell.slice}|${cell.recordId}`);
    if (!row) {
      failures.push(
        `${where} prices ${hub} ${tenor} from row '${cell.recordId}' of slice '${cell.slice}', which`
        + " this read did not return (stale, other-context or foreign row)",
      );
      continue;
    }
    if (row.hub !== hub || row.tenor !== tenor) {
      failures.push(
        `${where} prices ${hub} ${tenor} from row '${row.id}', which this read places on`
        + ` ${row.hub} ${row.tenor}`,
      );
      continue;
    }
    if (row.boardEligible === false) {
      failures.push(
        `${where} prices row '${row.id}', which the board's own gas-price rule excludes`
        + " (is_gas_price is false)",
      );
      continue;
    }
    const displayed = priceNumbers(cell.priceText);
    const wanted = row.values.filter((value) => value !== null);
    if (row.values.some((value) => value === null) && !/\bn\/a\b/i.test(cell.priceText)) {
      failures.push(
        `${where} shows '${cell.priceText || "(nothing)"}' while row '${row.id}' carries no value for`
        + " one side of the price",
      );
      continue;
    }
    if (displayed.length !== wanted.length) {
      failures.push(
        `${where} shows ${displayed.length} number(s) (${cell.priceText || "(nothing)"}) while row`
        + ` '${row.id}' carries ${wanted.length}: the two could not be compared`,
      );
      continue;
    }
    const wrong = wanted
      .map((value, position) => ({ value, shown: displayed[position] }))
      .filter((entry) => Math.abs(entry.shown - entry.value) > QUOTED_PRICE_TOLERANCE);
    if (wrong.length > 0) {
      failures.push(
        `${where} shows ${wrong.map((entry) => entry.shown).join(", ")} while row '${row.id}' carries`
        + ` ${wrong.map((entry) => entry.value).join(", ")}`,
      );
      continue;
    }
    const unit = displayPriceUnit(row.currency, row.unit);
    if (unit === null) {
      failures.push(
        `${where} prices row '${row.id}', which carries no currency/unit to display the price in`,
      );
      continue;
    }
    if (!`${cell.priceText} ${cell.metaText}`.includes(unit)) {
      failures.push(
        `${where} prices row '${row.id}' without displaying its unit '${unit}'`
        + ` ('${`${cell.priceText} ${cell.metaText}`.trim() || "(nothing)"}')`,
      );
      continue;
    }
    if (row.source === null) {
      failures.push(`${where} prices row '${row.id}', which names no source system`);
      continue;
    }
    if (cell.sourceText !== row.source) {
      failures.push(
        `${where} attributes the price to '${cell.sourceText || "(nothing)"}' while row '${row.id}'`
        + ` carries '${row.source}'`,
      );
      continue;
    }
  }

  const priced = [...cardsByHub.values()].filter((cell) => cell.recordId !== "").length;
  observations.push(
    `the board priced ${priced} of its ${scope.length} declared hub(s) from the read's rows`
    + ` (displayed tenor '${boardTenor}', served: ${available
      .map((slice) => slice.label ?? slice.key ?? "slice")
      .join(", ")})`,
  );

  for (const hub of scope) {
    if (!rowsByPair.has(`${hub}|${boardTenor}`)) continue;
    if (cardsByHub.has(hub)) continue;
    const served = rowsByPair.get(`${hub}|${boardTenor}`).length;
    failures.push(
      `the read served ${served} row(s) for ${hub} ${boardTenor} (200) and the price board renders no`
      + " card for that hub",
    );
  }

  if (asOf) {
    const label = utcInstantLabel(board.asOf);
    if (!board.asOf) {
      failures.push(
        "the surface states no as-of instant while the projection payload declares one",
      );
    } else if (label === null || utcInstantLabel(asOf) === null) {
      failures.push(`the surface or read answered an unusable as-of instant`);
    } else if (!String(board.asOfText ?? "").includes(label)) {
      failures.push(
        `the surface states as-of '${board.asOfText || "(nothing)"}' while the payload it declares`
        + ` is '${board.asOf}' (${label})`,
      );
    } else {
      observations.push(`the surface states the projection's as-of (${label})`);
    }
    // The lane polls, so the surface legitimately holds a payload read before this one; the distance
    // between the two instants is reported rather than required to be zero.
    const heldMs = Date.parse(String(board.asOf));
    const readMs = Date.parse(String(asOf));
    if (Number.isFinite(heldMs) && Number.isFinite(readMs)) {
      observations.push(
        `the surface's stated as-of is ${Math.round((readMs - heldMs) / 1000)}s before this read's`
        + (source ? ` (read from ${source})` : ""),
      );
    }
  }
  return { failures, observations };
}
