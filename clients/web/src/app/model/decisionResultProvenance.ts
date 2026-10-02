/**
 * Deterministic result provenance for the Decision workspace's governed computes.
 *
 * A result is only current for the inputs it was computed from. The trading context (gas day,
 * delivery product, hub) is one part of that, and `decisionActionModel.ts` already refuses to
 * present a result whose context has changed. But the two governed computes - Compare Options
 * and Optimize Resource Pool - read more than the trading context: the persisted contract
 * economics behind the resource-pool read, the market marks that read exposed, and (for the
 * optimiser) the annual financing-rate input. Editing any of those used to leave the previous
 * result displayed as current.
 *
 * This module owns one posture for all of them:
 *
 * - `decisionInputIdentity` canonicalises the caller-known effective inputs: the exact request
 *   object the client will send, plus the identity tokens the caller's reads exposed (saved
 *   contract edit tokens, sale-price observation marks). Object keys are sorted; explicitly
 *   unordered string collections (`required_tso_access`, `accessible_tsos`, ...) are sorted too;
 *   every other array keeps its order, and numbers, `null`, `false` and `0` are preserved
 *   exactly (an absent field is not the same identity as a recorded `null`).
 * - `decisionProvenanceKey` is what a run is stamped with: which action, the trading context,
 *   and the input identity. Two actions with the same inputs still carry distinct keys because
 *   their request dependencies differ.
 * - `decisionProvenanceMismatch` is the one rule consumers apply: a held result whose key does
 *   not equal the key of the inputs the caller now knows is stale, and a result the client
 *   cannot vouch for (null key, or no current key) is stale as well.
 *
 * Limits that must not be overstated:
 *
 * - The backend exposes no immutable snapshot, revision hash or read token for the composed
 *   resource-pool payload or the market rows behind it. The identity therefore proves which
 *   inputs *the caller sent and believed*, not what the backend read or executed against; no
 *   hash value is presented as server-verified proof of a server-side input snapshot.
 * - Only fields the client can name deterministically are part of the identity: a re-read that
 *   returns the same values yields the same identity by design, and a draft field no request
 *   consumes is not part of any identity.
 */

/** Which governed act a provenance key belongs to. */
export type DecisionProvenanceScope =
  | "optimize_pool"
  | "compare_routes"
  | "strategy_evaluation";

/**
 * Keys whose array value is a semantically unordered set of strings (TSO access names, allowed
 * exit points, evidence references). Sorting only these keeps a re-read that returns the same
 * set in another order from marking a result stale, while leaving every order-meaningful array
 * (resources, sale options, candidates, price observations) in its own order.
 */
export const UNORDERED_DECISION_INPUT_KEYS: ReadonlySet<string> = new Set([
  "required_tso_access",
  "accessible_tsos",
  "company_accessible_tsos",
  "allowed_exit_points",
  "eligible_sale_modes",
  "eligible_resource_ids",
  "source_refs",
]);

/** One saved upstream contract as the caller's library read exposed it. */
export interface SavedContractIdentityLike {
  contract_id?: string | null;
  edit_token?: string | null;
  updated_at_utc?: string | null;
}

/** The market-read marks one resource-pool sale option carries. */
export interface MarketReadIdentityLike {
  option_id?: string | null;
  sale_price_gbp_mwh?: number | null;
  sale_price_observed_at_utc?: string | null;
  sale_price_source_system?: string | null;
  sale_price_source_reference?: string | null;
  sale_price_freshness?: string | null;
  sale_price_quality_score?: number | null;
  sale_price_simulated?: boolean | null;
}

export interface DecisionInputIdentityParts {
  /**
   * The exact request object the client will send. It must be the composed request, not the
   * inputs it was composed from, so a field the request ignores cannot invalidate a result.
   */
  readonly request: unknown;
  /** The saved-contract identity tokens the caller's library read exposed. */
  readonly savedContracts?: readonly SavedContractIdentityLike[];
  /**
   * The market-read marks the sale options were derived from. Needed where the request
   * projection drops them (the route comparison sends only prices and costs); a request that
   * embeds its own observations (the strategy evaluation) already covers them through
   * `request`.
   */
  readonly marketReads?: readonly MarketReadIdentityLike[];
}

/**
 * Serialise a value deterministically: sorted object keys, order-preserving arrays (except the
 * explicitly unordered string sets above), and exact number/`null`/boolean rendering.
 */
