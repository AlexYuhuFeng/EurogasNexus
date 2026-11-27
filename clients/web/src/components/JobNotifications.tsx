/**
 * Background work in the notification centre.
 *
 * Two pieces, both following `stores/backgroundJobs.ts`:
 *
 * - `JobNotifications` is the section inside the alerts drawer: each background job with its
 *   step while it runs (and Cancel), "Open result" when it is done, the reason and "Retry" when
 *   it failed, and Dismiss / Clear finished so a finished job does not stay for ever;
 * - `JobActivityIndicator` is the small mark beside the alerts trigger: how many jobs run and
 *   how far they are, or a dot when one finished since the user last looked. It also carries the
 *   polite live region that says a job finished, wherever the user is.
 *
 * The `*View` components are pure (props in, markup out) so they render in tests; the connected
 * ones bind the signed-in user and the store.
 */

import { useEffect, useMemo, useState } from "react";

import type { JobDTO } from "@/api/client";
import {
  jobActivity,
  jobCanRetry,
  jobFailureText,
  jobResultHref,
  jobResultRef,
  jobStepText,
  visibleJobNotices,
  type JobActivity,
  type StartedJob,
} from "@/app/jobs/backgroundJobsModel";
import {
  jobCanCancel,
  jobDurationLabel,
  jobIsActive,
  jobKindLabelKey,
  jobProgressPercent,
  jobStatusLabelKey,
} from "@/app/model/jobTimelineModel";
import { useNow } from "@/app/data/connection";
import { useApiStore } from "@/stores/api";
import { useBackgroundJobsStore } from "@/stores/backgroundJobs";
import { Button } from "./ui/Button";
import "./job-notifications.css";

type Translate = (key: string, options?: Record<string, unknown>) => string;

/* ------------------------------------------------------------------ pure views */

export interface JobNotificationsViewProps {
  readonly notices: readonly JobDTO[];
  readonly started: Readonly<Record<string, StartedJob>>;
  readonly busyJobId: string | null;
  readonly t: Translate;
  readonly onOpenResult: (href: string) => void;
  readonly onRetry: (jobId: string) => void;
  readonly onCancel: (jobId: string) => void;
  readonly onDismiss: (jobId: string) => void;
  readonly onClearFinished: () => void;
}

function jobName(job: JobDTO, started: StartedJob | undefined, t: Translate): string {
  return started?.title?.trim() || t(jobKindLabelKey(job.kind));
}

function statusTone(job: JobDTO): "running" | "done" | "failed" | "stopped" {
  if (jobIsActive(job)) return "running";
  if (job.status === "SUCCEEDED") return "done";
  if (job.status === "FAILED") return "failed";
  return "stopped";
}

