/**
 * Live read-only browser capture runner for the WF-1 captured-board comparator.
 *
 * `compareCapturedBoard.mjs` compares an operator-made capture offline. This runner is the bounded
 * next slice: it opens one real browser session against a deployment the caller names, navigates
 * the minimal existing market/curves route, and captures evidence from *that session's own* view:
 *
 * - the exact `GET /api/projections/market-context` response the browser consumed (recorded from
 *   the page's own response events, never re-issued by this tool - a second HTTP refetch would be
 *   a different read than the one the board rendered from, and no code path here issues one);
 * - the hub board the surface actually displayed (`collectQuotedBoard`, the browser sweep's own
 *   collector) including the as-of instant it states.
 *
 * The board's stated as-of must equal one recorded response's own `data.as_of_utc`; when the
 * surface's 10-second projection poll races the capture, the runner retries, bounded
 * (`CAPTURE_BOUNDS`), and refuses (`capture_race_unmatched`) rather than comparing a board with a
 * response it did not consume. The formed capture goes to the comparator's own
 * `compareCapturedBoard`, so one comparison rule serves both tools; stdout carries the
 * comparator's redacted summary only - status, counts and fixed reason codes, never a raw body,
 * URL, header, cookie, storage state, record id or screenshot. Nothing is written anywhere.
 *
 * The read-only guarantees, in the order they are enforced:
 * - the caller supplies a *preauthenticated* browser storage state FILE through the environment
 *   (`EUROGAS_UAT_STORAGE_STATE`); this runner has no login, seed, import, deployment, provider or
 *   mutation option, takes no credential on argv, and never prints the state it was given;
 * - the target base URL is explicit (`EUROGAS_UAT_BASE_URL`, no default): `https://` anywhere, or
 *   `http://` for a loopback host only, and never with credentials in the URL;
 * - before the first navigation every request in the context is classified: only `GET`/`HEAD` to
 *   the target origin is continued, everything else is aborted and recorded
 *   (`readonly_guard_blocked`, `external_request_blocked`), and service workers are blocked so no
 *   cached or synthetic response can stand in for the session's own read. Any refused request
 *   refuses the attempt, even when the board itself matched: a session the guard had to restrain
 *   is not the session the operator runs. Request routing does not see WebSocket channels, so
 *   every channel is guarded separately: it is closed before any server connection is made
 *   (`websocket_blocked`), and an installed Playwright without the WebSocket routing API fails
 *   closed (`websocket_guard_unavailable`) rather than running unguarded;
 * - the runner installs no init script and writes nothing to the application - app state is read
 *   exactly as the supplied session already has it. A deployment whose session cannot be
 *   represented as a Playwright storage state (e.g. a desktop shell session token held in memory,
 *   or an interactive sign-in this tool deliberately cannot perform) is unsupported: the run
 *   refuses (`board_not_displayed`) and the offline comparator remains for operator-made captures;
 * - the browser is closed in `finally`; every navigation, evaluation, response-body parse, wait
 *   and retry is bounded (`CAPTURE_BOUNDS`, optional `EUROGAS_UAT_CAPTURE_TIMEOUT_MS`); and a
 *   whole-run watchdog over the entire capture - launch, context, navigation, bodies, evaluation -
 *   closes the browser and refuses with the fixed `capture_timeout` code when its budget expires.
 *   A hanging body or evaluation cannot be cancelled through any supported API, and this runner
 *   does not claim to cancel one: the bounded waits stop *waiting* for it, the browser close ends
 *   the session, and the abandoned operation's late settlement is observed so it cannot surface
 *   as an unhandled rejection or a raw error.
 *
 * What a live `pass` is not: capture authenticity (the storage state and the `source` labels are
 * operator-supplied and unattested), customer acceptance, the operator's *intended* context
 * selection, other hubs or tenors, non-price slices, pagination beyond the captured slice, or the
 * portfolio workflow. The comparator's own `unverified` list travels with the summary; only its
 * offline qualifier `live_capture_automation` is dropped, because this run *is* the live
 * automation.
 *
 * Usage: node scripts/uat/captureLiveBoard.mjs   (no arguments; see `--help`)
 * Exit codes: 0 = pass, 1 = refused, 2 = invalid (invocation, environment or unusable capture).
 */