export function canonicalDecisionIdentity(
  value: unknown,
  unorderedKeys: ReadonlySet<string> = UNORDERED_DECISION_INPUT_KEYS,
): string {
  return canonicalValue(value, null, unorderedKeys);
}

function canonicalValue(
  value: unknown,
  key: string | null,
  unorderedKeys: ReadonlySet<string>,
): string {
  if (value === null) return "null";
  if (value === undefined) return "undefined";
  if (typeof value === "number") {
    // No finite-preserving shortcut: NaN and infinities are recorded as themselves rather than
    // serialised to `null` (JSON.stringify would lose them).
    if (Number.isNaN(value)) return "nan";
    if (value === Number.POSITIVE_INFINITY) return "inf";
    if (value === Number.NEGATIVE_INFINITY) return "-inf";
    return String(value);
  }
  if (typeof value === "string") return JSON.stringify(value);
  if (typeof value === "boolean") return value ? "true" : "false";
  if (Array.isArray(value)) {
    const items = value.map((item) => canonicalValue(item, null, unorderedKeys));
    const sortable =
      key !== null &&
      unorderedKeys.has(key) &&
      value.every((item) => typeof item === "string");
    if (sortable) items.sort();
    return `[${items.join(",")}]`;
  }
  if (typeof value === "object") {
    const record = value as Record<string, unknown>;
    const parts = Object.keys(record)
      .sort()
      .map(
        (entryKey) =>
          `${JSON.stringify(entryKey)}:${canonicalValue(record[entryKey], entryKey, unorderedKeys)}`,
      );
    return `{${parts.join(",")}}`;
  }
  return JSON.stringify(String(value));
}

/**
 * Identity tokens for the saved contracts the resource-pool read is composed from.
 *
 * The edit token is the stored row's opaque stale-edit lease; `updated_at_utc` is the fallback
 * for a row that exposes no token. A row exposing neither contributes a constant marker, and
 * that limit is stated rather than hidden: the client cannot prove such a row unchanged.
 */
export function savedContractIdentityTokens(
  contracts: readonly SavedContractIdentityLike[],
): string[] {
  const tokens = contracts.map((contract) => {
    const id = contract.contract_id ?? "unknown-contract";
    const token =
      contract.edit_token ??
      (contract.updated_at_utc ? `updated_at:${contract.updated_at_utc}` : "unavailable");
    return `${id}@${token}`;
  });
  return [...new Set(tokens)].sort();
}

/**
 * Identity tokens for the market read behind the sale options: the observation the read
 * selected and the marks that describe it, never a claim that the backend re-read the same row.
 */
export function marketReadIdentityTokens(
  saleOptions: readonly MarketReadIdentityLike[],
): string[] {
  const tokens = saleOptions.map((option) =>
    canonicalDecisionIdentity([
      option.option_id ?? "unknown-option",
      option.sale_price_gbp_mwh ?? null,
      option.sale_price_observed_at_utc ?? null,
      option.sale_price_source_system ?? null,
      option.sale_price_source_reference ?? null,
      option.sale_price_freshness ?? null,
      option.sale_price_quality_score ?? null,
      option.sale_price_simulated ?? null,
    ]),
  );
  return [...new Set(tokens)].sort();
}

/** The canonical input identity of one governed act's caller-known effective inputs. */
export function decisionInputIdentity(parts: DecisionInputIdentityParts): string {
  return canonicalDecisionIdentity({
    request: parts.request ?? null,
    saved_contracts: savedContractIdentityTokens(parts.savedContracts ?? []),
    market_reads: marketReadIdentityTokens(parts.marketReads ?? []),
  });
}

/** The key a run is stamped with: action scope, trading context and input identity. */
export function decisionProvenanceKey(
  scope: DecisionProvenanceScope,
  tradingContextKey: string,
  inputIdentity: string,
): string {
  return `${scope}::${tradingContextKey}::${inputIdentity}`;
}

/**
 * The one mismatch rule: a held result is current only while its provenance key equals the key
 * of the inputs the caller now knows. An unknown key on either side is not a match - a result
 * the client cannot vouch for is stale, never silently current.
 */
export function decisionProvenanceMismatch(
  hasResult: boolean,
  resultProvenanceKey: string | null,
  currentProvenanceKey: string | null,
): boolean {
  if (!hasResult) return false;
  return resultProvenanceKey === null || resultProvenanceKey !== currentProvenanceKey;
}
