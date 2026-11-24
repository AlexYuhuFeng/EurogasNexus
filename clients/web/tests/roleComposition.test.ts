import assert from "node:assert/strict";
import test from "node:test";

import type { CurrentUserDTO } from "../src/api/client.ts";
import {
  COMPOSITION_IDS,
  JOB_FUNCTION_COMPOSITION,
  JOB_FUNCTION_IDS,
  MAX_SHORTLIST,
  ROLE_COMPOSITIONS,
  ROLE_COMPOSITION_GRANTS_AUTHORITY,
  STRIP_AUDIENCES,
  composedLanding,
  composedShortlist,
  composedTodayRows,
  moreTasks,
  panelDefault,
  placeKey,
  placeVisible,
  resolveComposition,
} from "../src/app/experience/roleComposition.ts";
import { WORK_MODE_GRANTS_AUTHORITY } from "../src/app/experience/workModes.ts";
import { navigationCommands } from "../src/app/experience/commandPalette.ts";
import { visibleModes } from "../src/app/navigation/modeNavigation.ts";

/*
 * The server's role -> permission table (security/authorization.py ROLE_PERMISSIONS). Client
 * tests never read backend sources (FF1); tests/contract/test_role_composition_parity.py
 * proves this copy and JOB_FUNCTION_IDS match the server.
 */
const ROLE_PERMISSIONS: Record<string, string[]> = {
  VIEWER: ["agent.read", "capability.read", "market.read", "me.read", "portfolio.read", "review.read", "runtime.read", "source.read", "strategy.read"],
  SCHEDULER: ["agent.read", "capability.read", "gas_day.record", "market.read", "me.read", "portfolio.read", "review.read", "runtime.read", "source.read", "strategy.read"],
  REVIEWER: ["agent.read", "capability.read", "market.read", "me.read", "portfolio.read", "review.read", "review.record", "runtime.read", "source.read", "strategy.read"],
  ANALYST: ["agent.read", "agent.research", "analysis.query", "capability.invoke", "capability.read", "gas_day.record", "market.read", "me.read", "optimization.run", "portfolio.read", "portfolio.write", "review.read", "runtime.read", "scenario.create", "source.read", "strategy.create", "strategy.edit", "strategy.freeze", "strategy.read", "strategy.retire", "strategy.shadow.manage"],
  OPERATOR: ["agent.read", "agent.research", "capability.invoke", "capability.read", "market.read", "me.read", "portfolio.read", "review.read", "runtime.read", "source.backfill", "source.certification.manage", "source.credentials.write", "source.read", "source.run", "strategy.read", "strategy.shadow.manage"],
  ADMIN: ["api_keys.manage", "audit.read", "capability.read", "identity.manage", "identity.read", "me.read", "runtime.read", "source.backfill", "source.certification.manage", "source.credentials.write", "source.read", "source.run"],
};

const ADMIN_CAPABILITY: Record<string, string> = {
  "identity.manage": "access.manage",
  "api_keys.manage": "api_keys.manage",
  "source.run": "provider.ingestion.operate",
  "source.backfill": "provider.backfill.operate",
  "source.credentials.write": "provider.credential.manage",
  "source.certification.manage": "provider.certification.manage",
};

function user(roles: string[], declared: string[] = []): CurrentUserDTO {
  const permissions = [...new Set(roles.flatMap((role) => ROLE_PERMISSIONS[role]))];
  const commercial = roles.some((role) => role !== "ADMIN");
  return {
    principal_id: `p-${roles.join("-")}`, name: "u", principal_type: "USER", role: roles[0], roles,
    email: null, identity_source: "test", status: "ACTIVE", data_scopes: [], permissions,
    auth_method: "test", csrf_token: null,
    experience: {
      principal_id: "p", role: roles[0], roles, functional_assignments: declared,
      declared_job_functions: declared, unsatisfied_job_functions: [], home: null,
      available_work_modes: [], default_work_mode: null,
      effective_capabilities: permissions.map((item) => ADMIN_CAPABILITY[item] ?? item),
      commercial_capabilities: commercial ? ["market.read"] : [], scope_refs: [],
      data_entitlement_refs: [], unsupported_scope_kinds: [], work_mode_grants_authority: false,
    },
  };
}

const ROLES = ["VIEWER", "REVIEWER", "ANALYST", "OPERATOR", "ADMIN"];

test("composition grants nothing, like the work modes", () => {
  assert.equal(ROLE_COMPOSITION_GRANTS_AUTHORITY, false);
  assert.equal(WORK_MODE_GRANTS_AUTHORITY, false);
  assert.equal(resolveComposition(user(["ANALYST"], ["TRADER"])).grantsAuthority, false);
});