import { statSync } from "node:fs";
import { createRequire } from "node:module";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";

import {
  CAPTURE_SCHEMA_VERSION,
  captureAttemptSummary,
  compareCapturedBoard,
  instantMs,
} from "./compareCapturedBoard.mjs";
import { collectQuotedBoard } from "./readToRender.mjs";

/** The projection the market cockpit's hub board prices from; the read this runner captures. */
const MARKET_CONTEXT_PATH = "/api/projections/market-context";

/**
 * The minimal existing route that mounts the numeric market task and its hub board: the shell
 * reads `?workspace=` (`clients/web/src/app/hooks/useWorkspaceNavigation.ts`) and the market
 * cockpit mounts `MarketTerminal` - the `[data-market-board="hub-prices"]` board - for
 * `?task=curves`, the declared numeric landing task
 * (`clients/web/src/components/MarketCockpit.tsx`, `app/model/marketCockpitModel.ts`).
 */
const MARKET_ROUTE = "/?workspace=market&task=curves";

/** The hosts a plain-HTTP target may name: the only non-TLS targets this runner will open. */
const LOOPBACK_HOSTNAMES = ["127.0.0.1", "localhost", "::1"];

/** The caller's whole configuration; no credential value ever travels on argv. */
const ENV = {
  baseUrl: "EUROGAS_UAT_BASE_URL",
  storageState: "EUROGAS_UAT_STORAGE_STATE",
  commit: "EUROGAS_UAT_CAPTURE_COMMIT",
  deployment: "EUROGAS_UAT_CAPTURE_DEPLOYMENT",
  playwright: "EUROGAS_UAT_PLAYWRIGHT_PATH",
  timeoutMs: "EUROGAS_UAT_CAPTURE_TIMEOUT_MS",
};

/**
 * Every bounded wait of one capture. Each is a ceiling: the runner refuses rather than extending
 * one, and an operator may only shrink the whole-capture budget through the environment.
 */
export const CAPTURE_BOUNDS = Object.freeze({
  attempts: 3,
  boardPollMs: 500,
  settleTimeoutMs: 20_000,
  refreshWaitMs: 12_000,
  navigationTimeoutMs: 30_000,
  launchTimeoutMs: 60_000,
  operationTimeoutMs: 20_000,
  timeoutMs: 120_000,
  maxRecordedResponses: 40,
  viewport: Object.freeze({ width: 1440, height: 900 }),
});

/** One `--help` line: the variable name, then its meaning, aligned for the terminal. */
function usageLine(name, description) {
  return `  ${name.padEnd(32)}${description}`;
}

const USAGE = [
  "usage: node scripts/uat/captureLiveBoard.mjs",
  "",
  "Read-only live capture of the market cockpit's hub board and the exact",
  "GET /api/projections/market-context response the browser consumed, compared through",
  "the captured-board comparator. Takes no arguments; the caller configures it with:",
  usageLine(ENV.baseUrl, "explicit target (required; https, or http on loopback)"),
  usageLine(ENV.storageState, "preauthenticated Playwright storage state file (required)"),
  usageLine(ENV.commit, "operator-supplied commit label (required; unattested)"),
  usageLine(ENV.deployment, "operator-supplied deployment label (required; unattested)"),
  usageLine(ENV.timeoutMs, "whole-capture budget in ms (optional; 1000..600000)"),
  usageLine(ENV.playwright, "Playwright module path (optional; defaults to 'playwright')"),
  "Prints one redacted JSON summary to stdout. Exit codes: 0 = pass, 1 = refused,",
  "2 = invalid. There is no login, seed, import, deployment, provider or mutation option:",
  "a missing or unsupported preauthentication stays a refusal, and the offline comparator",
  "remains for operator-made captures.",
].join("\n");

