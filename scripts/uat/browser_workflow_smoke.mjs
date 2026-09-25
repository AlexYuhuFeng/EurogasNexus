// Whole-product browser acceptance for the current main ref.
//
// Requires:
// - development/test API on :8000 backed by migrated PostgreSQL
// - Vite dev server on :3000
// - preview/UAT fixtures plus scripts/uat/seed_browser_identity.py
// - Playwright + axe-core (CI installs exact versions outside the repo)
//
// The sweep is deliberately evidence-oriented: every declared workspace is
// rendered in English and Mandarin at 1440x900, 1920x1080, and 390x844,
// checked with axe, checked for document-level horizontal overflow, and
// captured as a screenshot. It does not convert unavailable/licensed data into
// a pass; it only verifies the UI state that the authenticated seeded runtime
// actually exposes.
import { createRequire } from "node:module";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import {
  collectVisibleElements,
  evaluateReadToRender,
  readGroupRows,
  readSourceLabel,
} from "./readToRender.mjs";

const require = createRequire(import.meta.url);
const { chromium } = require(
  process.env.EUROGAS_UAT_PLAYWRIGHT_PATH || "playwright",
);
const axePath =
  process.env.EUROGAS_UAT_AXE_PATH || require.resolve("axe-core/axe.min.js");
const axeSource = readFileSync(axePath, "utf8");

const BASE = process.env.EUROGAS_UAT_BASE_URL || "http://127.0.0.1:3000";
const OUTPUT_DIR =
  process.env.EUROGAS_UAT_OUTPUT_DIR ||
  path.resolve("artifacts", "uat-browser");
const LANGUAGE_STORAGE_KEY = "eurogas.language.v1";

const WORKSPACES = [
  "network",
  "capacity",
  "market",
  "scenario",
  "contracts",
  "strategy",
  "review",
  "orders",
  "sources",
  "glossary",
  "runtime",
  "settings",
  "manual",
  "access",
  "research",
  "agents",
];

const LANGUAGES = [
  { id: "en", htmlPrefix: "en" },
  { id: "zh-CN", htmlPrefix: "zh" },
];

const VIEWPORTS = [
  { id: "desktop-1440", width: 1440, height: 900 },
  { id: "desktop-1920", width: 1920, height: 1080 },
  { id: "narrow-390", width: 390, height: 844 },
];


/**
 * What each workspace must show, and where the data it shows comes from.
 *
 * `heading` is matched against the displayed page's own heading, so a deep link that lands on a
 * different surface fails instead of being screenshotted as if it were the requested one.
 * `apiPath` is read from the same session the browser holds.
 *
 * A surface whose own read can be compared row by row declares `readToRender` (see
 * `readToRender.mjs`). Each group names the path the rows have in the read's payload, the payload
 * field that carries each row's record id, and the selector the surface renders those rows under
 * (`data-record` kinds carrying `data-record-id`), so a returned row is compared only with its own
 * group's rendered rows - by exact id, never by page copy. `rowLimit` mirrors the bound the
 * surface itself applies, and `emptySelector` names the surface's own declared empty state
 * (`data-empty-state`), used when the read is a successful, measured zero.
 *
 * A surface without `readToRender` keeps the older whole-page check: it is weaker, and it is
 * why the declared functional gaps below stay declared.
 */
const SURFACE_SIGNALS = {
  network: { heading: /network|market/i, apiPath: "/api/reference-network/edges?limit=5" },
  capacity: { heading: /capacity/i, apiPath: "/api/physical/capacity?limit=5" },
  market: { heading: /market/i, apiPath: "/api/market/observations?limit=5" },
  scenario: { heading: /decision/i, apiPath: "/api/decision-cases?limit=5" },
  // Match the client's upstream-terms read; this endpoint has no limit parameter. One persisted
  // contract is rendered in two places - the pool row the Portfolio Overview task draws from the
  // projection's `resources` slice, and the contract library row - and both carry the contract's
  // own id (`portfolio_resource_from_contract` maps `contract_id` to `resource_id`), so one group
  // covers both views. `rowLimit` 25 mirrors the overview's own bound. The deep link lands on the
  // overview task, which declares no empty-state row, so an empty read is reported as unmeasured
  // rather than against an empty state this view does not render.
  contracts: { heading: /portfolio|contract/i, apiPath: "/api/route-cost/upstream-contracts", readToRender: [{ label: "upstream contracts", rowsPath: "data", recordIdField: "contract_id", rowSelectors: ['[data-record="portfolio-resource"]', '[data-record="upstream-contract"]'], rowLimit: 25 }] },
  strategy: { heading: /strategy/i, apiPath: "/api/strategies?limit=5" },
  review: { heading: /review|decision/i, apiPath: "/api/review/decisions?limit=5" },
  // The orders surface renders the rows of the portfolio projection it reads in its own workspace
  // batch (`screen_orders`/`pnl_snapshots`), not the legacy live-summary aggregate the probe used
  // to read: an aggregate is not a row set. `rowLimit` 8 mirrors the PnL table's own bound.
  orders: { heading: /portfolio|order/i, apiPath: "/api/projections/portfolio-snapshot", readToRender: [{ label: "screen orders", rowsPath: "data.slices.screen_orders", recordIdField: "order_observation_id", rowSelectors: ['[data-record="screen-order"]'], emptySelector: '[data-empty-state="screen-orders"]' }, { label: "pnl snapshots", rowsPath: "data.slices.pnl_snapshots", recordIdField: "pnl_snapshot_id", rowSelectors: ['[data-record="pnl-snapshot"]'], emptySelector: '[data-empty-state="pnl-snapshots"]', rowLimit: 8 }] },
  sources: { heading: /source/i, apiPath: "/api/sources?limit=5" },
  // The glossary surface's own read (`api.glossary` in the client) answers the whole term
  // catalogue; the probe reads the same route bounded to five terms, so every term it returns must
  // be one the left term index rendered - by the term's own id, in both languages. The surface
  // bounds its own list at 40 terms, which five cannot exceed, and it renders its declared empty
  // state (`data-empty-state="glossary-terms"`) when it has no terms at all.
  glossary: { heading: /glossary/i, apiPath: "/api/glossary?limit=5", readToRender: [{ label: "glossary term index", rowsPath: "data", recordIdField: "term_id", rowSelectors: ['[data-record="glossary-term"]'], emptySelector: '[data-empty-state="glossary-terms"]' }] },
  runtime: { heading: /runtime/i, apiPath: "/api/runtime/pipeline-health" },
  settings: { heading: /settings/i, apiPath: "/api/runtime/release" },
  manual: { heading: /manual/i, apiPath: null },
  access: { heading: /access/i, apiPath: "/api/access/users" },
  research: { heading: /research/i, apiPath: "/api/capabilities?limit=5" },
  agents: { heading: /agent/i, apiPath: "/api/capabilities?limit=5" },
};

