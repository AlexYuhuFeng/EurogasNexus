import assert from "node:assert/strict";
import test from "node:test";
import {
  commitWorkspaceLoad,
  IdentityReadCoordinator,
  identityDeniedWorkspaceReset,
  isIdentityDeniedMessage,
  loadWorkspaceEndpoint,
  loadWorkspaceEndpoints,
  ReadRefreshLane,
  ReadRefreshCoordinator,
  resetIdentityScopedCaches,
  withAbortTimeout,
  workspaceLoadHasIdentityDenial,
  WorkspaceLoadCoordinator,
} from "../src/stores/workspaceLoading.ts";

test("a hanging optional endpoint times out while successful slices remain available", async () => {
  let aborted = false;
  const outcomes = await loadWorkspaceEndpoints<unknown>(
    [
      ["runtimeDb", async () => ({ database_url_present: true })],
      [
        "referenceNodes",
        ({ signal }) => new Promise((_, reject) => {
          signal?.addEventListener("abort", () => {
            aborted = true;
            reject(new DOMException("aborted", "AbortError"));
          }, { once: true });
        }),
      ],
    ],
    { retries: 0, timeoutMs: 10 },
  );

  assert.equal(outcomes[0].outcome.ok, true);
  assert.equal(outcomes[1].outcome.ok, false);
  if (!outcomes[1].outcome.ok) assert.equal(outcomes[1].outcome.error.code, "timeout");
  assert.equal(aborted, true);
});

test("a replaced workspace generation cannot become current again", () => {
  const coordinator = new WorkspaceLoadCoordinator();
  const first = coordinator.start();
  const second = coordinator.start();

  assert.equal(first.signal.aborted, true);
  assert.equal(coordinator.isCurrent(first.generation, first.signal), false);
  assert.equal(coordinator.isCurrent(second.generation, second.signal), true);
});

test("a new workspace generation aborts both periodic read lanes", () => {
  const coordinator = new ReadRefreshCoordinator();
  const market = coordinator.market.tryStart();
  const monitoring = coordinator.monitoring.tryStart();
  const previousGeneration = coordinator.currentGeneration();

  coordinator.beginWorkspaceLoad();

  assert.equal(market?.signal.aborted, true);
  assert.equal(monitoring?.signal.aborted, true);
  assert.equal(coordinator.isCurrent(previousGeneration), false);
});

test("an invalidated identity generation cannot commit an old response", () => {
  const coordinator = new IdentityReadCoordinator();
  const oldGeneration = coordinator.capture();
  coordinator.invalidate();

  let committed = false;
  if (coordinator.isCurrent(oldGeneration)) committed = true;
  assert.equal(committed, false);
});

test("only explicit identity denial responses invalidate startup reads", () => {
  assert.equal(isIdentityDeniedMessage("API 401: session expired"), true);
  assert.equal(isIdentityDeniedMessage("API 403: forbidden"), true);
  assert.equal(isIdentityDeniedMessage("TypeError: Failed to fetch"), false);
  assert.equal(isIdentityDeniedMessage("Workspace endpoint timed out after 10ms."), false);
  assert.equal(workspaceLoadHasIdentityDenial([
    { key: "referenceNodes", outcome: { ok: true, value: "retained" } },
    { key: "me", outcome: { ok: false, error: { code: "request", message: "API 401: session expired" } } },
  ]), true);
  assert.equal(workspaceLoadHasIdentityDenial([
    { key: "referenceNodes", outcome: { ok: true, value: "retained" } },
    { key: "me", outcome: { ok: false, error: { code: "timeout", message: "Workspace endpoint timed out after 10ms." } } },
  ]), false);
});

test("retry transition fails closed before applying successful slices after /me denial", () => {
  const reset = identityDeniedWorkspaceReset([
    { key: "resourcePoolOptions", outcome: { ok: true, value: "restricted result" } },
    { key: "me", outcome: { ok: false, error: { code: "request", message: "API 403: forbidden" } } },
  ], { open_count: 0 });

  assert.ok(reset);
  assert.deepEqual(reset.resourcePoolOptions, null);
  assert.equal(reset.currentUser, null);
  assert.equal(reset.loading, false);
  assert.equal(reset.dataStatus, "unavailable");
});

test("logout timeout aborts its request and returns control", async () => {
  let aborted = false;
  await assert.rejects(
    withAbortTimeout(
      (signal) => new Promise((_, reject) => {
        signal.addEventListener("abort", () => {
          aborted = true;
          reject(new DOMException("aborted", "AbortError"));
        }, { once: true });
      }),
      10,
    ),
    /timed out after 10ms/,
  );
  assert.equal(aborted, true);
});

test("identity reset clears rendered data and returns to unavailable loading state", () => {
  const reset = resetIdentityScopedCaches({ open_count: 0 });

  assert.deepEqual(reset.sources, []);
  assert.deepEqual(reset.normalizedMarkets, []);
  assert.deepEqual(reset.marketSpreads, []);
  assert.deepEqual(reset.marketQuotes, []);
  assert.deepEqual(reset.intradayOpportunities, []);
  assert.deepEqual(reset.fxRates, []);
  assert.equal(reset.currentUser, null);
  assert.equal(reset.loading, false);
  assert.equal(reset.dataStatus, "unavailable");
});

test("workspace commit clears loading and retains successful runtime and identity slices", () => {
  const commit = commitWorkspaceLoad([
    { key: "runtimeDb", outcome: { ok: true, value: { database_url_present: true } } },
    { key: "me", outcome: { ok: true, value: { principal_id: "operator-1" } } },
    {
      key: "referenceNodes",
      outcome: {
        ok: false,
        error: { code: "timeout", message: "Workspace endpoint timed out after 10ms." },
      },
    },
  ]);

  assert.equal(commit.loading, false);
  assert.equal(commit.error, null);
  assert.deepEqual(commit.slices.runtimeDb, { database_url_present: true });
  assert.deepEqual(commit.slices.me, { principal_id: "operator-1" });
  assert.equal(commit.endpointErrorCodes.referenceNodes, "timeout");
});

test("a pending refresh lane coalesces callers and releases after timeout", async () => {
  const lane = new ReadRefreshLane();
  let requests = 0;
  const run = async () => {
    const lease = lane.tryStart();
    if (!lease) return undefined;
    try {
      requests += 1;
      return await loadWorkspaceEndpoint(
        ({ signal }) => new Promise((_, reject) => {
          signal?.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError")), { once: true });
        }),
        { signal: lease.signal, retries: 0, timeoutMs: 10 },
      );
    } finally {
      lease.release();
    }
  };

  const first = run();
  assert.equal(await run(), undefined);
  const firstOutcome = await first;
  assert.equal(firstOutcome?.ok, false);
  if (firstOutcome && !firstOutcome.ok) assert.equal(firstOutcome.error.code, "timeout");
  const nextOutcome = await run();
  assert.equal(nextOutcome?.ok, false);
  assert.equal(requests, 2);
});

test("normal endpoint success and one retry remain supported", async () => {
  let attempts = 0;
  const outcome = await loadWorkspaceEndpoint(
    async () => {
      attempts += 1;
      if (attempts === 1) throw new Error("transient");
      return "ok";
    },
    { retries: 1, timeoutMs: 100 },
  );

  assert.deepEqual(outcome, { ok: true, value: "ok" });
  assert.equal(attempts, 2);
});