function isPlainObject(value) {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function parseUrl(value) {
  try {
    return new URL(String(value));
  } catch {
    return null;
  }
}

function isReadableFile(candidate) {
  try {
    return statSync(candidate).isFile();
  } catch {
    return false;
  }
}

/**
 * Validate the explicit target. Only `https:` anywhere, or `http:` on a loopback host, without
 * credentials, query or fragment; a path is allowed for subpath deployments.
 */
export function validateBaseUrl(raw) {
  if (typeof raw !== "string" || raw.trim() === "") return { ok: false, code: "base_url_missing" };
  const parsed = parseUrl(raw.trim());
  if (!parsed) return { ok: false, code: "base_url_not_allowed" };
  if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
    return { ok: false, code: "base_url_not_allowed" };
  }
  if (parsed.username !== "" || parsed.password !== "") {
    return { ok: false, code: "base_url_not_allowed" };
  }
  if (parsed.search !== "" || parsed.hash !== "") {
    return { ok: false, code: "base_url_not_allowed" };
  }
  const host = parsed.hostname.replace(/^\[|\]$/g, "").toLowerCase();
  if (parsed.protocol === "http:" && !LOOPBACK_HOSTNAMES.includes(host)) {
    return { ok: false, code: "base_url_not_allowed" };
  }
  const path = parsed.pathname.replace(/\/+$/, "");
  return { ok: true, origin: parsed.origin, base: `${parsed.origin}${path}` };
}

/**
 * The read-only request policy one intercepted request is decided by: `GET`/`HEAD` to the target
 * origin continues, every other method or target is blocked with the code the summary reports.
 */
export function classifyRequest({ method, url, origin }) {
  const upper = String(method ?? "").toUpperCase();
  if (upper !== "GET" && upper !== "HEAD") {
    return { action: "block", code: "readonly_guard_blocked" };
  }
  const parsed = parseUrl(url);
  if (!parsed) return { action: "block", code: "external_request_blocked" };
  if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
    return { action: "block", code: "external_request_blocked" };
  }
  if (parsed.origin !== origin) return { action: "block", code: "external_request_blocked" };
  return { action: "allow" };
}

/** Whether the collected board states the reading the comparison needs (as-of and tenor). */
export function boardIsSettled(board) {
  return isPlainObject(board)
    && typeof board.asOf === "string"
    && board.asOf.trim() !== ""
    && typeof board.boardTenor === "string"
    && board.boardTenor.trim() !== "";
}

/**
 * Whether one recorded response is usable evidence for the board comparison: a 200 whose payload
 * is the market-context projection, whose single as-of instant parses, and whose echoed Active
 * Context matches the query the browser itself sent (present parameters only - an absent
 * dimension is the client deliberately omitting it, not a mismatch).
 */
export function usableConsumedResponse(entry) {
  if (!entry || entry.status !== 200 || !isPlainObject(entry.body)) return false;
  const data = entry.body.data;
  if (!isPlainObject(data) || data.projection !== "market-context") return false;
  if (instantMs(data.as_of_utc) === null) return false;
  const active = data.active_context;
  if (!isPlainObject(active)) return false;
  const query = isPlainObject(entry.query) ? entry.query : {};
  if (typeof query.gas_day !== "string" || query.gas_day.trim() === "") return false;
  const echoed = (value) => (
    value === null || value === undefined ? null : String(value).trim()
  );
  if (query.gas_day.trim() !== echoed(active.gas_day)) return false;
  if (query.delivery_product !== undefined) {
    if (query.delivery_product !== echoed(active.delivery_product)) return false;
  }
  if (query.hub !== undefined && query.hub !== echoed(active.hub)) return false;
  return true;
}

/**
 * The newest recorded response whose own `data.as_of_utc` is the instant the board states, or
 * `null` when no recorded response is that read. The as-of rule is `instantMs`, the comparator's
 * own.
 */
export function selectConsumedResponse(recorded, boardAsOf) {
  const wanted = instantMs(boardAsOf);
  if (wanted === null) return null;
  for (let index = recorded.length - 1; index >= 0; index -= 1) {
    const entry = recorded[index];
    if (!entry.usable) continue;
    if (instantMs(entry.body?.data?.as_of_utc) === wanted) return entry;
  }
  return null;
}

/** Why a bounded capture attempt could not match a board to a response it consumed. */
export function classifyCaptureFailure(recorded) {
  if (recorded.length === 0) return "no_consumed_response";
  const answered = recorded.filter((entry) => entry.status === 200);
  if (answered.length === 0) return "projection_status_not_200";
  if (!answered.some((entry) => entry.usable)) return "consumed_response_unusable";
  return "capture_race_unmatched";
}