test("every job function has a composition, and every composition is well formed", () => {
  for (const id of JOB_FUNCTION_IDS) assert.ok(ROLE_COMPOSITIONS[JOB_FUNCTION_COMPOSITION[id]], id);
  for (const id of COMPOSITION_IDS) {
    const composition = ROLE_COMPOSITIONS[id];
    assert.equal(composition.id, id);
    assert.ok(composition.shortlist.length <= MAX_SHORTLIST, id);
    assert.equal(placeKey(composition.shortlist[0]), placeKey(composition.landing), `${id}: landing first`);
    assert.ok(STRIP_AUDIENCES.includes(composition.stripAudience), id);
    // Today's rows (design basis 2, E.3): two to six of the six, none twice.
    assert.equal(new Set(composition.todayRows).size, composition.todayRows.length, id);
    assert.ok(composition.todayRows.length >= 2 && composition.todayRows.length <= 6, id);
    // Every task named is a real task of a real mode.
    for (const ref of composition.shortlist) {
      if (ref.kind === "task") {
        assert.ok(navigationCommands().some((command) => command.id === `navigate.mode.${ref.mode}.${ref.task}`), `${id}: ${placeKey(ref)}`);
      }
    }
  }
});

test("§4.2 landings: trader on Today (D1), risk on Limits, operations on Delivery, admin on Connectors", () => {
  const landing = (roles: string[], fn: string) => placeKey(composedLanding(resolveComposition(user(roles, [fn])).composition, user(roles, [fn]))!);
  assert.equal(landing(["ANALYST"], "TRADER"), "desk.today");
  assert.equal(landing(["ANALYST"], "ORIGINATOR"), "deals.opportunities");
  assert.equal(landing(["REVIEWER"], "RISK_MANAGER"), "book.limits");
  assert.equal(landing(["VIEWER"], "OPERATIONS"), "book.delivery");
  assert.equal(landing(["VIEWER"], "FINANCE_SETTLEMENT"), "book.position");
  assert.equal(landing(["REVIEWER"], "LEGAL_COMPLIANCE"), "deals.review");
  assert.equal(landing(["REVIEWER"], "MANAGEMENT"), "desk.today");
  assert.equal(landing(["ADMIN"], "PLATFORM_ADMINISTRATOR"), "page.sources");
});

test("I11: for every job function and every role the composed places are a subset of what the role may open", () => {
  for (const role of ROLES) {
    for (const fn of [...JOB_FUNCTION_IDS, null]) {
      const person = user([role], fn ? [fn] : []);
      const { composition } = resolveComposition(person);
      const permitted = new Set(visibleModes(person).flatMap((mode) => mode.tasks.map((item) => `${mode.id}.${item.id}`)));
      for (const ref of composedShortlist(composition, person)) {
        if (ref.kind === "task") assert.ok(permitted.has(placeKey(ref)), `${role}/${fn}: ${placeKey(ref)}`);
        else assert.ok(placeVisible(ref, person), `${role}/${fn}: ${ref.page}`);
      }
      const landing = composedLanding(composition, person);
      if (landing?.kind === "task") assert.ok(permitted.has(placeKey(landing)), `${role}/${fn} landing`);
      // A viewer never gets the planning task (scenario.create) even as operations.
      if (role === "VIEWER") assert.ok(!composedShortlist(composition, person).some((ref) => placeKey(ref) === "book.planning"));
      // An administrator without a commercial role is offered no mode task at all.
      if (role === "ADMIN") assert.ok(composedShortlist(composition, person).every((ref) => ref.kind === "page"));
    }
  }
});

test("I12: nothing permitted becomes unreachable: shortlist plus More is every task the role may open, each in the palette", () => {
  const palette = new Set(navigationCommands().map((command) => command.id));
  for (const role of ROLES) {
    for (const fn of JOB_FUNCTION_IDS) {
      const person = user([role], [fn]);
      const { composition } = resolveComposition(person);
      const shown = [...composedShortlist(composition, person), ...moreTasks(composition, person)]
        .filter((ref) => ref.kind === "task")
        .map(placeKey);
      const permitted = visibleModes(person).flatMap((mode) => mode.tasks.map((item) => `${mode.id}.${item.id}`));
      assert.deepEqual([...shown].sort(), [...permitted].sort(), `${role}/${fn}`);
      for (const key of permitted) assert.ok(palette.has(`navigate.mode.${key}`), key);
    }
  }
});

