/**
 * QA-R-07: the day a risk row's marks were closed, in words. A late or stale row says so in text
 * ("stale · marks 18 Nov") beside its figures, and the row is greyed by `data-marks-state`, so the
 * state never rests on colour alone. The state is the server's (one business-day rule).
 */
import { useTranslation } from "react-i18next";

import { marksBehind, marksLine, type MarksFreshness } from "@/app/model/riskLimitsModel";

type Translate = (key: string, options?: Record<string, unknown>) => string;

export function MarksAsOf({ row, t, quietWhenCurrent = false }: { row: MarksFreshness; t: Translate; quietWhenCurrent?: boolean }) {
  const { i18n } = useTranslation();
  const line = marksLine(row, i18n.language);
  if (!line) return null;
  const behind = marksBehind(row.state);
  if (quietWhenCurrent && !behind && row.state !== "never") return null;
  return (
    <small
      className={behind || row.state === "never" ? "risk-marks is-behind" : "risk-marks muted"}
      data-marks-state={row.state ?? undefined}
      title={t("risk.marks.help")}
    >
      {t(line.key, { day: line.day ?? "" })}
    </small>
  );
}

/** Row attributes that grey a late or stale row (the text says why). */
export function marksRowAttributes(row: MarksFreshness): Record<string, string | undefined> {
  return { "data-marks-state": marksBehind(row.state) ? row.state ?? undefined : undefined };
}
