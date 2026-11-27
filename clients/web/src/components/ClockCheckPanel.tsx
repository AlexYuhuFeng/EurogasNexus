/**
 * Runtime → Delivery: is the server's clock right, and does this computer agree with it?
 * (small-desk plan section 5: deals and prices are ordered by time.)
 *
 * The server's own check against NTP (application/clock_check.py, via `/api/health`): offset,
 * whether synchronisation is active, and the threshold (0.5 s). And this browser's clock against
 * the server's, measured over the round trip (app/data/connection.ts); above 5 s the line under
 * the top bar says so to everyone.
 */
import { CLOCK_SKEW_WARN_MS, probe, useConnection } from "@/app/data/connection";
import { formatMeasure } from "@/app/time/valueFormat";
import { StatusBadge } from "@/components/ui";

type Translate = (key: string, options?: Record<string, unknown>) => string;

function seconds(value: number | null | undefined, digits = 3): string {
  // A signed offset in seconds, at the precision the check has (formatMeasure: one sign rule).
  return formatMeasure("change", value, { decimals: digits, signed: true, unit: "s" });
}

export function ClockCheckPanel({ t }: { t: Translate }) {
  const connection = useConnection();
  const clock = connection.serverClock;
  const skew = connection.clockSkewMs;
  const browserState = skew === null ? "unknown" : Math.abs(skew) > CLOCK_SKEW_WARN_MS ? "warning" : "ok";
  return (
    <div className="workspace-panel span-3" data-clock-check={clock?.state ?? "unknown"}>
      <h2>{t("clock.title")}</h2>
      <p className="panel-copy">{t("clock.help")}</p>
      <div className="metric-grid three-column">
        <div>
          <span>{t("clock.server")}</span>
          <strong>
            <StatusBadge variant="pipeline" status={clock?.state === "ok" ? "healthy" : clock?.state === "warning" ? "degraded" : "unknown"}>
              {t(`clock.state.${clock?.state ?? "unknown"}`)}
            </StatusBadge>
          </strong>
          <small>
            {t("clock.offset", { value: seconds(clock?.offsetSeconds) })}
            {" · "}
            {t(clock?.synchronised === true ? "clock.synced" : clock?.synchronised === false ? "clock.not_synced" : "clock.sync_unknown")}
            {" · "}
            {t("clock.threshold", { value: clock?.thresholdSeconds ?? 0.5 })}
          </small>
        </div>
        <div>
          <span>{t("clock.browser")}</span>
          <strong>{t(`clock.state.${browserState}`)}</strong>
          <small>{t("clock.browser_detail", { value: seconds(skew === null ? null : skew / 1000, 1), limit: CLOCK_SKEW_WARN_MS / 1000 })}</small>
        </div>
      </div>
      <button type="button" className="secondary-button" onClick={() => void probe()}>{t("clock.check_now")}</button>
    </div>
  );
}
