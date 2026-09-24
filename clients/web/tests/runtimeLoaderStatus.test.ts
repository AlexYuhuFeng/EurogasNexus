/**
 * Runtime loader status: unknown is not disconnected, and pending is not loading workspace.
 *
 * CI run 35966584093 captured the Network surface reporting "Runtime PostgreSQL is not connected"
 * beside PostgreSQL-backed rows it had just rendered. The store's status slice is null until the
 * workspace batch's status read answers (and stays null when that read fails or is superseded), so
 * every surface that rendered the boolean `runtimeDbReady === false` as a disconnection was
 * claiming a fact it had no reading for. The status vocabulary is three-valued here, the pending
 * state has its own copy in both locales, and a surface that is already loaded cannot be painted
 * as loading by an unrelated action that happens to be in flight.
 */

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import {
  runtimeStoreStatus,
  type RuntimeStoreStatus,
} from "../src/app/model/dataPlaneStatus.ts";
import { resolveNetworkGeometryState } from "../src/app/workspaceDerivedData.ts";
import type { EdgeDTO, NodeDTO, RuntimeDbStatusDTO } from "../src/api/client.ts";

function readWebSource(relativePath: string): string {
  return readFileSync(new URL(`../src/${relativePath}`, import.meta.url), "utf8");
}

function readLocale(name: "en" | "zh"): Record<string, string> {
  return JSON.parse(readWebSource(`i18n/${name}.json`)) as Record<string, string>;
}

function runtimeDb(overrides: Partial<RuntimeDbStatusDTO> = {}): RuntimeDbStatusDTO {
  return {
    database_url_present: true,
    connectivity: { ok: true },
    missing_tables: [],
    alembic_revision: "0036_job_records",
    ...overrides,
  } as unknown as RuntimeDbStatusDTO;
}

function node(id: string): NodeDTO {
  return { node_id: id, name: id, node_type: "hub", lat: 52, lon: 4, country: "NL" } as unknown as NodeDTO;
}

test("a status read that has not answered is unknown, never disconnected and never ready", () => {
  for (const pending of [null, undefined]) {
    assert.equal(runtimeStoreStatus(pending), "unknown", String(pending));
  }
  // Answered the question, with the two answers the backend can give.
  assert.equal(runtimeStoreStatus(runtimeDb()), "ready");
  assert.equal(runtimeStoreStatus(runtimeDb({ database_url_present: false })), "unavailable");
  assert.equal(runtimeStoreStatus(runtimeDb({ connectivity: { ok: false } })), "unavailable");
  assert.equal(
    runtimeStoreStatus(runtimeDb({ database_url_present: false, connectivity: { ok: false } })),
    "unavailable",
  );

  // The three values are distinct facts: no pending reading may collapse onto either verdict.
  const pending: RuntimeStoreStatus = runtimeStoreStatus(null);
  assert.notEqual(pending, "ready");
  assert.notEqual(pending, "unavailable");
});

test("pending geometry is not missing geometry and not loaded geometry", () => {
  const nodes = [node("n1"), node("n2")];
  const edges = [{ edge_id: "e1", from_node_id: "n1", to_node_id: "n2" }] as unknown as EdgeDTO[];

  // The contradiction CI captured: rows on screen, status not yet read. The map says it does not
  // know, and it does not say the store is gone.
  assert.equal(resolveNetworkGeometryState("unknown", nodes, edges), "runtime_unknown");
  assert.equal(resolveNetworkGeometryState("unknown", [], []), "runtime_unknown");
  assert.notEqual(resolveNetworkGeometryState("unknown", nodes, edges), "runtime_missing");

  // The answered states keep their existing meaning, so the repair does not soften a real finding.
  assert.equal(resolveNetworkGeometryState("unavailable", nodes, edges), "runtime_missing");
  assert.equal(resolveNetworkGeometryState("ready", [], []), "nodes_missing");
  assert.equal(resolveNetworkGeometryState("ready", nodes, []), "edges_missing");
  assert.equal(resolveNetworkGeometryState("ready", nodes, edges), "unverified_geometry");
});

test("the pending status has copy of its own, in both locales, that claims no connection verdict", () => {
  const en = readLocale("en");
  const zh = readLocale("zh");

  for (const [locale, translations] of [["en", en], ["zh", zh]] as const) {
    const body = translations["map.runtime_unknown_body"];
    assert.equal(typeof body, "string", `${locale} map.runtime_unknown_body`);
    assert.notEqual(body, translations["map.runtime_missing_body"], locale);
    assert.notEqual(body, translations["map.network_ready_body"], locale);
    assert.equal(/not connected|disconnected|is unavailable/i.test(body), false, locale);
    assert.equal(body.includes("未连接"), false, locale);
    assert.equal(body.includes("不可用"), false, locale);
    assert.match(body, locale === "en" ? /runtime database status/i : /运行时数据库状态/, locale);

    const blocker = translations["home.blocker_runtime_unknown"];
    assert.equal(typeof blocker, "string", `${locale} home.blocker_runtime_unknown`);
    assert.equal(blocker.includes(translations["home.blocker_runtime_db"]), false, locale);
    assert.equal(/not connected|disconnected/i.test(blocker), false, locale);
    assert.equal(blocker.includes("未连接"), false, locale);
  }

  // The disconnection copy the repair must not delete: it still exists, for the case that proves it.
  assert.match(en["map.runtime_missing_body"], /not connected/i);
  assert.match(zh["map.runtime_missing_body"], /未连接/);
});

