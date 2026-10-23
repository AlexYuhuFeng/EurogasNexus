import assert from "node:assert/strict";
import test from "node:test";
import type { StrategyVersionDTO } from "../src/api/client.ts";
import { DEFAULT_STRATEGY_FORM, strategyDraftBody } from "../src/app/model/strategyDraftModel.ts";
import { draftVersionRecoveryKey, newStrategyDraftCreation, saveFirstStrategyDraft, type StrategyDraftSaveClient } from "../src/app/model/strategyDraftSave.ts";

const body = strategyDraftBody({ ...DEFAULT_STRATEGY_FORM, hubs: "NBP", dayAheadNames: "SAP", intradayNames: "ICE_OCM", name: "DEV UAT", resourceId: "own-resource", resourceName: "Own", resourceQuantity: "987", resourceCost: "31.125" });
function version(status = "DRAFT"): StrategyVersionDTO {
  return { strategy_version_id: "owned-version", strategy_id: "own-id", status, hypothesis: "", definition_json: {
    ...body.definition, strategy_name: body.strategy_name, run_mode: body.run_mode,
    resource_contexts: body.resource_contexts, price_observations: body.price_observations,
    existing_shadow_pnl_gbp: body.existing_shadow_pnl_gbp,
  } } as StrategyVersionDTO;
}
const identity = { name: "DEV UAT", description: "Explicit synthetic assumption" };

function fixture() {
  let exists = false, versions: StrategyVersionDTO[] = [];
  const counts = { identities: 0, versions: 0 };
  const client: StrategyDraftSaveClient = {
    strategy: async () => { if (!exists) throw Object.assign(Error("missing"), { status: 404 }); },
    createStrategy: async input => { assert.equal(input.strategy_id, "own-id"); counts.identities++; exists = true; },
    strategyVersions: async () => ({ data: versions }),
    createStrategyVersion: async () => { counts.versions++; const created = version(); versions = [created]; return { data: created }; },
  };
  return { client, counts, setVersions: (next: StrategyVersionDTO[]) => { versions = next; }, creation: newStrategyDraftCreation("own-id") };
}

test("failed version POST retains acknowledged identity but empty authoritative read blocks blind retry", async () => {
  const f = fixture(), post = f.client.createStrategyVersion;
  f.client.createStrategyVersion = async () => { throw Error("request aborted before server"); };
  await assert.rejects(saveFirstStrategyDraft({ ...f, identity, body }));
  assert.equal(f.creation.identityKnown, true);
  f.client.createStrategyVersion = post;
  await assert.rejects(saveFirstStrategyDraft({ ...f, identity, body }), /version_outcome_unknown/);
  assert.deepEqual(f.counts, { identities: 1, versions: 0 });
});

test("lost identity response reconciles by stable client id before any repeat create", async () => {
  const f = fixture(), post = f.client.createStrategy;
  f.client.createStrategy = async input => { await post(input); throw Error("response lost after commit"); };
  await assert.rejects(saveFirstStrategyDraft({ ...f, identity, body }));
  await saveFirstStrategyDraft({ ...f, identity, body });
  assert.deepEqual(f.counts, { identities: 1, versions: 1 });
});

test("lost version response reuses one exact editable match, including server-added defaults", async () => {
  const f = fixture(), post = f.client.createStrategyVersion;
  f.client.createStrategyVersion = async (id, input) => { await post(id, input); throw Error("response lost after commit"); };
  await assert.rejects(saveFirstStrategyDraft({ ...f, identity, body }));
  const stored = version(); (stored.definition_json.risk_controls as Record<string, unknown>).additional_default = null;
  f.setVersions([stored]);
  assert.equal((await saveFirstStrategyDraft({ ...f, identity, body })).strategy_version_id, "owned-version");
  assert.deepEqual(f.counts, { identities: 1, versions: 1 });
});

test("unavailable authoritative version read blocks retry instead of assuming no commit", async () => {
  const f = fixture(); f.creation.identityKnown = true; f.creation.versionAttempted = true;
  f.client.strategyVersions = async () => { throw Error("read unavailable"); };
  await assert.rejects(saveFirstStrategyDraft({ ...f, identity, body }), /read unavailable/);
  assert.deepEqual(f.counts, { identities: 0, versions: 0 });
});

test("frozen, changed, multiple or pre-existing versions require review with zero writes", async () => {
  for (const kind of ["frozen", "changed", "multiple", "pre-existing"]) {
    const f = fixture(); f.creation.identityKnown = true; f.creation.versionAttempted = kind !== "pre-existing";
    const stored = version(kind === "frozen" ? "FROZEN" : "DRAFT");
    if (kind === "changed") stored.hypothesis = "Another definition";
    f.setVersions(kind === "multiple" ? [stored, version()] : [stored]);
    await assert.rejects(saveFirstStrategyDraft({ ...f, identity, body }), /version_recovery_review/);
    assert.deepEqual(f.counts, { identities: 0, versions: 0 });
  }
});

test("explicitly selected empty identity recovers its first version without creating another identity", async () => {
  const f = fixture(); f.creation = newStrategyDraftCreation("own-id", true);
  await saveFirstStrategyDraft({ ...f, identity, body });
  assert.deepEqual(f.counts, { identities: 0, versions: 1 });
});

test("reload-restored uncertainty and later empty reads never authorize another version POST", async () => {
  const f = fixture(); f.creation = newStrategyDraftCreation("own-id", true); f.creation.versionAttempted = true;
  for (let retry = 0; retry < 3; retry++) await assert.rejects(saveFirstStrategyDraft({ ...f, identity, body }), /version_outcome_unknown/);
  assert.deepEqual(f.counts, { identities: 0, versions: 0 });
});

test("pending marker namespace separates deployment, authenticated principal and strategy", () => {
  const key = draftVersionRecoveryKey("https://one.example/api", "user-one", "own-id");
  assert.notEqual(key, draftVersionRecoveryKey("https://two.example/api", "user-one", "own-id"));
  assert.notEqual(key, draftVersionRecoveryKey("https://one.example/api", "user-two", "own-id"));
  assert.notEqual(key, draftVersionRecoveryKey("https://one.example/api", "user-one", "other-id"));
});
