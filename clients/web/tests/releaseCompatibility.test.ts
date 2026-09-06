import assert from "node:assert/strict";
import test from "node:test";
import {
  CLIENT_RELEASE_METADATA,
  compareVersions,
  compatibilityForServer,
  isBlockingCompatibility,
} from "../src/app/releaseCompatibility.ts";

function server(overrides: Record<string, unknown> = {}) {
  return {
    application_version: "0.5.0",
    release_channel: "preview",
    git_sha: "033df92a856e8820dd0f4d2a02367b21a285664d",
    api_contract_version: "api-contract/v1",
    database_schema_revision: "0030_reliability_indexes",
    minimum_supported_client: "0.5.0",
    minimum_supported_server: "0.5.0",
    backtest_engine_version: "backtest-engine/1",
    strategy_schema_version: "strategy-definition/v1",
    strategy_run_schema_version: "strategy-run-manifest/v1",
    solver_version: "min-cost-flow/v1",
    ...overrides,
  } as Parameters<typeof compatibilityForServer>[1];
}

test("stable client metadata exposes version channel and commit separately", () => {
  assert.equal(CLIENT_RELEASE_METADATA.version, "0.5.0");
  assert.equal(CLIENT_RELEASE_METADATA.channel, "preview");
  assert.equal(CLIENT_RELEASE_METADATA.minimumSupportedServer, "0.5.0");
});

test("compatible server is accepted", () => {
  const compatibility = compatibilityForServer(CLIENT_RELEASE_METADATA, server());
  assert.equal(compatibility.state, "compatible");
  assert.equal(isBlockingCompatibility(compatibility.state), false);
});

test("client update required is blocking and explicit", () => {
  const compatibility = compatibilityForServer(
    { ...CLIENT_RELEASE_METADATA, version: "0.4.9" },
    server({ minimum_supported_client: "0.5.0" }),
  );
  assert.equal(compatibility.state, "client_update_required");
  assert.equal(compatibility.messageKey, "release.compat_client_update_required");
  assert.equal(isBlockingCompatibility(compatibility.state), true);
});

test("server upgrade required is blocking and explicit", () => {
  const compatibility = compatibilityForServer(
    { ...CLIENT_RELEASE_METADATA, minimumSupportedServer: "0.5.0" },
    server({ application_version: "0.4.9", minimum_supported_server: "0.4.9" }),
  );
  assert.equal(compatibility.state, "server_upgrade_required");
  assert.equal(isBlockingCompatibility(compatibility.state), true);
});

test("contract mismatch blocks before any workspace screen", () => {
  const compatibility = compatibilityForServer(
    CLIENT_RELEASE_METADATA,
    server({ api_contract_version: "api-contract/v2" }),
  );
  assert.equal(compatibility.state, "contract_mismatch");
  assert.equal(isBlockingCompatibility(compatibility.state), true);
});

test("prerelease ordering is deterministic", () => {
  assert.ok(compareVersions("0.5.0-rc.1", "0.5.0-rc.2") < 0);
  assert.ok(compareVersions("0.5.0-rc.10", "0.5.0") < 0);
  assert.ok(compareVersions("0.5.0-preview.1.aaaaaaaa", "0.5.0-preview.2.aaaaaaaa") < 0);
  assert.equal(compareVersions("0.5.0", "0.5.0"), 0);
});
