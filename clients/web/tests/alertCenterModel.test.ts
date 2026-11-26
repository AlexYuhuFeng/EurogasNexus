/**
 * The alert centre reads one desk-wide list two ways: grouped so repeats of one condition are
 * one row, and against the reader's own marks so read and dismissed rows stop shouting. These
 * tests pin the grouping, the ordering, the badge count and the optimistic marks.
 */

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import type { MonitoringAlertDTO } from "../src/api/client.ts";
import {
  alertCounts,
  alertGroupKey,
  applyReaderAction,
  categoryKey,
  groupAlerts,
  memberIds,
} from "../src/app/alerts/alertCenterModel.ts";

function alert(overrides: Partial<MonitoringAlertDTO>): MonitoringAlertDTO {
  return {
    alert_id: "a",
    fingerprint: "f",
    category: "limits",
    alert_type: "credit_limit",
    severity: "warning",
    status: "open",
    title_en: "Title",
    title_zh_cn: "标题",
    message_en: "",
    message_zh_cn: "",
    entity_type: "counterparty",
    entity_id: "c",
    event_time_utc: "2026-11-25T08:00:00Z",
    detected_at_utc: "2026-11-25T08:00:00Z",
    updated_at_utc: "2026-11-25T08:00:00Z",
    acknowledged_at_utc: null,
    resolved_at_utc: null,
    occurrence_count: 1,
    evidence_snapshot: {},
    source_refs: [],
    warnings: [],
    llm_provider_id: "",
    llm_status: "",
    llm_summary_en: null,
    llm_summary_zh_cn: null,
    llm_last_attempt_at_utc: null,
    simulated: false,
    human_review_required: false,
    ...overrides,
  };
}

const outage = (id: string, time: string, severity: MonitoringAlertDTO["severity"] = "warning") =>
  alert({
    alert_id: id,
    category: "physical",
    alert_type: "remit_outage",
    severity,
    title_en: "VIP France-Germany: 120 GWh/d unavailable",
    event_time_utc: time,
  });

test("repeats of one outage are one row, led by the most severe and dated from the first", () => {
  const groups = groupAlerts(
    [
      outage("o1", "2026-11-24T06:00:00Z"),
      outage("o2", "2026-11-25T06:00:00Z", "critical"),
      outage("o3", "2026-11-23T06:00:00Z"),
      outage("o4", "2026-11-25T07:00:00Z"),
    ],
    {},
  );
  assert.equal(groups.length, 1);
  assert.equal(groups[0].members.length, 4);
  assert.equal(groups[0].lead.alert_id, "o2");
  assert.equal(groups[0].severity, "critical");
  assert.equal(groups[0].since, "2026-11-23T06:00:00Z");
});

test("delivery shortfalls group by contract; other alerts stand alone", () => {
  const short = (id: string, contract: string) =>
    alert({ alert_id: id, category: "delivery", alert_type: "shortfall", evidence_snapshot: { contract_id: contract } });
  assert.equal(alertGroupKey(short("d1", "k1")), alertGroupKey(short("d2", "k1")));
  assert.notEqual(alertGroupKey(short("d1", "k1")), alertGroupKey(short("d3", "k2")));
  assert.notEqual(alertGroupKey(alert({ alert_id: "l1" })), alertGroupKey(alert({ alert_id: "l2" })));
  // A shortfall that names no contract cannot be grouped safely.
  assert.equal(alertGroupKey(alert({ alert_id: "d9", category: "delivery" })), "alert|d9");
});

test("resolved alerts are not listed, and unread rows come first, then severity, then newest", () => {
  const groups = groupAlerts(
    [
      alert({ alert_id: "gone", status: "resolved", severity: "critical" }),
      alert({ alert_id: "read-critical", severity: "critical" }),
      alert({ alert_id: "warn-old", event_time_utc: "2026-11-24T08:00:00Z" }),
      alert({ alert_id: "warn-new", event_time_utc: "2026-11-25T09:00:00Z" }),
    ],
    { "read-critical": { read: true, dismissed: false, read_at_utc: "x", dismissed_at_utc: null } },
  );
  assert.deepEqual(groups.map((group) => group.lead.alert_id), ["warn-new", "warn-old", "read-critical"]);
});

