/**
 * Source Center credential-entry and connection-scoping rules (REAL-SOURCES-02 review).
 *
 * The panel used to say "externally managed" in text while leaving the label, key and save
 * controls live, and it rendered whatever the store's last connection aggregate happened to
 * be. These tests pin the actual rule - not a source substring - so an ineffective rotation
 * is refused and a stale provider's probe result can never be shown as the current one.
 */

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import {
  canSubmitCredential,
  credentialConnectionForProvider,
  isExternallyManagedCredential,
  type CredentialProviderSubject,
} from "../src/app/model/credentialProviderModel.ts";

function readWebSource(relativePath: string): string {
  return readFileSync(new URL(`../src/${relativePath}`, import.meta.url), "utf8");
}

function provider(
  overrides: Partial<CredentialProviderSubject> = {},
): CredentialProviderSubject {
  return {
    provider_id: "GIE",
    credential_required: true,
    configured: true,
    credential_source_kind: "env",
    ...overrides,
  };
}

test("only an active env/file key counts as externally managed", () => {
  assert.equal(isExternallyManagedCredential(provider({ credential_source_kind: "env" })), true);
  assert.equal(isExternallyManagedCredential(provider({ credential_source_kind: "file" })), true);

  for (const kind of [
    "credential_store",
    "missing",
    "operator_disabled",
    "file_unreadable",
    "state_unreadable",
    "",
  ]) {
    assert.equal(
      isExternallyManagedCredential(provider({ credential_source_kind: kind })),
      false,
      kind,
    );
  }
  assert.equal(isExternallyManagedCredential(undefined), false);
});

test("submitting an externally managed credential is refused, not merely hidden", () => {
  // The handler guard uses the same rule, so a direct form submit cannot rotate an env/file key.
  assert.equal(canSubmitCredential(provider({ credential_source_kind: "env" }), "value"), false);
  assert.equal(canSubmitCredential(provider({ credential_source_kind: "file" }), "value"), false);
});

test("a store-backed or missing credential keeps the normal submit rule", () => {
  assert.equal(
    canSubmitCredential(provider({ credential_source_kind: "credential_store" }), " value "),
    true,
  );
  assert.equal(canSubmitCredential(provider({ credential_source_kind: "missing" }), "value"), true);
  assert.equal(canSubmitCredential(provider({ credential_source_kind: "missing" }), "   "), false);
  assert.equal(
    canSubmitCredential(provider({ credential_source_kind: "operator_disabled" }), "value"),
    true,
  );
});

test("a provider that does not require a key never submits", () => {
  assert.equal(canSubmitCredential(provider({ credential_required: false }), "value"), false);
  assert.equal(canSubmitCredential(undefined, "value"), false);
});

test("a connection aggregate is shown only for its own provider", () => {
  const gie = { providerId: "GIE", ok: true, errorCode: null };
  const deepseek = { providerId: "DEEPSEEK", ok: true, errorCode: null };

  assert.equal(credentialConnectionForProvider(gie, "GIE"), gie);
  // A stale DeepSeek probe must not render while GIE is selected, and vice versa.
  assert.equal(credentialConnectionForProvider(deepseek, "GIE"), null);
  assert.equal(credentialConnectionForProvider(gie, "DEEPSEEK"), null);
  assert.equal(credentialConnectionForProvider(gie, undefined), null);
  assert.equal(credentialConnectionForProvider(null, "GIE"), null);
});

test("the component and controller wire the rule instead of a text-only label", () => {
  const component = readWebSource("components/SourceCenter.tsx");
  const controller = readWebSource("app/hooks/useSourceCenterController.ts");
  const renderer = readWebSource("app/workspaces/WorkspaceRenderer.tsx");

  assert.ok(component.includes("disabled={credentialEntryReadonly}"), "label input");
  assert.ok(
    component.includes("credentialEntryReadonly || !selectedCredentialProvider?.credential_required"),
    "key input",
  );
  assert.ok(component.includes("credentialEntryReadonly ||"), "save button");
  assert.ok(controller.includes("canSubmitCredential(selectedCredentialProvider, credentialValue)"));
  assert.ok(controller.includes("credentialConnectionForProvider("));
  assert.ok(
    renderer.includes("credentialConnection={sources.credentialConnection}"),
    "the renderer must pass the provider-scoped aggregate",
  );
  assert.ok(renderer.includes("credentialEntryReadonly={sources.credentialEntryReadonly}"));
});
