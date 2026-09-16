import type { CommercialDiagnosticItem } from "@/app/model/commercialWarnings";
import { warningLabel } from "@/app/warningLabel";

type Translate = (key: string) => string;

interface CommercialWarningListProps {
  items: readonly CommercialDiagnosticItem[];
  t: Translate;
  limit?: number;
  emptyLabel?: string;
}

function formatUtc(value: string | null): string | null {
  if (!value) return null;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return `${date.toISOString().slice(0, 19).replace("T", " ")} UTC`;
}

function label(item: CommercialDiagnosticItem, t: Translate): string {
  return item.code ? warningLabel(item.raw, t) : item.detail;
}

export function CommercialWarningList({
  items,
  t,
  limit = 12,
  emptyLabel,
}: CommercialWarningListProps) {
  if (items.length === 0) {
    return emptyLabel ? <p className="muted">{emptyLabel}</p> : null;
  }

  return (
    <ul className="commercial-diagnostic-list">
      {items.slice(0, limit).map((item, index) => {
        const observedAt = formatUtc(item.observedAtUtc);
        return (
          <li key={`${item.level}-${item.raw}-${item.affectedResourceId ?? ""}-${item.affectedRouteId ?? ""}-${index}`}>
            <div className="commercial-diagnostic-heading">
              <span className={`commercial-diagnostic-level level-${item.level}`}>
                {t(`commercial.warning.level.${item.level}`)}
              </span>
              <strong>{label(item, t)}</strong>
              {item.code && <code>{item.code}</code>}
            </div>
            <div className="commercial-diagnostic-evidence">
              <span>
                {t("commercial.warning.origin")}:{" "}
                {item.origins.map((origin) => t(`commercial.warning.origin.${origin}`)).join(" / ")}
              </span>
              {item.affectedResourceId && <span>{t("commercial.warning.resource")}: {item.affectedResourceId}</span>}
              {item.affectedRouteId && <span>{t("commercial.warning.route")}: {item.affectedRouteId}</span>}
              {item.sourceSystem && (
                <span>
                  {t("commercial.warning.source")}: {item.sourceSystem}
                  {item.simulated ? ` · ${t("market.simulated_source")}` : ""}
                </span>
              )}
              {item.freshness && <span>{t("commercial.warning.freshness")}: {item.freshness}</span>}
              {observedAt && <span>{t("commercial.warning.observed")}: {observedAt}</span>}
              {item.sourceReference && <span>{t("commercial.warning.source_ref")}: {item.sourceReference}</span>}
              {item.sourceRefs.length > 0 && (
                <span>{t("commercial.warning.lineage")}: {item.sourceRefs.join(" / ")}</span>
              )}
            </div>
          </li>
        );
      })}
      {items.length > limit && (
        <li className="commercial-diagnostic-more">
          {t("commercial.warning.more")}: {items.length - limit}
        </li>
      )}
    </ul>
  );
}
