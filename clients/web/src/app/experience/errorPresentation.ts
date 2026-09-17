/**
 * Error presentation (Architecture V2 Wave 8, client half).
 *
 * Architecture V2 requires a failure to answer four questions in one consistent
 * place: what happened, what it affects, the likely cause, and how to recover.
 * The backend supplies a stable code, family, severity and recoverability
 * (`domain/operations/error_taxonomy.py`); this module turns that into the
 * presentation vocabulary, so a surface never has to interpret a raw exception
 * string and never invents its own wording.
 *
 * Unknown codes fail closed to a generic SYSTEM explanation that still names the
 * correlation id, so a user always has something to quote to an operator.
 */

export interface ApiErrorBody {
  readonly error?: string;
  readonly family?: string;
  readonly severity?: string;
  readonly recoverability?: string;
  readonly message?: string;
  readonly message_key?: string;
  readonly action_key?: string;
  readonly correlation_id?: string | null;
}

export type ErrorFamilyId =
  | "AUTH"
  | "ENTITLEMENT"
  | "VALIDATION"
  | "DATA"
  | "CALCULATION"
  | "DEPENDENCY"
  | "CONFIGURATION"
  | "JOB"
  | "AGENT"
  | "SYSTEM";

const FAMILIES: readonly ErrorFamilyId[] = [
  "AUTH",
  "ENTITLEMENT",
  "VALIDATION",
  "DATA",
  "CALCULATION",
  "DEPENDENCY",
  "CONFIGURATION",
  "JOB",
  "AGENT",
  "SYSTEM",
];

export interface ErrorPresentation {
  readonly code: string;
  readonly family: ErrorFamilyId;
  readonly severity: "info" | "warning" | "error" | "critical";
  readonly recoverability: "retry" | "after_user_action" | "permanent" | "unknown";
  /** What happened. */
  readonly titleKey: string;
  /** What it affects. */
  readonly impactKey: string;
  /** The likely cause. */
  readonly causeKey: string;
  /** How to recover. */
  readonly actionKey: string;
  /** Backend-supplied safe message, when present. */
  readonly message: string | null;
  readonly correlationId: string | null;
}

const SEVERITIES = ["info", "warning", "error", "critical"] as const;
const RECOVERABILITIES = ["retry", "after_user_action", "permanent", "unknown"] as const;

function asFamily(value: unknown): ErrorFamilyId {
  return FAMILIES.includes(value as ErrorFamilyId) ? (value as ErrorFamilyId) : "SYSTEM";
}

function asSeverity(value: unknown): ErrorPresentation["severity"] {
  return SEVERITIES.includes(value as (typeof SEVERITIES)[number])
    ? (value as ErrorPresentation["severity"])
    : "error";
}

function asRecoverability(value: unknown): ErrorPresentation["recoverability"] {
  return RECOVERABILITIES.includes(value as (typeof RECOVERABILITIES)[number])
    ? (value as ErrorPresentation["recoverability"])
    : "unknown";
}

/**
 * Codes with their own cause wording. Everything else falls back to the family's
 * explanation, which is still specific enough to be actionable.
 */
const CODE_CAUSES: Readonly<Record<string, string>> = {
  unauthenticated: "errors.cause.session_missing",
  invalid_credentials: "errors.cause.credentials_rejected",
  session_invalid: "errors.cause.session_expired",
  identity_role_forbidden: "errors.cause.role_insufficient",
  permission_denied: "errors.cause.capability_missing",
  entitlement_denied: "errors.cause.licence_restriction",
  commercial_access_not_granted: "errors.cause.administration_is_not_commercial",
  entitlement_self_grant_forbidden: "errors.cause.self_grant_refused",
  export_denied: "errors.cause.export_restriction",
  DATA_STALE: "errors.cause.data_beyond_freshness",
  DATA_MISSING: "errors.cause.source_has_no_rows",
  PORTFOLIO_INCOMPLETE: "errors.cause.portfolio_inputs_missing",
  SNAPSHOT_EXPIRED: "errors.cause.snapshot_out_of_date",
  ROUTE_INFEASIBLE: "errors.cause.constraints_block_route",
  OPTIMIZATION_INFEASIBLE: "errors.cause.no_feasible_allocation",
  PROVIDER_UNAVAILABLE: "errors.cause.provider_unreachable",
  runtime_db_unavailable: "errors.cause.runtime_store_unreachable",
  AGENT_BUDGET_EXCEEDED: "errors.cause.agent_budget_reached",
  JOB_FAILED: "errors.cause.job_step_failed",
};

export function describeApiError(body: ApiErrorBody | null | undefined): ErrorPresentation {
  const code = (body?.error ?? "").trim() || "UNCLASSIFIED_ERROR";
  const family = asFamily(body?.family);
  const severity = asSeverity(body?.severity);
  const recoverability = asRecoverability(body?.recoverability);

  return {
    code,
    family,
    severity,
    recoverability,
    titleKey: body?.message_key ?? `errors.${code}.message`,
    impactKey: `errors.family.${family}.impact`,
    causeKey: CODE_CAUSES[code] ?? `errors.family.${family}.cause`,
    actionKey: body?.action_key ?? `errors.family.${family}.action`,
    message: body?.message?.trim() ? body.message.trim() : null,
    correlationId: body?.correlation_id ?? null,
  };
}

/** Whether a retry is worth offering, so a surface does not show a dead button. */
export function isRetryable(presentation: ErrorPresentation): boolean {
  return presentation.recoverability === "retry";
}

/** Whether the user must change something (context, entitlement, input) first. */
export function requiresUserAction(presentation: ErrorPresentation): boolean {
  return presentation.recoverability === "after_user_action";
}

export function errorFamilyIds(): readonly ErrorFamilyId[] {
  return FAMILIES;
}
