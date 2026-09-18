/**
 * Manual ingestion runs from the source surface (Architecture V2 Wave 4/8, client half).
 *
 * `POST /api/sources/{source_id}/run` queues a MANUAL ingestion run for the dataops worker; the
 * route deliberately does not execute anything itself. The client never called it, so the Source
 * Center *recommended* "Run the source ingestion job" as an operator's next action while offering
 * no control that could do it - a recommendation with no reachable act.
 *
 * This module is the rule for offering it, and it draws one line carefully: the platform's own
 * guards decide whether a run produces data, so the surface **discloses** what it can see about
 * them (credential state, an open circuit, workflow readiness) and blocks only on facts that make
 * the request itself meaningless:
 *
 * - nothing selected, or no runtime store to queue into;
 * - a request already in flight.
 *
 * An operator retry is a deliberate act - the person may be retrying precisely because the circuit
 * tripped - so an open circuit is stated next to the control rather than used to hide it.
 */

export interface SourceRunSubject {
  readonly sourceId: string;
  readonly sourceSystem: string;
  readonly schedulerEnabled: boolean;
  readonly workflowReady: boolean;
  readonly credentialState: string;
  readonly connectivityStatus: string;
  readonly circuitState: string | null | undefined;
  readonly consecutiveFailures: number;
  readonly lastIngestionStatus: string | null | undefined;
}

export interface SourceRunReadiness {
  readonly canRequest: boolean;
  readonly blockerKeys: readonly string[];
  readonly firstBlockerKey: string | null;
  /** What the platform's own guards are doing, as translation keys. Never a silent refusal. */
  readonly disclosureKeys: readonly string[];
}

/** Credential states that mean a run would start without a usable credential. */
function credentialMissing(subject: SourceRunSubject): boolean {
  const state = subject.credentialState.trim().toLowerCase();
  return state !== "" && state !== "configured" && state !== "not_required";
}

/**
 * Whether the manual run may be requested, and what the operator should know before asking.
 *
 * The blocker list is deliberately short: it contains only the states in which there is nothing to
 * ask for. Everything else the client can see is a disclosure, because the decision to run
 * belongs to the operator and the outcome to the platform.
 */
export function sourceRunReadiness(input: {
  readonly subject: SourceRunSubject | null;
  readonly runtimeDbReady: boolean;
  readonly running: boolean;
}): SourceRunReadiness {
  const blockerKeys: string[] = [];
  if (!input.subject) blockerKeys.push("sources.run.blocker.no_source");
  else if (!input.runtimeDbReady) blockerKeys.push("sources.run.blocker.runtime_db");
  if (input.running) blockerKeys.push("sources.run.blocker.in_flight");

  const disclosureKeys: string[] = [];
  const subject = input.subject;
  if (subject) {
    if (credentialMissing(subject)) disclosureKeys.push("sources.run.disclosure.credential_missing");
    if ((subject.circuitState ?? "").toUpperCase() === "OPEN_CIRCUIT") {
      disclosureKeys.push("sources.run.disclosure.circuit_open");
    }
    if (!subject.workflowReady) disclosureKeys.push("sources.run.disclosure.workflow_not_ready");
    if (subject.connectivityStatus.trim().toLowerCase() === "unreachable") {
      disclosureKeys.push("sources.run.disclosure.unreachable");
    }
    if (subject.consecutiveFailures >= 3) {
      disclosureKeys.push("sources.run.disclosure.repeated_failures");
    }
  }

  return {
    canRequest: blockerKeys.length === 0,
    blockerKeys,
    firstBlockerKey: blockerKeys.length > 0 ? blockerKeys[0] : null,
    disclosureKeys,
  };
}

/**
 * The reason recorded on the run.
 *
 * The backend stores it verbatim on the run row, so it names the source and the surface that asked
 * rather than being an empty string: a queued run whose reason cannot be read later is not
 * auditable.
 */
export function sourceRunReason(subject: SourceRunSubject): string {
  const label = subject.sourceSystem.trim() || subject.sourceId.trim() || "unknown-source";
  return `operator-requested from Source Center: ${label}`;
}

/** What a queued run reported, as the surface shows it. */
export interface SourceRunOutcome {
  readonly runId: string | null;
  readonly status: string | null;
  readonly sourceId: string | null;
  readonly triggerType: string | null;
}

/**
 * Read one queued run without inventing fields it did not report.
 *
 * The route returns the run row it queued; a field it did not send stays null, so the surface
 * cannot show a placeholder status as though the run had one.
 */
export function sourceRunOutcome(payload: Record<string, unknown> | null): SourceRunOutcome | null {
  if (!payload) return null;
  const text = (value: unknown): string | null => (typeof value === "string" ? value : null);
  return {
    runId: text(payload.run_id),
    status: text(payload.status),
    sourceId: text(payload.source_id),
    triggerType: text(payload.trigger_type),
  };
}
