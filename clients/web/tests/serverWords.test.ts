/**
 * Server text in the reader's language (review 2026-11-26): engine blockers, Today's warnings
 * and empty grid columns. No raw key, id or English diagnostic reaches a Chinese screen.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { columnsWithValues } from "../src/components/ui/dataGridModel.ts";
import { serverNoteText, shownServerNotes } from "../src/app/model/serverNotes.ts";
import { blockerText, periodLabel, subjectWords } from "../src/app/model/opportunitiesModel.ts";

const en = JSON.parse(readFileSync(new URL("../src/i18n/en.json", import.meta.url), "utf8")) as Record<string, string>;
const zh = JSON.parse(readFileSync(new URL("../src/i18n/zh.json", import.meta.url), "utf8")) as Record<string, string>;

/** A minimal i18next stand-in: key lookup, `{{name}}` interpolation, `_one/_other`, defaultValue. */
function translator(dict: Record<string, string>) {
  return (key: string, options: Record<string, unknown> = {}): string => {
    const count = options.count as number | undefined;
    const template = (count !== undefined && dict[`${key}_${count === 1 ? "one" : "other"}`]) || dict[key] || (options.defaultValue as string) || key;
    return template.replace(/\{\{(\w+)\}\}/g, (_m, name: string) => String(options[name] ?? ""));
  };
}
const tEn = translator(en);
const tZh = translator(zh);

test("a blocker reads in words, never its catalogue key", () => {
  const blocked = {
    code: "input_missing",
    subject: "balancing.long_discount",
    text: "Cannot evaluate: balancing.long_discount not held.",
    fix: "supply the input",
  };
  const english = blockerText(blocked, tEn, "en");
  assert.equal(english.text, "Cannot evaluate: Cash-out discount when long (under day-ahead) not held.");
  assert.equal(english.fix, "Supply the input.");
  const chinese = blockerText(blocked, tZh, "zh-CN");
  assert.equal(chinese.text, "无法评估：未持有多头时的平衡结算折价（低于日前）。");
  assert.doesNotMatch(chinese.text + chinese.fix, /[A-Za-z_]{4,}/);
});

test("a stale blocker from an older server keeps its detail, translated", () => {
  const blocked = {
    code: "input_stale",
    subject: "ESTR fixing of 2026-11-24",
    text: "Cannot evaluate: ESTR fixing of 2026-11-24 is stale (ESTR fixing of 2026-11-24: as of 2026-11-24).",
    fix: "refresh it",
  };
  assert.equal(blockerText(blocked, tZh, "zh").text, "无法评估：ESTR 定盘（2026-11-24）已过时（截至 2026-11-24）。");
  // The detail does not name the subject a second time.
  assert.equal(
    blockerText({ ...blocked, detail: "ESTR fixing of 2026-11-24: as of 2026-11-24" }, tEn, "en").text,
    "Cannot evaluate: ESTR fixing of 2026-11-24 is stale (as of 2026-11-24).",
  );
});

test("a sentence the engine did not template is generic in Chinese, verbatim in English", () => {
  const blocked = { code: "input_missing", subject: "Point X", text: "Cannot evaluate: no per-MWh tariff.", fix: "" };
  assert.equal(blockerText(blocked, tZh, "zh").text, zh["opportunities.blocked.other"]);
  assert.equal(blockerText(blocked, tEn, "en").text, blocked.text);
});

test("a subject's position side and a day are written in the reader's language", () => {
  assert.equal(subjectWords("NBP · long", tZh), "NBP · 多头");
  assert.equal(subjectWords("Haldor supply (Easington)", tZh), "Haldor supply (Easington)");
  assert.equal(periodLabel("2026-11-26", "zh-CN"), "11月26日");
  assert.equal(periodLabel("2026-11-26", "en"), "26 Nov");
  assert.equal(periodLabel("2026-12", "zh-CN"), "Dec-26");
});

test("every assumption label exists in both languages", () => {
  for (const key of Object.keys(en).filter((item) => item.startsWith("assumption.label."))) {
    assert.ok(zh[key], `${key} missing in zh`);
  }
});