test("the first declared function sets the defaults; View as only among the person's own functions", () => {
  const manager = user(["REVIEWER"], ["MANAGEMENT", "REVIEWER_MANAGEMENT"]);
  assert.equal(resolveComposition(manager).composition.id, "desk_head");
  assert.equal(resolveComposition(manager, "REVIEWER_MANAGEMENT").composition.id, "reviewer");
  // Not declared: ignored, the first declared one stands.
  assert.equal(resolveComposition(manager, "TRADER").composition.id, "desk_head");
  assert.equal(resolveComposition(manager, "nonsense").composition.id, "desk_head");
  assert.deepEqual(resolveComposition(manager).declared, ["MANAGEMENT", "REVIEWER_MANAGEMENT"]);
});

test("a declared function the server could not honour does not compose", () => {
  const person = user(["VIEWER"], ["ORIGINATOR"]);
  person.experience!.unsatisfied_job_functions = ["ORIGINATOR"];
  person.experience!.functional_assignments = [];
  const resolved = resolveComposition(person);
  assert.equal(resolved.jobFunction, null);
  assert.equal(resolved.composition.id, "desk_head");
});

test("no job function: the composition follows the permissions", () => {
  assert.equal(resolveComposition(user(["ANALYST"])).composition.id, "trader");
  assert.equal(resolveComposition(user(["REVIEWER"])).composition.id, "reviewer");
  assert.equal(resolveComposition(user(["VIEWER"])).composition.id, "desk_head");
  assert.equal(resolveComposition(user(["ADMIN"])).composition.id, "platform");
  assert.equal(resolveComposition(user(["OPERATOR"])).composition.id, "platform");
  assert.equal(resolveComposition(null).composition.id, "desk_head");
});

test("a panel the role may not read is hidden whatever the registry says; the registry can only narrow", () => {
  const composition = { ...ROLE_COMPOSITIONS.trader, panels: { contracts: { hedge_bands: "folded" as const, books: "open" as const } } };
  assert.equal(panelDefault(composition, "contracts", "hedge_bands", true), "folded");
  assert.equal(panelDefault(composition, "contracts", "books", false), "hidden");
  assert.equal(panelDefault(composition, "contracts", "unlisted", true), "open");
  assert.equal(panelDefault(composition, "contracts", "unlisted", false), "hidden");
});

test("Today's row order keeps only the rows the read returned", () => {
  assert.deepEqual(composedTodayRows(ROLE_COMPOSITIONS.analyst, ["market", "book", "fundamentals"]), ["fundamentals", "market", "book"]);
  // E.3: the trader and operations lead with the gas day to clear (owner, 2026-11-19), risk
  // with the book, the analyst with fundamentals, the originator with what needs them; every
  // other role keeps its order and has no gas-day row.
  assert.equal(ROLE_COMPOSITIONS.trader.todayRows[0], "gas_day");
  assert.equal(ROLE_COMPOSITIONS.trader.todayRows[2], "market");
  assert.equal(ROLE_COMPOSITIONS.risk.todayRows[0], "book");
  assert.equal(ROLE_COMPOSITIONS.analyst.todayRows[0], "fundamentals");
  assert.equal(ROLE_COMPOSITIONS.operations.todayRows[0], "checklist");
  assert.equal(ROLE_COMPOSITIONS.operations.todayRows[1], "gas_day");
  assert.equal(ROLE_COMPOSITIONS.trader.todayRows.indexOf("checklist"), 1);
  for (const id of ["analyst", "risk", "finance", "compliance", "originator", "reviewer", "desk_head"] as const) {
    assert.ok(!ROLE_COMPOSITIONS[id].todayRows.includes("gas_day"), id);
    assert.ok(!ROLE_COMPOSITIONS[id].todayRows.includes("checklist"), id);
  }
  assert.equal(ROLE_COMPOSITIONS.originator.todayRows[0], "needs_me");
});

test("strip audience per composition (§5.2)", () => {
  const audience = (roles: string[], fns: string[]) => resolveComposition(user(roles, fns)).composition.stripAudience;
  assert.equal(audience(["ANALYST"], ["TRADER"]), "trader");
  assert.equal(audience(["REVIEWER"], ["RISK_MANAGER"]), "risk");
  assert.equal(audience(["VIEWER"], ["FINANCE_SETTLEMENT"]), "finance");
  assert.equal(audience(["ADMIN"], ["PLATFORM_ADMINISTRATOR"]), "platform");
  assert.equal(audience(["OPERATOR"], ["DATA_OPERATOR"]), "platform");
  assert.equal(audience(["VIEWER"], ["OPERATIONS"]), "operations");
  assert.equal(audience(["REVIEWER"], ["MANAGEMENT", "REVIEWER_MANAGEMENT"]), "desk_head");
});
