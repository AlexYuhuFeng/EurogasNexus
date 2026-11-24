/**
 * The cargo board's pure logic (QA-L-05): sorting and pinning, the header strip's sums, the
 * keyboard map, import age, unit conversion, the energy waterfall, send-out by month, the
 * suggestion arithmetic, the hedge editor's validation, the what-if table and the palette's
 * cargo commands.
 */
import assert from "node:assert/strict";
import test from "node:test";

import type { CargoPlanBodyDTO, CargoPlanBoardLineDTO, CargoPlanMonthDTO, CargoPlanSuggestionDTO } from "../src/api/client.ts";
import {
  boardKeyAction,
  convertEnergy,
  countdown,
  countdownText,
  coverTone,
  endOfDayMs,
  energyWaterfall,
  etaChangeHours,
  headerStrip,
  hedgeRowsCoveringPhysical,
  hedgeRowsFrom,
  importAge,
  isPinned,
  sendOutByMonth,
  sendOutGap,
  slotBar,
  slotChoices,
  sortCargoBoard,
  statusTone,
  suggestionArithmetic,
  suggestionsByDue,
  validateHedges,
  whatIfRows,
  MAX_HEDGE_LEGS,
} from "../src/app/model/cargoBoardModel.ts";
import { cargoCommands, filterPaletteCommands } from "../src/app/experience/commandPalette.ts";

const suggestion = (patch: Partial<CargoPlanSuggestionDTO>): CargoPlanSuggestionDTO => ({
  kind: "sell",
  text: "",
  hub: "THE",
  from_month: "2026-12",
  to_month: null,
  mwh: null,
  due_utc: null,
  ...patch,
});

const month = (patch: Partial<CargoPlanMonthDTO>): CargoPlanMonthDTO => ({
  hub: "THE",
  month: "2026-12",
  physical_mwh: 0,
  hedge_mwh: 0,
  net_mwh: 0,
  cover_ratio: null,
  last_trading_day: "2026-11-27",
  trading: true,
  ...patch,
});

const line = (patch: Partial<CargoPlanBoardLineDTO>): CargoPlanBoardLineDTO => ({
  cargo_id: "C-1",
  slot_status: "on_time",
  eta_utc: "2026-12-01T06:00:00+00:00",
  months: [],
  next_action: null,
  next_expiry: null,
  ...patch,
});

const plan = (patch: Partial<CargoPlanBodyDTO>): CargoPlanBodyDTO => ({
  cargo_id: "C-1",
  slot_status: "on_time",
  berth_utc: "2026-12-01T06:00:00+00:00",
  wait_hours: 0,
  days_to_berth: 7,
  boil_off_mwh: 1_000,
  gas_in_kind_mwh: 500,
  delivered_mwh: 98_500,
  energy_at_eta_mwh: 99_000,
  send_out: [],
  months: [],
  demurrage_hours: 0,
  demurrage_cost: null,
  suggestions: [],
  ...patch,
});

test("missed and no-slot rows pin to the top; then next due, then ETA, then id; unplanned last", () => {
  const lines = [
    line({ cargo_id: "OK-LATE", next_action: suggestion({ due_utc: "2026-11-30T12:00:00Z" }) }),
    line({ cargo_id: "BROKEN", error: "cargo_incomplete", slot_status: undefined }),
    line({ cargo_id: "NOSLOT", slot_status: "no_slot" }),
    line({ cargo_id: "OK-SOON", next_action: suggestion({ due_utc: "2026-11-25T12:00:00Z" }) }),
    line({ cargo_id: "MISSED", slot_status: "missed" }),
    line({ cargo_id: "OK-NODUE-B", eta_utc: "2026-12-03T00:00:00Z" }),
    line({ cargo_id: "OK-NODUE-A", eta_utc: "2026-12-02T00:00:00Z" }),
  ];
  assert.deepEqual(
    sortCargoBoard(lines).map((item) => item.cargo_id),
    ["MISSED", "NOSLOT", "OK-SOON", "OK-LATE", "OK-NODUE-A", "OK-NODUE-B", "BROKEN"],
  );
  assert.equal(isPinned({ slot_status: "missed" }), true);
  assert.equal(isPinned({ slot_status: "no_slot" }), true);
  assert.equal(isPinned({ slot_status: "waiting" }), false);
  assert.equal(statusTone({ slot_status: "missed" }), "breach");
  assert.equal(statusTone({ slot_status: "waiting" }), "watch");
  assert.equal(statusTone({ slot_status: "on_time", error: "x" }), "stale");
  // Sorting never mutates what the read returned.
  assert.equal(lines[0].cargo_id, "OK-LATE");
});