/**
 * The comparator's capture object, formed from the session's own evidence only: the hub scope is
 * the set of hubs the displayed cards declare (never a hardcoded hub list), the projection is the
 * recorded response verbatim, and the board is `collectQuotedBoard`'s own evidence.
 */
export function buildCapture({ source, board, response }) {
  const hubScope = [];
  for (const cell of Array.isArray(board?.cells) ? board.cells : []) {
    const hub = typeof cell?.hub === "string" ? cell.hub.trim().toUpperCase() : "";
    if (hub !== "" && !hubScope.includes(hub)) hubScope.push(hub);
  }
  return {
    schema_version: CAPTURE_SCHEMA_VERSION,
    source: { commit: source.commit, deployment: source.deployment },
    hub_scope: hubScope,
    projection: { status: response.status, body: response.body },
    board: {
      boardTenor: board.boardTenor,
      activeTenorTab: board.activeTenorTab,
      asOf: board.asOf,
      asOfText: board.asOfText,
      cells: board.cells,
    },
  };
}

function readTimeout(raw) {
  if (raw === undefined || String(raw).trim() === "") return CAPTURE_BOUNDS.timeoutMs;
  const value = Number(String(raw).trim());
  if (!Number.isInteger(value) || value < 1_000 || value > 600_000) return null;
  return value;
}

function label(raw) {
  return typeof raw === "string" ? raw.trim() : "";
}

/**
 * Read and validate the invocation environment. Returns the run config, or the refusal codes for
 * a missing/unsafe target, an absent or unreadable storage state, absent operator labels or an
 * out-of-range timeout. The storage state is only checked for readability here; its content is
 * never read, parsed or printed by the runner.
 */
export function readConfig(env) {
  const codes = new Map();
  const base = validateBaseUrl(env[ENV.baseUrl]);
  if (!base.ok) codes.set(base.code, 1);

  const storageStatePath = label(env[ENV.storageState]);
  if (storageStatePath === "") codes.set("storage_state_missing", 1);
  else if (!isReadableFile(storageStatePath)) codes.set("storage_state_unreadable", 1);

  const commit = label(env[ENV.commit]);
  const deployment = label(env[ENV.deployment]);
  if (commit === "" || deployment === "") codes.set("source_label_missing", 1);

  const timeoutMs = readTimeout(env[ENV.timeoutMs]);
  if (timeoutMs === null) codes.set("invocation_invalid", 1);

  if (codes.size > 0) return { ok: false, codes };
  return {
    ok: true,
    config: {
      ...CAPTURE_BOUNDS,
      viewport: { ...CAPTURE_BOUNDS.viewport },
      origin: base.origin,
      base: base.base,
      storageStatePath,
      source: { commit, deployment },
      timeoutMs,
    },
  };
}

/** The default wait: real time, so the shipped runner's bounds are wall-clock bounds. */
function defaultSleep(ms) {
  return new Promise((resolvePromise) => {
    setTimeout(resolvePromise, ms);
  });
}

/**
 * The value a bounded wait yields when its operation did not answer in time. There is no supported
 * way to cancel a response-body read or a `page.evaluate` that has not answered, so this means
 * "not completed within the bound", never "stopped" - only the browser close can end the
 * operation, and callers must not report a cancellation this helper does not perform.
 */
const TIMED_OUT = Symbol("capture-operation-timed-out");

/**
 * Await `promise` for at most `timeoutMs` real milliseconds, yielding `TIMED_OUT` when the bound
 * expires first. The losing operation keeps running; its late settlement is observed by the race
 * (including a rejection), so it can neither hang the caller nor surface as an unhandled
 * rejection. The bound's own timer is unref'ed: the whole-run watchdog is what keeps the process
 * alive to the capture's deadline, never a wait for an operation the run has moved past.
 */
function boundedWait(promise, timeoutMs) {
  let timer = null;
  const expired = new Promise((resolveExpired) => {
    timer = setTimeout(() => resolveExpired(TIMED_OUT), timeoutMs);
    if (typeof timer.unref === "function") timer.unref();
  });
  return Promise.race([promise, expired]).finally(() => clearTimeout(timer));
}

/** Settle every outstanding body-parse promise, bounded; `false` when the bound expired first. */
async function flushRecorded(pending, timeoutMs) {
  if (pending.length === 0) return true;
  const outstanding = pending.splice(0, pending.length);
  const settled = await boundedWait(Promise.all(outstanding), timeoutMs);
  return settled !== TIMED_OUT;
}

