/**
 * LNG-2: a cargo change reaches each role. Today's "What needs me" shows the reader's cargo
 * message with its role and due time; the plan sheet shows each role's message (the reader's
 * own first, withdrawn ones struck through with the reason, in the reader's language); the
 * board shows who must act and what the ETA rests on (lesson P3).
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test, { after } from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import type { CargoEtaDTO, CargoPlanBoardLineDTO, CargoRoleMessageDTO, DeskTodayDTO } from "../src/api/client.ts";
import { closeApiStoreHarness, loadApiStore } from "./support/apiStoreHarness.ts";

after(closeApiStoreHarness);

const h = React.createElement;
const render = (element: React.ReactElement) => renderToStaticMarkup(element);
const t = (key: string, options?: Record<string, unknown>) =>
  options && Object.keys(options).length ? `${key}(${Object.entries(options).map(([k, v]) => `${k}=${String(v)}`).join(",")})` : key;

const ETA: CargoEtaDTO = {
  basis: "ais_declared",
  confidence: "low",
  source: "KPLER",
  recorded_at_utc: "2026-11-24T09:00:00+00:00",
  text: "ETA from KPLER (the ETA declared in AIS, low confidence)",
};

function message(role: CargoRoleMessageDTO["role"], extra: Partial<CargoRoleMessageDTO> = {}): CargoRoleMessageDTO {
  return {
    alert_id: `a-${role}`,
    cargo_id: "SAB-0420",
    role,
    category: `lng_${role}`,
    for: [],
    status: "open",
    severity: "warning",
    title: `${role} title`,
    title_zh: `${role} 标题`,
    lines: [`${role} line`],
    lines_zh: [`${role} 行`],
    items: [],
    due_utc: "2026-11-28T00:00:00+00:00",
    inputs_as_of: { eta: ETA, revision: 2, event_at_utc: "2026-11-24T09:00:00+00:00", rebuilt_at_utc: "2026-11-24T09:00:01+00:00", line: "Inputs: ..." },
    withdrawn: null,
    notified_at_utc: "2026-11-24T09:00:01+00:00",
    updated_at_utc: "2026-11-24T09:00:01+00:00",
    simulated: false,
    mine: false,
    ...extra,
  };
}

test("Today: a cargo message names the reader's role and says by when its first step is due", async () => {
  const { load } = await loadApiStore();
  const { TodayScreen } = await load<typeof import("../src/components/TodayScreen.tsx")>("/src/components/TodayScreen.tsx");
  const item = {
    kind: "cargo", id: "a-trader", title: "Hedges no longer match Aurora (SAB-0420): sell 379,373 MWh TTF 2026-12",
    title_zh: "套保已不匹配 Aurora (SAB-0420)", role: "trader", status: "breach", simulated: false,
    as_of: "2026-11-24T09:00:01+00:00", since_utc: "2026-11-24T09:00:00+00:00", deadline_utc: "2026-11-28T00:00:00+00:00",
    cargo_id: "SAB-0420", target: { mode: "desk", task: "cargoes", params: { cargo: "SAB-0420" } }, why: { subject: "alert", id: "a-trader" },
  };
  const today = {
    as_of: "2026-11-24T09:00:00+00:00", gas_day: "2026-11-24", front_month: "Dec-26", simulated: false, stale_figures: [], warnings: [],
    // Rows are positional: key figures, changes, book, fundamentals, then what needs me.
    rows: [null, null, null, null, { key: "needs_me", title: "What needs me", populated: true, empty: null, more: 0, quiet: null, items: [item] }],
  } as unknown as DeskTodayDTO;
  const props = {
    today, loading: false, error: null, t, nowMs: Date.parse("2026-11-24T10:00:00Z"),
    onRefresh: () => undefined, onOpenBrief: () => undefined, onOpenLimits: () => undefined,
  };
  const html = render(h(TodayScreen, { ...props, language: "en" }));
  assert.match(html, /data-need="cargo"/);
  assert.match(html, /data-tone="breach"[^>]*>(<svg[\s\S]*?<\/svg>)?today\.needs\.kind\.cargo</);
  assert.match(html, /Hedges no longer match Aurora/);
  assert.match(html, /today\.needs\.cargo_for\(role=lng\.cargo\.role\.trader\)/);
  assert.match(html, /today\.needs\.due\(when=/);
  const zh = render(h(TodayScreen, { ...props, language: "zh-CN" }));
  assert.match(zh, /套保已不匹配 Aurora/);
});

test("Plan sheet: each role's message, the reader's first, withdrawn ones with their reason", async () => {
  const { load } = await loadApiStore();
  const { RoleMessages } = await load<typeof import("../src/components/CargoPlanView.tsx")>("/src/components/CargoPlanView.tsx");
  const roles = [
    message("desk_head", { status: "withdrawn", withdrawn: { reason: "the change is no longer material", reason_zh: "变化已不再重大", at_utc: "2026-11-24T09:30:00+00:00", revision: 3 } }),
    message("risk", { severity: "critical" }),
    message("trader", { mine: true }),
  ];
  const html = render(h(RoleMessages, { roles, t, language: "en" }));
  const order = [...html.matchAll(/data-role="([a-z_]+)"/g)].map((match) => match[1]);
  assert.deepEqual(order, ["trader", "risk", "desk_head"]);
  assert.match(html, /data-role="risk" data-severity="critical" data-status="open"/);
  assert.match(html, /lng\.cargo\.role_mine/);
  assert.match(html, /trader line/);
  assert.match(html, /data-status="withdrawn"/);
  assert.match(html, /lng\.cargo\.roles\.withdrawn_because\(reason=the change is no longer material\)/);
  assert.doesNotMatch(html, /desk_head line/); // a withdrawn message is not acted on
  assert.match(html, /lng\.cargo\.roles\.revision\(revision=2\)/);
  const zh = render(h(RoleMessages, { roles, t, language: "zh-CN" }));
  assert.match(zh, /trader 标题/);
  assert.match(zh, /trader 行/);
  assert.match(zh, /reason=变化已不再重大/);
  assert.match(render(h(RoleMessages, { roles: [], t, language: "en" })), /lng\.cargo\.roles\.none/);
});

test("Board: who must act, the reader's role marked, and what the ETA rests on", async () => {
  const { load } = await loadApiStore();
  const { RoleChips } = await load<typeof import("../src/components/CargoBoard.tsx")>("/src/components/CargoBoard.tsx");
  const { EtaBasis } = await load<typeof import("../src/components/CargoPlanView.tsx")>("/src/components/CargoPlanView.tsx");
  const line = {
    cargo_id: "SAB-0420",
    attention: [
      { alert_id: "a-trader", role: "trader", severity: "critical", title: "t", title_zh: null, due_utc: null, mine: true, updated_at_utc: "2026-11-24T09:00:01+00:00" },
      { alert_id: "a-risk", role: "risk", severity: "warning", title: "r", title_zh: null, due_utc: null, mine: false, updated_at_utc: "2026-11-24T09:00:01+00:00" },
    ],
  } as CargoPlanBoardLineDTO;
  const chips = render(h(RoleChips, { line, t, language: "en" }));
  assert.match(chips, /data-mine="true" data-role="trader"><span[^>]*data-tone="breach"[^>]*>(<svg[\s\S]*?<\/svg>)?lng\.cargo\.role\.trader · lng\.cargo\.role_mine/);
  assert.match(chips, /data-mine="false" data-role="risk"><span[^>]*data-tone="watch"/);
  assert.match(render(h(RoleChips, { line: { cargo_id: "x" } as CargoPlanBoardLineDTO, t, language: "en" })), />–</);
  const basis = render(h(EtaBasis, { eta: ETA, t }));
  assert.match(basis, /data-confidence="low"/);
  assert.match(basis, /lng\.cargo\.eta_basis\.ais_declared · lng\.cargo\.eta_confidence\.low/);
  assert.match(render(h(EtaBasis, { eta: { ...ETA, basis: null, confidence: null }, t })), /eta_basis\.none · lng\.cargo\.eta_confidence\.none/);
});

test("Every new string has English and Chinese, and channels can subscribe to both new categories", () => {
  const en = JSON.parse(readFileSync(new URL("../src/i18n/en.json", import.meta.url), "utf8")) as Record<string, string>;
  const zh = JSON.parse(readFileSync(new URL("../src/i18n/zh.json", import.meta.url), "utf8")) as Record<string, string>;
  const keys = [
    "today.needs.kind.cargo", "today.needs.cargo_for", "today.needs.due", "lng.cargo.col.attention",
    "notify.category_cargo", "notify.category_desk_head", "lng.cargo.roles.title", "lng.cargo.role_mine",
    ...["trader", "scheduler", "risk", "desk_head"].map((role) => `lng.cargo.role.${role}`),
    ...["master_notice", "ais_declared", "feed_estimate", "schedule", "manual", "none"].map((basis) => `lng.cargo.eta_basis.${basis}`),
    ...["high", "medium", "low", "none"].map((confidence) => `lng.cargo.eta_confidence.${confidence}`),
  ];
  for (const key of keys) {
    assert.ok(en[key], `en ${key}`);
    assert.ok(zh[key] && zh[key] !== en[key], `zh ${key}`);
  }
  const panel = readFileSync(new URL("../src/components/NotificationChannelsPanel.tsx", import.meta.url), "utf8");
  assert.match(panel, /"cargo"/);
  assert.match(panel, /"desk_head"/);
});