test("the geometry message and the topology status route the pending state to its own words", () => {
  const network = readWebSource("components/NetworkWorkspace.tsx");
  assert.match(
    network,
    /if \(state === "runtime_unknown"\) return "map\.runtime_unknown_body";[\s\S]*?if \(state === "runtime_missing"\) return "map\.runtime_missing_body";/,
  );
  // The status cell states the unknown reading rather than the unavailable one.
  assert.match(
    network,
    /networkGeometryState === "runtime_unknown"[\s\S]{0,80}t\("status\.unknown"\)/,
  );

  const model = readWebSource("app/model/usePortfolioDecisionModel.ts");
  assert.match(model, /const runtimeStore = runtimeStoreStatus\(api\.runtimeDb\);/);
  assert.match(model, /const runtimeDbReady = runtimeStore === "ready";/);
  assert.match(model, /resolveNetworkGeometryState\(runtimeStore, api\.nodes, api\.edges\)/);
  assert.equal(
    model.includes("resolveNetworkGeometryState(runtimeDbReady"),
    false,
    "the boolean must not reach the geometry resolver again",
  );
  assert.match(
    model,
    /if \(runtimeStore === "unknown"\) blockers\.push\(t\("home\.blocker_runtime_unknown"\)\);[\s\S]{0,90}else if \(!runtimeDbReady\) blockers\.push\(t\("home\.blocker_runtime_db"\)\);/,
  );
});

test("the store carries the unread status and publishes the workspace batch's own loading state", () => {
  const store = readWebSource("stores/api.ts");
  assert.match(store, /dataStatus: "unknown" \| "runtime" \| "delayed" \| "partial" \| "unavailable";/);
  assert.match(store, /dataStatus: "unknown",/);
  // The batch's provenance comes from the three-valued status, not from a null check.
  assert.match(store, /const runtimeStatus = runtimeStoreStatus\(runtimeDb\);/);
  assert.match(store, /runtimeStatus === "unknown"[\s\S]{0,60}\? "unknown"/);
  // A page-level load claim reads the batch flag; the on-demand flag keeps its own meaning.
  assert.match(store, /set\(\{ loading: true, workspaceLoading: true, error: null \}\);/);
  assert.match(store, /workspaceLoading: workspaceCommit\.loading,/);
  // A committed batch is a fact of its own: the pre-read state is not the settled one.
  assert.match(store, /workspaceLoadsCommitted: number;/);
  assert.match(store, /workspaceLoadsCommitted: get\(\)\.workspaceLoadsCommitted \+ 1,/);
  assert.match(
    store,
    /\? \{ loading: false, workspaceLoading: false, endpointRetryBusy: false \}/,
  );

  const reset = readWebSource("stores/workspaceLoading.ts");
  assert.match(reset, /workspaceLoading: false,/);
  assert.match(reset, /workspaceLoadsCommitted: 0,/);
  assert.match(reset, /dataStatus: "unknown" as const,/);
});

test("page-level loading claims read the workspace batch, not any in-flight action", () => {
  const cockpit = readWebSource("components/MarketCockpit.tsx");
  assert.match(cockpit, /<NetworkWorkspace[\s\S]*?loading=\{api\.workspaceLoading\}/);
  assert.equal(cockpit.includes("loading={api.loading}"), false);

  const renderer = readWebSource("app/workspaces/WorkspaceRenderer.tsx");
  assert.match(renderer, /data-workspace-load-state=\{workspaceLoadState\}/);
  assert.match(
    renderer,
    /api\.workspaceLoading\s*\?\s*"loading"\s*:\s*api\.workspaceLoadsCommitted > 0\s*\?\s*"settled"\s*:\s*"unread"/,
  );
  assert.match(renderer, /<GlossaryWiki[\s\S]*?loading=\{api\.workspaceLoading\}/);
  // The sweep's settle signal lives on the same element the sweep already resolves.
  assert.match(renderer, /className="workspace-page"/);
});

test("a panel's own pending read is named as that read, not as the workspace", () => {
  for (const [file, key] of [
    ["components/ReferenceNetworkCatalogue.tsx", "network.reference.loading"],
    ["components/CapacityContractBook.tsx", "capacity.contracts.loading"],
  ] as const) {
    const source = readWebSource(file);
    assert.match(source, new RegExp(`\\{loading && <p className="muted">\\{t\\("${key.replace(".", "\\.")}"\\)\\}</p>\\}`), file);
    assert.equal(source.includes('t("status.loading")'), false, `${file} claims the workspace loads`);
    // An unread panel header states that it is unread rather than "unavailable".
    assert.match(source, /meta=\{[\w.]+ \?\? t\("status\.unknown"\)\}/, file);
  }
  for (const locale of ["en", "zh"] as const) {
    const translations = readLocale(locale);
    for (const key of ["network.reference.loading", "capacity.contracts.loading"]) {
      assert.equal(typeof translations[key], "string", `${locale} ${key}`);
      assert.equal(/loading workspace|工作台/.test(translations[key]), false, `${locale} ${key}`);
    }
  }
});