/**
 * Functional gaps this run already knows about: a surface whose read returns rows while the
 * surface renders none. Declared with the reason so the number is visible in every summary, and so
 * a *new* one fails the run rather than joining a silent list.
 */
const KNOWN_FUNCTIONAL_GAPS = {
  market:
    "market observations return rows while every hub card renders n/a - recorded by the visual "
    + "review and not yet fixed",
  capacity:
    "physical capacity returns rows while the operating board renders no rows and every KPI reads 0",
  sources:
    "sources return rows while the administration surface reports Total sources 0",
  access: "access users return rows while the Users table renders the empty row 'No users'",
  research: "the capability catalogue returns rows while the table renders 'Loading workspace'",
  agents: "the capability catalogue returns rows while the table renders 'Loading workspace'",
};

/**
 * Surface defects this run has measured and that are still open.
 *
 * Declared rather than ignored: each one is counted in `functionalGapCount`, printed in
 * `observations`, and stated in `docs/release/FUNCTIONAL_ACCEPTANCE_REPORT.md`, so the delivery
 * conversation starts from the measured state. A surface that is *not* listed here fails the run.
 */
const KNOWN_SURFACE_DEFECTS = {
  agents:
    "the capability catalogue renders 'Loading workspace' after load while /api/capabilities "
    + "returns rows (measured 2026-09-19; the surface's own read never completes on a fresh login)",
};

/** Console noise that is a known, declared condition rather than a defect. */
const ALLOWED_CONSOLE_ERRORS = [
  // The shell asks who it is before the session exists; the 401 there is the expected answer.
  /the server responded with a status of 401/,
];

function safeName(value) {
  return value.replaceAll(/[^a-zA-Z0-9._-]+/g, "-");
}

function recordFailure(failures, scope, detail) {
  failures.push({ scope, detail: String(detail) });
}

/** Record something the run could not measure, or a gap it declares. Never a failure. */
function recordObservation(observations, detail) {
  observations.push(String(detail));
}

/**
 * Capture a stack for errors React only logs.
 *
 * React's internal errors arrive as a bare console.error with no component name and no stack;
 * wrapping console.error before the app loads takes a real stack at the moment React reports.
 */
async function installReactErrorStackCapture(page) {
  await page.addInitScript(() => {
    const previous = console.error;
    window.__reactErrorStacks = [];
    console.error = function patchedConsoleError(...args) {
      try {
        const first = args[0];
        if (typeof first === "string" && /Internal React error|static flag/i.test(first)) {
          window.__reactErrorStacks.push({
            message: first,
            stack: String(new Error(first).stack || ""),
          });
        }
      } catch {
        // never let the capture break the page it is observing
      }
      return previous.apply(this, args);
    };
  });
}

async function ensureAuthenticated(page) {
  await page.goto(BASE, { waitUntil: "domcontentloaded" });
  await page.waitForTimeout(500);

  if (await page.locator("main").isVisible().catch(() => false)) return;

  const username = process.env.EUROGAS_NEXUS_DEV_LOGIN_USERNAME || "";
  const password = process.env.EUROGAS_NEXUS_DEV_LOGIN_PASSWORD || "";
  if (!username || !password) {
    throw new Error(
      "Browser UAT requires EUROGAS_NEXUS_DEV_LOGIN_USERNAME and EUROGAS_NEXUS_DEV_LOGIN_PASSWORD",
    );
  }

  const usernameInput = page.locator("#sign-in-username");
  await usernameInput.waitFor({ state: "visible", timeout: 15_000 });
  await usernameInput.fill(username);
  await page.locator("#sign-in-password").fill(password);
  await page.locator(".sign-in-dev-form button[type=submit]").click();
  await page.locator("main").waitFor({ state: "visible", timeout: 20_000 });
}

async function setLanguage(page, language) {
  await page.evaluate(
    ([key, value]) => window.localStorage.setItem(key, value),
    [LANGUAGE_STORAGE_KEY, language],
  );
}

async function axeViolations(page) {
  await page.addScriptTag({ content: axeSource });
  return page.evaluate(async () => {
    const result = await window.axe.run(document, {
      runOnly: {
        type: "tag",
        values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"],
      },
    });
    return result.violations.map((violation) => ({
      id: violation.id,
      impact: violation.impact,
      nodes: violation.nodes.length,
      help: violation.help,
      targets: violation.nodes.slice(0, 4).map((node) => node.target),
      html: violation.nodes.slice(0, 2).map((node) => node.html),
      failureSummary: violation.nodes.slice(0, 2).map((node) => node.failureSummary),
    }));
  });
}


