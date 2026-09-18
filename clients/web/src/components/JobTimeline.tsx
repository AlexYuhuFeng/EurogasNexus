/**
 * Job timeline (Architecture V2 Wave 8, activity region).
 *
 * The unified job model only helps a user if the product shows it. This panel is
 * the activity surface: what the deployment is running, what it produced, what
 * failed and with which stable code - and a cancellation control only where the
 * backend says cancellation would be accepted.
 *
 * It is operator-facing, so it lives on the Administration surface. Failure codes
 * are rendered through the product error taxonomy rather than as raw strings.
 */

import { useCallback, useEffect, useState } from "react";

import { api } from "@/api/client";
import type { JobDTO } from "@/api/client";
import { inspectorSubjectFor } from "@/app/model/inspectorDetail";
import { describeApiError } from "@/app/experience/errorPresentation";
import { useApiStore } from "@/stores/api";
import { useInspectorStore } from "@/stores/inspector";
import {
  JOB_STATUS_BADGE_VARIANT,
  jobCanCancel,
  jobDurationLabel,
  jobIsActive,
  jobKindLabelKey,
  jobProgressPercent,
  jobStatusLabelKey,
  jobTimelineOrder,
  jobTimelineSummary,
} from "@/app/model/jobTimelineModel";
import { MetricStrip, PanelHeader, StatusBadge } from "@/components/ui";

type Translate = (key: string) => string;

interface JobTimelineProps {
  t: Translate;
}

const TIMELINE_LIMIT = 25;

export function JobTimeline({ t }: JobTimelineProps) {
  const [jobs, setJobs] = useState<JobDTO[]>([]);
  const [busy, setBusy] = useState(false);
  const [errorText, setErrorText] = useState<string | null>(null);
  const publishJobsRead = useApiStore((state) => state.publishJobsRead);
  const inspector = useInspectorStore();

  const refresh = useCallback(async () => {
    setBusy(true);
    setErrorText(null);
    try {
      const response = await api.jobs({ limit: String(TIMELINE_LIMIT) });
      setJobs(response.data);
      // The Inspector resolves detail from state the identity already received; this is the row
      // set it can resolve a `job` subject against, without a fetch of its own.
      publishJobsRead(response.data);
    } catch (error) {
      setErrorText(explain(error, t));
    } finally {
      setBusy(false);
    }
  }, [t]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  async function cancel(jobId: string) {
    setBusy(true);
    setErrorText(null);
    try {
      await api.cancelJob(jobId);
      await refresh();
    } catch (error) {
      setErrorText(explain(error, t));
      setBusy(false);
    }
  }

  const ordered = jobTimelineOrder(jobs);
  const summary = jobTimelineSummary(jobs);

  return (
    <section className="job-timeline" aria-label={t("job.title")}>
      <PanelHeader title={t("job.title")} meta={t("job.subtitle")} />

      <MetricStrip
        items={[
          { label: t("job.summary.active"), value: String(summary.active) },
          { label: t("job.summary.failed"), value: String(summary.failed) },
          { label: t("job.summary.succeeded"), value: String(summary.succeeded) },
          { label: t("job.summary.cancelled"), value: String(summary.cancelled) },
        ]}
      />

      <div className="job-timeline-actions">
        <button type="button" disabled={busy} onClick={() => void refresh()}>
          {busy ? t("job.refreshing") : t("job.refresh")}
        </button>
      </div>

      <ul className="job-timeline-list">
        {ordered.map((job) => (
          <li key={job.job_id} className={jobIsActive(job) ? "active" : undefined}>
            <div className="job-timeline-row">
              <span className="job-timeline-kind">{t(jobKindLabelKey(job.kind))}</span>
              <StatusBadge variant={JOB_STATUS_BADGE_VARIANT} status={job.status}>
                {t(jobStatusLabelKey(job.status))}
              </StatusBadge>
              <span className="job-timeline-principal">{job.principal}</span>
              <span className="job-timeline-progress">
                {jobProgressPercent(job)}%
              </span>
              <time>{job.created_at_utc}</time>
              {jobDurationLabel(job) && <span>{jobDurationLabel(job)}</span>}
              {jobCanCancel(job) && (
                <button type="button" disabled={busy} onClick={() => void cancel(job.job_id)}>
                  {t("job.cancel")}
                </button>
              )}
              {/* Wave 9: the run's own record belongs to the canonical Inspector, so this
                  timeline hands the subject over instead of growing a detail pane. The row it
                  shows is what the Inspector resolves against - no fetch. */}
              <button
                type="button"
                className="text-action"
                onClick={() => {
                  const subject = inspectorSubjectFor(
                    "job",
                    job.job_id,
                    t(jobKindLabelKey(job.kind)),
                    "runtime",
                  );
                  if (subject) inspector.open(subject);
                }}
              >
                {t("job.inspect")}
              </button>
            </div>
            <div className="job-timeline-detail">
              {job.output_refs.length > 0 && (
                <span>
                  {t("job.outputs")}: {job.output_refs.join(", ")}
                </span>
              )}
              {job.error_code && (
                <span className="job-timeline-error">
                  {t(describeApiError({ error: job.error_code }).titleKey)}
                </span>
              )}
              {job.correlation_id && (
                <span>
                  {t("job.correlation")}: <code>{job.correlation_id}</code>
                </span>
              )}
            </div>
          </li>
        ))}
        {ordered.length === 0 && <li className="job-timeline-empty">{t("job.empty")}</li>}
      </ul>

      {errorText && (
        <p className="job-timeline-error" role="alert">
          {errorText}
        </p>
      )}
    </section>
  );
}

function explain(error: unknown, t: Translate): string {
  const detail =
    error && typeof error === "object" && "detail" in error
      ? (error as { detail?: unknown }).detail
      : undefined;
  const body =
    detail && typeof detail === "object" ? (detail as Record<string, unknown>) : undefined;
  const presentation = describeApiError(body ?? { error: "service_unavailable" });
  return `${t(presentation.titleKey)}. ${t(presentation.actionKey)}`;
}
