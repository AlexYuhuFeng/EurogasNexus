import { useMemo } from "react";
import type { IntradayOpportunityDTO } from "@/api/client";

type Translate = (key: string) => string;

interface IntradayDecisionFeedProps {
  opportunities: IntradayOpportunityDTO[];
  lastUpdatedAtUtc: string | null;
  t: Translate;
  compact?: boolean;
}

function formatValue(value: number | null | undefined, digits = 2): string {
  return value == null || !Number.isFinite(value) ? "n/a" : value.toFixed(digits);
}

function statusKey(status: string): string {
  if (status === "ACTIONABLE_REVIEW") return "intraday.actionable_review";
  if (status === "BLOCKED") return "intraday.blocked";
  if (status === "EXPIRED") return "intraday.expired";
  return "intraday.watch";
}

export function IntradayDecisionFeed({
  opportunities,
  lastUpdatedAtUtc,
  t,
  compact = false,
}: IntradayDecisionFeedProps) {
  const latest = useMemo(() => {
    const rows = [...opportunities].sort((left, right) =>
      right.detected_at_utc.localeCompare(left.detected_at_utc));
    const seen = new Set<string>();
    return rows.filter((row) => {
      const key = `${row.route_id}:${row.product}:${row.buy_venue}:${row.sell_venue}`;
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    }).slice(0, compact ? 3 : 8);
  }, [compact, opportunities]);

  const actionableCount = latest.filter((row) => row.status === "ACTIONABLE_REVIEW").length;

  return (
    <section
      className={`intraday-decision-feed ${compact ? "compact" : ""}`}
      aria-live="polite"
      aria-label={t("intraday.title")}
    >
      <div className="panel-title-row intraday-feed-heading">
        <div>
          <span className="eyebrow">{t("intraday.eyebrow")}</span>
          <h3>{t("intraday.title")}</h3>
        </div>
        <span className={`intraday-feed-counter ${actionableCount > 0 ? "active" : ""}`}>
          {actionableCount} {t("intraday.active")}
        </span>
      </div>

      {latest.length === 0 ? (
        <div className="intraday-empty-state">
          <strong>{t("intraday.monitoring")}</strong>
          <span>{t("intraday.no_candidates")}</span>
        </div>
      ) : (
        <div className="intraday-opportunity-list">
          {latest.map((row) => (
            <details
              key={row.opportunity_id}
              className={`intraday-opportunity status-${row.status.toLowerCase()}`}
              open={!compact && row.status === "ACTIONABLE_REVIEW"}
            >
              <summary>
                <span className="intraday-route-label">
                  <small>{row.buy_venue} / {row.sell_venue}</small>
                  <strong>{row.buy_hub} → {row.sell_hub} · {row.product}</strong>
                </span>
                <span className="intraday-margin-label">
                  <em>{t(statusKey(row.status))}</em>
                  <strong>
                    {formatValue(row.net_margin)} {row.comparison_currency}/MWh
                  </strong>
                </span>
              </summary>
              <div className="intraday-economics-grid">
                <span><small>{t("intraday.buy_ask")}</small><strong>{formatValue(row.buy_ask)}</strong></span>
                <span><small>{t("intraday.sell_bid")}</small><strong>{formatValue(row.sell_bid)}</strong></span>
                <span><small>{t("intraday.gross_spread")}</small><strong>{formatValue(row.gross_spread)}</strong></span>
                <span><small>{t("intraday.route_cost")}</small><strong>{formatValue(row.route_cost)}</strong></span>
                <span><small>{t("intraday.max_quantity")}</small><strong>{row.max_quantity_mwh?.toLocaleString() ?? "n/a"} MWh</strong></span>
                <span><small>{t("intraday.net_value")}</small><strong>{formatValue(row.indicative_net_value, 0)} {row.comparison_currency}</strong></span>
              </div>
              <div className="intraday-evidence-line">
                <span>{row.route_name}</span>
                <span>{t("intraday.quote_age")}: {formatValue(row.quote_age_seconds, 1)}s</span>
                <span>{t("intraday.confidence")}: {(row.confidence_score * 100).toFixed(0)}%</span>
                {row.simulated && <strong>{t("market.simulated_source")}</strong>}
              </div>
              {(row.missing_inputs.length > 0 || row.warnings.length > 0) && (
                <div className="intraday-warning-list">
                  {[...row.missing_inputs, ...row.warnings].map((item) => (
                    <span key={`${row.opportunity_id}-${item}`}>{item}</span>
                  ))}
                </div>
              )}
              <p>{t("intraday.human_review")}</p>
            </details>
          ))}
        </div>
      )}

      <div className="intraday-feed-footer">
        <span>{t("intraday.refresh_10s")}</span>
        <strong>
          {lastUpdatedAtUtc
            ? new Date(lastUpdatedAtUtc).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })
            : "n/a"}
        </strong>
      </div>
    </section>
  );
}
