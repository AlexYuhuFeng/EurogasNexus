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
 *   and a group whose evidence was not collected are failures rather than quiet observations.
 *
 * The decision logic is pure so every negative case can be exercised without a browser
 * (`clients/web/tests/readToRender.test.ts`); `collectVisibleElements` is serialised into the
 * page by `page.evaluate` and exercised there against a stub document.
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
  });
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
