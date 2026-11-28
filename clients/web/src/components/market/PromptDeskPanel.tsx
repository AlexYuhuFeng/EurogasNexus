/**
 * Prices → Prompt: within-day and day-ahead for one hub (`GET /api/market/prompt`), re-read
 * when a price or a trade changes (app/data/liveStream.ts), and every two seconds while the
 * live stream is down: the live screen (bid/offer with size, last, VWAP, volume, trades),
 * the WD − DA spread, today's booked prompt trades against VWAP, settlement and the mid at
 * decision time, and the tracked signals that expired unused. The gas day's position,
 * deadlines and imbalance are Today's. Decision support only: orders go on the execution
 * screen; nothing here sends one.
 */
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import "@/styles/promptDesk.css";
import { api } from "@/api/client";
import type { PromptMarketDTO, PromptQuoteDTO } from "@/api/promptMarket";
import { EmptyState, Instant, LiveValue, Segmented, Skeleton } from "@/components/ui";
import { formatMeasure } from "@/app/time/valueFormat";
import { liveStatus } from "@/app/data/liveStream";
import { useLiveTopics } from "@/app/hooks/useLive";

const POLL_MS = 2_000;
/** While live, a read this often keeps the quotes' age current between notices. */
const LIVE_AGE_MS = 10_000;
/** The shortest time between two re-reads on a burst of ticks. */
const LIVE_REREAD_MS = 500;
const HUBS = ["TTF", "NBP"] as const;

function num(value: number | null | undefined, places = 3): string {
  return formatMeasure("price", value, { decimals: places });
}

function signed(value: number | null | undefined, places = 3): string {
  return formatMeasure("change", value, { decimals: places });
}

