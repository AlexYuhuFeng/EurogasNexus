import { useEffect, useState } from "react";

import { api, type SellDownPlanDTO, type TodayKeyFiguresRowDTO } from "@/api/client";
import { formatMoney, formatQuantity } from "@/app/model/riskLimitsModel";
import { PanelHelp } from "@/components/ui/PanelHelp";
import { latestBoardPrice } from "@/app/model/boardInputs";
import { sourceSystemLabel } from "@/app/model/enumLabels";
import { formatGasDay } from "@/app/time/timeFormat";
import { useApiStore } from "@/stores/api";
import { useCachedRead } from "@/app/data/readCache";
import { useDeskToday } from "@/app/hooks/useDeskToday";
import { useTranslation } from "react-i18next";
import { formatMeasure, plainDecimal } from "@/app/time/valueFormat";

type Translate = (key: string, options?: Record<string, unknown>) => string;

const HUBS = ["NBP", "TTF", "THE", "PEG", "ZTP", "PSV", "PVB", "CEGH"];

/**
 * Tomorrow's sell-down: how much of the hub's flowing supply to sell day-ahead and how much
 * to keep for within-day, from the contracts' own delivery volatility and the cost of being
 * short or long. Prices come from the board by default (UX_REFERENCE rule 25); a typed price is
 * said in the result. Nothing is sold.
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
  const { i18n } = useTranslation();
  // The board's rows: the store's when the page loaded them, else this panel's own cached read
  // (Book does not load the market board for every task).
  const storeMarkets = useApiStore((state) => state.normalizedMarkets);
  const marketRead = useCachedRead(storeMarkets.length ? null : "/market/normalized?limit=500", (signal) => api.normalizedMarketObservations({ signal }));
  // Today's read holds each hub's day-ahead close (the market board's rows hold the curves).
  const today = useDeskToday().today;
  const todayMarket = today?.rows.find((row): row is TodayKeyFiguresRowDTO => row?.key === "key_figures")?.market;
  const todayCloses = (todayMarket?.hubs ?? []).flatMap((row) =>
    row.day_ahead && row.day_ahead.value !== null
      ? [{
          hub: row.hub,
          product: "day-ahead",
          price: row.day_ahead.value,
          unit: row.day_ahead.unit,
          currency: row.day_ahead.unit.slice(0, 3).toUpperCase(),
          period_start_utc: row.day_ahead.close_day,
          source_system: row.day_ahead.source ?? undefined,
          freshness: row.day_ahead.simulated ? "simulated" : undefined,
        }]
      : [],
  );
  const markets = [...(storeMarkets.length ? storeMarkets : marketRead.data?.data ?? []), ...todayCloses];
  const boardDa = latestBoardPrice(markets, hub, "day-ahead", currency);
  const boardWd = latestBoardPrice(markets, hub, "within-day", currency);
  const [typed, setTyped] = useState<{ da: boolean; wd: boolean }>({ da: false, wd: false });
  // A new hub, or a new board read, refills what was not typed by hand.
  useEffect(() => {
    if (!typed.da) setDa(boardDa ? plainDecimal(boardDa.value, 3) : "");
    if (!typed.wd) setWd(boardWd ? plainDecimal(boardWd.value, 3) : boardDa ? plainDecimal(boardDa.value, 3) : "");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hub, boardDa?.value, boardWd?.value]);
  const sourceLine = (price: ReturnType<typeof latestBoardPrice>, wasTyped: boolean) =>
    wasTyped
      ? t("selldown.typed")
      : price
        ? t("selldown.from_board", { day: formatGasDay(price.day, i18n.language), source: price.simulated ? t("today.simulated_short") : price.source ? sourceSystemLabel(price.source, t) : "" })
        : t("selldown.no_board");
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
      <PanelHelp text={t("selldown.copy")} label={t("panel.how_to_read")} />
      <div className="licence-form">
        <label>
          <span>{t("selldown.hub")}</span>
          <select value={hub} onChange={(event) => { setHub(event.target.value); setTyped({ da: false, wd: false }); }}>
            {HUBS.map((code) => <option key={code} value={code}>{code}</option>)}
          </select>
        </label>
        <label><span>{t("selldown.da", { currency })}</span><input inputMode="decimal" value={da} onChange={(event) => { setDa(event.target.value); setTyped((current) => ({ ...current, da: true })); }} /><small className="muted" data-input-source="da">{sourceLine(boardDa, typed.da)}</small></label>
        <label><span>{t("selldown.wd", { currency })}</span><input inputMode="decimal" value={wd} onChange={(event) => { setWd(event.target.value); setTyped((current) => ({ ...current, wd: true })); }} /><small className="muted" data-input-source="wd">{sourceLine(boardWd ?? boardDa, typed.wd)}</small></label>
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
          {(typed.da || typed.wd) && (
            <p className="muted" data-manual-inputs="true">
              {t("selldown.manual_inputs", {
                inputs: [typed.da ? t("selldown.da", { currency }) : null, typed.wd ? t("selldown.wd", { currency }) : null].filter(Boolean).join(", "),
              })}
            </p>
          )}
          <dl className="contract-command-facts">
            <div><dt>{t("selldown.expected")}</dt><dd>{formatQuantity(plan.expected_supply_mwh)} <small>± {formatQuantity(plan.supply_stdev_mwh)}</small></dd></div>
            <div><dt>{t("selldown.p_short")}</dt><dd>{formatMeasure("percent", plan.probability_short_pct)}</dd></div>
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