/**
 * Poll the displayed page, bounded by one settle window, until the board states a reading. A
 * page that never renders a board is `board_not_displayed`; a board that never states its as-of or
 * tenor is `board_not_settled` - neither is guessed into a comparison.
 */
async function awaitSettledBoard({ page, config, now, sleep, deadline }) {
  const settleUntil = Math.min(now() + config.settleTimeoutMs, deadline);
  let sawBoard = false;
  for (;;) {
    let board = null;
    try {
      // `page.evaluate` has no timeout of its own and is not bounded by `page.setDefaultTimeout`,
      // so each sample is awaited under this runner's own operation bound; an evaluation that
      // does not answer ends the polling (and the capture) instead of hanging it.
      const sample = await boundedWait(
        Promise.resolve().then(() => page.evaluate(collectQuotedBoard)),
        config.operationTimeoutMs,
      );
      if (sample === TIMED_OUT) return { board: null, sawBoard, timedOut: true };
      board = sample;
    } catch {
      // A transient evaluation failure (navigation, a closing context) is a sample that measured
      // nothing, not a verdict about the surface.
      board = null;
    }
    if (boardIsSettled(board)) return { board, sawBoard: true, timedOut: false };
    if (board) sawBoard = true;
    if (now() + config.boardPollMs > settleUntil) break;
    await sleep(config.boardPollMs);
  }
  return { board: null, sawBoard, timedOut: false };
}

/**
 * Wait for a settled board and for a recorded response whose own as-of is that board's instant.
 * When they do not line up - the surface's projection poll may hold an older reading than the
 * response it just consumed, or the reverse - wait one refresh interval and look again, bounded
 * by the attempts and the whole-capture budget. The runner never issues the read itself, so a
 * failure here is a refusal (`capture_race_unmatched` and friends), never a relabelled refetch.
 */
async function awaitConsumedCapture({ page, recorded, pending, config, now, sleep }) {
  const deadline = now() + config.timeoutMs;
  let sawBoard = false;
  let settledBoard = null;
  for (let attempt = 0; attempt < config.attempts && now() < deadline; attempt += 1) {
    const settled = await awaitSettledBoard({ page, config, now, sleep, deadline });
    sawBoard = sawBoard || settled.sawBoard;
    if (settled.timedOut) return { outcome: "capture_timeout" };
    if (settled.board === null) break;
    settledBoard = settled.board;
    // The response event fires before its body is parsed; wait for the parse so "no recorded
    // response for this instant" cannot be read from a promise that has not settled yet. A body
    // that never parses cannot be waited out, so the wait is bounded and the attempt refuses
    // rather than letting a hanging body consume the capture.
    if (!(await flushRecorded(pending, config.operationTimeoutMs))) {
      return { outcome: "capture_timeout" };
    }
    const response = selectConsumedResponse(recorded, settled.board.asOf);
    if (response) return { outcome: "captured", board: settled.board, response };
    if (now() + config.refreshWaitMs > deadline) break;
    await sleep(config.refreshWaitMs);
  }
  if (settledBoard === null) return { outcome: sawBoard ? "board_not_settled" : "board_not_displayed" };
  return { outcome: classifyCaptureFailure(recorded) };
}

/**
 * Open one read-only browser session, capture the board and the response it consumed, and compare
 * through the comparator. Returns `{ summary, exitCode }`; nothing is written anywhere.
 *
 * `now`/`sleep` are injectable so the bounded retry, deadline and cleanup paths are exercised
 * deterministically without a browser; the shipped entrypoint uses real time.
 */
