/**
 * Background jobs in the notification centre: the pure rules.
 *
 * Long work (a dataset build takes 35-45 s on the demo desk) runs on the server as a job, so the
 * user can start it and go elsewhere. The notification centre then shows it: running with its
 * step, finished with a link to the result, or failed with a plain reason and a retry. These
 * helpers decide what is shown and when the client asks again; the store and the component only
 * apply them.
 *
 * - Polling runs only while a job is active, quickly at first (a short job finishes inside the
 *   first seconds) and then at a calmer pace; with nothing active the client does not ask.
 * - The centre lists the user's background jobs and the jobs this browser started. Work that was
 *   tracked inside a request (it answered while the user waited) is history for the Activity
 *   page, not a notification.
 * - A finished job stays until the user dismisses it or a day has passed.
 */

import type { JobDTO } from "../../api/client.ts";
import { jobIsActive, jobProgressPercent } from "../model/jobTimelineModel.ts";

/** Poll interval while a job started less than {@link JOB_POLL_FAST_WINDOW_MS} ago is active. */
export const JOB_POLL_FAST_MS = 2_500;
/** Poll interval for longer-running jobs. */
export const JOB_POLL_SLOW_MS = 8_000;
/** How long after a job's start the fast interval applies. */
export const JOB_POLL_FAST_WINDOW_MS = 45_000;
/** A finished job is listed for this long unless dismissed. */
export const JOB_NOTICE_TTL_MS = 24 * 3_600_000;
/** At most this many jobs are listed. */
export const JOB_NOTICE_LIMIT = 8;
/** The provenance label the server puts on every background job. */
export const BACKGROUND_PROVENANCE = "background-job";

type Translate = (key: string, options?: Record<string, unknown>) => string;

/** What re-runs a job: an action this client knows, with the request it sent. */
export interface JobRetry {
  readonly action: "dataset-build";
  readonly body: Record<string, unknown>;
}

/** A job this browser started: where it was started from and how to run it again. */
export interface StartedJob {
  readonly job_id: string;
  /** The page that started it (path and query), opened by "Open result". */
  readonly return_to: string;
  /** A short name for the work the user recognises, e.g. the dataset spec's name. */
  readonly title?: string;
  readonly retry?: JobRetry | null;
  readonly started_at_ms: number;
}

function timeOf(value: string | null | undefined): number {
  const parsed = value ? Date.parse(value) : Number.NaN;
  return Number.isFinite(parsed) ? parsed : 0;
}

/** Whether a job ran (or runs) in the background, by the server's mark. */
export function isBackgroundJob(job: Pick<JobDTO, "provenance">): boolean {
  return (job.provenance ?? []).includes(BACKGROUND_PROVENANCE);
}

/**
 * How long to wait before asking again, or null when nothing is active and the client should
 * not poll at all.
 */
export function jobPollDelay(jobs: readonly JobDTO[], nowMs: number): number | null {
  const active = jobs.filter((job) => jobIsActive(job));
  if (active.length === 0) return null;
  const young = active.some(
    (job) => nowMs - timeOf(job.started_at_utc ?? job.created_at_utc) < JOB_POLL_FAST_WINDOW_MS,
  );
  return young ? JOB_POLL_FAST_MS : JOB_POLL_SLOW_MS;
}

/**
 * The jobs the notification centre lists, active first and then newest first: background jobs
 * and jobs this browser started, minus dismissed ones and finished ones older than a day.
 */
export function visibleJobNotices(
  jobs: readonly JobDTO[],
  started: Readonly<Record<string, StartedJob>>,
  dismissed: ReadonlySet<string>,
  nowMs: number,
): JobDTO[] {
  return jobs
    .filter((job) => isBackgroundJob(job) || job.job_id in started)
    .filter((job) => !dismissed.has(job.job_id))
    .filter(
      (job) =>
        jobIsActive(job) ||
        nowMs - timeOf(job.finished_at_utc ?? job.created_at_utc) < JOB_NOTICE_TTL_MS,
    )
    .sort((left, right) => {
      const activeOrder = Number(!jobIsActive(left)) - Number(!jobIsActive(right));
      if (activeOrder !== 0) return activeOrder;
      return timeOf(right.created_at_utc) - timeOf(left.created_at_utc);
    })
    .slice(0, JOB_NOTICE_LIMIT);
}

export interface JobActivity {
  /** Jobs still queued or running. */
  readonly running: number;
  /** Progress of the running jobs together, in whole percent, or null with none running. */
  readonly percent: number | null;
  /** Finished jobs the user has not seen yet. */
  readonly unseenFinished: number;
  /** Of those, how many failed (the indicator shows a failure differently). */
  readonly unseenFailed: number;
}

