/**
 * What a person is called (owner bug 2026-11-19: the demo trader was shown as "Analyst", its
 * authority role). Every demo and test identity shows the function its name implies, in English
 * and Chinese; authority roles appear only in Admin → Access as permissions.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { personFunction, personFunctionOfJob } from "../src/app/experience/roleComposition.ts";
import type { CurrentUserDTO } from "../src/api/client.ts";

const read = (path: string) => readFileSync(new URL(path, import.meta.url), "utf8");
const en = JSON.parse(read("../src/i18n/en.json")) as Record<string, string>;
const zh = JSON.parse(read("../src/i18n/zh.json")) as Record<string, string>;

/** The demo testers as the start script declares them: name, roles, job functions. */
function testers(): { name: string; roles: string[]; functions: string[] }[] {
  const source = read("../../../scripts/demo/start_public_demo.py");
  const block = source.slice(source.indexOf("TESTERS"), source.indexOf("TESTER_NAMES"));
  const rows: { name: string; roles: string[]; functions: string[] }[] = [];
  const pattern = /\(\s*"(demo\.[a-z.]+)",\s*"[^"]*",\s*"[A-Z]+",\s*\(([^)]*)\),\s*\(([^)]*)\),\s*"[A-Z]+",?\s*\)/g;
  for (const match of block.matchAll(pattern)) {
    const list = (text: string) => [...text.matchAll(/"([A-Z_]+)"/g)].map((item) => item[1]);
    rows.push({ name: match[1], roles: list(match[2]), functions: list(match[3]) });
  }
  return rows;
}

/** The name each identity implies. */
const IMPLIED: Record<string, string> = {
  "demo.trader": "Trader",
  "demo.nl.trader": "Trader",
  "demo.analyst": "Analyst",
  "demo.risk": "Risk manager",
  "demo.manager": "Desk head",
  "demo.finance": "Finance",
  "demo.compliance": "Compliance",
  "demo.ops": "Administrator",
  "demo.originator": "Originator",
  "demo.operations": "Operations",
  "demo.admin": "Administrator",
};

function user(roles: string[], functions: string[]): CurrentUserDTO {
  return {
    principal_id: "p",
    role: roles[0],
    roles,
    permissions: [],
    experience: { commercial_capabilities: ["market.read"], declared_job_functions: functions, functional_assignments: functions, unsatisfied_job_functions: [] },
  } as unknown as CurrentUserDTO;
}

test("every demo identity shows the function its name implies, never its authority role", () => {
  const rows = testers();
  assert.deepEqual(rows.map((row) => row.name).sort(), Object.keys(IMPLIED).sort());
  for (const row of rows) {
    const fn = personFunction(user(row.roles, row.functions));
    assert.ok(fn, row.name);
    assert.equal(en[`person.function.${fn}`], IMPLIED[row.name], row.name);
    assert.ok(zh[`person.function.${fn}`] && zh[`person.function.${fn}`] !== en[`person.function.${fn}`], `${row.name} zh`);
  }
});

test("the account menu, Access review and the users table show the function; permissions only in Admin → Access", () => {
  const menu = read("../src/components/HeaderPreferencesMenu.tsx");
  assert.doesNotMatch(menu, /\{currentUser\.role\}/);
  assert.match(menu, /person\.function\./);
  const access = read("../src/components/AccessCenter.tsx");
  assert.doesNotMatch(access, /· \$\{currentUser\.role\}/);
  const users = read("../src/components/AccessUsers.tsx");
  assert.match(users, /access\.users\.function/);
  assert.match(users, /access\.users\.permissions/);
  assert.equal(personFunctionOfJob("TRADER"), "trader");
  assert.equal(personFunctionOfJob("ANALYST"), null);
  // Without a declared function the person is still not their authority role.
  assert.equal(personFunction(user(["ANALYST"], [])), "desk_head");
});