export async function runLiveCapture({ config, playwright, now = Date.now, sleep = defaultSleep }) {
  const blocked = new Map();
  const refused = (codes) => {
    const reasons = new Map(codes);
    for (const [code, count] of blocked) reasons.set(code, (reasons.get(code) ?? 0) + count);
    return { summary: captureAttemptSummary("refused", reasons), exitCode: 1 };
  };
  const invalid = (code) => ({
    summary: captureAttemptSummary("invalid", new Map([[code, 1]])),
    exitCode: 2,
  });

  if (!playwright || typeof playwright.chromium?.launch !== "function") {
    return invalid("playwright_unavailable");
  }

  let browser = null;
  let closed = false;
  let timedOut = false;

  // One close, ever: the verdict already stands and a close failure must not replace it with a
  // stack trace. Idempotent, so the deadline path and the flow's own exit can both ask.
  const closeBrowser = async () => {
    if (closed || browser === null) return;
    closed = true;
    await Promise.resolve()
      .then(() => browser.close())
      .catch(() => {});
  };

  // After an awaited step, a run the watchdog has already ended stops here. The close is retried
  // because a launch or context that completes after the deadline would otherwise leave a session
  // this run no longer owns.
  const stopIfExpired = async () => {
    if (!timedOut) return false;
    await closeBrowser();
    return true;
  };

  // The whole-run watchdog is the capture's real bound: one wall-clock budget over launch, context
  // creation, navigation, response bodies, evaluation and the retry loops. When it expires the run
  // stops waiting for the session and closes the browser - there is no supported cancellation for
  // a hung body parse or evaluation, and this runner does not pretend there is - then refuses with
  // the fixed `capture_timeout` code. The abandoned flow's later outcome is discarded and its
  // rejections stay observed by the race, so nothing about it can surface as an unhandled
  // rejection or a raw error.
  let watchdogTimer = null;
  const watchdogOutcome = Symbol("capture-timeout");
  const watchdog = new Promise((resolveWatchdog) => {
    watchdogTimer = setTimeout(() => {
      timedOut = true;
      resolveWatchdog(watchdogOutcome);
    }, config.timeoutMs);
  });

  const flow = (async () => {
    try {
      try {
        browser = await playwright.chromium.launch({
          headless: true,
          timeout: config.launchTimeoutMs,
        });
      } catch {
        return invalid("capture_launch_failed");
      }
      if (await stopIfExpired()) return invalid("capture_timeout");

      let context = null;
      try {
        context = await browser.newContext({
          storageState: config.storageStatePath,
          serviceWorkers: "block",
          viewport: { ...config.viewport },
        });
      } catch {
        return invalid("storage_state_unreadable");
      }
      if (await stopIfExpired()) return invalid("capture_timeout");

      const page = await context.newPage();
      page.setDefaultTimeout(config.operationTimeoutMs);
      page.setDefaultNavigationTimeout(config.navigationTimeoutMs);

      // Recorded before navigation: the response the board is rendered from must be observed in the
      // session itself, never re-issued by this tool.
      const recorded = [];
      const pending = [];
      page.on("response", (response) => {
        try {
          const parsed = parseUrl(response.request().url());
          if (!parsed || parsed.origin !== config.origin) return;
          if (!parsed.pathname.replace(/\/+$/, "").endsWith(MARKET_CONTEXT_PATH)) return;
          const entry = {
            status: response.status(),
            body: null,
            usable: false,
            query: Object.fromEntries(parsed.searchParams.entries()),
          };
          recorded.push(entry);
          if (recorded.length > config.maxRecordedResponses) recorded.shift();
          pending.push(
            response
              .json()
              .then((body) => {
                entry.body = isPlainObject(body) ? body : null;
                entry.usable = usableConsumedResponse(entry);
              })
              .catch(() => {}),
          );
        } catch {
          // An observation this runner could not record is not a reason to fail the page.
        }
      });

      // The read-only guard is installed before the first navigation, so nothing the page does can
      // reach the deployment except a same-origin GET/HEAD.
      await context.route("**/*", (route) => {
        const request = route.request();
        const decision = classifyRequest({
          method: request.method(),
          url: request.url(),
          origin: config.origin,
        });
        if (decision.action === "allow") return route.continue();
        blocked.set(decision.code, (blocked.get(decision.code) ?? 0) + 1);
        return route.abort("blockedbyclient");
      });

      // Request routing does not see WebSocket channels, so the channel guard is Playwright's own
      // WebSocket routing (`browserContext.routeWebSocket`, available since 1.48; CI pins 1.55.0
      // and the local suite probes the installed dependency). Every channel is closed before any
      // server connection is made and recorded as blocked; a dependency without this API fails
      // closed here, before the first navigation, rather than running the session unguarded.
      if (typeof context.routeWebSocket !== "function") {
        return invalid("websocket_guard_unavailable");
      }
      await context.routeWebSocket("**/*", (webSocket) => {
        blocked.set("websocket_blocked", (blocked.get("websocket_blocked") ?? 0) + 1);
        try {
          return webSocket.close();
        } catch {
          return undefined;
        }
      });

      if (await stopIfExpired()) return invalid("capture_timeout");
      try {
        await page.goto(`${config.base}${MARKET_ROUTE}`, {
          waitUntil: "domcontentloaded",
          timeout: config.navigationTimeoutMs,
        });
      } catch {
        return refused([["navigation_failed", 1]]);
      }
      if (await stopIfExpired()) return invalid("capture_timeout");

      const captured = await awaitConsumedCapture({ page, recorded, pending, config, now, sleep });
      if (await stopIfExpired()) return invalid("capture_timeout");
      if (captured.outcome !== "captured") {
        return refused([[captured.outcome, 1]]);
      }
      if (blocked.size > 0) {
        // The board matched, but a request the session would have made was refused: the capture is
        // not a faithful observation of the operator's own session and cannot pass.
        return refused([]);
      }

      const capture = buildCapture({
        source: config.source,
        board: captured.board,
        response: captured.response,
      });
      let summary;
      try {
        summary = compareCapturedBoard(capture);
      } catch {
        return invalid("capture_error");
      }
      // The comparison ran on a capture this runner formed from the live session, so the offline
      // qualifier does not apply; every other statement the comparator leaves unverified stands.
      summary = {
        ...summary,
        unverified: summary.unverified.filter(
          (statement) => statement !== "live_capture_automation",
        ),
      };
      return {
        summary,
        exitCode: summary.verdict === "pass" ? 0 : summary.verdict === "refused" ? 1 : 2,
      };
    } catch {
      // An unexpected failure (a Playwright error can quote the URL it was driving) never prints
      // its own message: the summary reports the fixed code and nothing else.
      return invalid("capture_error");
    }
  })();

  let outcome = null;
  try {
    outcome = await Promise.race([flow, watchdog]);
  } finally {
    clearTimeout(watchdogTimer);
    await closeBrowser();
  }
  if (outcome === watchdogOutcome) return refused([["capture_timeout", 1]]);
  return outcome;
}

