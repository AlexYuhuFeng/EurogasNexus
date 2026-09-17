/**
 * Architecture V2 Wave 2 - ExperienceProfile composition tests (client side).
 *
 * The client half of the identity/experience split. These tests pin the two
 * properties that keep a composition contract safe: it is parsed from the server
 * response without inventing modes the client does not implement, and it is
 * never treated as authority.
 */

import assert from "node:assert/strict";
import test from "node:test";

import {
  SERVER_WORK_MODE_IDS,
  WORK_MODE_IDS,
  availableModeCompositions,
  compositionAllowsMode,
  compositionFromProfile,
  compositionHasCommercialAccess,
  compositionHoldsCapability,
} from "../src/app/experience/index.ts";
import type { ExperienceProfileDTO } from "../src/api/client.ts";

function profile(overrides: Partial<ExperienceProfileDTO> = {}): ExperienceProfileDTO {
  return {
    principal_id: "principal-analyst",
    role: "ANALYST",
    roles: ["ANALYST"],
    functional_assignments: ["TRADER", "QUANT_RESEARCHER"],
    available_work_modes: ["TRADING_ANALYSIS", "RESEARCH"],
    default_work_mode: "TRADING_ANALYSIS",
    effective_capabilities: ["market.read", "portfolio.read", "optimization.run"],
    commercial_capabilities: ["market.read", "portfolio.read"],
    scope_refs: ["DATA:EEX"],
    data_entitlement_refs: ["EEX"],
    unsupported_scope_kinds: ["ORGANIZATION", "PORTFOLIO", "MARKET", "REGION"],
    work_mode_grants_authority: false,
    ...overrides,
  };
}

test("server work modes map onto the client composition registry", () => {
  assert.deepEqual(Object.keys(SERVER_WORK_MODE_IDS).sort(), [...WORK_MODE_IDS].sort());
  assert.equal(new Set(Object.values(SERVER_WORK_MODE_IDS)).size, WORK_MODE_IDS.length);
});

test("a profile becomes a composition, never authority", () => {
  const composition = compositionFromProfile(profile());

  assert.equal(composition.available, true);
  assert.equal(composition.grantsAuthority, false);
  assert.deepEqual(composition.workModes, ["trading-analysis", "research"]);
  assert.equal(composition.defaultWorkMode, "trading-analysis");
  assert.deepEqual(composition.functionalAssignments, ["TRADER", "QUANT_RESEARCHER"]);
  assert.deepEqual(composition.scopeRefs, ["DATA:EEX"]);
  assert.deepEqual(composition.unsupportedScopeKinds, [
    "ORGANIZATION",
    "PORTFOLIO",
    "MARKET",
    "REGION",
  ]);
});

test("unknown modes and authority-claiming profiles are refused", () => {
  const unknown = compositionFromProfile(
    profile({ available_work_modes: ["TRADING_ANALYSIS", "TIME_TRAVEL"], default_work_mode: "TIME_TRAVEL" }),
  );
  assert.deepEqual(unknown.workModes, ["trading-analysis"]);
  // A default the client cannot compose falls back to the first usable mode.
  assert.equal(unknown.defaultWorkMode, "trading-analysis");

  const claiming = compositionFromProfile(
    profile({ work_mode_grants_authority: true as unknown as false }),
  );
  assert.equal(claiming.available, false);
  assert.deepEqual(claiming.workModes, []);
  assert.equal(claiming.defaultWorkMode, null);

  const missing = compositionFromProfile(null);
  assert.equal(missing.available, false);
  assert.equal(missing.defaultWorkMode, null);
  assert.deepEqual(missing.effectiveCapabilities, []);
});

test("malformed lists degrade to empty rather than to everything", () => {
  const malformed = compositionFromProfile(
    profile({
      available_work_modes: null as unknown as string[],
      effective_capabilities: [1, "market.read", null] as unknown as string[],
      scope_refs: undefined as unknown as string[],
    }),
  );

  assert.deepEqual(malformed.workModes, []);
  assert.deepEqual(malformed.effectiveCapabilities, ["market.read"]);
  assert.deepEqual(malformed.scopeRefs, []);
  assert.equal(malformed.defaultWorkMode, null);
});

test("composition helpers report the server's answer without widening it", () => {
  const composition = compositionFromProfile(profile());
  const adminOnly = compositionFromProfile(
    profile({
      role: "ADMIN",
      roles: ["ADMIN"],
      functional_assignments: ["PLATFORM_ADMINISTRATOR"],
      available_work_modes: ["ADMINISTRATION"],
      default_work_mode: "ADMINISTRATION",
      effective_capabilities: ["access.manage", "audit.read"],
      commercial_capabilities: [],
    }),
  );

  assert.equal(compositionAllowsMode(composition, "trading-analysis"), true);
  assert.equal(compositionAllowsMode(composition, "administration"), false);
  assert.equal(compositionHoldsCapability(composition, "market.read"), true);
  assert.equal(compositionHoldsCapability(composition, "access.manage"), false);
  assert.equal(compositionHasCommercialAccess(composition), true);

  assert.equal(compositionAllowsMode(adminOnly, "administration"), true);
  assert.equal(compositionAllowsMode(adminOnly, "trading-analysis"), false);
  assert.equal(compositionHasCommercialAccess(adminOnly), false);

  const compositions = availableModeCompositions(composition);
  assert.deepEqual(
    compositions.map((item) => item.id),
    ["trading-analysis", "research"],
  );
  assert.equal(compositions[0]?.canonicalSpec.endsWith("W1-05_CANONICAL_EXPERIENCE_SPECS.md"), true);
});
