import { useState } from "react";

import { downloadReport, type ReportFormat } from "@/api/client";
import { Popover } from "@/components/ui/Popover";

type Translate = (key: string, options?: Record<string, unknown>) => string;

const FORMATS: ReportFormat[] = ["xlsx", "pdf", "csv"];

/**
 * One "Export ▾" per table (owner: one menu, not three buttons): Excel, PDF and CSV in the same
 * order everywhere, from the same read as the figures on screen. A small menu on the shared
 * Popover, so it closes on navigation and returns focus to its button.
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
  const run = (format: ReportFormat, close: () => void) => {
    setBusy(format);
    setFailed(false);
    close();
    downloadReport(path, params, format)
      .catch(() => setFailed(true))
      .finally(() => setBusy(null));
  };
  return (
    <span className="report-export-group" data-report-export={path}>
      <Popover
        label={t("report.export")}
        width="sm"
        placement="bottom-end"
        className="report-export-menu"
        trigger={(props) => (
          <button {...props} type="button" className="report-export" aria-busy={busy !== null} disabled={busy !== null}>
            {t("report.export")} <span aria-hidden="true">▾</span>
          </button>
        )}
      >
        {(close) => (
          <ul className="report-export-list" role="list">
            {FORMATS.map((format) => (
              <li key={format}>
                <button type="button" className="report-export-option" onClick={() => run(format, close)}>
                  {t(`report.format_${format}`)}
                </button>
              </li>
            ))}
          </ul>
        )}
      </Popover>
      {failed ? <span className="report-export-error" role="status">{t("report.export_failed")}</span> : null}
    </span>
  );
}