test("the header strip sums open hub months over cargoes and counts what needs action today", () => {
  const dayEnd = Date.parse("2026-11-24T22:59:59.999Z");
  const strip = headerStrip(
    [
      line({
        cargo_id: "A",
        months: [month({ net_mwh: 60_000 }), month({ month: "2027-01", net_mwh: 0.4 })],
        next_action: suggestion({ due_utc: "2026-11-24T15:00:00Z" }),
        next_expiry: suggestion({ kind: "deadline", due_utc: "2026-11-27T16:00:00Z" }),
      }),
      line({
        cargo_id: "B",
        months: [month({ net_mwh: -20_000 }), month({ hub: "TTF", net_mwh: 5_000 })],
        next_action: suggestion({ due_utc: "2026-11-26T15:00:00Z" }),
        next_expiry: suggestion({ kind: "deadline", hub: "TTF", due_utc: "2026-11-26T16:00:00Z" }),
      }),
      line({ cargo_id: "C", slot_status: "no_slot" }),
      line({ cargo_id: "D", error: "terminal_hub_unknown", months: [month({ net_mwh: 1e9 })] }),
    ],
    dayEnd,
  );
  // THE Dec: 60 000 - 20 000 from two cargoes; the 0.4 MWh January cell is noise and dropped;
  // the cargo with no plan adds nothing.
  assert.deepEqual(strip.open, [
    { hub: "THE", month: "2026-12", net_mwh: 40_000, cargoes: 2 },
    { hub: "TTF", month: "2026-12", net_mwh: 5_000, cargoes: 1 },
  ]);
  assert.deepEqual(strip.nextExpiry, { cargo_id: "B", hub: "TTF", month: "2026-12", due_utc: "2026-11-26T16:00:00Z" });
  // A (due today) and C (pinned); B is due on the 26th.
  assert.equal(strip.needActionToday, 2);
  assert.equal(strip.unplanned, 1);
});

test("the end of the reader's day is local midnight", () => {
  const now = Date.parse("2026-11-24T10:00:00Z");
  assert.equal(new Date(endOfDayMs(now, "UTC") + 1).toISOString(), "2026-11-25T00:00:00.000Z");
  // Berlin is UTC+1 in November.
  assert.equal(new Date(endOfDayMs(now, "Europe/Berlin") + 1).toISOString(), "2026-11-24T23:00:00.000Z");
});

test("the board's keys: arrows move, Enter opens, w what-if, h hedges; modified keys are the shell's", () => {
  assert.equal(boardKeyAction({ key: "ArrowUp" }), "up");
  assert.equal(boardKeyAction({ key: "ArrowDown" }), "down");
  assert.equal(boardKeyAction({ key: "Enter" }), "open");
  assert.equal(boardKeyAction({ key: "w" }), "what_if");
  assert.equal(boardKeyAction({ key: "H" }), "hedge");
  assert.equal(boardKeyAction({ key: "h", ctrlKey: true }), null);
  assert.equal(boardKeyAction({ key: "w", metaKey: true }), null);
  assert.equal(boardKeyAction({ key: "x" }), null);
});

test("import age against the stated cadence, and the ETA move of the last change", () => {
  const now = Date.parse("2026-11-24T12:00:00Z");
  assert.deepEqual(importAge({ imported_at_utc: "2026-11-24T02:00:00Z", source_system: "ETRM_CSV" }, now), { hours: 10, cadenceHours: 24, stale: false });
  assert.equal(importAge({ imported_at_utc: "2026-11-24T02:00:00Z", source_system: "KPLER" }, now)?.stale, true);
  assert.equal(importAge({ imported_at_utc: null, source_system: "ETRM_CSV" }, now), null);
  const changed = { at_utc: "2026-11-24T08:00:00Z", kinds: ["eta"], by: "import ETRM_CSV", eta_before_utc: "2026-11-30T06:00:00Z" };
  assert.equal(etaChangeHours({ eta_utc: "2026-12-01T06:00:00Z", changed }), 24);
  assert.equal(etaChangeHours({ eta_utc: "2026-12-01T06:00:00Z", changed: { ...changed, kinds: ["energy"] } }), null);
});

test("energy units: GWh, TBtu and million therms from MWh", () => {
  assert.equal(convertEnergy(1_000_000, "GWh"), 1_000);
  assert.ok(Math.abs(convertEnergy(1_000_000, "TBtu") - 3.412141633) < 1e-9);
  assert.ok(Math.abs(convertEnergy(1_000_000, "Mth") - 34.12141633) < 1e-9);
});