export function PromptDeskPanel({ hub: initialHub }: { hub: string }) {
  const { t } = useTranslation();
  const [hub, setHub] = useState<string>(initialHub);
  const [data, setData] = useState<PromptMarketDTO | null>(null);
  const [error, setError] = useState<string | null>(null);
  const busy = useRef(false);
  const reload = useRef<() => void>(() => undefined);
  useLiveTopics(["prices", "trades"], () => reload.current(), { minIntervalMs: LIVE_REREAD_MS });

  useEffect(() => {
    let alive = true;
    let lastRead = 0;
    const load = async () => {
      if (busy.current || document.visibilityState !== "visible") return;
      busy.current = true;
      lastRead = Date.now();
      try {
        const response = await api.promptMarket(hub);
        if (alive) { setData(response.data); setError(null); }
      } catch (exc) {
        if (alive) setError(exc instanceof Error ? exc.message : String(exc));
      } finally {
        busy.current = false;
      }
    };
    reload.current = () => void load();
    void load();
    const timer = window.setInterval(() => {
      if (liveStatus().state === "live" && Date.now() - lastRead < LIVE_AGE_MS) return;
      void load();
    }, POLL_MS);
    return () => { alive = false; reload.current = () => undefined; window.clearInterval(timer); };
  }, [hub]);

  const unit = data?.market.within_day.quote?.currency ?? data?.market.day_ahead.quote?.currency ?? (hub === "NBP" ? "GBP" : "EUR");
  const row = (key: "within_day" | "day_ahead", quote: PromptQuoteDTO | null) => (
    <tr key={key} data-prompt-product={key}>
      <th scope="row">{t(`prompt.product.${key}`)}</th>
      <td className="num">{num(quote?.bid_mwh_per_day, 0)}</td>
      <td className="num" data-prompt-bid><LiveValue watch={quote?.bid} identity={`${hub}|${key}|bid`}>{num(quote?.bid)}</LiveValue></td>
      <td className="num" data-prompt-ask><LiveValue watch={quote?.ask} identity={`${hub}|${key}|ask`}>{num(quote?.ask)}</LiveValue></td>
      <td className="num">{num(quote?.ask_mwh_per_day, 0)}</td>
      <td className="num"><LiveValue watch={quote?.last_trade?.price ?? quote?.last} identity={`${hub}|${key}|last`}>{num(quote?.last_trade?.price ?? quote?.last)}</LiveValue></td>
      <td className="num">{num(quote?.vwap)}</td>
      <td className="num">{num(quote?.volume_mwh, 0)}</td>
      <td className="num">{quote?.trade_count ?? "–"}</td>
      <td className="num" title={quote?.observed_at_utc}>{quote ? `${Math.round(quote.age_seconds)} s` : "–"}</td>
    </tr>
  );

  return (
    <section className="prompt-desk" data-prompt-desk={hub} aria-label={t("prompt.title")}>
      <div className="prompt-head">
        <Segmented label={t("prompt.hub")} options={HUBS.map((code) => ({ value: code, label: code }))} value={hub} onChange={(value) => setHub(value)} />
        <span className="prompt-note">{t("prompt.no_orders")}</span>
      </div>
      {/* Simulated prices are said once, by the board's banner around this view (UX rule 10);
          each simulated trade row keeps its own mark. */}
      {error && !data && <p className="prompt-empty">{t("prompt.unavailable")}</p>}
      {!error && !data && <Skeleton label={t("prompt.loading")} rows={4} />}
      {data && (
        <>
          {/* No quote on either product: one line with where quotes come from, not a row of dashes. */}
          {!data.market.within_day.quote && !data.market.day_ahead.quote ? (
            <EmptyState compact id="prompt-quotes" need="licence" reason={t("prompt.no_quotes")} next={t("prompt.no_quotes_next")} />
          ) : (
          <div className="prompt-table-wrap" tabIndex={0} role="region" aria-label={t("prompt.screen")}>
            <table className="prompt-table">
              <caption>{t("prompt.screen_caption", { unit: `${unit}/MWh`, as_of: "" })}<Instant value={data.as_of_utc} seconds /></caption>
              <thead>
                <tr>
                  <th scope="col">{t("prompt.col.product")}</th>
                  <th scope="col" className="num">{t("prompt.col.bid_vol")}</th>
                  <th scope="col" className="num">{t("prompt.col.bid")}</th>
                  <th scope="col" className="num">{t("prompt.col.offer")}</th>
                  <th scope="col" className="num">{t("prompt.col.offer_vol")}</th>
                  <th scope="col" className="num">{t("prompt.col.last")}</th>
                  <th scope="col" className="num">{t("prompt.col.vwap")}</th>
                  <th scope="col" className="num">{t("prompt.col.volume")}</th>
                  <th scope="col" className="num">{t("prompt.col.trades")}</th>
                  <th scope="col" className="num">{t("prompt.col.age")}</th>
                </tr>
              </thead>
              <tbody>
                {row("within_day", data.market.within_day.quote)}
                {row("day_ahead", data.market.day_ahead.quote)}
              </tbody>
            </table>
          </div>
          )}
          <dl className="prompt-figures">
            <div data-figure="wd-da">
              <dt>{t("prompt.spread")}</dt>
              <dd>{data.spread_wd_da ? `${signed(data.spread_wd_da.mid)} (${num(data.spread_wd_da.sell)} / ${num(data.spread_wd_da.buy)})` : "–"}</dd>
            </div>
            <div data-figure="day-pnl">
              <dt>{t("prompt.day_pnl", { currency: data.performance.currency ?? unit })}</dt>
              {/* No prompt trade booked: the P&L is unknown, never shown as zero. */}
              <dd>{data.performance.trades.length ? signed(data.performance.day_pnl, 0) : "–"}</dd>
            </div>
          </dl>
          <h3 className="prompt-subtitle">{t("prompt.performance")}</h3>
          {data.performance.trades.length === 0 ? (
            <p className="prompt-empty">{t("prompt.performance.empty")}</p>
          ) : (
            <div className="prompt-table-wrap" tabIndex={0} role="region" aria-label={t("prompt.performance")}>
              <table className="prompt-table" data-prompt-performance>
                <caption>{t("prompt.performance.caption")}</caption>
                <thead>
                  <tr>
                    <th scope="col">{t("prompt.col.time")}</th>
                    <th scope="col">{t("prompt.col.product")}</th>
                    <th scope="col">{t("prompt.col.side")}</th>
                    <th scope="col" className="num">{t("prompt.col.price")}</th>
                    <th scope="col" className="num">{t("prompt.col.mwh")}</th>
                    <th scope="col" className="num">{t("prompt.col.vs_vwap")}</th>
                    <th scope="col" className="num">{t("prompt.col.vs_settlement")}</th>
                    <th scope="col" className="num">{t("prompt.col.vs_decision")}</th>
                    <th scope="col" className="num">{t("prompt.col.slippage")}</th>
                    <th scope="col" className="num">{t("prompt.col.pnl")}</th>
                  </tr>
                </thead>
                <tbody>
                  {data.performance.trades.slice(0, 20).map((trade) => (
                    <tr key={trade.id}>
                      <td><Instant value={trade.traded_at_utc} seconds /></td>
                      <td>{t(`prompt.product.${trade.product}`)}{trade.simulated ? <span className="prompt-sim-mark"> sim</span> : null}</td>
                      <td>{t(`prompt.side.${trade.side}`)}</td>
                      <td className="num">{num(trade.price)}</td>
                      <td className="num">{num(trade.mwh, 0)}</td>
                      <td className="num">{signed(trade.vs_vwap)}</td>
                      <td className="num">{signed(trade.vs_settlement)}</td>
                      <td className="num">{signed(trade.vs_decision_mid)}</td>
                      <td className="num">{signed(trade.slippage_vs_touch)}</td>
                      <td className="num">{signed(trade.pnl, 0)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </section>
  );
}
