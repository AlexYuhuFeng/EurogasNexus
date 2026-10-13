/**
 * The Source Center's GIE connection workflow: capability, not a hardcoded provider list.
 *
 * The surface used to allow the live connection test only for `["DEEPSEEK", "LLM"]`, so the
 * backend could implement a governed GIE probe and no operator could reach it. These assertions
 * pin the corrected contract: the control is driven by the backend's own
 * `connection_test_supported` + the resolved `configured` state, the external (owner-managed)
 * credential is rendered read-only without its value or path, and connectivity stays visibly
 * separate from certification.
 */

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

function readWebSource(relativePath: string): string {
  return readFileSync(new URL(`../src/${relativePath}`, import.meta.url), "utf8");
}

function readLocale(name: "en" | "zh"): Record<string, string> {
  return JSON.parse(readWebSource(`i18n/${name}.json`)) as Record<string, string>;
}

const component = readWebSource("components/SourceCenter.tsx");
const controller = readWebSource("app/hooks/useSourceCenterController.ts");
const store = readWebSource("stores/api.ts");
const client = readWebSource("api/client.ts");

test("the connection-test control is driven by the backend capability", () => {
  assert.ok(
    component.includes("!selectedCredentialProvider?.connection_test_supported"),
    "the control must be disabled when the backend declares no support",
  );
  assert.ok(
    component.includes("!selectedCredentialProvider?.configured"),
    "the control must be disabled when no credential resolves",
  );
  assert.equal(
    component.includes('["DEEPSEEK", "LLM"]'),
    false,
    "a hardcoded provider list must not gate the control",
  );
  assert.match(component, /onClick=\{onCredentialConnectionTest\}/);
});

test("the external owner-managed credential disables the entry form and save", () => {
  assert.ok(component.includes("credentialEntryReadonly"));
  assert.ok(controller.includes("isExternallyManagedCredential"));
  assert.ok(controller.includes("canSubmitCredential"));
  // Label, key and save are all disabled for an operator-managed env/file key.
  assert.ok(component.includes("disabled={credentialEntryReadonly}"));
  assert.ok(component.includes("credentialEntryReadonly ||"));
  assert.ok(component.includes('t("credentials.external_readonly")'));
  assert.equal(
    component.includes('credential_source_kind !== "credential_store"'),
    false,
    "a missing/disabled/unreadable credential must not be labelled as externally managed",
  );
});

test("connectivity is rendered separately from certification", () => {
  assert.ok(component.includes('t("credentials.certification")'));
  assert.ok(component.includes("selectedCredentialProvider.certification"));
  assert.ok(component.includes('t("credentials.live_connection")'));
  assert.ok(component.includes("credentialConnection.products"));
  assert.ok(
    component.includes("credentialConnection.providerId === selectedCredentialProvider.provider_id"),
    "the rendered aggregate must belong to the selected provider",
  );
  assert.match(
    component,
    /product\.bounded_partial \? ` · \$\{t\("credentials\.bounded_partial"\)\}` : ""/,
  );
});

test("the controller and store carry the per-product aggregate without a credential", () => {
  assert.ok(controller.includes("credentialConnection: ApiState[\"credentialConnection\"]"));
  assert.ok(controller.includes("credentialConnection,"));
  assert.ok(store.includes("credentialConnection: null"));
  assert.match(store, /connectionTestMessage\(providerId, result\.data\)/);
  // The key is never part of the client request body: the endpoint resolves it server-side.
  assert.match(client, /\/credentials\/\$\{providerId\}\/connection-test/);
  assert.ok(
    client.includes("connection?: GieConnectionTestDTO"),
    "the client type must carry the bounded per-product aggregate",
  );
});

test("every new credential string exists in both locales and is translated", () => {
  const en = readLocale("en");
  const zh = readLocale("zh");
  for (const locale of [en, zh]) {
    for (const key of [
      "credentials.source_kind",
      "credentials.source_kind.env",
      "credentials.source_kind.file",
      "credentials.source_kind.credential_store",
      "credentials.source_kind.missing",
      "credentials.source_kind.file_unreadable",
      "credentials.source_kind.operator_disabled",
      "credentials.source_kind.state_unreadable",
      "credentials.diagnostics",
      "credentials.certification",
      "credentials.live_connection",
      "credentials.connected",
      "credentials.failed",
      "credentials.bounded_partial",
      "credentials.external_readonly",
      "sources.diagnostic.credential_disabled",
      "sources.diagnostic.gie_key_file_unreadable",
      "sources.diagnostic.source_operation_disabled",
      "sources.diagnostic.credential_state_unreadable",
      "sources.diagnostic.source_operation_state_unreadable",
    ]) {
      assert.equal(typeof locale[key], "string", key);
      assert.ok(locale[key].length > 0, key);
    }
  }
  assert.notEqual(en["credentials.external_readonly"], zh["credentials.external_readonly"]);
  assert.notEqual(en["credentials.bounded_partial"], zh["credentials.bounded_partial"]);
  assert.notEqual(en["credentials.source_kind.state_unreadable"], zh["credentials.source_kind.state_unreadable"]);
});
