/**
 * Access administration reads and the API-key create rule (slice C of the D3 decision).
 *
 * Three declared calls had no surface, and each answers something the Access Center could not:
 *
 * - `GET /api/access/roles` publishes the role → permission catalogue the backend enforces. The
 *   surface listed a principal's roles without saying what they grant, so an administrator was
 *   editing grants against a vocabulary they could not see;
 * - `GET /api/access/data-scopes` publishes the declared scope families (a public baseline, the
 *   commercial families, and the wildcard). The surface showed a principal's scopes as free text,
 *   with no way to tell a declared family from a string nothing recognises;
 * - `POST /api/access/api-keys` creates a key. The surface could only *revoke* keys, so issuing one
 *   meant calling the API - the one administration act an operator needs most often.
 *
 * The create rule mirrors the route: a principal, a display name of 1..128 characters, and scopes
 * that are declared families or the wildcard. The route owns the bounds and re-checks them; this is
 * what the surface refuses before the click, and it never invents a value the caller did not choose.
 */

import type { AccessApiKeyCreateInputDTO, DataScopeCatalogueDTO } from "@/api/client";

/** Route bounds for a key's display name (`ApiKeyCreateRequest`). */
export const API_KEY_NAME_MAX_LENGTH = 128;

/**
 * The declared data-scope families, as `GET /api/access/data-scopes` publishes them.
 *
 * The DTO lives in the API layer because it is the route's own payload; this module only reads it.
 */
export type DataScopeCatalogue = DataScopeCatalogueDTO;

export interface ApiKeyDraft {
  readonly principalId: string;
  readonly displayName: string;
  /** `YYYY-MM-DD` from a date field, or "" for a key that never expires. */
  readonly expiresOn: string;
  readonly scopes: readonly string[];
}

export interface ApiKeyReadiness {
  readonly canCreate: boolean;
  readonly blockerKeys: readonly string[];
  readonly firstBlockerKey: string | null;
}

/** Every declared scope family, wildcard last, so a picker can offer them in one list. */
export function declaredScopes(catalogue: DataScopeCatalogue | null): string[] {
  if (!catalogue) return [];
  return [
    ...catalogue.public_baseline,
    ...catalogue.commercial,
    catalogue.wildcard,
  ];
}

/**
 * Whether a scope the operator picked is one the deployment declares.
 *
 * The route accepts a scope list as given and records it, so a typo would be stored as a grant that
 * matches nothing. The surface refuses it instead, naming the value, and the catalogue is the only
 * source of what is declared.
 */
export function undeclaredScopes(
  scopes: readonly string[],
  catalogue: DataScopeCatalogue | null,
): string[] {
  const declared = new Set(declaredScopes(catalogue));
  // Without a catalogue the surface cannot tell declared from undeclared, so it refuses nothing on
  // that ground: an unread catalogue is a missing fact, not evidence that a scope is wrong.
  if (declared.size === 0) return [];
  return scopes.filter((scope) => !declared.has(scope));
}

export function apiKeyReadiness(input: {
  readonly draft: ApiKeyDraft;
  readonly catalogue: DataScopeCatalogue | null;
}): ApiKeyReadiness {
  const blockerKeys: string[] = [];
  if (!input.draft.principalId.trim()) {
    blockerKeys.push("access.key.blocker.principal_required");
  }
  const name = input.draft.displayName.trim();
  if (!name) {
    blockerKeys.push("access.key.blocker.name_required");
  } else if (name.length > API_KEY_NAME_MAX_LENGTH) {
    blockerKeys.push("access.key.blocker.name_too_long");
  }
  const expiry = input.draft.expiresOn.trim();
  if (expiry && Number.isNaN(new Date(`${expiry}T00:00:00Z`).getTime())) {
    blockerKeys.push("access.key.blocker.expiry_invalid");
  }
  if (undeclaredScopes(input.draft.scopes, input.catalogue).length > 0) {
    blockerKeys.push("access.key.blocker.scope_undeclared");
  }
  return {
    canCreate: blockerKeys.length === 0,
    blockerKeys,
    firstBlockerKey: blockerKeys.length > 0 ? blockerKeys[0] : null,
  };
}

/**
 * The request body, or `null` when the draft is not ready.
 *
 * An empty scope list is sent as an empty list rather than omitted: the route's default is the same
 * empty list, and a key with no scopes is a key that can read only what every principal can - which
 * is a deliberate choice rather than an undecided one, and the surface says which it is.
 */