test("cover chips, countdowns and the slot bar", () => {
  assert.equal(coverTone(month({ cover_ratio: 1 })), "ok");
  assert.equal(coverTone(month({ cover_ratio: 0.6 })), "watch");
  assert.equal(coverTone(month({ cover_ratio: 1.2 })), "watch");
  assert.equal(coverTone(month({ cover_ratio: 0.1 })), "breach");
  // Hedged with nothing physical there: a naked hedge.
  assert.equal(coverTone(month({ cover_ratio: null, hedge_mwh: -5_000 })), "breach");
  const now = Date.parse("2026-11-24T12:00:00Z");
  assert.equal(countdownText(countdown(now + (2 * 24 + 4) * 3_600_000, now)), "2d 4h");
  assert.equal(countdownText(countdown(now + 200 * 60_000, now)), "3h 20m");
  assert.equal(countdown(now - 45 * 60_000, now).overdue, true);
  assert.equal(countdownText(countdown(now - 45 * 60_000, now)), "45m");
  const slot = { slot_id: "S", terminal: "T", window_start_utc: "2026-12-01T00:00:00Z", window_end_utc: "2026-12-02T00:00:00Z", send_out_mwh_per_day: 1 };
  assert.equal(slotBar({ eta_utc: "2026-12-01T12:00:00Z", slot })?.position, "inside");
  assert.equal(slotBar({ eta_utc: "2026-12-03T00:00:00Z", slot })?.position, "after");
  assert.equal(slotBar({ eta_utc: "2026-12-03T00:00:00Z", slot: null }), null);
});

test("the energy waterfall reconciles loaded to delivered, and stops aboard without a berth", () => {
  const berthed = energyWaterfall(100_000, plan({}));
  assert.deepEqual(berthed.map((step) => step.id), ["loaded", "boil_off", "gas_in_kind", "delivered"]);
  const deltas = berthed.filter((step) => step.kind === "delta").reduce((sum, step) => sum + step.value, 0);
  assert.equal(berthed[0].value + deltas, berthed[berthed.length - 1].value);
  const missed = energyWaterfall(100_000, plan({ slot_status: "missed", gas_in_kind_mwh: 0, delivered_mwh: 0 }));
  assert.deepEqual(missed.map((step) => step.id), ["loaded", "boil_off", "aboard"]);
  assert.equal(missed[2].value, 99_000);
  // No loaded energy in the import: the waterfall starts at the boil-off.
  assert.equal(energyWaterfall(null, plan({}))[0].id, "boil_off");
});

test("send-out by gas day splits at the month boundary and adds up to the delivered energy", () => {
  const body = plan({
    delivered_mwh: 300,
    send_out: [
      { gas_day: "2026-11-30", mwh: 100 },
      { gas_day: "2026-12-01", mwh: 100 },
      { gas_day: "2026-12-02", mwh: 100 },
    ],
  });
  const { days, series } = sendOutByMonth(body);
  assert.deepEqual(days, ["2026-11-30", "2026-12-01", "2026-12-02"]);
  assert.deepEqual(series, [
    { month: "2026-11", values: [100, null, null] },
    { month: "2026-12", values: [null, 100, 100] },
  ]);
  assert.equal(sendOutGap(body), 0);
  assert.equal(sendOutGap({ ...body, delivered_mwh: 310 }), -10);
});

test("suggestions by due time, each with the sum behind it", () => {
  const ordered = suggestionsByDue([
    suggestion({ kind: "deadline", due_utc: "2026-11-27T16:00:00Z" }),
    suggestion({ kind: "sell", due_utc: null }),
    suggestion({ kind: "roll", due_utc: "2026-11-25T16:00:00Z" }),
  ]);
  assert.deepEqual(ordered.map((item) => item.kind), ["roll", "deadline", "sell"]);
  const months = [
    month({ month: "2026-12", physical_mwh: 50_000, hedge_mwh: -100_000, net_mwh: -50_000 }),
    month({ month: "2027-01", physical_mwh: 50_000, hedge_mwh: 0, net_mwh: 50_000 }),
  ];
  const roll = suggestionArithmetic(suggestion({ kind: "roll", from_month: "2026-12", to_month: "2027-01", mwh: 50_000 }), months);
  assert.equal(roll?.key, "lng.cargo.arith.roll");
  assert.equal(roll?.values.fromNet, -50_000);
  assert.equal(roll?.values.toNet, 50_000);
  assert.equal(roll?.values.mwh, 50_000);
  const net = suggestionArithmetic(suggestion({ kind: "sell", from_month: "2027-01" }), months);
  assert.deepEqual(net, { key: "lng.cargo.arith.net", values: { month: "2027-01", physical: 50_000, hedge: 0, net: 50_000 } });
  assert.equal(suggestionArithmetic(suggestion({ kind: "find_slot" }), months)?.values.hedge, -100_000);
  assert.equal(suggestionArithmetic(suggestion({ kind: "demurrage" }), months, { demurrage_hours: 12.4, demurrage_cost: null })?.key, "lng.cargo.arith.demurrage_hours");
  // A suggestion about a month the plan does not hold has no sum to show.
  assert.equal(suggestionArithmetic(suggestion({ kind: "sell", from_month: "2028-01" }), months), null);
});

