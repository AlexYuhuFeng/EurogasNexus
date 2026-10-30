import { useEffect, useState } from "react";

import {
  api,
  type GasProductDTO,
  type PriceConversionDTO,
  type StorageTrajectoryDTO,
} from "@/api/client";
import { PanelHeader } from "@/components/ui";
import { apiErrorDetailCode, describeFailure, presentError } from "@/app/experience/errorPresentation";
import {
  FX_SOURCE_OPTIONS,
  PRICE_UNIT_OPTIONS,
  describeFxRate,
  STORAGE_CODES,
  formatConverted,
  formatSigned,
  storageStatusKey,
} from "@/app/model/traderDeskModel";
import "./trader-desk.css";

type Translate = (key: string) => string;

interface TraderDeskPanelProps {
  t: Translate;
}

/**
 * Desk conventions next to the price board: the standard product strip with its real delivery
 * window, a hub price converter (EUR/MWh, p/th, $/MMBtu) and the storage-target trajectory.
 *
 * Every number is the backend's: the strip comes from the gas-day calendar, the conversion from
 * the backend's factors and the latest ECB rate it echoes, the trajectory from AGSI rows. A
 * missing FX rate or storage series is shown as unavailable, never filled in client-side.
 */
export function TraderDeskPanel({ t }: TraderDeskPanelProps) {
  const [strip, setStrip] = useState<GasProductDTO[]>([]);
  const [tradeDate, setTradeDate] = useState<string | null>(null);
  const [stripError, setStripError] = useState<unknown>(null);

  const [priceText, setPriceText] = useState("35");
  const [fromUnit, setFromUnit] = useState<string>("EUR/MWh");
  const [fxSource, setFxSource] = useState<string>("ECB");
  const [conversion, setConversion] = useState<PriceConversionDTO | null>(null);
  const [conversionError, setConversionError] = useState<unknown>(null);

  const [storageCode, setStorageCode] = useState<string>("EU");
  const [trajectory, setTrajectory] = useState<StorageTrajectoryDTO | null>(null);
  const [storageError, setStorageError] = useState<unknown>(null);

  useEffect(() => {
    const controller = new AbortController();
    api.gasProductStrip({ signal: controller.signal })
      .then((response) => {
        setStrip(response.data.products);
        setTradeDate(response.data.trade_date);
        setStripError(null);
      })
      .catch((error: unknown) => {
        if (!controller.signal.aborted) setStripError(error);
      });
    return () => controller.abort();
  }, []);

  useEffect(() => {
    const value = Number(priceText);
    if (!priceText.trim() || !Number.isFinite(value)) {
      setConversion(null);
      return undefined;
    }
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      api.priceConversion(value, fromUnit, fxSource, { signal: controller.signal })
        .then((response) => {
          setConversion(response.data);
          setConversionError(null);
        })
        .catch((error: unknown) => {
          if (!controller.signal.aborted) setConversionError(error);
        });
    }, 250);
    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [priceText, fromUnit, fxSource]);

  useEffect(() => {
    const controller = new AbortController();
    api.storageTargetTrajectory(storageCode, { signal: controller.signal })
      .then((response) => {
        setTrajectory(response.data);
        setStorageError(null);
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        setTrajectory(null);
        setStorageError(error);
      });
    return () => controller.abort();
  }, [storageCode]);

  const failureText = (error: unknown) => {
    const failure = presentError(t, describeFailure(error));
    return (
      <div className="trader-desk-failure" role="status">
        <strong>{failure.title}</strong>
        <p>{failure.action}</p>
      </div>
    );
  };

  return (
    <section className="workspace-panel trader-desk" aria-label={t("desk.title")}>
      <PanelHeader title={t("desk.title")} meta={tradeDate ? `${t("desk.trade_date")} ${tradeDate}` : null} />
      <div className="trader-desk-grid">
        <div className="trader-desk-block" aria-label={t("desk.strip")}>
          <h3>{t("desk.strip")}</h3>
          {stripError ? failureText(stripError) : (
            <table className="trader-desk-table">
              <thead>
                <tr>
                  <th>{t("desk.product")}</th>
                  <th>{t("desk.delivery")}</th>
                  <th className="num">{t("desk.gas_days")}</th>
                  <th className="num">{t("desk.hours")}</th>
                </tr>
              </thead>
              <tbody>
                {strip.map((product) => (
                  <tr key={product.code} data-product-code={product.code}>
                    <td><strong>{product.code}</strong> <span className="muted">{product.label}</span></td>
                    <td>
                      {product.first_gas_day === product.last_gas_day
                        ? product.first_gas_day
                        : `${product.first_gas_day} → ${product.last_gas_day}`}
                    </td>
                    <td className="num">{product.gas_days}</td>
                    <td className="num">{product.hours}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          <p className="trader-desk-note">{t("desk.strip_note")}</p>
        </div>

        <div className="trader-desk-block" aria-label={t("desk.converter")}>
          <h3>{t("desk.converter")}</h3>
          <div className="trader-desk-inputs">
            <input
              type="number"
              inputMode="decimal"
              step="0.01"
              value={priceText}
              aria-label={t("desk.price")}
              onChange={(event) => setPriceText(event.target.value)}
            />
            <select
              value={fromUnit}
              aria-label={t("desk.from_unit")}
              onChange={(event) => setFromUnit(event.target.value)}
            >
              {PRICE_UNIT_OPTIONS.map((unit) => <option key={unit} value={unit}>{unit}</option>)}
            </select>
            <select
              value={fxSource}
              aria-label={t("desk.fx_source")}
              title={t("desk.fx_source_hint")}
              onChange={(event) => setFxSource(event.target.value)}
            >
              {FX_SOURCE_OPTIONS.map((source) => (
                <option key={source} value={source}>{t(`desk.fx_source.${source}`)}</option>
              ))}
            </select>
          </div>
          {conversionError ? failureText(conversionError) : conversion && (
            <>
              <table className="trader-desk-table">
                <tbody>
                  {PRICE_UNIT_OPTIONS.filter((unit) => unit !== conversion.from_unit).map((unit) => (
                    <tr key={unit}>
                      <td>{unit}</td>
                      <td className="num">{formatConverted(conversion.converted[unit], t("desk.fx_missing"))}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <p className="trader-desk-note">
                {conversion.fx_fixing.label}
                {" · "}
                {Object.entries(conversion.fx).length === 0
                  ? t(conversion.fx_fixing.licensed ? "desk.fx_licensed_none" : "desk.fx_none")
                  : Object.entries(conversion.fx).map(([ccy, fx]) => describeFxRate(ccy, fx)).join(" · ")}
              </p>
            </>
          )}
        </div>

        <div className="trader-desk-block" aria-label={t("desk.storage")}>
          <h3>{t("desk.storage")}</h3>
          <div className="trader-desk-inputs">
            <select
              value={storageCode}
              aria-label={t("desk.storage_code")}
              onChange={(event) => setStorageCode(event.target.value)}
            >
              {STORAGE_CODES.map((code) => <option key={code} value={code}>{code}</option>)}
            </select>
            {trajectory && (
              <span className={`trader-desk-status status-${trajectory.status}`}>
                {t(storageStatusKey(trajectory.status))}
              </span>
            )}
          </div>
          {storageError && apiErrorDetailCode(storageError) === "storage_series_unavailable" ? (
            <p className="trader-desk-note">{t("desk.storage_no_series")}</p>
          ) : storageError ? failureText(storageError) : trajectory === null ? (
            <p className="trader-desk-note">{t("desk.storage_unavailable")}</p>
          ) : (
            <>
              <dl className="trader-desk-metrics">
                <div><dt>{t("desk.fill")}</dt><dd>{trajectory.fill_pct.toFixed(1)}%</dd></div>
                <div><dt>{t("desk.target")}</dt><dd>{trajectory.effective_target_pct}% · {trajectory.deadline}</dd></div>
                <div><dt>{t("desk.gap")}</dt><dd>{trajectory.gap_twh.toFixed(1)} TWh</dd></div>
                <div>
                  <dt>{t("desk.required")}</dt>
                  <dd>{formatSigned(trajectory.required_net_injection_to_deadline_twh_d, "TWh/d")}</dd>
                </div>
                <div>
                  <dt>{t("desk.recent")}</dt>
                  <dd>{formatSigned(trajectory.recent_net_injection_twh_d, "TWh/d")} ({trajectory.pace_days_used}d)</dd>
                </div>
                <div>
                  <dt>{t("desk.projected")}</dt>
                  <dd>
                    {trajectory.projected_fill_at_deadline_pct === null
                      ? "n/a"
                      : `${trajectory.projected_fill_at_deadline_pct.toFixed(1)}%`}
                  </dd>
                </div>
              </dl>
              <p className="trader-desk-note">
                {t("desk.as_of")} {trajectory.as_of_gas_day} · {t("desk.storage_note")}
              </p>
            </>
          )}
        </div>
      </div>
    </section>
  );
}