/** The small summary beside the alerts trigger. */
export function jobActivity(
  notices: readonly JobDTO[],
  seen: ReadonlySet<string>,
): JobActivity {
  const running = notices.filter((job) => jobIsActive(job));
  const finished = notices.filter((job) => !jobIsActive(job) && !seen.has(job.job_id));
  const percent =
    running.length === 0
      ? null
      : Math.round(
          running.reduce((sum, job) => sum + jobProgressPercent(job), 0) / running.length,
        );
  return {
    running: running.length,
    percent,
    unseenFinished: finished.length,
    unseenFailed: finished.filter((job) => job.status === "FAILED" || job.status === "EXPIRED")
      .length,
  };
}

/** Jobs that were active in `previous` and are finished in `next`: the moments to announce. */
export function newlyFinishedJobs(
  previous: readonly JobDTO[],
  next: readonly JobDTO[],
): JobDTO[] {
  const wasActive = new Set(previous.filter((job) => jobIsActive(job)).map((job) => job.job_id));
  return next.filter((job) => wasActive.has(job.job_id) && !jobIsActive(job));
}

/** The translation key of a step code; unknown codes fall back to a generic "working". */
export function jobStepLabelKey(label: string | null | undefined): string {
  const code = (label ?? "").trim();
  return code ? `jobs.step.${code}` : "jobs.step.working";
}

/** "Step 3 of 6 · Reading prices", or the percent when the job reports no steps. */
export function jobStepText(job: JobDTO, t: Translate): string {
  if (job.status === "QUEUED") return t("jobs.queued");
  const total = job.step_total ?? 0;
  const step = job.step ?? 0;
  if (total > 0 && step > 0) {
    const key = jobStepLabelKey(job.step_label);
    const translated = t(key);
    return t("jobs.step_of", {
      step,
      total,
      label: translated === key ? t("jobs.step.working") : translated,
    });
  }
  return t("jobs.percent", { percent: jobProgressPercent(job) });
}

/**
 * The failure a user reads: the catalogued text for the job's code when this client has it,
 * otherwise the reason the server recorded, otherwise the generic job failure.
 */
export function jobFailureText(
  job: Pick<JobDTO, "error_code" | "error_message">,
  t: Translate,
): { readonly message: string; readonly action: string | null } {
  const code = (job.error_code ?? "").trim();
  if (code) {
    const messageKey = `errors.${code}.message`;
    const actionKey = `errors.${code}.action`;
    const message = t(messageKey);
    if (message !== messageKey) {
      const action = t(actionKey);
      return { message, action: action === actionKey ? null : action };
    }
  }
  const reason = (job.error_message ?? "").trim();
  if (reason) return { message: reason, action: null };
  return { message: t("errors.JOB_FAILED.message"), action: t("errors.JOB_FAILED.action") };
}

/** The stored result a job produced, from its output references. */
export function jobResultRef(
  job: Pick<JobDTO, "output_refs">,
): { readonly kind: string; readonly id: string } | null {
  for (const ref of job.output_refs ?? []) {
    const separator = ref.indexOf(":");
    if (separator <= 0) continue;
    const kind = ref.slice(0, separator);
    const id = ref.slice(separator + 1);
    if (!id || id === "true" || kind.endsWith("_reused")) continue;
    return { kind, id };
  }
  return null;
}

/**
 * Where "Open result" goes: the page that started the job, with the job named so the page can
 * show it. Only a same-origin path is accepted, so a stored entry can never send the user away.
 */
export function jobResultHref(job: Pick<JobDTO, "job_id">, started: StartedJob | undefined): string | null {
  const returnTo = started?.return_to ?? "";
  if (!returnTo.startsWith("/") || returnTo.startsWith("//")) return null;
  const [path, query = ""] = returnTo.split("?", 2);
  const params = new URLSearchParams(query);
  params.set("job", job.job_id);
  return `${path}?${params.toString()}`;
}

/** Whether a finished job offers "Retry": it failed, the server allows it, and we know how. */
export function jobCanRetry(job: Pick<JobDTO, "status" | "retryable">, started: StartedJob | undefined): boolean {
  if (!started?.retry) return false;
  if (job.status === "CANCELLED" || job.status === "EXPIRED") return true;
  return job.status === "FAILED" && job.retryable !== false;
}

/** Keep the started-jobs registry small: drop entries older than the notice window. */
export function pruneStartedJobs(
  started: Readonly<Record<string, StartedJob>>,
  nowMs: number,
): Record<string, StartedJob> {
  return Object.fromEntries(
    Object.entries(started).filter(([, entry]) => nowMs - entry.started_at_ms < JOB_NOTICE_TTL_MS),
  );
}