export function apiKeyRequest(
  input: { readonly draft: ApiKeyDraft; readonly catalogue: DataScopeCatalogue | null },
  readiness: ApiKeyReadiness = apiKeyReadiness(input),
): AccessApiKeyCreateInputDTO | null {
  if (!readiness.canCreate) return null;
  const expiry = input.draft.expiresOn.trim();
  return {
    principal_id: input.draft.principalId.trim(),
    display_name: input.draft.displayName.trim(),
    expires_at_utc: expiry ? `${expiry}T00:00:00Z` : null,
    scopes: [...input.draft.scopes],
  };
}

/**
 * What a role grants, as rows.
 *
 * A role with no permissions is reported as such rather than omitted: the catalogue is the
 * platform's own declaration, and a role that grants nothing is a fact an administrator needs.
 */
export function roleRows(
  roles: Readonly<Record<string, readonly string[]>> | null,
): Array<{ role: string; permissions: readonly string[] }> {
  if (!roles) return [];
  return Object.keys(roles)
    .sort()
    .map((role) => ({ role, permissions: (roles[role] ?? []).slice().sort() }));
}

/**
 * The research capability catalogue (slice E), read on the research surface.
 *
 * `GET /api/research/capabilities` declares what the research domain can do and the posture each
 * capability carries: whether it computes or only reads, whether it is deterministic, what it may
 * change, the permission it needs and whether it returns provenance. The route had no consumer, so
 * the declaration that makes a research figure checkable was invisible.
 */
export interface ResearchCapabilityRow {
  readonly name: string;
  readonly description: string;
  readonly readWriteClass: string;
  readonly deterministic: boolean;
  readonly sideEffectClass: string;
  readonly requiredPermission: string;
  readonly provenanceBehavior: string;
}

/** Rows for the catalogue table, ordered by name so two reads render the same way. */
export function researchCapabilityRows(
  capabilities: readonly {
    name: string;
    description: string;
    read_write_class: string;
    deterministic: boolean;
    side_effect_class: string;
    required_permission: string;
    provenance_behavior: string;
  }[] | null,
): ResearchCapabilityRow[] {
  if (!capabilities) return [];
  return capabilities
    .map((capability) => ({
      name: capability.name,
      description: capability.description,
      readWriteClass: capability.read_write_class,
      deterministic: capability.deterministic,
      sideEffectClass: capability.side_effect_class,
      requiredPermission: capability.required_permission,
      provenanceBehavior: capability.provenance_behavior,
    }))
    .sort((left, right) => left.name.localeCompare(right.name));
}

/**
 * The posture tokens the backend declares, spelled as `CapabilityReadWriteClass` and
 * `CapabilitySideEffectClass` spell them.
 *
 * A posture is read by a person deciding whether a research figure can be reproduced, so it is said
 * in words rather than shown as a lower-case token. A posture this build does not know is not
 * blanked and not guessed at: the caller renders the token the deployment itself sent.
 */
const READ_WRITE_CLASS_KEYS: Readonly<Record<string, string>> = {
  read: "research.capabilities.class_read",
  read_only_compute: "research.capabilities.class_read_only_compute",
  write_materialized: "research.capabilities.class_write_materialized",
  export: "research.capabilities.class_export",
};

const SIDE_EFFECT_CLASS_KEYS: Readonly<Record<string, string>> = {
  none: "research.capabilities.side_effect_none",
  persists_snapshot: "research.capabilities.side_effect_persists_snapshot",
  persists_definition: "research.capabilities.side_effect_persists_definition",
};

/** The translation key for a declared read/write class, or null when it is not one this build knows. */
export function readWriteClassKey(value: string): string | null {
  return READ_WRITE_CLASS_KEYS[value] ?? null;
}

/** The translation key for a declared side-effect class, or null when it is not one this build knows. */
export function sideEffectClassKey(value: string): string | null {
  return SIDE_EFFECT_CLASS_KEYS[value] ?? null;
}

/** Scope families as rows, so a picker or a table reads the deployment's own declaration. */
export function scopeFamilyRows(
  catalogue: DataScopeCatalogue | null,
): Array<{ family: string; scopes: readonly string[] }> {
  if (!catalogue) return [];
  return [
    { family: "public_baseline", scopes: catalogue.public_baseline },
    { family: "commercial", scopes: catalogue.commercial },
    { family: "wildcard", scopes: [catalogue.wildcard] },
  ];
}