function loadPlaywright() {
  // The browser sweep's own dependency convention: the CI job installs an exact Playwright
  // outside the repository and passes its path through `EUROGAS_UAT_PLAYWRIGHT_PATH`. The module
  // is required lazily so importing this runner (tests, docs tooling) does not need the browser
  // dependency installed.
  const require = createRequire(import.meta.url);
  return require(process.env[ENV.playwright] || "playwright");
}

function writeSummary(summary) {
  process.stdout.write(`${JSON.stringify(summary, null, 2)}\n`);
}

export async function main(argv = process.argv) {
  const args = Array.isArray(argv) ? argv.slice(2) : [];
  if (args.length === 1 && (args[0] === "--help" || args[0] === "-h")) {
    process.stdout.write(`${USAGE}\n`);
    return 0;
  }
  if (args.length !== 0) {
    // A credential or capture path passed on argv is refused unread: this runner takes no
    // positional argument.
    process.stderr.write(`${USAGE}\n`);
    writeSummary(captureAttemptSummary("invalid", new Map([["invocation_invalid", 1]])));
    return 2;
  }

  const parsed = readConfig(process.env);
  if (!parsed.ok) {
    writeSummary(captureAttemptSummary("invalid", parsed.codes));
    return 2;
  }

  let playwright;
  try {
    playwright = loadPlaywright();
  } catch {
    writeSummary(captureAttemptSummary("invalid", new Map([["playwright_unavailable", 1]])));
    return 2;
  }

  const outcome = await runLiveCapture({ config: parsed.config, playwright });
  writeSummary(outcome.summary);
  return outcome.exitCode;
}

const invokedDirectly = Boolean(process.argv[1])
  && pathToFileURL(resolve(process.argv[1])).href === import.meta.url;
if (invokedDirectly) {
  main(process.argv)
    .then((code) => {
      process.exitCode = code;
    })
    .catch(() => {
      // The summary never echoes payload detail, not even for an internal failure.
      writeSummary(captureAttemptSummary("invalid", new Map([["capture_error", 1]])));
      process.exitCode = 2;
    });
}