/**
 * The functional check for one workspace: is the requested page displayed, is its heading the
 * expected one, has loading finished, and does it render what its own API returned?
 */
async function inspectSurfaceFunction(
  page,
  workspace,
  failures,
  observations,
  functionalGaps,
) {
  const signal = SURFACE_SIGNALS[workspace];
  const scope = `functional/${workspace}`;
  if (!signal) {
    recordFailure(
      failures,
      scope,
      "no surface signal is declared for this workspace: add one, so the link cannot pass unmeasured",
    );
    return null;
  }

  const state = await page.evaluate(async (path) => {
    const pages = [...document.querySelectorAll(".workspace-page")];
    const displayed = pages.find((element) => {
      const style = getComputedStyle(element);
      const rect = element.getBoundingClientRect();
      return style.display !== "none" && rect.width > 0 && rect.height > 0;
    });
    // The shell marks the active workspace with a `workspace-<id>` class on an ancestor, which is
    // the only language-independent way to say "this is the page the link asked for": matching the
    // translated heading failed the whole Chinese run for no reason but translation.
    let markedWorkspace = null;
    const known = new Set([
      "network", "capacity", "market", "scenario", "contracts", "strategy", "review", "orders",
      "sources", "glossary", "runtime", "settings", "manual", "access", "research", "agents",
    ]);
    let node = displayed ?? null;
    while (node && markedWorkspace === null) {
      for (const name of String(node.className || "").split(/\s+/)) {
        // `workspace-page` is the page element's own class, not a workspace marker; only a class
        // naming a known workspace identifies which surface is on screen.
        if (name.startsWith("workspace-") && known.has(name.slice("workspace-".length))) {
          markedWorkspace = name.slice("workspace-".length);
          break;
        }
      }
      node = node.parentElement;
    }
    const heading = displayed?.querySelector("h1, h2")?.textContent?.trim() ?? null;
    const text = displayed ? displayed.innerText : "";
    let apiRows = null;
    let apiStatus = null;
    let apiBody = null;
    if (path) {
      try {
        const response = await fetch(path, { credentials: "include" });
        apiStatus = response.status;
        const body = await response.json();
        apiBody = body ?? null;
        const data = body?.data;
        apiRows = Array.isArray(data)
          ? data.length
          : data === null || data === undefined
            ? 0
            : 1;
      } catch (error) {
        apiStatus = 0;
        apiRows = null;
      }
    }
    const reactErrors = (window.__reactErrorStacks || []).slice(0, 2).map((entry) => ({
      message: String(entry.message).slice(0, 160),
      stack: String(entry.stack).split("\n").slice(0, 8).join(" | ").slice(0, 900),
    }));
    return {
      displayed: Boolean(displayed),
      reactErrors,
      markedWorkspace,
      heading,
      loading: /loading workspace/i.test(text),
      text: text.slice(0, 400),
      apiRows,
      apiStatus,
      apiBody,
    };
  }, signal.apiPath);

  if (!state.displayed) {
    recordFailure(failures, scope, "the requested workspace page is not displayed");
    return state;
  }
  if (state.markedWorkspace && state.markedWorkspace !== workspace) {
    // The deep link resolved to a different surface: the screenshot is evidence for the wrong page.
    // This is the defect that let `contracts.png` capture Portfolio Overview for a run that stayed
    // green.
    recordFailure(
      failures,
      scope,
      `the displayed page is the '${state.markedWorkspace}' workspace, not '${workspace}'`,
    );
  }
  if (state.loading) {
    const declared = KNOWN_SURFACE_DEFECTS[workspace];
    if (declared) {
      functionalGaps.push({ workspace, declared: true, reason: declared });
      recordObservation(observations, `${scope}: declared defect - ${declared}`);
    } else {
      recordFailure(failures, scope, "the surface still shows 'Loading workspace' after load");
    }
  }
  if (state.reactErrors && state.reactErrors.length > 0) {
    // A failure, with the captured stack: React's internal error is one per application mount and
    // is a defect on every workspace it reaches, not a condition to be carried in a list.
    recordFailure(
      failures,
      scope,
      `react-internal-error: ${state.reactErrors[0].message} :: ${
        state.reactErrors[0].stack || "(no stack captured)"
      }`,
    );
  }
  if (signal.readToRender) {
    // The surface's own read is compared with the rows the surface actually rendered, by exact
    // record id and only within each group's own selector (`readToRender.mjs`). Page copy is not
    // consulted: a legitimate `n/a` cell, or the portfolio context strip's own "stale, missing or
    // unavailable" sentence, used to be read as "the surface renders none of the read's rows" and
    // failed a surface that had rendered them.
    const groups = signal.readToRender.map((group) => readGroupRows(state.apiBody, group));
    const evidence = await page.evaluate(collectVisibleElements, {
      groups: groups.map((group) => ({
        rowSelectors: Array.isArray(group.rowSelectors) ? group.rowSelectors : [],
        emptySelector: group.emptySelector ?? null,
      })),
    });
    const compared = evaluateReadToRender({
      status: state.apiStatus,
      groups,
      evidence,
      source: readSourceLabel(state.apiBody),
    });
    for (const detail of compared.observations) {
      recordObservation(observations, `${scope}: ${detail}`);
    }
    for (const detail of compared.failures) {
      recordFailure(failures, scope, detail);
    }
  } else if (state.apiRows !== null && state.apiRows > 0) {
    // The read has data. If the surface renders none of it, it is telling the operator the
    // deployment is empty - the defect class this gate exists for. This whole-page check is the
    // weaker one kept for the surfaces that have not declared a scoped `readToRender` contract
    // yet; it treats any non-array body as one row and any `n/a` copy on the page as a missing
    // row, which is why the repaired surfaces no longer use it.
    const rendersNothing = /\bn\/a\b|unavailable|no records|no data|not (?:available|read|configured)/i.test(
      state.text,
    );
    if (rendersNothing) {
      const declared = KNOWN_FUNCTIONAL_GAPS[workspace];
      if (declared) {
        functionalGaps.push({ workspace, declared: true, reason: declared });
        recordObservation(
          observations,
          `${scope}: declared functional gap - ${declared} (api ${state.apiStatus}, ${state.apiRows} row(s))`,
        );
      } else {
        recordFailure(
          failures,
          scope,
          `the read returned ${state.apiRows} row(s) (${state.apiStatus}) and the surface renders none of them`,
        );
      }
    }
  }
  return state;
}

