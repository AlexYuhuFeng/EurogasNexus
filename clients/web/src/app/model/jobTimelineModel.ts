/**
 * Job timeline presentation model (Architecture V2 Wave 8, activity surface).
 *
 * The unified job lifecycle exists so a user and an operator can see what the
 * deployment is actually running. These helpers keep that reading honest: states
 * and kinds become translation keys, progress is reported as the backend recorded
 * it, and a cancellation is offered only when the payload says it is possible.
 */

import type { JobDTO } from "@/api/client";

export const TERMINAL_JOB_STATES: readonly JobDTO["status"][] = [
  "SUCCEEDED",
  "FAILED",
  "CANCELLED",
  "EXPIRED",
];

/** A job that is still working or waiting for the user. */
export function jobIsActive(job: Pick<JobDTO, "status">): boolean {
  return !TERMINAL_JOB_STATES.includes(job.status);
}

/** Cancellation is offered only when the backend says it would be accepted. */
export function jobCanCancel(job: Pick<JobDTO, "status" | "cancellable">): boolean {
  return jobIsActive(job) && job.cancellable === true;
}

export function jobKindLabelKey(kind: string): string {
  return `job.kind.${(kind ?? "").trim().toUpperCase() || "UNKNOWN"}`;
}

export function jobStatusLabelKey(status: string): string {
  return `job.status.${(status ?? "").trim().toUpperCase() || "UNKNOWN"}`;
}

/** Status badge variant for the shared primitive: the job-state vocabulary. */
export const JOB_STATUS_BADGE_VARIANT = "job-state" as const;

/** Progress as whole percent, clamped to the payload's 0..1 range. */
export function jobProgressPercent(job: Pick<JobDTO, "progress">): number {
  const value = Number.isFinite(job.progress) ? job.progress : 0;
  return Math.round(Math.min(1, Math.max(0, value)) * 100);
}

/** Duration in a compact human form, or null while the job is still running. */
export function jobDurationLabel(
  job: Pick<JobDTO, "duration_seconds">,
): string | null {
  const seconds = job.duration_seconds;
  if (seconds === null || seconds === undefined || !Number.isFinite(seconds)) return null;
  if (seconds < 60) return `${Math.round(seconds)}s`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ${Math.round(seconds % 60)}s`;
  return `${Math.floor(minutes / 60)}h ${minutes % 60}m`;
}

/**
 * Active jobs first, then newest first inside each group, so a running operation
 * is never below a finished one.
 */
export function jobTimelineOrder(jobs: readonly JobDTO[]): JobDTO[] {
  return [...jobs].sort((left, right) => {
    const leftActive = jobIsActive(left) ? 0 : 1;
    const rightActive = jobIsActive(right) ? 0 : 1;
    if (leftActive !== rightActive) return leftActive - rightActive;
    return (right.created_at_utc ?? "").localeCompare(left.created_at_utc ?? "");
  });
}

export interface JobTimelineSummary {
  readonly active: number;
  readonly failed: number;
  readonly succeeded: number;
  readonly cancelled: number;
}

/** Counts for the strip above the list, taken from the payload states. */
export function jobTimelineSummary(jobs: readonly JobDTO[]): JobTimelineSummary {
  let active = 0;
  let failed = 0;
  let succeeded = 0;
  let cancelled = 0;
  for (const job of jobs) {
    if (job.status === "FAILED") failed += 1;
    else if (job.status === "SUCCEEDED") succeeded += 1;
    else if (job.status === "CANCELLED" || job.status === "EXPIRED") cancelled += 1;
    else active += 1;
  }
  return { active, failed, succeeded, cancelled };
}

/**
 * Whether a failure offers a retry. The backend records retryability, so the
 * surface never promises a retry the job did not allow.
 */
export function jobRetryable(job: Pick<JobDTO, "status" | "retryable">): boolean {
  return job.status === "FAILED" && job.retryable === true;
}
