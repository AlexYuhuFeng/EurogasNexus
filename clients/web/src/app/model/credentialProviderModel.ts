/**
 * Source Center credential-entry rule (REAL-SOURCES-02 review correction).
 *
 * The credential panel is shared by every provider, but only a provider whose key is
 * *externally managed* (an operator-owned env var or secret file) must not offer an entry
 * form: rotating it in the browser cannot change the credential the source actually uses,
 * so an enabled "Save" would be an ineffective action. The rule lives here, outside the
 * component, so the rendered control, its disabled state and the submit handler cannot
 * disagree about it.
 *
 * The same distinction decides the advisory text: only an *active* external configuration
 * (`env` or `file`) is externally managed. `missing`, `operator_disabled`, `file_unreadable`
 * and `credential_store` are not external owner-managed keys, so none of them may be labelled
 * as one.
 *
 * The connection aggregate is provider-scoped for the same reason: a previous provider's
 * probe result must never be rendered under the currently selected provider.
 */

/** Credential source kinds whose key is configured and managed outside the credential store. */
export const EXTERNALLY_MANAGED_SOURCE_KINDS: readonly string[] = ["env", "file"];

export interface CredentialProviderSubject {
  readonly provider_id: string;
  readonly credential_required: boolean;
  readonly configured?: boolean;
  readonly credential_source_kind?: string;
}

/**
 * Whether the provider's active credential is externally configured and operator-managed.
 *
 * Only `env`/`file` qualify. A safe non-answer (`missing`, `operator_disabled`,
 * `file_unreadable`, `state_unreadable`) or a store-backed credential is never treated as
 * an external owner-managed key.
 */
export function isExternallyManagedCredential(
  provider: Pick<CredentialProviderSubject, "credential_source_kind"> | null | undefined,
): boolean {
  const kind = provider?.credential_source_kind;
  return typeof kind === "string" && EXTERNALLY_MANAGED_SOURCE_KINDS.includes(kind);
}

/**
 * Whether submitting the credential form is a meaningful action right now.
 *
 * A no-op submit must be refused by the handler, not merely hidden by a disabled button:
 * the provider must require a key, must not be externally managed, and a non-blank value
 * must be present.
 */
export function canSubmitCredential(
  provider: CredentialProviderSubject | null | undefined,
  value: string,
): boolean {
  if (!provider?.credential_required) return false;
  if (isExternallyManagedCredential(provider)) return false;
  return value.trim().length > 0;
}

export interface CredentialConnectionSubject {
  readonly providerId: string;
  readonly ok: boolean;
  readonly errorCode: string | null;
}

/**
 * The connection aggregate only when it belongs to the currently selected provider.
 *
 * Returns `null` for a missing aggregate or a provider mismatch, so a stale result from a
 * previously selected provider is never displayed as the current provider's connection.
 */
export function credentialConnectionForProvider<T extends CredentialConnectionSubject>(
  connection: T | null | undefined,
  providerId: string | null | undefined,
): T | null {
  if (!connection || !providerId) return null;
  return connection.providerId === providerId ? connection : null;
}
