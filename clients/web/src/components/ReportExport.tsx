import { useState } from "react";

import { downloadReport, type ReportFormat } from "@/api/client";

type Translate = (key: string, options?: Record<string, unknown>) => string;

const FORMATS: ReportFormat[] = ["xlsx", "pdf", "csv"];

/**
 * "Export · Excel · PDF · CSV": one control for every report read, so each panel offers the
 * same formats in the same order. The figures are the ones on screen, from the same read.
 */
export function ReportExport({
  path,
  params = {},
  t,
}: {
  path: string;
  params?: Record<string, string>;
  t: Translate;
}) {
  const [busy, setBusy] = useState<ReportFormat | null>(null);
  const [failed, setFailed] = useState(false);
  const run = (format: ReportFormat) => {
    setBusy(format);
    setFailed(false);
    downloadReport(path, params, format)
      .catch(() => setFailed(true))
      .finally(() => setBusy(null));
  };
  return (
    <div className="report-export-group" role="group" aria-label={t("report.export")}>
      <span className="report-export-label">{t("report.export")}</span>
      {FORMATS.map((format) => (
        <button
          key={format}
          type="button"
          className="report-export"
          disabled={busy !== null}
          aria-busy={busy === format}
          onClick={() => run(format)}
        >
          {t(`report.format_${format}`)}
        </button>
      ))}
      {failed ? <span className="report-export-error" role="status">{t("report.export_failed")}</span> : null}
    </div>
  );
}
