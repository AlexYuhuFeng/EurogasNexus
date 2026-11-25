/** SCHED-1, the reconciliation row's presentation rules (`src/app/model/reconciliationModel.ts`). */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import type { GasDayReconciliationDTO, ReconciliationBreakDTO, ReconciliationGroupDTO } from "../src/api/client.ts";
import {
  breakTone,
  breaksOf,
  breakWords,
  cashOutText,
  countdownUrgency,
  groupKey,
  kindOptions,
  minutesUntil,
  signedQuantity,
} from "../src/app/model/reconciliationModel.ts";

// The demo's R1 break (gas day 2026-12-11): 6,000 MWh nominated out to Aldermoor, the TSO
// confirmed 4,800 after Aldermoor nominated 4,800: 1,200 MWh cut, 50,000 kWh/h, 1,440 GBP.
const lesser: ReconciliationBreakDTO = {
  id: "2026-12-11:NBP::aldermoorenergyplc:lesser_rule_cut",
  gas_day: "2026-12-11",
  kind: "lesser_rule_cut",
  hub: "NBP",
  point: null,
  counterparty: "Aldermoor Energy plc",
  mwh_at_risk: 1200,
  gap_mwh: 1200,
  explanation: "Nominated 6,000 MWh … 6,000 − 4,800 = 1,200 MWh cut",
  explanation_zh: "已提名 6,000 MWh … 1,200 MWh 被削减",
  next_step: "Call Aldermoor Energy plc's scheduler",
  next_step_zh: "致电Aldermoor Energy plc调度",
  trade_ids: ["demo-etrm-ald-1"],
  line_refs: ["trade:demo-etrm-ald-1"],
  figures: {},
  quantity: { value: 40946, unit: "th/d", mwh: 1200, kwh_h: 50000 },
  urgency: "due_soon",
  severity: "warning",
  cutoff: { key: "last_renomination", name: null, at_utc: "2026-12-12T02:00:00+00:00", basis: "assumption", source: "default" },
  minutes_left: 180,
  cash_out: { basis: "indicative", value: 1440, currency: "GBP", rate: 1.2, rate_unit: "GBP/MWh", note: "Indicative" },
  book_ids: ["demo-uk-nbp"],
  simulated: true,
};

const group: ReconciliationGroupDTO = {
  hub: "NBP",
  point: null,
  counterparty: "Aldermoor Energy plc",
  shipper_codes: ["DEMO-ALD-01"],
  traded: { value: -204728, unit: "th/d", mwh: -6000, kwh_h: -250000 },
  confirmed: null,
  nominated: { value: -204728, unit: "th/d", mwh: -6000, kwh_h: -250000 },
  tso: { value: -163783, unit: "th/d", mwh: -4800, kwh_h: -200000 },
  held: { confirmation: false, nomination: true, tso: true },
  state: "break",
  urgency: "due_soon",
  cutoff: lesser.cutoff,
  minutes_left: 180,
  mwh_at_risk: 1200,
  break_ids: [lesser.id],
  book_ids: ["demo-uk-nbp"],
  trades: [],
  nominations: [],
  simulated: true,
};

test("a break's chip and countdown follow its cut-off", () => {
  assert.equal(breakTone(lesser), "watch");
  assert.equal(breakTone({ ...lesser, severity: "critical" }), "breach");
  assert.equal(breakTone({ ...lesser, urgency: "passed", severity: "info" }), "breach");
  assert.equal(breakTone({ ...lesser, urgency: "open", severity: "info" }), "neutral");
  assert.equal(breakTone({ ...lesser, kind: "not_confirmed" }), "info");
  assert.equal(countdownUrgency("due_soon", 180), "soon");
  assert.equal(countdownUrgency("due_soon", 45), "imminent");
  assert.equal(countdownUrgency("open", 600), "open");
  assert.equal(countdownUrgency("passed", null), "imminent");
  assert.equal(countdownUrgency("closed", null), "none");
  // 23:30 UTC to the 02:00 last renomination: 150 minutes, and it keeps moving.
  assert.equal(minutesUntil(lesser.cutoff?.at_utc, Date.parse("2026-12-11T23:30:00Z")), 150);
  assert.equal(minutesUntil(lesser.cutoff?.at_utc, Date.parse("2026-12-12T03:00:00Z")), 0);
  assert.equal(minutesUntil(null, 0), null);
});

test("figures read as the desk writes them; the cash-out only when indicative", () => {
  assert.equal(signedQuantity(group.traded), "−204,728");
  assert.equal(signedQuantity({ value: 40946 }), "+40,946");
  assert.equal(signedQuantity(null), "—");
  assert.equal(cashOutText(lesser), "1,440 GBP");
  assert.equal(cashOutText({ cash_out: { basis: "missing", reason: "no approved rate" } }), null);
  assert.equal(breakWords(lesser, "zh-CN").next, lesser.next_step_zh);
  assert.equal(breakWords(lesser, "en").explanation, lesser.explanation);
});

test("each group holds its own breaks; found kinds come first in the filter", () => {
  const other = { ...lesser, id: "other", kind: "not_nominated" as const };
  assert.deepEqual(breaksOf(group, [other, lesser]).map((item) => item.id), [lesser.id]);
  assert.equal(groupKey(group), "NBP||Aldermoor Energy plc");
  const payload = { kinds: ["not_nominated", "lesser_rule_cut", "late"], counts: { lesser_rule_cut: 1 } } as unknown as GasDayReconciliationDTO;
  assert.deepEqual(kindOptions(payload).map((item) => `${item.kind}:${item.count}`), ["lesser_rule_cut:1", "not_nominated:0", "late:0"]);
});

test("every break kind and the row are named in English and Chinese", () => {
  const en = JSON.parse(readFileSync(new URL("../src/i18n/en.json", import.meta.url), "utf8")) as Record<string, string>;
  const zh = JSON.parse(readFileSync(new URL("../src/i18n/zh.json", import.meta.url), "utf8")) as Record<string, string>;
  const kinds = ["not_nominated", "nomination_without_trade", "quantity_mismatch", "counterparty_mismatch", "shipper_code_mismatch", "wrong_direction", "lesser_rule_cut", "late", "unit_mismatch", "gas_day_misaligned", "not_confirmed"];
  for (const key of [...kinds.map((kind) => `recon.kind.${kind}`), "today.row.reconciliation", "today.needs.kind.reconciliation"]) {
    assert.ok(en[key], key);
    assert.ok(zh[key] && zh[key] !== en[key], key);
  }
  const recon = Object.keys(en).filter((key) => key.startsWith("recon."));
  assert.deepEqual(recon.filter((key) => !zh[key]), []);
});

test("the row is read only and draws from the shared components", () => {
  const source = readFileSync(new URL("../src/components/today/ReconciliationRow.tsx", import.meta.url), "utf8");
  assert.ok(source.includes('from "@/components/ui"'));
  assert.ok(!/api\.(post|put|record)/.test(source));
  assert.ok(source.includes("aria-expanded") && source.includes("<caption"));
});