async function inspectWorkspace(
  page,
  language,
  viewport,
  workspace,
  failures,
  observations,
  functionalGaps,
) {
  await page.setViewportSize({ width: viewport.width, height: viewport.height });
  await page.goto(
    `${BASE}/?workspace=${encodeURIComponent(workspace)}`,
    { waitUntil: "domcontentloaded" },
  );
  await page.waitForTimeout(350);

  const main = page.locator("main");
  try {
    await main.waitFor({ state: "visible", timeout: 12_000 });
  } catch {
    recordFailure(
      failures,
      `${language.id}/${viewport.id}/${workspace}`,
      "main landmark did not become visible",
    );
  }

  /**
   * The functional gate below judges a surface "after load", so the sweep waits for the page's own
   * workspace read to settle instead of racing it.
   *
   * The page publishes that fact itself (`data-workspace-load-state`, `unread | loading | settled`):
   * it is the batch's state, not `api.loading`, which is also true while an unrelated on-demand
   * action runs, and a settled read is not the same as a boolean that is false before the read even
   * starts. The sweep used to evaluate immediately, so on a slow CI database it measured surfaces
   * whose read was still in flight and reported pending states as lingering loading copy and missing
   * rows. A page that never settles is still a failure - the wait is bounded and its expiry recorded.
   */
  const settleScope = `${language.id}/${viewport.id}/${workspace}`;
  const settled = await page
    .waitForFunction(
      () => [...document.querySelectorAll(".workspace-page")]
        .some((element) => element.dataset.workspaceLoadState === "settled"),
      null,
      { timeout: 20_000 },
    )
    .then(() => true)
    .catch(() => false);
  if (!settled) {
    recordFailure(
      failures,
      settleScope,
      "the workspace read never settled (data-workspace-load-state was not 'settled' after 20s)",
    );
  }

  const state = await page.evaluate(() => ({
    lang: document.documentElement.lang,
    scrollWidth: document.documentElement.scrollWidth,
    clientWidth: document.documentElement.clientWidth,
    h1Count: document.querySelectorAll("main h1").length,
    signInVisible: Boolean(document.querySelector(".sign-in-screen")),
    // Whether the page the deep link asked for is actually on screen. Every other check in this
    // function - the language, the heading count, the overflow comparison, the axe sweep - is
    // vacuous for a hidden page: a `display: none` subtree has no overflow, no visible heading and
    // nothing for axe to judge. That is how a workspace whose page never renders could stay green
    // here for as long as this check was missing.
    pageVisible: [...document.querySelectorAll(".workspace-page")].some((element) => {
      const style = getComputedStyle(element);
      const rect = element.getBoundingClientRect();
      return style.display !== "none" && rect.width > 0 && rect.height > 0;
    }),
    pageCount: document.querySelectorAll(".workspace-page").length,
  }));

  const scope = `${language.id}/${viewport.id}/${workspace}`;
  if (!state.pageVisible) {
    // No exemption: a deep link whose page does not render is a failure for every workspace. The
    // map page's own blank view was the declared one; it is repaired, so the declaration is gone
    // with it rather than left to hide the next occurrence.
    recordFailure(
      failures,
      scope,
      `no workspace page is displayed (mounted pages: ${state.pageCount})`,
    );
  }
  if (!state.lang.toLowerCase().startsWith(language.htmlPrefix)) {
    recordFailure(
      failures,
      scope,
      `document language mismatch: ${state.lang}`,
    );
  }
  if (state.signInVisible) {
    recordFailure(failures, scope, "session fell back to sign-in screen");
  }
  if (state.h1Count !== 1) {
    recordFailure(failures, scope, `expected exactly one main h1, got ${state.h1Count}`);
  }
  if (state.scrollWidth > state.clientWidth + 2) {
    recordFailure(
      failures,
      scope,
      `document horizontal overflow ${state.scrollWidth}px > ${state.clientWidth}px`,
    );
  }

  const violations = await axeViolations(page);
  if (violations.length > 0) {
    recordFailure(failures, scope, `axe violations: ${JSON.stringify(violations)}`);
  }

  // The functional gate: the requested page, its data, and no unfinished loading state. The
  // chrome-level checks above cannot see any of that - which is how a run stayed green while the
  // surfaces it captured were empty.
  await inspectSurfaceFunction(page, workspace, failures, observations, functionalGaps);

  const screenshotDir = path.join(
    OUTPUT_DIR,
    safeName(language.id),
    viewport.id,
  );
  mkdirSync(screenshotDir, { recursive: true });
  await page.screenshot({
    path: path.join(screenshotDir, `${safeName(workspace)}.png`),
    fullPage: false,
  });

  return {
    language: language.id,
    viewport: viewport.id,
    workspace,
    axeViolations: violations.length,
    h1Count: state.h1Count,
    scrollWidth: state.scrollWidth,
    clientWidth: state.clientWidth,
  };
}

