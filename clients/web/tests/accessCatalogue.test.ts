/**
 * Access administration catalogue and API-key creation (slice C of the D3 decision).
 *
 * Three declared calls had no surface: the role catalogue and the data-scope catalogue the backend
 * enforces, and the ability to issue an API key at all (the surface could only revoke one). These
 * tests hold the create rule to the route it mirrors, and hold the panel to the declarations it
 * claims to use.
 */

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import {
  API_KEY_NAME_MAX_LENGTH,
  apiKeyReadiness,
  apiKeyRequest,
  declaredScopes,
  roleRows,
  scopeFamilyRows,
  undeclaredScopes,
  type DataScopeCatalogue,
} from "../src/app/model/accessCatalogueModel.ts";

function readWebSource(relativePath: string): string {
  return readFileSync(new URL(`../src/${relativePath}`, import.meta.url), "utf8");
}

const CATALOGUE: DataScopeCatalogue = {
  public_baseline: ["operator-input", "ENTSOG", "GIE", "ECB", "Weather"],
  commercial: ["EEX", "ICE_OCM", "TRAYPORT", "ICIS", "PLATTS", "ARGUS", "KPLER"],
  wildcard: "*",
};

const DRAFT = { principalId: "principal-1", displayName: "scheduler", expiresOn: "", scopes: ["EEX"] };

test("the create rule mirrors the route's own refusals", () => {
  // The key acts as a principal, so one is required.
  assert.deepEqual(
    apiKeyReadiness({ draft: { ...DRAFT, principalId: "" }, catalogue: CATALOGUE }).blockerKeys,
    ["access.key.blocker.principal_required"],
  );
  // A name is required and bounded (1..128), because a key nobody can identify is a key nobody
  // dares revoke.
  assert.deepEqual(
    apiKeyReadiness({ draft: { ...DRAFT, displayName: "  " }, catalogue: CATALOGUE }).blockerKeys,
    ["access.key.blocker.name_required"],
  );
  assert.deepEqual(
    apiKeyReadiness({
      draft: { ...DRAFT, displayName: "x".repeat(API_KEY_NAME_MAX_LENGTH + 1) },
      catalogue: CATALOGUE,
    }).blockerKeys,
    ["access.key.blocker.name_too_long"],
  );
  assert.equal(API_KEY_NAME_MAX_LENGTH, 128);
  // An expiry the platform would have to interpret is refused rather than guessed at.
  assert.deepEqual(
    apiKeyReadiness({ draft: { ...DRAFT, expiresOn: "not-a-date" }, catalogue: CATALOGUE })
      .blockerKeys,
    ["access.key.blocker.expiry_invalid"],
  );
  assert.equal(apiKeyReadiness({ draft: DRAFT, catalogue: CATALOGUE }).canCreate, true);
});

test("a scope the deployment does not declare is refused, and an unread catalogue is not evidence", () => {
  assert.deepEqual(undeclaredScopes(["EEX", "NOT_A_FAMILY"], CATALOGUE), ["NOT_A_FAMILY"]);
  assert.deepEqual(undeclaredScopes(["*", "Weather"], CATALOGUE), []);
  // Without a catalogue the surface cannot tell declared from undeclared, so it refuses nothing on
  // that ground: a missing read is a missing fact, not a wrong scope.
  assert.deepEqual(undeclaredScopes(["anything"], null), []);
  assert.deepEqual(declaredScopes(null), []);
  // The wildcard is offered last and once.
  const scopes = declaredScopes(CATALOGUE);
  assert.equal(scopes[scopes.length - 1], "*");
  assert.equal(scopes.length, 13);
});

