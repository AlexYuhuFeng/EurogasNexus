import { useState } from "react";

import { api, type SellDownPlanDTO } from "@/api/client";
import { formatMoney, formatQuantity } from "@/app/model/riskLimitsModel";

type Translate = (key: string, options?: Record<string, unknown>) => string;

const HUBS = ["NBP", "TTF", "THE", "PEG", "ZTP", "PSV", "PVB", "CEGH"];

/**
 * Tomorrow's sell-down: how much of the hub's flowing supply to sell day-ahead and how much
 * to keep for within-day, from the contracts' own delivery volatility and the cost of being
 * short or long. Prices are typed from the screen; nothing is sold.
 */
export function SellDownPanel({ t }: { t: Translate }) {
  const [hub, setHub] = useState("NBP");
  const [da, setDa] = useState("");
  const [wd, setWd] = useState("");
  const [shortPenalty, setShortPenalty] = useState("1.5");
  const [longDiscount, setLongDiscount] = useState("0.3");
  const [lot, setLot] = useState("24");
  const [plan, setPlan] = useState<SellDownPlanDTO | null>(null);
  const [warnings, setWarnings] = useState<string[]>([]);
  const [message, setMessage] = useState<string | null>(null);
  const currency = hub === "NBP" ? "GBP" : "EUR";
  const run = () => {
    setMessage(null);
    api.sellDownPlan({
      hub,
      da_price: Number(da),
      wd_expected_price: Number(wd),
      short_penalty_per_mwh: Number(shortPenalty || 0),
      long_discount_per_mwh: Number(longDiscount || 0),
      lot_mwh: Number(lot || 24),
    })
      .then((response) => {
        setPlan(response.data);
        setWarnings(response.meta?.warnings ?? []);
      })
      .catch((caught: unknown) => setMessage(caught instanceof Error ? caught.message : String(caught)));
  };
  return (
    <section className="workspace-panel span-3 sell-down-panel" aria-labelledby="sell-down-title">
      <h2 id="sell-down-title">{t("selldown.title")}</h2>
      <p className="panel-copy">{t("selldown.copy")}</p>
      <div className="licence-form">
        <label>
          <span>{t("selldown.hub")}</span>
          <select value={hub} onChange={(event) => setHub(event.target.value)}>
            {HUBS.map((code) => <option key={code} value={code}>{code}</option>)}
          </select>
        </label>
        <label><span>{t("selldown.da", { currency })}</span><input inputMode="decimal" value={da} onChange={(event) => setDa(event.target.value)} /></label>
        <label><span>{t("selldown.wd", { currency })}</span><input inputMode="decimal" value={wd} onChange={(event) => setWd(event.target.value)} /></label>
        <label><span>{t("selldown.short_penalty")}</span><input inputMode="decimal" value={shortPenalty} onChange={(event) => setShortPenalty(event.target.value)} /></label>
        <label><span>{t("selldown.long_discount")}</span><input inputMode="decimal" value={longDiscount} onChange={(event) => setLongDiscount(event.target.value)} /></label>
        <label><span>{t("selldown.lot")}</span><input inputMode="decimal" value={lot} onChange={(event) => setLot(event.target.value)} /></label>
        <button type="button" disabled={da === "" || wd === ""} onClick={run}>{t("selldown.run")}</button>
      </div>
      {plan && (
        <div className="sell-down-result">
          <p className="lng-bid-headline">
            {t("selldown.headline", {
              sell: formatQuantity(plan.sell_day_ahead_mwh),
              lots: plan.lots_day_ahead,
              keep: formatQuantity(plan.keep_within_day_mwh),
              hub: plan.hub,
            })}
          </p>
          <dl className="contract-command-facts">
            <div><dt>{t("selldown.expected")}</dt><dd>{formatQuantity(plan.expected_supply_mwh)} <small>± {formatQuantity(plan.supply_stdev_mwh)}</small></dd></div>
            <div><dt>{t("selldown.p_short")}</dt><dd>{plan.probability_short_pct.toFixed(1)}%</dd></div>
            <div><dt>{t("selldown.cost")}</dt><dd>{formatMoney(plan.expected_cost_vs_perfect, currency)} <small>{t("selldown.vs_all", { cost: formatMoney(plan.sell_all_cost_vs_perfect, currency) })}</small></dd></div>
            <div><dt>{t("selldown.basis")}</dt><dd><small>{plan.volatility_basis}</small></dd></div>
          </dl>
          <ul className="panel-copy">{plan.reasons.map((reason) => <li key={reason}>{reason}</li>)}</ul>
        </div>
      )}
      {warnings.length > 0 && <ul className="contract-intake-warnings">{warnings.map((w) => <li key={w}>{w}</li>)}</ul>}
      {message && <p role="status">{message}</p>}
    </section>
  );
}