test("the badge counts unread rows the reader has not dismissed, from the drawer's own list", () => {
  const groups = groupAlerts(
    [
      alert({ alert_id: "c", severity: "critical" }),
      alert({ alert_id: "w" }),
      alert({ alert_id: "hidden" }),
      outage("o1", "2026-11-24T06:00:00Z"),
      outage("o2", "2026-11-25T06:00:00Z"),
    ],
    { hidden: { read: true, dismissed: true, read_at_utc: "x", dismissed_at_utc: "x" } },
  );
  const counts = alertCounts(groups);
  assert.equal(counts.unread, 3); // c, w and the outage row, not five feed messages
  assert.equal(counts.unreadCritical, 1);
  assert.equal(counts.active, 3);
  assert.equal(counts.dismissed, 1);
});

test("a row is read only when all its notices are read, and dismissed only when all are", () => {
  const groups = groupAlerts(
    [outage("o1", "2026-11-24T06:00:00Z"), outage("o2", "2026-11-25T06:00:00Z")],
    { o1: { read: true, dismissed: true, read_at_utc: "x", dismissed_at_utc: "x" } },
  );
  assert.equal(groups[0].unread, true);
  assert.equal(groups[0].dismissed, false);
});

test("marks change at once as the server will record them", () => {
  const now = "2026-11-26T01:00:00Z";
  const read = applyReaderAction({}, "read", ["a"], now);
  assert.deepEqual(read.a, { read: true, dismissed: false, read_at_utc: now, dismissed_at_utc: null });
  const dismissed = applyReaderAction(read, "dismiss", ["a", "b"], now);
  assert.equal(dismissed.a.dismissed, true);
  assert.equal(dismissed.b.read, true, "dismissing marks read too");
  const restored = applyReaderAction(dismissed, "restore", ["a", "never-marked"], now);
  assert.equal(restored.a.dismissed, false);
  assert.equal(restored.a.read, true, "restoring keeps it read");
  assert.equal("never-marked" in restored, false);
});

test("member ids cover every notice of every row, and unknown categories have a name", () => {
  const groups = groupAlerts([outage("o1", "2026-11-24T06:00:00Z"), outage("o2", "2026-11-25T06:00:00Z")], {});
  assert.deepEqual(memberIds(groups).sort(), ["o1", "o2"]);
  assert.equal(categoryKey("limits"), "alerts.category.limits");
  assert.equal(categoryKey("something_new"), "alerts.category.other");
});

test("every category, severity and alert-centre string exists in both languages", () => {
  const en = JSON.parse(readFileSync(new URL("../src/i18n/en.json", import.meta.url), "utf8")) as Record<string, string>;
  const zh = JSON.parse(readFileSync(new URL("../src/i18n/zh.json", import.meta.url), "utf8")) as Record<string, string>;
  const source = readFileSync(new URL("../src/components/AlertCenter.tsx", import.meta.url), "utf8");
  const used = new Set([...source.matchAll(/t\("(alerts\.[a-z_.]+)"/g)].map((match) => match[1]));
  for (const category of ["limits", "delivery", "physical", "market", "fundamentals", "data_source", "opportunity", "market_opportunity", "strategy", "capacity", "lng_hedge", "lng_schedule", "lng_exposure", "lng_material", "gas_day_break", "news_trader", "news_lng", "news_scheduler", "other"]) {
    used.add(`alerts.category.${category}`);
  }
  for (const severity of ["info", "warning", "critical"]) used.add(`alerts.severity.${severity}`);
  for (const key of used) {
    const plural = [`${key}_one`, `${key}_other`];
    assert.ok(key in en || plural.every((form) => form in en), `en ${key}`);
    assert.ok(key in zh || plural.every((form) => form in zh), `zh ${key}`);
  }
  // The chips no longer print raw codes such as "data source", "warning" or "open".
  assert.equal(source.includes('alert.category.replace(/_/g, " ")'), false);
  assert.equal(source.includes("<span>{alert.status}</span>"), false);
});

test("the drawer offers dismiss, mark all read and a retry that says why it failed", () => {
  const source = readFileSync(new URL("../src/components/AlertCenter.tsx", import.meta.url), "utf8");
  assert.match(source, /api\.markAlerts\(action, ids\)/);
  assert.match(source, /t\("alerts\.action\.mark_all_read"\)/);
  assert.match(source, /t\("alerts\.action\.dismiss_all"\)/);
  assert.match(source, /role="alert"/);
  assert.match(source, /t\("alerts\.action\.retry"\)/);
  assert.match(source, /event\.key !== "Escape"/);
  // The badge counts the drawer's own unread rows, not a separately loaded summary.
  assert.match(source, /\{counts\.unread > 0 && <strong>\{counts\.unread\}<\/strong>\}/);
  assert.equal(source.includes("summary.open_count"), false);
});
