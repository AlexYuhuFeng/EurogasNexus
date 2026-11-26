import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { lineageNames } from "../src/app/model/lineageNames.ts";
import { warningLabel } from "../src/app/warningLabel.ts";
import { ladderNotes } from "../src/app/model/ladderNotes.ts";

// Server warnings are stable codes (`CODE:detail`) the client translates (AGENTS rule 17): a code
// the locale files did not know used to fall back to its own words in English, in Chinese too.

const read = (path: string) => readFileSync(new URL(path, import.meta.url), "utf8");
const en = JSON.parse(read("../src/i18n/en.json")) as Record<string, string>;
const zh = JSON.parse(read("../src/i18n/zh.json")) as Record<string, string>;
// The check that every server code has both languages reads the server, so it lives server-side
// (tests/unit/test_server_text_in_client_locales.py): a client source does not reference the
// backend (architecture fitness FF1).

test("a warning reads in words; an unknown code falls back to enum words, then the humanised code", () => {
  const table: Record<string, string> = { "warning.contract_index_priced": "合同按指数定价", "enum.quote_stale": "报价已过时" };
  const t = (key: string, options?: Record<string, unknown>) => table[key] ?? (options?.defaultValue as string | undefined) ?? key;
  assert.equal(warningLabel("CONTRACT_INDEX_PRICED:demo-tender-skarv:NBP", t), "合同按指数定价: demo-tender-skarv · NBP");
  assert.equal(warningLabel("QUOTE_STALE", t), "报价已过时");
  assert.equal(warningLabel("SOMETHING_NEW", t), "Something new");
});

test("lineage shows the records a trader knows by name; evidence lines and bare ids stay in the disclosure", () => {
  const t = (key: string, options?: Record<string, unknown>) => (options?.name ? `${options.name} price` : key === "lineage.kind.contract" ? "Contract" : key);
  const names = lineageNames(
    [
      "upstream_resource_contract:demo-brae-10",
      "upstream_resource_contract:demo-unknown",
      "ENTSOG TP [25-11-2026] (a source line with its address)",
      "DEMO_Sim:simulated-tariff",
      "published: 10.512 EUR/(kWh/h)/y",
    ],
    { resources: new Map([["demo-brae-10", "Brae North supply (St Fergus)"]]) },
    t,
  );
  assert.deepEqual(names.filter((entry) => entry.named).map((entry) => entry.name), ["Brae North supply (St Fergus) contract"]);
  assert.equal(names.length, 5, "every reference stays available for the identifiers disclosure");
});

test("the position ladder's notes are said from their codes, also when an older server sends only sentences", () => {
  const t = (key: string, options?: Record<string, unknown>) => (key.startsWith("warning.") ? `${key}${JSON.stringify(options ?? {})}` : key);
  assert.deepEqual(
    ladderNotes({ warnings: ["x"], notes: [{ code: "VAR_SHORT_HISTORY", params: { count: 4 } }] }, t),
    ['warning.var_short_history{"count":4}'],
  );
  assert.deepEqual(
    ladderNotes({ warnings: ["3 leg-months have no mark or no price and are not valued.", "Something else entirely."] }, t),
    ['warning.leg_months_not_valued{"count":3}', "Something else entirely."],
  );
});
