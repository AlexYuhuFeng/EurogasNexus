export type ResearchExportDecision = "allowed" | "restricted" | "unknown";

export function researchExportDecision(policy: unknown): ResearchExportDecision {
  if (typeof policy !== "string") return "unknown";
  const normalized = policy.trim().toUpperCase();
  if (normalized === "EXPORT_ALLOWED") return "allowed";
  if (!normalized || normalized === "UNKNOWN") return "unknown";
  return "restricted";
}

export function isCurrentResearchSelection(
  selectedDatasetId: string | null,
  requestedDatasetId: string,
  currentIdentity: string,
  requestedIdentity: string,
): boolean {
  return selectedDatasetId === requestedDatasetId && currentIdentity === requestedIdentity;
}

export function isResearchDetailForSelection(
  selectedDatasetId: string | null,
  detailDatasetId: string,
): boolean {
  return selectedDatasetId !== null && selectedDatasetId === detailDatasetId;
}

export interface SafeResearchErrorMessages {
  generic: string;
  unauthorized: string;
  forbidden: string;
  exportDenied: string;
}

export function safeResearchErrorMessage(
  reason: unknown,
  messages: SafeResearchErrorMessages,
): string {
  const raw = reason instanceof Error ? reason.message : typeof reason === "string" ? reason : "";
  const normalized = raw.toLowerCase();
  if (/^api 403\b/.test(normalized) && /export_denied_entitlement|entitlement|export/.test(normalized)) {
    return messages.exportDenied;
  }
  if (/^api 403\b/.test(normalized)) return messages.forbidden;
  if (/^api 401\b/.test(normalized)) return messages.unauthorized;
  return messages.generic;
}

export function researchDisplayValue(value: unknown, unknownLabel = "Unknown"): string {
  if (value === null || value === undefined || value === "") return unknownLabel;
  if (typeof value === "number" && !Number.isFinite(value)) return unknownLabel;
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  if (Array.isArray(value)) return value.length ? value.map((item) => researchDisplayValue(item, unknownLabel)).join(", ") : unknownLabel;
  try {
    return JSON.stringify(value);
  } catch {
    return unknownLabel;
  }
}

// --- Governed dataset spec/build surface (CR14-UI-001) -----------------------
//
// Every function below is pure derivation: it turns server answers into the
// states the workspace renders. It never decides authorization, never invents a
// default that implies data exists, and never claims a capability the backend
// has not confirmed in an answer.

