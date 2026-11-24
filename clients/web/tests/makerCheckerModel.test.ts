import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import type { ChangeRequestDTO } from "../src/api/client.ts";
import {
  changeErrorKey,
  changeValueText,
  orderChanges,
  pendingByTarget,
  provenanceParts,
  saveOutcome,
} from "../src/app/model/makerCheckerModel.ts";
import en from "../src/i18n/en.json" with { type: "json" };

const read = (path: string) => readFileSync(new URL(`../src/${path}`, import.meta.url), "utf8");

function change(overrides: Partial<ChangeRequestDTO>): ChangeRequestDTO {
  return {
    change_id: "chg-1",
    action: "risk.credit_line.update",
    kind: "credit_line",
    label: "Credit line",
    label_zh: "信用额度",
    resource: "credit_line:CP-1",
    target_key: "CP-1",
    subject: "Counterparty",
    new_record: false,
    fields: [{ name: "limit_amount", before: 500000, after: 750000 }],
    reason: "annual review",
    state: "pending",
    proposed_by: "maker",
    proposed_by_name: "Maker",
    proposed_at_utc: "2026-11-20T09:00:00+00:00",
    decided_by: null,
    decided_by_name: null,
    decided_at_utc: null,
    decision_note: null,
    own: false,
    may_approve: true,
    may_reject: true,
    may_withdraw: false,
    approver: "risk_function",
    ...overrides,
  };
}

test("a save under four eyes reads as proposed, not saved", () => {
  assert.equal(saveOutcome({ pending_approval: true, change: change({}) }), "proposed");
  assert.equal(saveOutcome({ key: "CP-1", created: false, changed: [], pending_approval: false }), "unchanged");
  assert.equal(saveOutcome({ key: "CP-1", created: true, pending_approval: false }), "saved");
  // A server without P-17 answers without the flag: still a plain save.
  assert.equal(saveOutcome({ key: "CP-1", created: false }), "saved");
});

test("before and after values read as words, never as an empty cell", () => {
  assert.equal(changeValueText(null), "–");
  assert.equal(changeValueText(""), "–");
  assert.equal(changeValueText(750000), "750000");
  assert.equal(changeValueText(["TTF", "THE"]), "TTF, THE");
  assert.equal(changeValueText([]), "–");
  assert.equal(changeValueText(true, { yes: "是", no: "否" }), "是");
});

test("only open proposals of the kind mark a row as awaiting approval", () => {
  const found = pendingByTarget(
    [
      change({}),
      change({ change_id: "chg-2", target_key: "CP-2", state: "approved" }),
      change({ change_id: "chg-3", kind: "trader_mandate", target_key: "M-1" }),
    ],
    "credit_line",
  );
  assert.deepEqual([...found.keys()], ["CP-1"]);
  assert.equal(pendingByTarget(null, "credit_line").size, 0);
});

test("provenance names who set a figure and who approved it, or says nobody did", () => {
  const approved = provenanceParts({
    second_approval: true,
    set_by: "maker",
    set_by_name: "Maker",
    set_at_utc: "2026-11-20T09:00:00+00:00",
    approved_by: "checker",
    approved_by_name: "",
    approved_at_utc: "2026-11-20T10:00:00+00:00",
    change_id: "chg-1",
    reason: "annual review",
  });
  assert.deepEqual(approved, {
    kind: "approved",
    value: { setBy: "Maker", approvedBy: "checker", at: "2026-11-20T10:00:00+00:00" },
  });
  const single = provenanceParts({
    second_approval: false,
    set_by: "admin",
    set_by_name: null,
    set_at_utc: null,
    approved_by: null,
    approved_by_name: null,
    approved_at_utc: null,
    change_id: null,
    reason: null,
  });
  assert.equal(single?.kind, "single");
  assert.equal(provenanceParts(undefined), null);
});

test("the longest-waiting proposal is on top; decided changes newest first", () => {
  const ordered = orderChanges([
    change({ change_id: "late", proposed_at_utc: "2026-11-21T09:00:00+00:00" }),
    change({ change_id: "done", state: "approved", decided_at_utc: "2026-11-22T09:00:00+00:00" }),
    change({ change_id: "early", proposed_at_utc: "2026-11-19T09:00:00+00:00" }),
  ]);
  assert.deepEqual(ordered.map((item) => item.change_id), ["early", "late", "done"]);
});

test("every refusal the change endpoints answer has its own sentence in both languages", () => {
  const known = changeErrorKey({ code: "four_eyes_required", message: "..." });
  assert.equal(known, "changes.error.four_eyes_required");
  assert.equal(changeErrorKey({ code: "something_else" }), null);
  assert.equal(changeErrorKey("text"), null);
  for (const code of [
    "four_eyes_required",
    "own_mandate",
    "segregation_of_duties",
    "change_pending",
    "change_stale",
    "note_required",
  ]) {
    assert.ok((en as Record<string, string>)[`changes.error.${code}`], code);
  }
});

test("the screens that make a governed change show the proposed state and the figure's provenance", () => {
  const limits = read("components/RiskLimitsPanel.tsx");
  assert.match(limits, /changes\.proposed/);
  assert.match(limits, /change_reason/);
  assert.match(limits, /<FigureProvenance/);
  const hedge = read("components/DealHedgeApprovalsPanel.tsx");
  assert.match(hedge, /changes\.awaiting/);
  assert.match(hedge, /<FigureProvenance/);
  assert.match(read("components/opportunities/FirmMarksGrid.tsx"), /opportunities\.marks\.proposed/);
  const panel = read("components/PendingChangesPanel.tsx");
  // Approver actions are the shared Button, and the reject needs a reason.
  assert.match(panel, /from "@\/components\/ui"/);
  assert.match(panel, /disabled=\{busy \|\| !note\.trim\(\)\}/);
  assert.doesNotMatch(panel, /<button/);
  assert.match(read("components/PortfolioWorkspace.tsx"), /<PendingChangesPanel/);
  assert.match(read("components/pending-changes.css"), /@layer ds-components/);
});
