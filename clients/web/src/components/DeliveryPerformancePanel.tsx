import { useEffect, useState } from "react";

import { api, type DeliveryPerformanceDTO } from "@/api/client";
import { deliveryBars, formatQuantity } from "@/app/model/riskLimitsModel";
import { ReportExport } from "./ReportExport";

type Translate = (key: string, options?: Record<string, unknown>) => string;

const WINDOWS = [30, 90, 365];

/**
 * Bilateral supply as it actually flowed: allocations against nominations and DCQ, per
 * contract. The trader sees which seller under-delivers, how volatile a field is, and the
 * imbalance the desk had to cover at the hub; selecting a contract shows its gas days.
 */
export function DeliveryPerformancePanel({ t }: { t: Translate }) {
  const [days, setDays] = useState(90);
  const [data, setData] = useState<DeliveryPerformanceDTO | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [detail, setDetail] = useState<DeliveryPerformanceDTO | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    api.deliveryPerformance(days, undefined, { signal: controller.signal })
      .then((response) => setData(response.data))
      .catch(() => setData(null));
    return () => controller.abort();
  }, [days]);

  useEffect(() => {
    if (!selected) {
      setDetail(null);
      return;
    }
    const controller = new AbortController();
    api.deliveryPerformance(days, selected, { signal: controller.signal })
      .then((response) => setDetail(response.data))
      .catch(() => setDetail(null));
    return () => controller.abort();
  }, [days, selected]);

  const bars = detail ? deliveryBars(detail.series) : [];

  return (
    <section className="workspace-panel span-3 delivery-panel" aria-labelledby="delivery-title">
      <div className="panel-title-row">
        <h2 id="delivery-title">{t("delivery.title")}</h2>
        <label className="position-horizon">
          <span>{t("delivery.window")}</span>
          <select value={days} onChange={(event) => setDays(Number(event.target.value))}>
            {WINDOWS.map((value) => <option key={value} value={value}>{t("delivery.days", { count: value })}</option>)}
          </select>
        </label>
        <ReportExport t={t} path="/contracts/delivery-performance" params={{ days: String(days) }} />
      </div>
      {data && data.rows.length === 0 && <p className="muted">{t("delivery.empty")}</p>}
      {data && data.rows.length > 0 && (
        <table className="position-ladder" data-delivery-performance="true">
          <thead>
            <tr>
              <th scope="col">{t("delivery.contract")}</th>
              <th scope="col" className="num">{t("delivery.dcq")}</th>
              <th scope="col" className="num">{t("delivery.mean_allocated")}</th>
              <th scope="col" className="num">{t("delivery.net_deviation")}</th>
              <th scope="col" className="num">{t("delivery.imbalance")}</th>
              <th scope="col" className="num">{t("delivery.short_long")}</th>
              <th scope="col" className="num">{t("delivery.cv")}</th>
              <th scope="col" className="num">{t("delivery.trend")}</th>
              <th scope="col">{t("delivery.flags")}</th>
            </tr>
          </thead>
          <tbody>
            {data.rows.map((row) => (
              <tr
                key={row.contract_id}
                data-status={row.status}
                aria-selected={selected === row.contract_id}
                className={selected === row.contract_id ? "selected" : undefined}
              >
                <td>
                  <button type="button" className="link-button" onClick={() => setSelected(selected === row.contract_id ? null : row.contract_id)}>
                    {row.contract}
                  </button>{" "}
                  <small>{[row.hub, row.tso].filter(Boolean).join(" · ")}</small>
                </td>
                <td className="num">{formatQuantity(row.dcq_mwh_d, "MWh/d")}</td>
                <td className="num">{formatQuantity(row.mean_allocated_mwh_d, "MWh/d")}</td>
                <td className="num">{formatQuantity(row.net_deviation_mwh)}</td>
                <td className="num">{formatQuantity(row.imbalance_mwh)}</td>
                <td className="num">{row.short_days} / {row.long_days}</td>
                <td className="num">{row.cv_pct === null ? "-" : `${row.cv_pct.toFixed(1)}%`}</td>
                <td className="num">{row.trend_7d_vs_dcq_pct === null ? "-" : `${row.trend_7d_vs_dcq_pct > 0 ? "+" : ""}${row.trend_7d_vs_dcq_pct.toFixed(1)}%`}</td>
                <td>
                  <span className="limit-badge" data-status={row.status}>{t(`delivery.status_${row.status}`)}</span>
                  {row.flags && <div className="limit-breaches">{row.flags}</div>}
                  {row.missing_days > 0 && <small> {t("delivery.missing", { count: row.missing_days })}</small>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {detail && detail.series.length > 0 && (
        <figure className="delivery-strip" aria-label={t("delivery.strip_label", { contract: selected })}>
          <div className="delivery-bars">
            {detail.series.map((day, index) => (
              <span
                key={day.gas_day}
                className="delivery-day"
                title={`${day.gas_day}: ${t("delivery.nominated")} ${formatQuantity(day.nominated_mwh)}, ${t("delivery.allocated")} ${formatQuantity(day.allocated_mwh)}`}
              >
                <span className="delivery-nominated" style={{ height: `${bars[index].nominated * 100}%` }} />
                {bars[index].allocated !== null && (
                  <span
                    className="delivery-allocated"
                    data-short={day.outside_tolerance === "short" ? "true" : undefined}
                    style={{ height: `${(bars[index].allocated ?? 0) * 100}%` }}
                  />
                )}
              </span>
            ))}
          </div>
          <figcaption>
            <span className="legend-swatch nominated" /> {t("delivery.nominated")}
            <span className="legend-swatch allocated" /> {t("delivery.allocated")}
            <span className="legend-swatch short" /> {t("delivery.short")}
            <ReportExport t={t} path="/contracts/delivery-performance" params={{ days: String(days), contract_id: selected ?? "" }} />
          </figcaption>
        </figure>
      )}
    </section>
  );
}