function asRecord(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function safeText(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}

function safeTextList(value: unknown): string[] {
  return Array.isArray(value)
    ? value.map((item) => safeText(item)).filter((item) => item.length > 0)
    : [];
}

// --- Structured issues ------------------------------------------------------

export interface ResearchIssue {
  field: string;
  code: string;
  message: string;
}

export interface ResearchIssueGroup {
  field: string;
  issues: ResearchIssue[];
}

function normalizeResearchIssue(value: unknown): ResearchIssue | null {
  // Only the structured shape is renderable. A bare string carries no field and
  // no safe code, so it is dropped rather than shown as an unlabelled line, and
  // an entry with neither code nor message carries nothing to render either.
  const record = asRecord(value);
  if (!record) return null;
  const code = safeText(record.code);
  const message = safeText(record.message);
  const field = safeText(record.field);
  if (!code && !message) return null;
  return { field, code, message };
}

/**
 * Normalise the backend's structured ``{field, code, message}`` issues.
 *
 * Entries that are not objects with any readable content are dropped rather
 * than rendered as `[object Object]`; identical triples are collapsed because
 * the backend can report one code more than once for the same field.
 */
export function normalizeResearchIssues(value: unknown): ResearchIssue[] {
  if (!Array.isArray(value)) return [];
  const seen = new Set<string>();
  const issues: ResearchIssue[] = [];
  for (const entry of value) {
    const issue = normalizeResearchIssue(entry);
    if (!issue) continue;
    const key = `${issue.field}\u0000${issue.code}\u0000${issue.message}`;
    if (seen.has(key)) continue;
    seen.add(key);
    issues.push(issue);
  }
  return issues;
}

/** Group issues by their spec field, fields sorted, unassigned field last. */
export function groupResearchIssues(value: unknown): ResearchIssueGroup[] {
  const grouped = new Map<string, ResearchIssue[]>();
  for (const issue of normalizeResearchIssues(value)) {
    const bucket = grouped.get(issue.field);
    if (bucket) bucket.push(issue);
    else grouped.set(issue.field, [issue]);
  }
  return [...grouped.entries()]
    .map(([field, issues]) => ({
      field,
      issues: [...issues].sort(
        (left, right) =>
          left.code.localeCompare(right.code) || left.message.localeCompare(right.message),
      ),
    }))
    .sort((left, right) => {
      if (!left.field) return right.field ? 1 : 0;
      if (!right.field) return -1;
      return left.field.localeCompare(right.field);
    });
}

export function researchIssueTotal(groups: readonly ResearchIssueGroup[]): number {
  return groups.reduce((total, group) => total + group.issues.length, 0);
}

// --- Server answer reading --------------------------------------------------

/**
 * The refusal envelope of an answer, in either shape the workspace can hold:
 * the `{ok:false, failure}` outcome wrapper or a bare `{status, detail}` error.
 */
function failureEnvelope(value: unknown): Record<string, unknown> | null {
  const record = asRecord(value);
  if (!record) return null;
  const nested = asRecord(record.failure);
  if (nested) return nested;
  const status = record.status ?? record.status_code;
  return typeof status === "number" && Number.isFinite(status) ? record : null;
}

/** HTTP status of a failure envelope, or from an ``API <status>:`` message. */
export function researchHttpStatus(value: unknown): number | null {
  const record = failureEnvelope(value) ?? asRecord(value);
  const direct = record?.status ?? record?.status_code;
  if (typeof direct === "number" && Number.isFinite(direct)) return direct;
  const message = value instanceof Error ? value.message : typeof value === "string" ? value : safeText(record?.message);
  const match = /^API (\d{3})\b/.exec(message.trim());
  return match ? Number(match[1]) : null;
}

/** Machine code of a refusal (``error`` on spec failures, ``code`` otherwise). */
export function researchAnswerCode(value: unknown): string {
  const base = failureEnvelope(value) ?? asRecord(value);
  if (!base) return "";
  const detail = asRecord(base.detail);
  for (const scope of [detail, base]) {
    const code = safeText(scope?.code) || safeText(scope?.error);
    if (code) return code;
  }
  return "";
}

/** Server-reported registered formats, or null when the answer never named any. */
export function researchAvailableFormats(value: unknown): string[] | null {
  const base = failureEnvelope(value) ?? asRecord(value);
  if (!base) return null;
  for (const scope of [base, asRecord(base.detail)]) {
    if (scope && Array.isArray(scope.available_formats)) return safeTextList(scope.available_formats);
  }
  return null;
}

/** Structured issues carried by a validate answer or a 422 refusal. */
export function researchIssuesFromAnswer(value: unknown): ResearchIssue[] {
  const base = failureEnvelope(value) ?? asRecord(value);
  if (!base) return [];
  if (Array.isArray(base.issues)) return normalizeResearchIssues(base.issues);
  const detail = asRecord(base.detail);
  return detail ? normalizeResearchIssues(detail.issues) : [];
}

export interface ResearchRequestMessages {
  unauthorized: string;
  forbidden: string;
  generic: string;
}

/**
 * Localised copy for a failed validate/build request. Only the status class is
 * used, so no backend text, path, or SQL fragment can reach the screen.
 */
export function researchRequestErrorMessage(
  reason: unknown,
  messages: ResearchRequestMessages,
): string {
  const status = researchHttpStatus(reason);
  if (status === 401) return messages.unauthorized;
  if (status === 403) return messages.forbidden;
  return messages.generic;
}

// --- Spec draft -------------------------------------------------------------

export interface ResearchSpecDraft {
  datasetSpecId: string;
  name: string;
  description: string;
  featureIds: string;
  targetIds: string;
  entityIds: string;
  start: string;
  end: string;
  historyLookback: string;
  forecastOriginFrequency: string;
  resamplingPolicyId: string;
  outputFormat: string;
}

/**
 * A blank draft: no field carries a value the operator did not type, so the
 * form can never imply that a dataset, feature, or target is available.
 */
export const EMPTY_RESEARCH_SPEC_DRAFT: ResearchSpecDraft = {
  datasetSpecId: "",
  name: "",
  description: "",
  featureIds: "",
  targetIds: "",
  entityIds: "",
  start: "",
  end: "",
  historyLookback: "",
  forecastOriginFrequency: "",
  resamplingPolicyId: "",
  outputFormat: "",
};

/**
 * Inputs the request needs before it is worth sending. These mirror fields the
 * backend model requires (``DatasetSpec`` has no default for them); they are a
 * request-shape check, never an authorization or data-availability decision.
 */
export const RESEARCH_SPEC_REQUIRED_INPUTS: ReadonlyArray<keyof ResearchSpecDraft> = [
  "datasetSpecId",
  "name",
  "description",
  "targetIds",
  "start",
  "end",
];

export function researchSpecListValues(value: string): string[] {
  return value
    .split(/[,\n]/)
    .map((item) => item.trim())
    .filter((item) => item.length > 0);
}

export function researchSpecMissingInputs(
  draft: ResearchSpecDraft,
): Array<keyof ResearchSpecDraft> {
  return RESEARCH_SPEC_REQUIRED_INPUTS.filter((key) => !draft[key].trim());
}

/**
 * Build the ``dataset_spec`` body from the draft.
 *
 * Only values the operator entered are sent: an omitted key lets the backend
 * apply its own documented default, so the client never fabricates a frequency,
 * lookback, policy, or format that would imply a dataset exists.
 */
export function researchSpecFromDraft(draft: ResearchSpecDraft): Record<string, unknown> {
  const spec: Record<string, unknown> = {};
  const putText = (key: string, value: string) => {
    const text = value.trim();
    if (text) spec[key] = text;
  };
  putText("dataset_spec_id", draft.datasetSpecId);
  putText("name", draft.name);
  putText("description", draft.description);
  putText("start", draft.start);
  putText("end", draft.end);
  putText("history_lookback", draft.historyLookback);
  putText("forecast_origin_frequency", draft.forecastOriginFrequency);
  putText("resampling_policy_id", draft.resamplingPolicyId);
  putText("output_format", draft.outputFormat);
  const putList = (key: string, value: string) => {
    const values = researchSpecListValues(value);
    if (values.length) spec[key] = values;
  };
  putList("feature_ids", draft.featureIds);
  putList("target_ids", draft.targetIds);
  putList("entity_ids", draft.entityIds);
  return spec;
}

function stableStringify(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(stableStringify).join(",")}]`;
  const record = asRecord(value);
  if (record) {
    return `{${Object.keys(record)
      .sort()
      .map((key) => `${JSON.stringify(key)}:${stableStringify(record[key])}`)
      .join(",")}}`;
  }
  return JSON.stringify(value) ?? "null";
}

/** Identity of a spec body, used to detect a draft edited after validation. */
export function researchSpecFingerprint(spec: Record<string, unknown>): string {
  return stableStringify(spec);
}

// --- Validation -------------------------------------------------------------

export interface ResearchValidationOutcome {
  ok: boolean;
  specHash: string;
  registryResolution: string;
  issues: ResearchIssue[];
  code: string;
}

/**
 * Read a validate answer.
 *
 * ``ok`` is a conjunction: the backend must report ``ok: true`` *and* carry no
 * structured issues, so a partial or contradictory answer can never unlock the
 * build action.
 */
export function researchValidationOutcome(value: unknown): ResearchValidationOutcome {
  const failure = failureEnvelope(value);
  const payload = (failure ? asRecord(failure.detail) : null) ?? failure ?? asRecord(value) ?? {};
  const issues = researchIssuesFromAnswer(value);
  const reportedOk = payload.ok === true;
  return {
    ok: reportedOk && issues.length === 0,
    specHash: safeText(payload.spec_hash),
    registryResolution: safeText(payload.registry_resolution),
    issues,
    code: researchAnswerCode(value),
  };
}

// --- Build gating -----------------------------------------------------------

export type ResearchBuildGateReason =
  | "not_validated"
  | "spec_changed"
  | "validation_failed"
  | "ready";

export interface ResearchBuildGate {
  canBuild: boolean;
  reason: ResearchBuildGateReason;
}

/** The last validation the operator ran, and whether it accepted that spec. */
export interface ResearchValidatedSpec {
  fingerprint: string;
  ok: boolean;
}

/**
 * Build is enabled only for the exact spec body the backend just accepted.
 * Editing any field after validation re-locks the action, and a rejected spec
 * never unlocks it.
 */
export function researchBuildGate(
  lastValidation: ResearchValidatedSpec | null,
  currentFingerprint: string,
): ResearchBuildGate {
  if (!lastValidation) return { canBuild: false, reason: "not_validated" };
  if (lastValidation.fingerprint !== currentFingerprint) return { canBuild: false, reason: "spec_changed" };
  if (!lastValidation.ok) return { canBuild: false, reason: "validation_failed" };
  return { canBuild: true, reason: "ready" };
}

export interface ResearchBuildSummary {
  datasetSnapshotId: string;
  datasetSpecId: string;
  specHash: string;
  artifactRef: string | null;
  rowCount: number | null;
  columnCount: number | null;
  availableFormats: string[] | null;
}

function numberOrNull(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

/** Read a materialize answer; null when the payload is not a build reply. */
export function researchBuildSummary(value: unknown): ResearchBuildSummary | null {
  const failure = failureEnvelope(value);
  const payload = (failure ? asRecord(failure.detail) : null) ?? (failure ? null : asRecord(value));
  if (!payload) return null;
  const snapshotId = safeText(payload.dataset_snapshot_id);
  if (!snapshotId) return null;
  const qualifiedVersion = safeText(payload.dataset_spec_version);
  return {
    datasetSnapshotId: snapshotId,
    datasetSpecId: safeText(payload.dataset_spec_id),
    // The build answer qualifies the version as <spec>@<version>@<hash8>, and the
    // backend persists the last segment as the snapshot spec hash.
    specHash: safeText(payload.spec_hash) || (qualifiedVersion.split("@").at(-1) ?? ""),
    artifactRef: safeText(payload.artifact_ref) || null,
    rowCount: numberOrNull(payload.row_count),
    columnCount: numberOrNull(payload.column_count),
    availableFormats: researchAvailableFormats(payload),
  };
}

// --- Export artifact delivery ----------------------------------------------

export const RESEARCH_EXPORT_FORMATS = ["parquet", "csv"] as const;
export type ResearchExportFormat = (typeof RESEARCH_EXPORT_FORMATS)[number];

export type ResearchFormatAvailability = "registered" | "unregistered" | "unknown";

export interface ResearchFormatRow {
  format: string;
  availability: ResearchFormatAvailability;
}

export type ResearchExportStatus =
  | "not_requested"
  | "granted"
  | "restricted"
  | "format_unregistered"
  | "file_missing"
  | "unavailable";

export interface ResearchExportState {
  status: ResearchExportStatus;
  httpStatus: number | null;
  code: string;
  reason: string;
  format: string | null;
  artifactRef: string | null;
  artifactId: string | null;
  artifactSha256: string | null;
  entitlementPolicy: string | null;
  availableFormats: string[] | null;
}

function emptyExportState(): ResearchExportState {
  return {
    status: "not_requested",
    httpStatus: null,
    code: "",
    reason: "",
    format: null,
    artifactRef: null,
    artifactId: null,
    artifactSha256: null,
    entitlementPolicy: null,
    availableFormats: null,
  };
}

/**
 * Derive the artifact-delivery state from one server answer.
 *
 * The permissions and formats always come from the answer: a 403 leaves the
 * surface restricted, a 409 reports which format was refused and which formats
 * the backend actually has, and only a 200 with a referenced artifact counts as
 * granted. No answer means "not requested" -- never an implied success.
 */
export function researchExportStateFromAnswer(value: unknown): ResearchExportState {
  if (value === null || value === undefined) return emptyExportState();
  const record = asRecord(value);
  if (!record) return emptyExportState();
  const failure = failureEnvelope(value);
  const state = emptyExportState();
  if (failure) {
    state.httpStatus = researchHttpStatus(failure);
    const detail = asRecord(failure.detail) ?? {};
    state.code = researchAnswerCode(failure);
    state.reason = safeText(detail.reason);
    state.format = safeText(detail.format) || null;
    state.availableFormats = researchAvailableFormats(failure);
    state.entitlementPolicy = safeText(detail.policy) || null;
    if (state.httpStatus === 403) {
      state.status = "restricted";
    } else if (state.httpStatus === 409 && state.reason === "FORMAT_NOT_REGISTERED") {
      state.status = "format_unregistered";
    } else if (state.httpStatus === 409 && state.reason === "FILE_MISSING") {
      state.status = "file_missing";
    } else {
      state.status = "unavailable";
    }
    return state;
  }
  const payload = asRecord(record.data) ?? record;
  const snapshotId = safeText(payload.dataset_snapshot_id);
  const format = safeText(payload.format);
  if (!snapshotId || !format) return state;
  state.status = "granted";
  state.httpStatus = 200;
  state.format = format;
  state.artifactRef = safeText(payload.artifact_ref) || null;
  state.artifactId = safeText(payload.artifact_id) || null;
  state.artifactSha256 = safeText(payload.artifact_sha256) || null;
  state.entitlementPolicy = safeText(payload.entitlement_policy) || null;
  state.availableFormats = researchAvailableFormats(payload);
  return state;
}

/** Whether a request for an artifact reference may be offered at all. */
export function researchExportCanRequest(decision: ResearchExportDecision): boolean {
  return decision === "allowed";
}

export function researchFormatAvailability(
  availableFormats: readonly string[] | null,
  format: string,
): ResearchFormatAvailability {
  if (availableFormats === null) return "unknown";
  return availableFormats.includes(format) ? "registered" : "unregistered";
}

/**
 * Formats the operator may ask for.
 *
 * Before any answer the deployment's candidate formats are offered (nothing has
 * been refused yet). Once an answer reports the registered formats, only those
 * are offered, so a refused format is never requested twice.
 */
export function researchFormatOptions(
  availableFormats: readonly string[] | null,
): string[] {
  if (availableFormats === null) return [...RESEARCH_EXPORT_FORMATS];
  return [...availableFormats];
}

export function researchFormatRows(
  availableFormats: readonly string[] | null,
): ResearchFormatRow[] {
  const formats = availableFormats === null
    ? [...RESEARCH_EXPORT_FORMATS]
    : [...new Set([...RESEARCH_EXPORT_FORMATS, ...availableFormats])];
  return formats.map((format) => ({
    format,
    availability: researchFormatAvailability(availableFormats, format),
  }));
}

/** Preferred requestable format: the operator's choice when it is registered. */
export function researchPreferredFormat(
  availableFormats: readonly string[] | null,
  preferred: string,
): string | null {
  const options = researchFormatOptions(availableFormats);
  if (!options.length) return null;
  return options.includes(preferred) ? preferred : (options[0] ?? null);
}
