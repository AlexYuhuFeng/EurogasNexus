import assert from "node:assert/strict";
import test from "node:test";
import { financingTranchesForSave } from "../src/app/model/contractDraftModel.ts";

test("complete funding segments are saved; incomplete ones are reported, not dropped silently", () => {
  const result = financingTranchesForSave([
    { lender: " Bank A ", principal: 100, annual_rate_pct: 3, day_count: "ACT/365F" },
    { lender: "Bank B", principal: 200, annual_rate_pct: 2, day_count: "ACT/360" },
    { lender: "", principal: 50, annual_rate_pct: 1, day_count: "ACT/365F" },
    { lender: "Bank C", principal: 0, annual_rate_pct: 1, day_count: "ACT/365F" },
    { lender: "Bank D", principal: 10, annual_rate_pct: null, day_count: "ACT/365F" },
  ]);
  assert.deepEqual(result.tranches, [
    { lender: "Bank A", principal: 100, annual_rate_pct: 3, day_count: "ACT/365F" },
    { lender: "Bank B", principal: 200, annual_rate_pct: 2, day_count: "ACT/360" },
  ]);
  assert.equal(result.incomplete, 3);
});

test("no segments means the single rate applies", () => {
  assert.deepEqual(financingTranchesForSave([]), { tranches: [], incomplete: 0 });
});