async function agentResearchE2E(page, failures) {
  const scope = "interaction/agent-research-review";
  const objective =
    "Assess whether the seeded NBP-TTF day-ahead spread is persistent enough for governed UAT research.";

  try {
    await setLanguage(page, "en");
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto(`${BASE}/?workspace=agents`, { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(400);

    await page.locator("#agents-task-research").click();
    await page.locator("#agents-objective").fill(objective);
    const allowStrategy = page.locator(
      '.agents-view-research label.field-inline input[type="checkbox"]',
    );
    if (!(await allowStrategy.isChecked())) await allowStrategy.check();

    // The run is the workspace's primary action, so it lives in the header's primary slot
    // (`data-primary-action`), not inside the panel - Wave 9 moved it there and this sweep kept
    // clicking `button.button.primary` inside the view, a class the header action never had. The
    // action is disabled until the workspace batch has answered (the run persists its own rows, so
    // it is gated on the runtime database), so wait for it to be usable and report the blocker it
    // shows rather than letting two 30-second timeouts race.
    const runButton = page.locator(".agents-workspace [data-primary-action]").first();
    await runButton.waitFor({ state: "visible", timeout: 30_000 });
    const runnable = await page
      .waitForFunction(
        () => {
          const button = document.querySelector(".agents-workspace [data-primary-action]");
          return Boolean(button) && !button.disabled;
        },
        null,
        { timeout: 60_000 },
      )
      .then(() => true)
      .catch(() => false);
    if (!runnable) {
      throw new Error(
        `agent research action stayed disabled: ${await runButton.getAttribute("title")}`,
      );
    }

    const researchResponsePromise = page.waitForResponse(
      (response) =>
        response.url().includes("/api/agent/research") &&
        response.request().method() === "POST",
      { timeout: 120_000 },
    );
    await runButton.click();
    const researchResponse = await researchResponsePromise;
    const researchBody = await researchResponse.json().catch(() => null);
    if (!researchResponse.ok()) {
      throw new Error(
        `agent research HTTP ${researchResponse.status()}: ${JSON.stringify(researchBody)}`,
      );
    }
    if (researchBody?.data?.stage !== "READY_FOR_HUMAN_REVIEW") {
      throw new Error(
        `agent research did not reach review gate: ${JSON.stringify(researchBody?.data ?? researchBody)}`,
      );
    }
    const resultPanel = page.locator(".agents-result-panel").first();
    await resultPanel.waitFor({ state: "visible", timeout: 10_000 });

    const runEnvelope = await page.evaluate(async (wantedObjective) => {
      const response = await fetch("/api/agent/runs?limit=50", {
        credentials: "include",
      });
      if (!response.ok) throw new Error(`agent runs HTTP ${response.status}`);
      const body = await response.json();
      const run = (body.data || []).find(
        (item) =>
          (item.user_objective ?? item.objective) === wantedObjective,
      );
      if (!run) throw new Error("new governed agent run not found");
      const replayResponse = await fetch(
        `/api/agent/runs/${encodeURIComponent(run.agent_run_id)}/replay`,
        { credentials: "include" },
      );
      if (!replayResponse.ok) {
        throw new Error(`agent replay HTTP ${replayResponse.status}`);
      }
      return { run, replay: (await replayResponse.json()).data };
    }, objective);

    if (runEnvelope.run.status !== "READY_FOR_HUMAN_REVIEW") {
      recordFailure(
        failures,
        scope,
        `unexpected run status: ${runEnvelope.run.status}`,
      );
    }
    if (runEnvelope.replay.artifact_chain?.complete !== true) {
      recordFailure(
        failures,
        scope,
        `artifact chain incomplete: ${JSON.stringify(runEnvelope.replay.artifact_chain)}`,
      );
    }
    if ((runEnvelope.replay.tool_invocations || []).length === 0) {
      recordFailure(failures, scope, "governed run persisted no tool invocations");
    }

    await page.locator("#agents-task-runs").click();
    const runRow = page
      .locator("button.data-table-row.link-row")
      .filter({ hasText: objective })
      .first();
    await runRow.waitFor({ state: "visible", timeout: 10_000 });
    await runRow.click();

    const replayPanel = page.locator(".agents-replay-panel");
    await replayPanel.waitFor({ state: "visible", timeout: 10_000 });
    const presentArtifacts = await replayPanel.locator(
      ".agents-chain-entry:not(.is-absent)",
    ).count();
    if (presentArtifacts !== 6) {
      recordFailure(
        failures,
        scope,
        `replay rendered ${presentArtifacts}/6 persisted artifacts`,
      );
    }

    const accept = replayPanel.locator(".review-decision-accepted");
    await accept.waitFor({ state: "visible", timeout: 10_000 });
    if (await accept.isDisabled()) {
      recordFailure(failures, scope, "review-pack accept action is disabled");
    } else {
      await accept.click();
    }

    /**
     * The accepted decision, read back from PostgreSQL.
     *
     * One property, asserted once and bounded in time: the decision the operator just accepted is
     * replayable from the persisted run. It used to be read twice in a row - a `waitForFunction`
     * poll that proved the property, followed by an immediate second read that could disagree with
     * it and did, once, in CI:
     *
     *     interaction/agent-research-review: accepted review decision was not replayed from PostgreSQL
     *
     * The poll had already seen the decision, so the write was persisted and replayable; the
     * duplicate read is a race in the check rather than a fact about the product. The check now
     * retries the *same* read until the decision appears (15s) and, if it never does, reports what
     * every attempt observed, so a genuine persistence failure is distinguishable from a stale read.
     */
    const readReplayDecisions = () =>
      page.evaluate(async (runId) => {
        const response = await fetch(
          `/api/agent/runs/${encodeURIComponent(runId)}/replay`,
          { credentials: "include" },
        );
        if (!response.ok) throw new Error(`agent replay HTTP ${response.status}`);
        return (await response.json()).data;
      }, runEnvelope.run.agent_run_id);

    let confirmedReplay = null;
    const observations = [];
    const replayDeadline = Date.now() + 15_000;
    for (;;) {
      try {
        const candidate = await readReplayDecisions();
        const seen = candidate?.artifacts?.review_pack?.payload?.human_confirmation?.decisions || [];
        if (seen.some((item) => item.decision === "accepted")) {
          confirmedReplay = candidate;
          break;
        }
        observations.push(
          `read returned ${seen.length} decision(s): ${JSON.stringify(seen.map((item) => item.decision))}`,
        );
      } catch (error) {
        observations.push(`read failed: ${String(error)}`);
      }
      if (Date.now() >= replayDeadline) break;
      await page.waitForTimeout(500);
    }

    if (!confirmedReplay) {
      recordFailure(
        failures,
        scope,
        `accepted review decision was not replayed from PostgreSQL after 15s (${observations.join("; ")})`,
      );
      return null;
    }

    const decisions =
      confirmedReplay?.artifacts?.review_pack?.payload?.human_confirmation?.decisions || [];

    const evidence = {
      runId: runEnvelope.run.agent_run_id,
      status: runEnvelope.run.status,
      chainComplete: confirmedReplay.artifact_chain?.complete === true,
      presentArtifacts: confirmedReplay.artifact_chain?.present || [],
      invocationCount: (confirmedReplay.tool_invocations || []).length,
      reviewPackId: confirmedReplay.artifacts?.review_pack?.artifact_id || null,
      reviewDecisions: decisions,
      fixture: confirmedReplay.fixture || null,
    };
    writeFileSync(
      path.join(OUTPUT_DIR, "agent-research-e2e.json"),
      JSON.stringify(evidence, null, 2),
      "utf8",
    );
    return evidence;
  } catch (error) {
    recordFailure(failures, scope, error);
    return null;
  }
}

async function interactionChecks(page, failures) {
  await setLanguage(page, "en");
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto(`${BASE}/?workspace=market`, { waitUntil: "domcontentloaded" });
  await page.waitForTimeout(350);

  const preferenceTrigger = page.locator(".topbar-preferences-trigger");
  try {
    await preferenceTrigger.click();
    const menu = page.locator('[role="menu"]#topbar-preferences-menu');
    await menu.waitFor({ state: "visible", timeout: 5_000 });
    // Wait for the menu to hold focus before exercising its keyboard model, rather than assuming a
    // frame has run: the popover moves focus into itself on the next animation frame, and a run that
    // pressed ArrowDown before that was testing an unspecified state.
    await page
      .waitForFunction(() => document.activeElement?.closest("#topbar-preferences-menu") !== null, {
        timeout: 5_000,
      })
      .catch(() => recordFailure(failures, "interaction/preferences", "the menu never took focus"));
    await page.keyboard.press("ArrowDown");
    await page.keyboard.press("Escape");
    // Focus restoration is asserted as an outcome with a bounded wait rather than as an instant: a
    // surface that moves focus on the next frame is not wrong, and a surface that never moves it
    // still fails. (The header menu now moves it synchronously, so this passes on the first read.)
    let focusReturned = false;
    for (let attempt = 0; attempt < 20 && !focusReturned; attempt += 1) {
      focusReturned = await preferenceTrigger.evaluate(
        (element) => document.activeElement === element,
      );
      if (!focusReturned) await page.waitForTimeout(50);
    }
    if (!focusReturned) {
      recordFailure(failures, "interaction/preferences", "Escape did not return focus to invoker");
    }
  } catch (error) {
    recordFailure(failures, "interaction/preferences", error);
  }

  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(`${BASE}/?workspace=network`, { waitUntil: "domcontentloaded" });
  await page.waitForTimeout(350);
  try {
    const disclosure = page.locator("details.topbar-context-disclosure");
    const initiallyOpen = await disclosure.getAttribute("open");
    if (initiallyOpen !== null) {
      recordFailure(failures, "interaction/narrow-disclosure", "narrow context disclosure should start closed");
    }
    await disclosure.locator("summary").click();
    await page.locator(".topbar-context-disclosure-content").waitFor({
      state: "visible",
      timeout: 5_000,
    });
  } catch (error) {
    recordFailure(failures, "interaction/narrow-disclosure", error);
  }

  // The day board (the desk's clock). The seeded UAT fixture declares two nomination windows, so a
  // deadline row must exist: this asserts the whole chain the unit and API tests assert in pieces -
  // the fixture declaration, the READ-floor route, the gas-day resolution and the panel - against a
  // running browser. The instant shown must be the API's resolved one (a UTC timestamp), and the
  // countdown beside it must be labelled as the browser's clock, because those are two clocks.
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto(`${BASE}/?workspace=scenario`, { waitUntil: "domcontentloaded" });
  await page.waitForTimeout(500);
  try {
    const board = page.locator("section.day-board");
    await board.waitFor({ state: "visible", timeout: 10_000 });
    const deadlines = board.locator(".day-board-clock .day-board-deadline strong");
    await deadlines
      .first()
      .waitFor({ state: "visible", timeout: 10_000 })
      .catch(() =>
        recordFailure(
          failures,
          "interaction/day-board",
          "no nomination-window deadline rendered (the fixture declares two)",
        ),
      );
    const rendered = await deadlines.allTextContents();
    if (rendered.length < 2) {
      recordFailure(
        failures,
        "interaction/day-board",
        `expected two declared windows, rendered ${rendered.length}`,
      );
    }
    for (const value of rendered) {
      if (!/UTC/.test(value)) {
        recordFailure(
          failures,
          "interaction/day-board",
          `deadline is not the API's resolved UTC instant: ${value}`,
        );
      }
    }
    const qualifiers = await board
      .locator(".day-board-clock .day-board-qualifier")
      .allTextContents();
    if (qualifiers.length === 0) {
      recordFailure(
        failures,
        "interaction/day-board",
        "the countdown is not labelled with the clock it was measured against",
      );
    }
    // The board must be usable whatever time the sweep runs: every window row either still has time
    // left on this gas day's deadline, or states the next occurrence the API resolved. A row that
    // has closed without saying when the window next opens leaves the desk with nothing to act on.
    await page
      .waitForFunction(
        () => {
          const rows = [...document.querySelectorAll(".day-board-clock .day-board-row")];
          if (rows.length === 0) return false;
          return rows.every((row) => {
            const overdue = row.querySelector(".day-board-countdown.is-overdue") !== null;
            if (!overdue) return true;
            return row.querySelector(".day-board-next-window") !== null;
          });
        },
        { timeout: 10_000 },
      )
      .catch(() =>
        recordFailure(
          failures,
          "interaction/day-board",
          "a closed window states no next occurrence",
        ),
      );
    const basis = await board.locator(".day-board-clock .day-board-note").first().textContent();
    if (!basis || !/utc-clock-on-gas-day|UTC/i.test(basis)) {
      recordFailure(
        failures,
        "interaction/day-board",
        `the day board does not state the clock basis it assumed: ${basis}`,
      );
    }
  } catch (error) {
    recordFailure(failures, "interaction/day-board", error);
  }
}

/**
 * The glossary's own interaction: the left term index selects, the right wiki article follows.
 *
 * The scoped read-to-render check proves the index rendered the terms its read returned; it cannot
 * prove the index is a control, and this surface's recorded 2026-09-19 finding was only ever a
 * statement about page copy. The two-pane walkthrough at b566459
 * (`docs/ux/POST_CR15_UI_AUDIT.md`) was a visual review with no executable assertion that a
 * selection changes the article. This clicks a term the article is *not* showing and holds the
 * result to the record, never to the copy:
 *
 * - the article starts on a term the read returned, so the comparison below is not vacuous;
 * - after the click the article carries the clicked term's own `data-record-id`;
 * - the article's definition is the clicked term's definition from the same read;
 * - the index's own filter is exercised on the term it just selected: searching for the selected
 *   term's own name must keep that term in the index rather than hiding it.
 */
async function glossaryTermSelectionInteraction(page, failures) {
  const scope = "interaction/glossary-term-selection";
  try {
    await setLanguage(page, "en");
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto(`${BASE}/?workspace=glossary`, { waitUntil: "domcontentloaded" });
    const settled = await page
      .waitForFunction(
        () => [...document.querySelectorAll(".workspace-page")]
          .some((element) => element.dataset.workspaceLoadState === "settled"),
        null,
        { timeout: 20_000 },
      )
      .then(() => true)
      .catch(() => false);
    if (!settled) {
      throw new Error("the glossary workspace read never settled");
    }

    const readRows = await page.evaluate(async () => {
      const response = await fetch("/api/glossary?limit=5", { credentials: "include" });
      if (!response.ok) throw new Error(`the glossary read answered ${response.status}`);
      const body = await response.json();
      return (Array.isArray(body?.data) ? body.data : []).map((row) => ({
        id: typeof row?.term_id === "string" ? row.term_id.trim() : "",
        term: typeof row?.term === "string" ? row.term : "",
        definition: typeof row?.definition_en === "string" ? row.definition_en : "",
      }));
    });
    const terms = readRows.filter((row) => row.id !== "");
    if (terms.length < 2) {
      throw new Error(
        `the glossary read returned ${terms.length} identifiable term(s): a different term cannot`
        + " be selected",
      );
    }

    const article = page.locator('[data-record="glossary-article"]');
    await article.waitFor({ state: "visible", timeout: 10_000 });
    const initialId = (await article.getAttribute("data-record-id")) ?? "";
    if (!terms.some((row) => row.id === initialId)) {
      recordFailure(
        failures,
        scope,
        `the article opens on '${initialId || "(no term)"}', which the glossary read did not return`,
      );
    }

    const next = terms.find((row) => row.id !== initialId);
    if (!next) {
      // Only possible if the read returned the same id twice, which is the backend's defect, not
      // a page to click around.
      recordFailure(failures, scope, `every term the read returned carries '${initialId}'`);
      return;
    }
    const renderedIds = await page
      .locator('[data-record="glossary-term"]')
      .evaluateAll((cards) => cards.map((card) => card.getAttribute("data-record-id")));
    const cardIndex = renderedIds.indexOf(next.id);
    if (cardIndex === -1) {
      recordFailure(
        failures,
        scope,
        `the term index renders no row for '${next.id}', a term its own read returned`,
      );
      return;
    }
    await page.locator('[data-record="glossary-term"]').nth(cardIndex).click();

    const followed = await page
      .waitForFunction(
        (id) => document.querySelector('[data-record="glossary-article"]')
          ?.getAttribute("data-record-id") === id,
        next.id,
        { timeout: 10_000 },
      )
      .then(() => true)
      .catch(() => false);
    if (!followed) {
      const stayed = (await article.getAttribute("data-record-id")) || "(no term)";
      recordFailure(
        failures,
        scope,
        `selecting '${next.id}' left the wiki article on '${stayed}'`,
      );
      return;
    }

    const definition = ((await article.locator(".glossary-definition").first().textContent()) ?? "").trim();
    const expected = next.definition.trim();
    if (expected !== "" && definition !== expected) {
      recordFailure(
        failures,
        scope,
        `the wiki article shows '${next.id}' with copy its own read did not return:`
        + ` '${definition.slice(0, 120)}'`,
      );
    }

    if (next.term !== "") {
      // The index's filter is the surface's search. Searching for the selected term's own name is
      // the one query whose expected answer this read knows without reimplementing the filter: the
      // term must stay in the index, and the article must stay on it.
      await page.locator(".glossary-left-rail input").first().fill(next.term);
      const filteredIds = await page
        .locator('[data-record="glossary-term"]')
        .evaluateAll((cards) => cards.map((card) => card.getAttribute("data-record-id")));
      if (!filteredIds.includes(next.id)) {
        recordFailure(
          failures,
          scope,
          `filtering the term index by '${next.term}' hides the term its own read returned`,
        );
      } else if ((await article.getAttribute("data-record-id")) !== next.id) {
        recordFailure(
          failures,
          scope,
          `filtering the term index by '${next.term}' moved the article off the selected term`,
        );
      }
    }
  } catch (error) {
    recordFailure(failures, scope, error);
  }
}

export async function runWorkflowSmoke() {
  mkdirSync(OUTPUT_DIR, { recursive: true });
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
  });
  const page = await context.newPage();

  const failures = [];
  // Observations are not failures: a declared gap or a check that could not measure anything. They
  // are reported in the summary so a green run cannot hide them.
  const observations = [];
  const pageErrors = [];
  // Declared functional gaps: a surface whose read returns rows while the surface renders none.
  // Counted and printed in every summary, and a new one fails the run rather than joining a list
  // nobody reads.
  const functionalGaps = [];
  const consoleErrors = [];
  const results = [];
  let agentResearch = null;
  let currentScope = "startup";

  page.on("pageerror", (error) => {
    pageErrors.push({ scope: currentScope, detail: String(error) });
  });

  // A React internal error arrives as a console error rather than a pageerror, so a console
  // listener is the only way to see it. Anything outside the declared allowlist is a defect.
  page.on("console", (message) => {
    if (message.type() !== "error") return;
    const text = message.text();
    if (ALLOWED_CONSOLE_ERRORS.some((pattern) => pattern.test(text))) return;
    consoleErrors.push({ scope: currentScope, detail: text.slice(0, 300) });
  });

  try {
    await installReactErrorStackCapture(page);
    await ensureAuthenticated(page);

    for (const language of LANGUAGES) {
      await setLanguage(page, language.id);
      for (const viewport of VIEWPORTS) {
        for (const workspace of WORKSPACES) {
          currentScope = `${language.id}/${viewport.id}/${workspace}`;
          try {
            results.push(
              await inspectWorkspace(
                page,
                language,
                viewport,
                workspace,
                failures,
                observations,
                functionalGaps,
              ),
            );
          } catch (error) {
            recordFailure(failures, currentScope, error);
          }
        }
      }
    }

    currentScope = "interaction-checks";
    await interactionChecks(page, failures);

    // The glossary's selection behaviour is asserted as an interaction, not inferred from the
    // rendered rows: the index is a control and the article must follow the clicked record.
    currentScope = "interaction/glossary-term-selection";
    await glossaryTermSelectionInteraction(page, failures);

    currentScope = "interaction/agent-research-review";
    agentResearch = await agentResearchE2E(page, failures);
  } finally {
    await context.close();
    await browser.close();
  }

  for (const error of pageErrors) {
    recordFailure(failures, error.scope, `pageerror: ${error.detail}`);
  }
  for (const error of consoleErrors) {
    recordFailure(failures, error.scope, `console error: ${error.detail}`);
  }

  const summary = {
    ok: failures.length === 0,
    baseUrl: BASE,
    workspaces: WORKSPACES.length,
    languages: LANGUAGES.map((language) => language.id),
    viewports: VIEWPORTS,
    checks: results.length,
    agentResearch,
    // Declared gaps and skipped checks travel with the result: a green run that quietly measured
    // nothing is the failure mode this list exists to prevent.
    observations,
    // The functional state, measured rather than assumed: which declared gaps are still present,
    // and whether every surface rendered what its own API returned.
    functionalGaps,
    functionalGapCount: functionalGaps.length,
    results,
    failures,
  };
  writeFileSync(
    path.join(OUTPUT_DIR, "summary.json"),
    JSON.stringify(summary, null, 2),
    "utf8",
  );
  return summary;
}

const entryPath = process.argv[1] ? path.resolve(process.argv[1]) : "";
if (entryPath === fileURLToPath(import.meta.url)) {
  const result = await runWorkflowSmoke();
  console.log(JSON.stringify(result, null, 2));
  process.exit(result.ok ? 0 : 1);
}
