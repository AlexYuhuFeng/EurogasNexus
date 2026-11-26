import assert from "node:assert/strict";
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

import { lineageNames } from "../src/app/model/lineageNames.ts";
import { warningLabel } from "../src/app/warningLabel.ts";
import { ladderNotes } from "../src/app/model/ladderNotes.ts";

// Server warnings are stable codes (`CODE:detail`) the client translates (AGENTS rule 17, BRIEF:
// "server-produced warnings render through i18n from a code"). A code the locale files do not
// know used to fall back to its own words in English ("contract index priced"), in the Chinese
// interface too. This test reads the codes the server appends to its warning, blocker and
// missing-input lists and requires a `warning.<code>` line for each in both languages.

const read = (path: string) => readFileSync(new URL(path, import.meta.url), "utf8");
const en = JSON.parse(read("../src/i18n/en.json")) as Record<string, string>;
const zh = JSON.parse(read("../src/i18n/zh.json")) as Record<string, string>;
const serverRoot = fileURLToPath(new URL("../../../src/eurogas_nexus", import.meta.url));

function pythonFiles(dir: string): string[] {
  const out: string[] = [];
  for (const name of readdirSync(dir)) {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) out.push(...pythonFiles(path));
    else if (name.endsWith(".py")) out.push(path);
  }
  return out;
}

/** Codes the server writes into a warnings / blockers / missing list (`warnings.append("CODE:...")`). */
function serverWarningCodes(): Set<string> {
  const codes = new Set<string>();
  const pattern = /(?:warning|blocker|missing|issue)s?\w*\.(?:append|add)\(\s*f?"([A-Z][A-Z0-9_]{3,})(?=[:"{])/g;
  for (const file of pythonFiles(serverRoot)) {
    for (const match of readFileSync(file, "utf8").matchAll(pattern)) codes.add(match[1]);
  }
  // Notes declared once on the server (domain/ontology/notes.py `declare("CODE", template)`).
  for (const file of pythonFiles(serverRoot)) {
    for (const match of readFileSync(file, "utf8").matchAll(/\bdeclare\(\s*"([A-Z][A-Z0-9_]+)"/g)) codes.add(match[1]);
  }
  // `TARIFF_STATUS_{status}`: every non-final tariff status (domain/ontology/vocabulary.py).
  codes.delete("TARIFF_STATUS_");
  for (const status of ["INDICATIVE", "PROVISIONAL", "DRAFT", "SIMULATOR_ONLY"]) codes.add(`TARIFF_STATUS_${status}`);
  codes.add("TARIFF_APPLICABILITY_NOT_ASSESSED");
  return codes;
}

test("every warning code the server emits has words in English and Chinese", () => {
  const codes = serverWarningCodes();
  assert.ok(codes.size > 50, `found only ${codes.size} codes; the pattern no longer matches the server`);
  const missing: string[] = [];
  for (const code of codes) {
    const key = `warning.${code.toLowerCase()}`;
    if (!en[key]) missing.push(`en ${key}`);
    if (!zh[key]) missing.push(`zh ${key}`);
    else if (!/\p{Script=Han}/u.test(zh[key])) missing.push(`zh ${key} is not Chinese`);
  }
  assert.deepEqual(missing, []);
});

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
      "ENTSOG TP [25-11-2026] https://transparency.entsog.eu/",
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
