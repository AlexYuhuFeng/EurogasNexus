/** Connectors view: one group, one status word and one action per source (#26, #33). */
import assert from "node:assert/strict";
import test from "node:test";
import { connectorCard, groupConnectors, type ConnectorSourceFacts } from "../src/app/model/connectorCatalogModel.ts";

const base: ConnectorSourceFacts = {
  source_id: "src-x",
  connectivity_status: "needs_credential",
  operational_status: "needs_credential",
  integration: "api",
  credential_state: "missing",
  scheduler_enabled: false,
  last_success_at_utc: null,
  effective_last_success_at_utc: null,
  consecutive_failures: 0,
};

test("an optional provider nobody connected is available, not an alarm", () => {
  assert.deepEqual(connectorCard(base), { sourceId: "src-x", group: "available", statusKey: "connectors.status.needs_key", action: "connect" });
});

test("a key that went missing after the feed worked needs attention", () => {
  assert.equal(connectorCard({ ...base, last_success_at_utc: "2026-11-01T00:00:00Z" }).group, "attention");
  assert.equal(connectorCard({ ...base, scheduler_enabled: true }).statusKey, "connectors.status.key_missing");
});

test("failures, stale feeds, disabled keys and a missing store need attention", () => {
  for (const [status, key] of [
    ["failed", "connectors.status.failing"],
    ["stale", "connectors.status.stale"],
    ["credential_disabled", "connectors.status.key_disabled"],
    ["runtime_unconfigured", "connectors.status.no_store"],
  ] as const) {
    const card = connectorCard({ ...base, connectivity_status: status });
    assert.equal(card.group, "attention", status);
    assert.equal(card.statusKey, key);
    assert.equal(card.action, "fix");
  }
});

test("a delivering feed is connected; a simulated one says so", () => {
  assert.equal(connectorCard({ ...base, connectivity_status: "active" }).statusKey, "connectors.status.live");
  assert.equal(
    connectorCard({ ...base, connectivity_status: "active", operational_status: "active_simulated" }).statusKey,
    "connectors.status.simulated",
  );
});

test("templates and file imports offer their own first step", () => {
  assert.equal(connectorCard({ ...base, connectivity_status: "no_records", integration: "template" }).action, "configure");
  assert.equal(connectorCard({ ...base, connectivity_status: "no_records", integration: "file_import" }).action, "import");
  assert.equal(connectorCard({ ...base, connectivity_status: "no_records", scheduler_enabled: true }).group, "attention");
});

test("every source lands in exactly one group", () => {
  const sources = [base, { ...base, source_id: "a", connectivity_status: "active" }, { ...base, source_id: "b", connectivity_status: "failed" }];
  const groups = groupConnectors(sources);
  assert.equal(groups.attention.length + groups.connected.length + groups.available.length, sources.length);
});

test("a TSO tariff register is a manual register: never stale, never an alarm (DATA-05)", () => {
  const register = { ...base, integration: "manual_register" as const, credential_state: "not_required" };
  const empty = connectorCard({ ...register, connectivity_status: "manual_register", operational_status: "manual_register" });
  assert.deepEqual(empty, { sourceId: "src-x", group: "available", statusKey: "connectors.status.manual_register", action: "open" });
  const held = connectorCard({
    ...register,
    connectivity_status: "manual_register",
    operational_status: "manual_register",
    last_success_at_utc: "2025-01-01T00:00:00Z",
  });
  assert.equal(held.group, "connected");
  assert.equal(held.statusKey, "connectors.status.manual_register");
});

test("a public source the gate holds back says so in plain words, with the approve action", () => {
  // ENTSOG on a fresh installation: no records, no key needed, not approved yet.
  const entsog = { ...base, source_id: "src-entsog", approval: { required: true, state: "not_approved" } };
  assert.deepEqual(connectorCard(entsog), {
    sourceId: "src-entsog", group: "attention", statusKey: "connectors.status.not_approved", action: "approve",
  });
  const waiting = { ...entsog, approval: { required: true, state: "approved_waiting_for_key" } };
  assert.equal(connectorCard(waiting).statusKey, "connectors.status.approved_waiting_for_key");
  assert.equal(connectorCard(waiting).action, "connect");
  const failing = { ...entsog, approval: { required: true, state: "failing" } };
  assert.equal(connectorCard(failing).statusKey, "connectors.status.failing");
  // Approved and reading: the ordinary statuses apply.
  const running = { ...entsog, connectivity_status: "active", operational_status: "active", approval: { required: true, state: "running" } };
  assert.equal(connectorCard(running).statusKey, "connectors.status.live");
  // A source that needs no approval is untouched.
  const ecb = { ...base, approval: { required: false, state: "not_required" } };
  assert.deepEqual(connectorCard(ecb), connectorCard(base));
});
