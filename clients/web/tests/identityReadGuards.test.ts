import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

function readWebSource(relativePath: string): string {
  return readFileSync(new URL(`../src/${relativePath}`, import.meta.url), "utf8");
}

const store = readWebSource("stores/api.ts");

/**
 * The four user-triggered follow-up reads the register names under
 * RELIABILITY-READ-001. Each one asks the backend a question on behalf of one
 * identity, so its answer may only be written back while that identity is still
 * the current one.
 */
const FOLLOW_UP_READS = [
  "fetchGlossaryContext",
  "askAnalysis",
  "generatePortfolioReport",
  "analyzeMonitoringAlert",
] as const;

/** One store action body, from its declaration to its closing `},`. */
function actionBody(name: string): string {
  const start = store.indexOf(`  ${name}: async `);
  assert.ok(start >= 0, `${name} is missing from the store`);
  const end = store.indexOf("\n  },\n", start);
  assert.ok(end > start, `${name} has no closing brace`);
  return store.slice(start, end);
}

test("a follow-up read answer is only written back for the identity that asked", () => {
  for (const name of FOLLOW_UP_READS) {
    const body = actionBody(name);
    const label = `${name} must guard its follow-up read`;

    // A read started while signing out never leaves the client.
    assert.ok(
      body.indexOf("if (logoutInProgress) return;") > -1 &&
        body.indexOf("if (logoutInProgress) return;") < body.indexOf("set("),
      `${label}: expected a logout guard before any state write`,
    );

    assert.equal(
      body.match(/identityReadCoordinator\.capture\(\)/g)?.length,
      1,
      `${label}: expected exactly one captured generation`,
    );

    const awaited = body.indexOf("await ");
    assert.ok(awaited > -1, `${label}: the action should await its read`);

    // Every state write after the read must sit behind a currency check, on both
    // the success and the failure path - a late rejection is just as capable of
    // writing a stale error into a signed-out shell as a late success is.
    const afterRead = body.slice(awaited);
    const segments = afterRead.split(/await /).slice(1);
    assert.ok(segments.length >= 1, `${label}: expected a post-read segment`);
    segments.forEach((segment, index) => {
      const firstWrite = segment.indexOf("set(");
      if (firstWrite === -1) return;
      assert.ok(
        segment.slice(0, firstWrite).includes("followUpReadIsCurrent(requestGeneration)"),
        `${label}: state write ${index + 1} is unguarded`,
      );
    });

    assert.equal(
      body.match(/followUpReadIsCurrent\(requestGeneration\)/g)?.length,
      2,
      `${label}: expected a guard on both the success and the failure path`,
    );
  }
});

test("currency means both an open session and an unchanged identity generation", () => {
  assert.match(
    store,
    /function followUpReadIsCurrent\(generation: number\): boolean \{\n {2}return !logoutInProgress && identityReadCoordinator\.isCurrent\(generation\);\n\}/,
  );
  // Dropping a stale answer must not strand the loading flag: every path that
  // invalidates the generation also resets the identity-scoped slices, and that
  // reset clears `loading` and `error` (workspaceLoading.resetIdentityScopedCaches).
  const invalidations = [...store.matchAll(/invalidateIdentitySession\(\);/g)];
  assert.equal(invalidations.length, 7);
  for (const invalidation of invalidations) {
    const after = store.slice(invalidation.index ?? 0, (invalidation.index ?? 0) + 400);
    assert.ok(
      after.includes("...resetIdentityScopedCaches(") || after.includes("...identityReset"),
      "an identity invalidation must be followed by an identity-scoped reset",
    );
  }
});

test("the invalidated generation is the one the follow-up reads captured", () => {
  const invalidation = (/function invalidateIdentitySession\(\) \{\n([\s\S]*?)\n\}/.exec(store)?.[1] ?? "");
  assert.match(invalidation, /identityReadCoordinator\.invalidate\(\);/);
});