test("the request is composed only when the rule allows it, and says what it means by no expiry", () => {
  const body = apiKeyRequest({ draft: DRAFT, catalogue: CATALOGUE });
  assert.ok(body);
  assert.equal(body.principal_id, "principal-1");
  assert.equal(body.display_name, "scheduler");
  // No date means a key that never expires, stated as null rather than omitted: the route's default
  // is the same, and the surface says which it chose.
  assert.equal(body.expires_at_utc, null);
  assert.deepEqual(body.scopes, ["EEX"]);

  const dated = apiKeyRequest({
    draft: { ...DRAFT, expiresOn: "2026-12-31" },
    catalogue: CATALOGUE,
  });
  assert.equal(dated?.expires_at_utc, "2026-12-31T00:00:00Z");

  // A key with no scopes is a decision, not an omission, and it is sent as such.
  const noScopes = apiKeyRequest({ draft: { ...DRAFT, scopes: [] }, catalogue: CATALOGUE });
  assert.deepEqual(noScopes?.scopes, []);

  // An unready draft produces no body: a partial one would invent the principal or the name.
  assert.equal(apiKeyRequest({ draft: { ...DRAFT, principalId: "" }, catalogue: CATALOGUE }), null);
});

test("the catalogues are rendered as rows, including a role that grants nothing", () => {
  const rows = roleRows({ VIEWER: ["read"], EMPTY_ROLE: [], ADMIN: ["a", "b"] });
  assert.deepEqual(rows.map((row) => row.role), ["ADMIN", "EMPTY_ROLE", "VIEWER"]);
  assert.deepEqual(rows[1].permissions, []);
  assert.deepEqual(roleRows(null), []);

  const families = scopeFamilyRows(CATALOGUE);
  assert.deepEqual(families.map((row) => row.family), ["public_baseline", "commercial", "wildcard"]);
  assert.deepEqual(scopeFamilyRows(null), []);
});

test("the Access Center uses the declared catalogue and key calls, not ad-hoc ones", () => {
  const panel = readWebSource("components/AccessCenter.tsx");
  const client = readWebSource("api/client.ts");

  // The three calls that had no caller, and the DTO the scope read needed to stop being an open
  // record: the surface offers what the deployment declares, not whatever string is typed.
  assert.match(panel, /api\.accessRoles\(\)/);
  assert.match(panel, /api\.accessDataScopes\(\)/);
  assert.match(panel, /api\.createAccessApiKey\(body\)/);
  assert.match(client, /accessDataScopes: \(\) => get<DataScopeCatalogueDTO>/);

  // The rule gates the action, the panel never composes a body itself, and the bearer is shown once
  // and stored nowhere.
  assert.match(panel, /apiKeyReadiness\(\{ draft, catalogue: scopeCatalogue \}\)/);
  assert.match(panel, /apiKeyRequest\(\{ draft, catalogue: scopeCatalogue \}, readiness\)/);
  assert.match(panel, /setIssuedKey\(response\.data\.api_key\)/);
  assert.match(panel, /access\.key\.issued_once/);
  assert.equal(/localStorage/.test(panel), false);
  assert.equal(/sessionStorage/.test(panel), false);
});

test("the access vocabulary is bilingual", () => {
  const en = JSON.parse(readWebSource("i18n/en.json")) as Record<string, string>;
  const zh = JSON.parse(readWebSource("i18n/zh.json")) as Record<string, string>;
  const keys = [
    "access.view.catalogue",
    "access.catalogue.roles",
    "access.catalogue.permissions",
    "access.catalogue.grants_nothing",
    "access.catalogue.scope_families",
    "access.catalogue.family",
    "access.catalogue.family_public_baseline",
    "access.catalogue.family_commercial",
    "access.catalogue.family_wildcard",
    "access.catalogue.unavailable",
    "access.key.create",
    "access.key.create_note",
    "access.key.owner",
    "access.key.choose_principal",
    "access.key.expires_on",
    "access.key.scopes",
    "access.key.issue",
    "access.key.issued_once",
    "access.key.dismiss",
    "access.key.undeclared",
    "access.key.create_failed",
    "access.key.blocker.principal_required",
    "access.key.blocker.name_required",
    "access.key.blocker.name_too_long",
    "access.key.blocker.expiry_invalid",
    "access.key.blocker.scope_undeclared",
  ];
  for (const key of keys) {
    assert.ok(en[key]?.trim(), `en ${key}`);
    assert.ok(zh[key]?.trim(), `zh ${key}`);
    assert.notEqual(en[key], zh[key], key);
  }
});
