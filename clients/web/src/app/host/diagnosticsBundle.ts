/**
 * Diagnostics bundle composition (Architecture V2 Wave 10, consumer surface).
 *
 * Wave 10 declared the bundle contract - an allowlist with declared forbidden names, and
 * `buildDiagnosticsBundle` as the only way to compose one - but nothing in the product ever
 * composed one, so the contract was a claim with no consumer. This module is that consumer's
 * rule: it takes the facts the client already holds and produces the exact bundle that would
 * leave the machine, plus what it could not report.
 *
 * Two things it deliberately does not do:
 *
 * - it does not invent a value for a fact the client does not have. A declared field with no
 *   fact behind it is reported as unavailable, so the surface can say so instead of printing a
 *   zero that reads like a measurement;
 * - it does not reach for anything outside the allowlist, and it composes through
 *   `buildDiagnosticsBundle` rather than assembling an object of its own, so the forbidden
 *   names stay enforced in one place.
 */

import { CLIENT_RELEASE_METADATA } from "../releaseCompatibility.ts";
import { hostCapabilities, type HostCapabilities, type HostKind } from "./hostCapabilities.ts";
import { buildDiagnosticsBundle, DIAGNOSTICS_ALLOWED_FIELDS } from "./workstation.ts";

/** The client facts a bundle is composed from. Every one of them is already in memory. */
export interface DiagnosticsFacts {
  readonly hostKind: HostKind;
  readonly capabilities: HostCapabilities;
  readonly language: string;
  /** Server application version, from the deployment's own release metadata. */
  readonly serverVersion: string | null;
  /** Alembic revision the deployment reports, not the one a client hopes for. */
  readonly schemaRevision: string | null;
  /** Client/server compatibility state, e.g. `compatible`. */
  readonly releaseCompatibility: string | null;
  readonly dataStatus: string | null;
  /** Endpoint slice to failure code, as the loaders reported them. */
  readonly endpointFailureCodes: Record<string, string> | null;
  /** Degraded projection slices, as `lane:slice:STATE`. */
  readonly degradedSlices: readonly string[] | null;
  /** Job status to count, from the unified job model. */
  readonly jobStates: Record<string, number> | null;
  /** When the bundle was composed; supplied by the caller so the rule stays pure. */
  readonly generatedAtUtc: string;
}

export interface DiagnosticsComposition {
  /** The bundle as it would leave the client: only declared fields, only real values. */
  readonly bundle: Record<string, unknown>;
  /**
   * Declared fields with no fact behind them. The surface states these rather than letting a
   * reader assume the deployment reported nothing wrong.
   */
  readonly unavailableFields: readonly string[];
}

/**
 * Compose the bundle from the client's own facts.
 *
 * `clientVersion` is the one field the client always knows, because it is this build's own
 * identity. Everything else is either reported by the deployment or reported as unavailable.
 */
export function composeDiagnosticsBundle(facts: DiagnosticsFacts): DiagnosticsComposition {
  const candidates: Record<string, unknown> = {
    clientVersion: CLIENT_RELEASE_METADATA.version,
    serverVersion: facts.serverVersion,
    releaseCompatibility: facts.releaseCompatibility,
    schemaRevision: facts.schemaRevision,
    hostKind: facts.hostKind,
    capabilities: { ...facts.capabilities },
    language: facts.language,
    dataStatus: facts.dataStatus,
    endpointFailureCodes: facts.endpointFailureCodes,
    degradedSlices: facts.degradedSlices,
    jobStates: facts.jobStates,
    generatedAtUtc: facts.generatedAtUtc,
  };

  const reported: Record<string, unknown> = {};
  for (const [field, value] of Object.entries(candidates)) {
    if (value === null || value === undefined) continue;
    reported[field] = value;
  }

  const bundle = buildDiagnosticsBundle(reported);
  return {
    bundle,
    unavailableFields: DIAGNOSTICS_ALLOWED_FIELDS.filter((field) => !(field in bundle)),
  };
}

/** How the composed bundle leaves the client. */
export interface DiagnosticsHandover {
  readonly method: "browser-download";
  /** Translation keys explaining the handover for this host, in order. */
  readonly noteKeys: readonly string[];
}

/**
 * How the bundle is handed over, per host.
 *
 * Both hosts hand the bundle over as a download from the WebView itself. The desktop host
 * *declares* `diagnosticsExport`, but the native save is not implemented in this build and no
 * allowlisted command exists for it, so this says that rather than offering a control with
 * nothing behind it. When that command arrives, it belongs in `HOST_COMMANDS` with its
 * capability class before any surface calls it.
 */
export function diagnosticsHandover(kind: HostKind): DiagnosticsHandover {
  const noteKeys = ["diagnostics.handover.download"];
  if (hostCapabilities(kind).diagnosticsExport) {
    noteKeys.push("diagnostics.handover.native_export_pending");
  }
  return { method: "browser-download", noteKeys };
}

/** An ISO-8601 UTC instant, as `generatedAtUtc` is required to be. */
const ISO_UTC_PREFIX = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})/;

/**
 * The suggested file name. Support evidence is identified by when it was taken, and the name
 * carries nothing else - no host name, no principal, no deployment identifier.
 *
 * Only a real ISO-8601 instant is read, so the guarantee is structural rather than a property
 * of the current caller: anything else produces the unnamed fallback instead of a name built
 * from whatever string it was handed.
 */
export function diagnosticsBundleFileName(generatedAtUtc: string): string {
  const match = ISO_UTC_PREFIX.exec(generatedAtUtc);
  if (!match) return "eurogas-nexus-diagnostics.json";
  const [, year, month, day, hour, minute, second] = match;
  return `eurogas-nexus-diagnostics-${year}${month}${day}T${hour}${minute}${second}.json`;
}
