import type { RuntimeDbStatusDTO } from "@/api/client";

/**
 * The shell's runtime data-availability badge.
 *
 * `dataStatus` is the workspace batch's *provenance* reading: which store answered,
 * as the batch's `source_references` and the runtime-database status report it - the
 * runtime PostgreSQL store answered, only some of it did, or none did. It says
 * nothing about whether the market data inside that store is fresh, complete,
 * licensed or fit to decide on, so no surface may render it as an overall "Ready"
 * (September 2026 authenticated-HMI audit, readiness semantics).
 *
 * `dataPlaneState` keeps the established chip vocabulary's *tone* (the
 * `runtime-readiness-state` modifiers, the market grid's ready/issue class).
 * `runtimeDataAvailability` names what a label actually claims, and
 * `runtimeDataAvailabilityLabelKey` is the one place a surface gets the words, so
 * the header, settings and the market grid cannot drift apart. Surfaces that show a
 * caption beside the value take `RUNTIME_DATA_AVAILABILITY_CAPTION_KEY` rather than
 * writing their own phrase.
 *
 * Fail-closed: only the states this module knows yield a state label at all -
 * anything else reads as `unknown` - and the tone never reads as healthy unless the
 * runtime store actually answered. The `delayed` slot the store type still carries
 * with no producer keeps its own label but the fail-closed tone.
 */

export type DataPlaneState = "ready" | "partial" | "unavailable";

export function dataPlaneState(dataStatus: string | null | undefined): DataPlaneState {
  if (dataStatus === "runtime") return "ready";
  if (dataStatus === "partial") return "partial";
  return "unavailable";
}

/**
 * What the workspace batch reported about the runtime store's own data.
 *
 * A value this module does not model - nothing loaded yet, or a token the client
 * has never heard of - is `unknown`, never a guess.
 */
export type RuntimeDataAvailability = "available" | "partial" | "delayed" | "unavailable" | "unknown";

const AVAILABILITY_BY_STATUS = new Map<string, RuntimeDataAvailability>([
  ["runtime", "available"],
  ["partial", "partial"],
  ["delayed", "delayed"],
  ["unavailable", "unavailable"],
]);

export function runtimeDataAvailability(
  dataStatus: string | null | undefined,
): RuntimeDataAvailability {
  const known = typeof dataStatus === "string" ? AVAILABILITY_BY_STATUS.get(dataStatus) : undefined;
  return known ?? "unknown";
}

const AVAILABILITY_LABEL_KEYS: Readonly<Record<RuntimeDataAvailability, string>> = {
  available: "data.runtime_available",
  partial: "data.runtime_partial",
  delayed: "data.runtime_delayed",
  unavailable: "data.runtime_unavailable",
  unknown: "data.runtime_unknown",
};

/** Translation key for a runtime-data-availability label, so every surface shares one label. */
export function runtimeDataAvailabilityLabelKey(availability: RuntimeDataAvailability): string {
  return AVAILABILITY_LABEL_KEYS[availability];
}

/** Translation key for the caption naming what those labels are about. */
export const RUNTIME_DATA_AVAILABILITY_CAPTION_KEY = "data.runtime_availability";

/**
 * Whether the runtime store's own status read has answered for this session.
 *
 * The status slice is null until the workspace batch's status read answers, and it stays null when
 * that read fails or is superseded. Neither is the fact "the store answered and is not connected",
 * which is what a surface claims when it renders a boolean `runtimeDbReady` as `false`.
 */
export type RuntimeStoreStatus = "unknown" | "ready" | "unavailable";

export function runtimeStoreStatus(
  runtimeDb: RuntimeDbStatusDTO | null | undefined,
): RuntimeStoreStatus {
  if (!runtimeDb) return "unknown";
  return runtimeDb.database_url_present === true && runtimeDb.connectivity.ok === true
    ? "ready"
    : "unavailable";
}