export function JobNotificationsView({
  notices,
  started,
  busyJobId,
  t,
  onOpenResult,
  onRetry,
  onCancel,
  onDismiss,
  onClearFinished,
}: JobNotificationsViewProps) {
  if (notices.length === 0) return null;
  const anyFinished = notices.some((job) => !jobIsActive(job));
  return (
    <section className="job-notices" aria-label={t("jobs.title")}>
      <header className="job-notices-header">
        <span>{t("jobs.title")}</span>
        {anyFinished && (
          <Button variant="quiet" onClick={onClearFinished}>
            {t("jobs.clear_finished")}
          </Button>
        )}
      </header>
      <ul className="job-notices-list">
        {notices.map((job) => {
          const entry = started[job.job_id];
          const name = jobName(job, entry, t);
          const tone = statusTone(job);
          const busy = busyJobId === job.job_id;
          const failure = tone === "failed" ? jobFailureText(job, t) : null;
          const href = tone === "done" ? jobResultHref(job, entry) : null;
          const result = tone === "done" ? jobResultRef(job) : null;
          const duration = jobDurationLabel(job);
          return (
            <li key={job.job_id} className={`job-notice is-${tone}`} data-job-status={job.status}>
              <div className="job-notice-heading">
                <strong>{name}</strong>
                <span className="job-notice-status">{t(jobStatusLabelKey(job.status))}</span>
              </div>
              {tone === "running" && (
                <>
                  <div
                    className="job-notice-bar"
                    role="progressbar"
                    aria-label={t("jobs.progress_label", { name })}
                    aria-valuemin={0}
                    aria-valuemax={100}
                    aria-valuenow={jobProgressPercent(job)}
                  >
                    <span style={{ width: `${Math.max(4, jobProgressPercent(job))}%` }} />
                  </div>
                  <p className="job-notice-detail">{jobStepText(job, t)}</p>
                  <p className="job-notice-hint">{t("jobs.leave_hint")}</p>
                </>
              )}
              {tone === "done" && (
                <p className="job-notice-detail">
                  {duration ? t("jobs.done_in", { duration }) : t("jobs.done")}
                  {result && !href && <> · {t("jobs.saved_as", { id: result.id })}</>}
                </p>
              )}
              {failure && (
                <p className="job-notice-detail" role="note">
                  {failure.message}
                  {failure.action && <> {failure.action}</>}
                </p>
              )}
              {tone === "stopped" && <p className="job-notice-detail">{t("jobs.stopped")}</p>}
              <div className="job-notice-actions">
                {href && (
                  <a
                    className="job-notice-open"
                    href={href}
                    onClick={(event) => {
                      event.preventDefault();
                      onOpenResult(href);
                    }}
                  >
                    {t("jobs.open_result")}
                  </a>
                )}
                {tone !== "running" && jobCanRetry(job, entry) && (
                  <Button variant="secondary" loading={busy} onClick={() => onRetry(job.job_id)}>
                    {t("jobs.retry")}
                  </Button>
                )}
                {tone === "running" && jobCanCancel(job) && (
                  <Button variant="quiet" loading={busy} onClick={() => onCancel(job.job_id)}>
                    {t("jobs.cancel")}
                  </Button>
                )}
                {tone !== "running" && (
                  <Button
                    variant="quiet"
                    aria-label={t("jobs.dismiss_label", { name })}
                    onClick={() => onDismiss(job.job_id)}
                  >
                    {t("jobs.dismiss")}
                  </Button>
                )}
              </div>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

export interface JobActivityIndicatorViewProps {
  readonly activity: JobActivity;
  /** The latest announcement ("Dataset build finished."), read once by assistive technology. */
  readonly announcement: string;
  readonly t: Translate;
}

export function JobActivityIndicatorView({ activity, announcement, t }: JobActivityIndicatorViewProps) {
  const label =
    activity.running > 0
      ? t("jobs.indicator.running_label", { count: activity.running, percent: activity.percent ?? 0 })
      : activity.unseenFinished > 0
        ? t("jobs.indicator.finished_label", { count: activity.unseenFinished })
        : "";
  return (
    <>
      {label && (
        <span
          className={[
            "job-activity",
            activity.running > 0 ? "is-running" : "is-finished",
            activity.unseenFailed > 0 ? "has-failed" : "",
          ]
            .filter(Boolean)
            .join(" ")}
          title={label}
          aria-hidden="true"
        >
          {activity.running > 0 ? (
            <>
              <span className="job-activity-ring" />
              <span className="job-activity-text">
                {t("jobs.indicator.running", { count: activity.running, percent: activity.percent ?? 0 })}
              </span>
            </>
          ) : (
            <span className="job-activity-dot" />
          )}
        </span>
      )}
      <span className="visually-hidden" role="status" aria-live="polite">
        {announcement}
      </span>
    </>
  );
}

/* ------------------------------------------------------------------ connected */

function useFollowSignedInUser(): void {
  const principalId = useApiStore((state) => state.currentUser?.principal_id ?? null);
  const bindIdentity = useBackgroundJobsStore((state) => state.bindIdentity);
  useEffect(() => {
    bindIdentity(principalId);
  }, [bindIdentity, principalId]);
}

function navigateTo(href: string): void {
  // The app routes on the URL: push it and let the shell's popstate listeners follow.
  window.history.pushState({}, "", href);
  window.dispatchEvent(new PopStateEvent("popstate"));
}

/** The drawer section. Mount it inside the alerts drawer; it renders nothing with no jobs. */
export function JobNotifications({ t, onNavigate }: { t: Translate; onNavigate?: () => void }) {
  useFollowSignedInUser();
  const jobs = useBackgroundJobsStore((state) => state.jobs);
  const started = useBackgroundJobsStore((state) => state.started);
  const dismissed = useBackgroundJobsStore((state) => state.dismissed);
  const store = useBackgroundJobsStore.getState;
  const [busyJobId, setBusyJobId] = useState<string | null>(null);
  // Finished notices expire while the drawer stays open: the shared clock, not a snapshot.
  const nowMs = useNow();

  // Opening the drawer reads the jobs once (the store polls only while one runs) and marks
  // what finished as seen, which clears the dot beside the trigger.
  useEffect(() => {
    void store().refresh();
  }, [store]);
  useEffect(() => {
    store().markSeen();
  }, [jobs, store]);

  const notices = useMemo(
    () => visibleJobNotices(jobs, started, new Set(dismissed), nowMs),
    [jobs, started, dismissed, nowMs],
  );

  async function act(jobId: string, action: () => Promise<unknown>) {
    setBusyJobId(jobId);
    try {
      await action();
    } catch {
      // The job's own row says what happened; a failed request leaves it as it was.
      void store().refresh();
    } finally {
      setBusyJobId(null);
    }
  }

  return (
    <JobNotificationsView
      notices={notices}
      started={started}
      busyJobId={busyJobId}
      t={t}
      onOpenResult={(href) => {
        navigateTo(href);
        onNavigate?.();
      }}
      onRetry={(jobId) => void act(jobId, () => store().retry(jobId))}
      onCancel={(jobId) => void act(jobId, () => store().cancel(jobId))}
      onDismiss={(jobId) => store().dismiss(jobId)}
      onClearFinished={() => store().clearFinished()}
    />
  );
}

/** The mark beside (or inside) the alerts trigger; always mounted, so it starts the follow-up. */
export function JobActivityIndicator({ t }: { t: Translate }) {
  useFollowSignedInUser();
  const jobs = useBackgroundJobsStore((state) => state.jobs);
  const started = useBackgroundJobsStore((state) => state.started);
  const dismissed = useBackgroundJobsStore((state) => state.dismissed);
  const seen = useBackgroundJobsStore((state) => state.seen);
  const justFinished = useBackgroundJobsStore((state) => state.justFinished);
  const activity = useMemo(
    () => jobActivity(visibleJobNotices(jobs, started, new Set(dismissed), Date.now()), new Set(seen)),
    [jobs, started, dismissed, seen],
  );
  const announcement = justFinished
    .map((job) =>
      t(job.status === "SUCCEEDED" ? "jobs.announce.succeeded" : "jobs.announce.stopped", {
        name: started[job.job_id]?.title?.trim() || t(jobKindLabelKey(job.kind)),
      }),
    )
    .join(" ");
  return <JobActivityIndicatorView activity={activity} announcement={announcement} t={t} />;
}
