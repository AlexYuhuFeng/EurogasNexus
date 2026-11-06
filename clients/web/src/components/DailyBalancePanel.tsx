import { useEffect, useState } from "react";

import { api, type DailyBalanceDTO } from "@/api/client";
import { formatQuantity } from "@/app/model/riskLimitsModel";
import { GAS_HUBS } from "@/app/contractChoices";
import { PanelHelp } from "@/components/ui/PanelHelp";

type Translate = (key: string, options?: Record<string, unknown>) => string;

function signed(value: number): string {
  if (Math.abs(value) < 0.5) return "0";
  return `${value > 0 ? "+" : "−"}${formatQuantity(Math.abs(value)).replace(" MWh", "")}`;
}

/**
 * The desk's gas balance per gas day at one hub. Gas is balanced daily: whatever is still
 * long or short at the end of a gas day is cashed out by the TSO at a penal price. For each
 * coming day this shows expected supply (contracts corrected by how they deliver), what has
 * been bought and sold on the exchange and bilaterally, and the residual still to close,
 * with what leaving it open would cost at the desk's own cash-out spreads.
 */
export function DailyBalancePanel({ t }: { t: Translate }) {
  const [hub, setHub] = useState("NBP");
  const [days, setDays] = useState(7);
  const [shortPremium, setShortPremium] = useState("1.5");
  const [longDiscount, setLongDiscount] = useState("0.3");
  const [balance, setBalance] = useState<DailyBalanceDTO | null>(null);
  const [warnings, setWarnings] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    setError(null);
    api
      .dailyBalance(
        {
          hub,
          days,
          short_premium_per_mwh: shortPremium === "" ? undefined : Number(shortPremium),
          long_discount_per_mwh: longDiscount === "" ? undefined : Number(longDiscount),
        },
        { signal: controller.signal },
      )
      .then((response) => {
        setBalance(response.data);
        setWarnings(response.meta?.warnings ?? []);
      })
      .catch((caught: unknown) => {
        if (!controller.signal.aborted) setError(caught instanceof Error ? caught.message : String(caught));
      });
    return () => controller.abort();
  }, [hub, days, shortPremium, longDiscount]);

  const currency = balance?.currency ?? (hub === "NBP" ? "GBP" : "EUR");
  const open = balance?.days.filter((day) => day.state !== "balanced") ?? [];
  const exposure = open.reduce((sum, day) => sum + (day.cash_out_cost ?? 0), 0);

  return (
    <section className="workspace-panel span-3 daily-balance-panel" aria-labelledby="daily-balance-title">
      <h2 id="daily-balance-title">{t("balance.title")}</h2>
      <PanelHelp text={t("balance.copy")} label={t("panel.how_to_read")} />
      <div className="licence-form">
        <label>
          <span>{t("selldown.hub")}</span>
          <select value={hub} onChange={(event) => setHub(event.target.value)}>
            {GAS_HUBS.map((code) => <option key={code} value={code}>{code}</option>)}
          </select>
        </label>
        <label>
          <span>{t("balance.days")}</span>
          <select value={days} onChange={(event) => setDays(Number(event.target.value))}>
            {[3, 7, 14, 31].map((count) => <option key={count} value={count}>{t("balance.days_n", { count })}</option>)}
          </select>
        </label>
        <label><span>{t("balance.short_premium", { currency })}</span><input inputMode="decimal" value={shortPremium} onChange={(event) => setShortPremium(event.target.value)} /></label>
        <label><span>{t("balance.long_discount", { currency })}</span><input inputMode="decimal" value={longDiscount} onChange={(event) => setLongDiscount(event.target.value)} /></label>
      </div>
      {error && <p role="alert" className="limit-breaches">{error}</p>}
      {balance && (
        <>
          <p className={open.length ? "balance-headline warning-text" : "balance-headline"}>
            <strong>
              {open.length
                ? t("balance.headline_open", { count: open.length, cost: `${currency} ${Math.round(exposure).toLocaleString()}` })
                : t("balance.headline_flat")}
            </strong>{" "}
            <small className="muted">{t("balance.delivery_ratio", { pct: (balance.delivery_ratio * 100).toFixed(1) })}</small>
          </p>
          <table className="position-ladder daily-balance">
            <thead>
              <tr>
                <th scope="col">{t("balance.gas_day")}</th>
                <th scope="col" className="num">{t("balance.supply")}</th>
                <th scope="col" className="num">{t("balance.exchange")}</th>
                <th scope="col" className="num">{t("balance.bilateral")}</th>
                <th scope="col" className="num">{t("balance.residual")}</th>
                <th scope="col">{t("balance.state")}</th>
                <th scope="col" className="num">{t("balance.cash_out", { currency })}</th>
              </tr>
            </thead>
            <tbody>
              {balance.days.map((day) => (
                <tr key={day.gas_day} data-status={day.state === "balanced" ? undefined : "watch"}>
                  <td>{day.gas_day}</td>
                  <td className="num">{formatQuantity(day.supply)}</td>
                  <td className="num">{signed(day.exchange_bought - day.exchange_sold)}</td>
                  <td className="num">{signed(day.bilateral_bought - day.bilateral_sold)}</td>
                  <td className="num"><strong>{signed(day.residual_mwh)}</strong></td>
                  <td><span className="limit-badge" data-status={day.state === "balanced" ? "ok" : "watch"}>{t(`balance.state_${day.state}`)}</span></td>
                  <td className="num">{day.cash_out_cost == null ? "–" : Math.round(day.cash_out_cost).toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {warnings.length > 0 && <ul className="muted">{warnings.map((warning) => <li key={warning}><small>{warning}</small></li>)}</ul>}
        </>
      )}
    </section>
  );
}