test("the hedge editor validates every row before the PUT, and starts from the physical", () => {
  const ok = validateHedges([{ hub: "the", month: "2026-12", mwh: "-50 000", reference: " DEAL-1 " }], ["THE", "TTF"]);
  assert.deepEqual(ok.legs, [{ hub: "THE", month: "2026-12", mwh: -50_000, reference: "DEAL-1" }]);
  const bad = validateHedges(
    [
      { hub: "XXX", month: "2026-13", mwh: "abc", reference: "" },
      { hub: "THE", month: "2026-12", mwh: "0", reference: "r".repeat(161) },
      { hub: "THE", month: "2026-12", mwh: "1", reference: "A" },
      { hub: "THE", month: "2026-12", mwh: "2", reference: "A" },
    ],
    ["THE"],
  );
  assert.equal(bad.legs, null);
  assert.deepEqual(bad.rows, [["hub_unknown", "month_invalid", "mwh_invalid"], ["mwh_zero", "reference_long"], [], ["duplicate"]]);
  assert.equal(validateHedges([{ hub: "THE", month: "2026-12", mwh: "2e7", reference: "" }], ["THE"]).rows[0][0], "mwh_invalid");
  const many = Array.from({ length: MAX_HEDGE_LEGS + 1 }, (_, index) => ({ hub: "THE", month: "2026-12", mwh: "1", reference: `R${index}` }));
  assert.equal(validateHedges(many, ["THE"]).tooMany, true);
  assert.equal(validateHedges(many, ["THE"]).legs, null);
  assert.deepEqual(hedgeRowsFrom(null), [{ hub: "", month: "", mwh: "", reference: "" }]);
  assert.deepEqual(hedgeRowsCoveringPhysical([month({ physical_mwh: 49_999.6 }), month({ month: "2027-01", physical_mwh: 0 })]), [
    { hub: "THE", month: "2026-12", mwh: "-50000", reference: "" },
  ]);
});

test("the what-if reads as before and after; only free slots are offered", () => {
  const before = plan({ demurrage_hours: 0 });
  const after = plan({ slot_status: "waiting", boil_off_mwh: 1_200, delivered_mwh: 98_300, demurrage_hours: 12, demurrage_cost: 50_000 });
  const rows = whatIfRows({
    headline: "",
    boil_off_change_mwh: 200,
    delivered_change_mwh: -200,
    before,
    after,
    months: [{ hub: "THE", month: "2026-12", physical_before_mwh: 98_500, physical_after_mwh: 98_300, change_mwh: -200 }],
  });
  const byId = Object.fromEntries(rows.map((row) => [row.id, row]));
  assert.equal(byId.status.after, "waiting");
  assert.equal(byId.delivered.change, -200);
  assert.equal(byId.demurrage_cost.change, null);
  assert.equal(byId["month:THE:2026-12"].change, -200);
  assert.deepEqual(whatIfRows({ headline: "", boil_off_change_mwh: 0, delivered_change_mwh: 0, before }), []);
  const choices = slotChoices([
    { slot_id: "B", free: true, window_start_utc: "2026-12-05T00:00:00Z" },
    { slot_id: "H", free: false, window_start_utc: "2026-12-01T00:00:00Z" },
    { slot_id: "A", free: true, window_start_utc: "2026-12-02T00:00:00Z" },
  ]);
  assert.deepEqual(choices.free.map((slot) => slot.slot_id), ["A", "B"]);
  assert.deepEqual(choices.held.map((slot) => slot.slot_id), ["H"]);
});

test("the palette finds a cargo by id, vessel or IMO, and never lists cargoes for an empty query", () => {
  const commands = cargoCommands([
    { cargo_id: "CRG-0042", vessel_name: "Arctic Dawn", vessel_imo: "9876543", destination_terminal: "Gate" },
    { cargo_id: "CRG-0043", vessel_name: null, vessel_imo: null },
  ]);
  assert.equal(commands[0].target.cargo, "CRG-0042");
  assert.equal(commands[0].target.modeTask, "cargoes");
  const label = (command: (typeof commands)[number]) => command.label ?? command.labelKey;
  assert.deepEqual(filterPaletteCommands(commands, "arctic", label).map((item) => item.id), ["cargo.CRG-0042"]);
  assert.deepEqual(filterPaletteCommands(commands, "9876543", label).map((item) => item.id), ["cargo.CRG-0042"]);
  assert.deepEqual(filterPaletteCommands(commands, "crg-0043", label).map((item) => item.id), ["cargo.CRG-0043"]);
  assert.deepEqual(filterPaletteCommands(commands, "", label), []);
});
