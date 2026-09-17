export type StatusBadgeVariant = "source" | "pipeline" | "runtime-readiness-state" | "job-state";

const STATUS_BADGE_BASE: Record<StatusBadgeVariant, string> = {
  source: "source-status",
  pipeline: "pipeline-status",
  "runtime-readiness-state": "runtime-readiness-state",
  "job-state": "job-state",
};

export function statusBadgeClass(variant: StatusBadgeVariant, status: string): string {
  const base = STATUS_BADGE_BASE[variant];
  // Readiness badges already carry the state as a bare modifier class
  // (runtime-readiness-state ready); source and pipeline badges use a
  // prefix-status class (source-status-active, pipeline-status-succeeded).
  if (variant === "runtime-readiness-state") return `${base} ${status}`;
  // Job states arrive as the lifecycle constant (SUCCEEDED); the class is lower case.
  if (variant === "job-state") return `${base} ${base}-${status.toLowerCase()}`;
  return `${base} ${base}-${status}`;
}
