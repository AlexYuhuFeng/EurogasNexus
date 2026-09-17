/**
 * Architecture V2 Wave 3 - control-plane separation tests.
 *
 * `06_IDENTITY_ACCESS_CONTROL_PLANE.md` section 8 states that normal business
 * users should not navigate through administration controls. The administration
 * primary is therefore offered only to an identity whose composition includes an
 * administration capability, and a deep link into it renders a bounded
 * restricted notice instead of a workspace the backend would refuse.
 *
 * Navigation is not a security boundary: the backend authorises every request
 * independently (`api/dependencies/commercial_access.py`, `route_permission.py`).
 */

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import {
  ADMINISTRATION_CAPABILITIES,
  compositionFromProfile,
  compositionSeesAdministration,
} from "../src/app/experience/index.ts";
import {
  controlPlanePrimaries,
  isControlPlanePage,
  primaryWorkspaces,
} from "../src/app/navigation/productNavigation.ts";
import type { ExperienceProfileDTO } from "../src/api/client.ts";

function profile(overrides: Partial<ExperienceProfileDTO> = {}): ExperienceProfileDTO {
  return {
    principal_id: "principal",
    role: "ANALYST",
    roles: ["ANALYST"],
    functional_assignments: ["TRADER"],
    available_work_modes: ["TRADING_ANALYSIS"],
    default_work_mode: "TRADING_ANALYSIS",
    effective_capabilities: ["market.read", "portfolio.read"],
    commercial_capabilities: ["market.read"],
    scope_refs: ["DATA:EEX"],
    data_entitlement_refs: ["EEX"],
    unsupported_scope_kinds: ["ORGANIZATION"],
    work_mode_grants_authority: false,
    ...overrides,
  };
}

function readWebSource(relativePath: string): string {
  return readFileSync(new URL(`../src/${relativePath}`, import.meta.url), "utf8");
}

test("only an administration capability reveals the administration surface", () => {
  const analyst = compositionFromProfile(profile());
  assert.equal(compositionSeesAdministration(analyst), false);

  // Reading source/runtime status is not administration: those indicators stay in
  // the business shell and every role may read them.
  const statusOnly = compositionFromProfile(
    profile({ effective_capabilities: ["source.read", "runtime.read", "market.read"] }),
  );
  assert.equal(compositionSeesAdministration(statusOnly), false);

  const operator = compositionFromProfile(
    profile({ effective_capabilities: ["provider.ingestion.operate", "market.read"] }),
  );
  assert.equal(compositionSeesAdministration(operator), true);

  const admin = compositionFromProfile(
    profile({
      role: "ADMIN",
      roles: ["ADMIN"],
      effective_capabilities: ["access.manage", "audit.read"],
      commercial_capabilities: [],
    }),
  );
  assert.equal(compositionSeesAdministration(admin), true);

  // Fail closed: no profile, or a profile that claims authority, hides it.
  assert.equal(compositionSeesAdministration(compositionFromProfile(null)), false);
  assert.equal(
    compositionSeesAdministration(
      compositionFromProfile(
        profile({ work_mode_grants_authority: true as unknown as false }),
      ),
    ),
    false,
  );

  for (const capability of ADMINISTRATION_CAPABILITIES) {
    const single = compositionFromProfile(profile({ effective_capabilities: [capability] }));
    assert.equal(compositionSeesAdministration(single), true, capability);
  }
});

test("the shell hides the administrative primary and refuses its deep links", () => {
  const topBar = readWebSource("components/WorkspaceTopBar.tsx");
  const shell = readWebSource("app/shell/AppShell.tsx");
  const restricted = readWebSource("components/RestrictedSurface.tsx");

  // The tab row is filtered by the composition, not by a client-side role check.
  assert.match(topBar, /const visiblePrimaries = compositionSeesAdministration\(composition\)/);
  assert.match(topBar, /primary\.controlPlane !== true/);
  assert.match(topBar, /visiblePrimaries\.map/);
  assert.equal(topBar.includes("groupedMenuOpen"), false);

  // A deep link into a control-plane page cannot mount the workspace.
  assert.match(shell, /isControlPlanePage\(navigation\.activeWorkspace\)/);
  assert.match(shell, /const composition = compositionFromProfile\(api\.currentUser\?\.experience\);/);
  assert.match(shell, /!compositionSeesAdministration\(composition\)/);
  // ...and the refusal is the only branch the shell keeps: every page it does not refuse
  // composes through the workspace renderer (conflicting register C9).
  assert.match(
    shell,
    /controlPlaneRestricted \? <RestrictedSurface t=\{t\} \/> : <WorkspaceRenderer controller=\{controller\} \/>/,
  );
  assert.equal(shell.includes("activeWorkspace === "), false);

  // The restricted notice is presentation only: no control, no data, one h1.
  assert.equal(restricted.includes("<button"), false);
  assert.equal(restricted.includes("useApiStore"), false);
  assert.equal((restricted.match(/<h1>/g) ?? []).length, 1);
  assert.match(restricted, /data-restricted-surface="true"/);
  assert.match(restricted, /role="alert"/);
});

test("the administration pages keep their routes and stay declared once", () => {
  const [administration] = controlPlanePrimaries();
  assert.ok(administration);
  assert.deepEqual(administration.pages, ["sources", "runtime", "access"]);
  assert.equal(administration.defaultPage, "sources");

  // Every page still maps to exactly one primary, and the control-plane pages are
  // not reachable through a business primary.
  const businessPages = primaryWorkspaces
    .filter((primary) => primary.controlPlane !== true)
    .flatMap((primary) => primary.pages);
  for (const page of administration.pages) {
    assert.equal(businessPages.includes(page), false, page);
    assert.equal(isControlPlanePage(page), true, page);
  }
});

test("the administration labels exist in both locales", () => {
  const en = JSON.parse(readWebSource("i18n/en.json")) as Record<string, string>;
  const zh = JSON.parse(readWebSource("i18n/zh.json")) as Record<string, string>;

  for (const key of [
    "nav.primary.administration",
    "nav.primary.administration.description",
    "nav.primary.system",
    "nav.primary.system.description",
    "restricted.eyebrow",
    "restricted.title",
    "restricted.body",
    "restricted.note",
  ]) {
    assert.ok(en[key]?.trim(), key);
    assert.ok(zh[key]?.trim(), key);
    assert.notEqual(en[key], zh[key], key);
  }
  assert.equal(Object.keys(en).length, Object.keys(zh).length);
});
