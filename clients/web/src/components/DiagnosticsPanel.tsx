/**
 * Diagnostics panel (Architecture V2 Wave 10, consumer surface).
 *
 * Wave 10 declared the diagnostics bundle - an allowlist, declared forbidden names and a
 * composer that refuses to leak - but no surface ever produced one, so an operator with a
 * problem had nothing to hand to support. This panel is the consumer: it composes the bundle
 * from facts the client already holds, shows exactly what would leave the machine before it
 * leaves, and hands it over.
 *
 * It is an operator surface, so it sits with the runtime readiness evidence rather than in a
 * work workspace. It composes through `composeDiagnosticsBundle` instead of assembling an
 * object here, and it reports a field the deployment did not give as not reported rather than
 * as a zero - a bundle that quietly reads as "nothing was wrong" would be worse than no bundle.
 */

import { useState } from "react";

import { api, type JobDTO } from "@/api/client";
import i18n from "@/i18n";
import { degradedSlices } from "@/app/model/marketContextModel";
import { degradedPortfolioSlices } from "@/app/model/portfolioSnapshotModel";
import { degradedReviewSlices } from "@/app/model/reviewContextModel";
import {
  composeDiagnosticsBundle,
  diagnosticsBundleFileName,
  diagnosticsHandover,
  type DiagnosticsComposition,
} from "@/app/host/diagnosticsBundle";
import { hostCapabilities, resolveHostKind } from "@/app/host/hostCapabilities";
import { MetricStrip, PanelHeader } from "@/components/ui";
import { useApiStore } from "@/stores/api";

type Translate = (key: string) => string;

interface DiagnosticsPanelProps {
  t: Translate;
}

const JOB_SAMPLE_LIMIT = 25;

function jobStatesFrom(jobs: readonly JobDTO[]): Record<string, number> {
  const counts: Record<string, number> = {};
  for (const job of jobs) counts[job.status] = (counts[job.status] ?? 0) + 1;
  return counts;
}

function preview(value: unknown): string {
  return typeof value === "string" ? value : JSON.stringify(value);
}

export function DiagnosticsPanel({ t }: DiagnosticsPanelProps) {
  const runtimeRelease = useApiStore((state) => state.runtimeRelease);
  const releaseCompatibility = useApiStore((state) => state.releaseCompatibility);
  const dataStatus = useApiStore((state) => state.dataStatus);
  const endpointErrorCodes = useApiStore((state) => state.endpointErrorCodes);
  const marketContext = useApiStore((state) => state.marketContext);
  const portfolioSnapshot = useApiStore((state) => state.portfolioSnapshot);
  const reviewContext = useApiStore((state) => state.reviewContext);

  const [composition, setComposition] = useState<DiagnosticsComposition | null>(null);
  const [busy, setBusy] = useState(false);
  const [messageKey, setMessageKey] = useState<string | null>(null);

  const hostKind = resolveHostKind();
  const handover = diagnosticsHandover(hostKind);

  async function prepare() {
    setBusy(true);
    setMessageKey(null);
    // The job sample is the one fact the panel does not already hold. A failed read is not
    // evidence that nothing ran, so it is reported as unavailable rather than as zero.
    let jobStates: Record<string, number> | null = null;
    try {
      const response = await api.jobs({ limit: String(JOB_SAMPLE_LIMIT) });
      jobStates = jobStatesFrom(response.data);
    } catch {
      jobStates = null;
    }
    // Before the workspace reads completed, an empty failure map is the absence of evidence
    // rather than evidence of health, so the slices are reported as unavailable instead.
    const slicesLoaded = dataStatus !== "unavailable";
    setComposition(
      composeDiagnosticsBundle({
        hostKind,
        capabilities: hostCapabilities(hostKind),
        language: i18n.language,
        serverVersion: runtimeRelease?.application_version ?? null,
        schemaRevision: runtimeRelease?.database_schema_revision ?? null,
        releaseCompatibility: releaseCompatibility?.state ?? null,
        dataStatus,
        endpointFailureCodes: slicesLoaded ? { ...endpointErrorCodes } : null,
        degradedSlices: slicesLoaded
          ? [
              ...degradedSlices(marketContext).map((reading) => `market:${reading.key}:${reading.freshnessState}`),
              ...degradedPortfolioSlices(portfolioSnapshot).map(
                (reading) => `portfolio:${reading.key}:${reading.freshnessState}`,
              ),
              ...degradedReviewSlices(reviewContext).map(
                (reading) => `review:${reading.key}:${reading.freshnessState}`,
              ),
            ]
          : null,
        jobStates,
        generatedAtUtc: new Date().toISOString(),
      }),
    );
    setBusy(false);
  }

  async function copyBundle() {
    if (!composition) return;
    try {
      await navigator.clipboard.writeText(JSON.stringify(composition.bundle, null, 2));
      setMessageKey("diagnostics.message.copied");
    } catch {
      setMessageKey("diagnostics.message.copy_failed");
    }
  }

  function downloadBundle() {
    if (!composition) return;
    const blob = new Blob([JSON.stringify(composition.bundle, null, 2)], {
      type: "application/json",
    });
    const href = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = href;
    anchor.download = diagnosticsBundleFileName(String(composition.bundle.generatedAtUtc ?? ""));
    anchor.click();
    URL.revokeObjectURL(href);
    setMessageKey("diagnostics.message.downloaded");
  }

  const fields = composition ? Object.entries(composition.bundle) : [];

  return (
    <section className="diagnostics-panel" aria-label={t("diagnostics.title")}>
      <PanelHeader title={t("diagnostics.title")} meta={t("diagnostics.subtitle")} />

      {composition && (
        <MetricStrip
          className="metric-grid three-column"
          items={[
            { label: t("diagnostics.reported"), value: String(fields.length) },
            {
              label: t("diagnostics.unavailable"),
              value: String(composition.unavailableFields.length),
            },
            { label: t("diagnostics.host"), value: hostKind },
          ]}
        />
      )}

      <div className="diagnostics-actions">
        <button type="button" disabled={busy} onClick={() => void prepare()}>
          {busy ? t("diagnostics.action.preparing") : t("diagnostics.action.prepare")}
        </button>
        {composition && (
          <>
            <button type="button" onClick={() => void copyBundle()}>
              {t("diagnostics.action.copy")}
            </button>
            <button type="button" onClick={downloadBundle}>
              {t("diagnostics.action.download")}
            </button>
          </>
        )}
      </div>

      <p className="diagnostics-guarantee">{t("diagnostics.guarantee")}</p>
      {handover.noteKeys.map((key) => (
        <p key={key} className="diagnostics-note">{t(key)}</p>
      ))}
      {messageKey && (
        <p className="diagnostics-message" role="status" aria-live="polite">
          {t(messageKey)}
        </p>
      )}

      {composition && (
        <>
          <dl className="diagnostics-fields">
            {fields.map(([field, value]) => (
              <div key={field}>
                <dt><code>{field}</code></dt>
                <dd>{preview(value)}</dd>
              </div>
            ))}
          </dl>
          {composition.unavailableFields.length > 0 && (
            <div className="diagnostics-unavailable">
              <strong>{t("diagnostics.unavailable")}</strong>
              <p>{t("diagnostics.unavailable_hint")}</p>
              <ul>
                {composition.unavailableFields.map((field) => (
                  <li key={field}><code>{field}</code></li>
                ))}
              </ul>
            </div>
          )}
        </>
      )}
    </section>
  );
}
