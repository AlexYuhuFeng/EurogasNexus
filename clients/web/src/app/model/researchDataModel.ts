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