test("Today's warnings: method notes are left out, failures are said in words", () => {
  const notes = shownServerNotes([
    "contract demo-tender-skarv: price floats with NBP day-ahead; volume only on the ladder",
    "contract demo-mspa-atlantic-cn07: an FOB cargo is not on a European hub until it is sold or discharged",
    "book: not available (OperationalError)",
    "book: not available (OperationalError)",
  ]);
  assert.deepEqual(notes, ["book: not available (OperationalError)"]);
  assert.equal(serverNoteText(notes[0], tEn, "en"), "The book could not be read.");
  assert.equal(serverNoteText(notes[0], tZh, "zh"), "账簿未能读取。");
  assert.equal(serverNoteText("strategy findings unavailable: KeyError", tZh, "zh"), zh["server_note.other"]);
  assert.equal(serverNoteText("contract demo-x: gas year '2025' not understood", tEn, "en"), en["server_note.other"]);
});

test("a grid leaves out a column no row has a value in", () => {
  type Row = { name: string; last: number | null; avg: number | null };
  const rows: Row[] = [{ name: "DE", last: null, avg: 1 }, { name: "NL", last: null, avg: null }];
  const columns = [
    { id: "name", rowHeader: true, value: (row: Row) => row.name },
    { id: "last", value: (row: Row) => row.last },
    { id: "avg", value: (row: Row) => row.avg },
    { id: "kept", keepWhenEmpty: true, value: (row: Row) => row.last },
    { id: "drawn", render: () => null, value: (row: Row) => row.last },
  ];
  assert.deepEqual(columnsWithValues(columns, rows).map((column) => column.id), ["name", "avg", "kept", "drawn"]);
  assert.equal(columnsWithValues(columns, []).length, columns.length);
});

test("a server notice is said by its code, with its params, English as the fallback", async () => {
  const { serverWarningText, serverNotices } = await import("../src/app/warningLabel.ts");
  const floating = { code: "contract_floating", params: { contract: "demo-x", index: "NBP DA" }, text: "contract demo-x: …" };
  const names = new Map([["demo-x", "Skarv West tender"]]);
  assert.equal(serverWarningText(floating, tZh, names), "Skarv West tender：价格随 NBP DA 浮动；头寸阶梯仅计气量");
  assert.equal(serverWarningText({ code: "no_terminal_terms", text: "x" }, tZh), zh["server.sentence.no_terminal_terms"]);
  assert.equal(serverWarningText({ code: "brand_new_code", text: "A new English line." }, tEn), "A new English line.");
  assert.deepEqual(serverNotices({ warnings: ["a"], notices: [] }), ["a"]);
  assert.deepEqual(serverNotices({ warnings: ["a"], notices: [floating] }), [floating]);
});

test("an opportunity's claim and arithmetic rows are said from their data", async () => {
  const { claimText, legLabel } = await import("../src/app/model/opportunitiesModel.ts");
  const row = {
    claim: "NBP gas day 2026-11-26: long residual …",
    claim_key: "sell_down.residual",
    claim_fields: { hub: "NBP", gas_day: "2026-11-26", side: "long", volume: "23,000", relation: "below", penalty: "1.20 GBP/MWh", value: "GBP 27,600.00" },
  };
  assert.equal(
    claimText(row, tZh),
    "NBP 燃气日 2026-11-26：多头余量 23,000 MWh 未平；按交易台 1.20 GBP/MWh 的平衡结算价（低于日前价）计，成本 GBP 27,600.00。",
  );
  assert.equal(claimText({ claim: "As sent." }, tZh), "As sent.");
  assert.equal(legLabel({ label_key: "locational.volume", label: "Volume 1 MWh/d x 3 d", label_params: { mwh_d: "1", days: "3" } }, tZh), "量 1 MWh/d × 3 天");
  // An older server sends no params: a template that names values keeps the English label.
  assert.equal(legLabel({ label_key: "locational.volume", label: "Volume 1 MWh/d x 3 d" }, tZh), "Volume 1 MWh/d x 3 d");
  assert.equal(legLabel({ label_key: "locational.gross", label: "Gross spread" }, tZh), "毛价差");
  assert.equal(legLabel({ label_key: "capacity.sunk", label: "exit at X: capacity held" }, tZh), "exit at X: capacity held");
});
