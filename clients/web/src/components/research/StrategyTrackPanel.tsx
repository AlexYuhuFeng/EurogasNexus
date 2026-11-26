/**
 * Research → Spreads → Track: a shadow run of the strategy on the screen (paper only).
 *
 * "Track this strategy" saves the current StrategySpec: a history with a rule is tracked daily
 * on new closes with that rule; otherwise legs on prompt products (WD, DA, WE, BOM) are tracked
 * intraday on arriving quotes with a 30-minute mean-reversion rule (see ``trackModeOf``). The panel lists the caller's own tracks and shows
 * the selected one: the signal while it is actionable (with its countdown and the cut-off it
 * comes from; withdrawn when it expires or its quote goes stale), the paper position and P&L,
 * the blotter and the assumptions. Nothing is sent anywhere: every fill is a paper fill.
 */
import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import "@/styles/promptDesk.css";
import { api } from "@/api/client";
import type { StrategySpecDTO } from "@/api/spreads";
import type { StrategyTrackDTO } from "@/api/strategyTracks";
import { Button, Instant } from "@/components/ui";
import { trackModeOf } from "@/app/model/strategyTrack";
import { formatMeasure } from "@/app/time/valueFormat";

export { trackModeOf };

const INTRADAY_RULE = {
  kind: "zscore_window", window_minutes: 30, min_points: 30, entry_z: 2, exit_z: 0.5, size_mw: 10,
  min_top_size_mwh: 24, max_quote_age_seconds: 60, max_no_trade_minutes: 10, debounce_seconds: 1,
};

function fixed(value: number | null | undefined, places: number): string {
  return formatMeasure("ratio", value, { decimals: places });
}

function useSecondClock(): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1_000);
    return () => window.clearInterval(timer);
  }, []);
  return now;
}

export function StrategyTrackPanel({ spec }: { spec: StrategySpecDTO | null }) {
  const { t } = useTranslation();
  const now = useSecondClock();
  const [tracks, setTracks] = useState<StrategyTrackDTO[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [detail, setDetail] = useState<StrategyTrackDTO | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const mode = trackModeOf(spec);

  const loadList = useCallback(async () => {
    try {
      const response = await api.strategyTracks();
      setTracks(response.data);
      setSelected((current) => current ?? response.data.find((item) => item.state === "active")?.track_id ?? null);
    } catch {
      setTracks([]);
    }
  }, []);

  useEffect(() => { void loadList(); }, [loadList]);

  useEffect(() => {
    if (!selected) { setDetail(null); return; }
    let alive = true;
    const load = async () => {
      if (document.visibilityState !== "visible") return;
      try {
        const response = await api.strategyTrack(selected);
        if (alive) setDetail(response.data);
      } catch {
        if (alive) setDetail(null);
      }
    };
    void load();
    const intraday = tracks.find((item) => item.track_id === selected)?.mode === "intraday";
    const timer = window.setInterval(() => void load(), intraday ? 2_000 : 60_000);
    return () => { alive = false; window.clearInterval(timer); };
  }, [selected, tracks]);

  const track = async () => {
    if (!spec || !mode) return;
    setSaving(true);
    setMessage(null);
    try {
      const name = spec.legs.map((leg) => `${leg.weight > 0 ? "+" : "−"}${leg.hub} ${leg.tenor ?? ""}`.trim()).join(" ");
      const response = await api.createStrategyTrack({ name, mode, spec, rule: mode === "intraday" ? INTRADAY_RULE : null });
      setSelected(response.data.track_id);
      await loadList();
    } catch (exc) {
      const text = exc instanceof Error ? exc.message : String(exc);
      setMessage(/403|permission/i.test(text) ? t("track.permission") : t("track.refused", { reason: text }));
    } finally {
      setSaving(false);
    }
  };

  const stop = async () => {
    if (!selected) return;
    await api.stopStrategyTrack(selected);
    await loadList();
  };

  const snapshot = detail?.snapshot;
  const advice = snapshot?.advice ?? null;
  const left = advice?.expires_at ? Math.max(0, Math.round((Date.parse(advice.expires_at) - now) / 1000)) : null;
  const actionable = advice && (left === null || left > 0);
  const currency = snapshot?.currency ?? snapshot?.unit ?? "";
  return (
    <section className="track-panel" data-track-panel aria-label={t("track.title")}>
      <div className="track-head">
        <strong>{t("track.title")}</strong>
        <Button size="sm" onClick={() => void track()} disabled={!mode} loading={saving} data-track-start>
          {t("track.start")}
        </Button>
        <span className="track-note">{mode ? t(`track.mode.${mode}`) : t("track.not_trackable")}</span>
      </div>
      {message && <p className="track-note" role="status">{message}</p>}
      {tracks.length > 0 && (
        <ul className="track-list" aria-label={t("track.list")}>
          {tracks.slice(0, 8).map((item) => (
            <li key={item.track_id}>
              <Button size="sm" variant={item.track_id === selected ? "primary" : "secondary"} aria-pressed={item.track_id === selected} onClick={() => setSelected(item.track_id)}>
                {item.name}{item.state !== "active" ? ` · ${t(`track.state.${item.state}`)}` : ""}
              </Button>
            </li>
          ))}
        </ul>
      )}
      {detail && (
        <>
          <p className="track-paper" data-track-paper>{t("track.paper")}{snapshot?.simulated ? ` ${t("track.simulated")}` : ""}</p>
          {actionable && advice ? (
            <div className="track-advice" data-track-advice={advice.signal} aria-live="polite">
              <span>{t(`track.advice.${advice.signal}`, { level: fixed(advice.entry_level, 3), bid: fixed(advice.spread_bid, 3), offer: fixed(advice.spread_offer, 3), currency })}</span>
              {advice.edge_net_per_mwh !== null && advice.edge_net_per_mwh !== undefined && (
                <span>{t("track.edge", { edge: fixed(advice.edge_net_per_mwh, 3) })}</span>
              )}
              <span data-track-countdown>
                {t("track.actionable", { seconds: left ?? 0 })} · <Instant value={advice.computed_at ?? advice.at} seconds prefix={t("track.computed")} />
              </span>
            </div>
          ) : snapshot?.withdrawn ? (
            <p className="track-note" data-track-withdrawn>{t("track.withdrawn", { reason: t(`track.withdrawn.${snapshot.withdrawn.reason.replace(" ", "_")}`) })}</p>
          ) : (
            <p className="track-note">{snapshot?.gated?.length ? t("track.gated", { reasons: snapshot.gated.slice(0, 2).join("; ") }) : t("track.no_signal")}</p>
          )}
          <dl className="prompt-figures">
            {detail.mode === "intraday" ? (
              <>
                <div><dt>{t("track.position")}</dt><dd data-figure="paper-position">{snapshot?.position ? t(`track.side.${snapshot.position > 0 ? "long" : "short"}`, { mwh: fixed(snapshot.qty_mwh_per_day, 0), price: fixed(snapshot.entry_price, 3) }) : t("track.flat")}</dd></div>
                <div><dt>{t("track.realised", { currency })}</dt><dd>{fixed(snapshot?.realised, 2)}</dd></div>
                <div><dt>{t("track.unrealised", { currency })}</dt><dd>{fixed(snapshot?.unrealised, 2)}</dd></div>
                <div><dt>{t("track.max_drawdown", { currency })}</dt><dd>{fixed(snapshot?.max_drawdown, 2)}</dd></div>
                <div><dt>{t("track.trades")}</dt><dd>{`${snapshot?.winning_trades ?? 0} / ${snapshot?.closed_trades ?? 0}`}</dd></div>
                <div><dt>{t("track.latency")}</dt><dd>{snapshot?.latency_ms === null || snapshot?.latency_ms === undefined ? "–" : `${Math.round(snapshot.latency_ms)} ms`}</dd></div>
              </>
            ) : (
              <>
                <div><dt>{t("track.signal")}</dt><dd>{t(`track.signal.${snapshot?.signal ?? "flat"}`)}</dd></div>
                <div><dt>{t("track.close")}</dt><dd>{snapshot?.close_date ?? "–"} · {fixed(snapshot?.spread, 3)} {snapshot?.unit ?? ""}</dd></div>
                <div><dt>{t("track.since_start")}</dt><dd>{fixed(snapshot?.paper_pnl_since_start, 0)}</dd></div>
              </>
            )}
          </dl>
          {(detail.blotter?.length ?? 0) > 0 && (
            <div className="prompt-table-wrap" tabIndex={0} role="region" aria-label={t("track.blotter")}>
              <table className="prompt-table" data-track-blotter>
                <caption>{t("track.blotter_caption")}</caption>
                <thead>
                  <tr>
                    <th scope="col">{t("prompt.col.time")}</th>
                    <th scope="col">{t("track.col.action")}</th>
                    <th scope="col" className="num">{t("prompt.col.price")}</th>
                    <th scope="col" className="num">{t("track.col.qty")}</th>
                    <th scope="col" className="num">{t("prompt.col.pnl")}</th>
                    <th scope="col">{t("track.col.note")}</th>
                  </tr>
                </thead>
                <tbody>
                  {(detail.blotter ?? []).slice(-12).reverse().map((entry, index) => (
                    <tr key={`${entry.at}-${index}`}>
                      <td><Instant value={entry.at} seconds /></td>
                      <td>{entry.kind === "no_fill" ? t("track.no_fill") : t(`track.action.${entry.action ?? "open"}.${entry.side ?? "buy"}`)}</td>
                      <td className="num">{fixed(entry.price, 3)}</td>
                      <td className="num">{fixed(entry.qty_mwh_per_day, 0)}</td>
                      <td className="num">{fixed(entry.pnl, 2)}</td>
                      <td>{entry.reason ?? ""}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <p className="track-note" data-track-assumptions>{detail.assumptions}</p>
          {detail.state === "active" && (
            <div className="track-head">
              <Button size="sm" variant="secondary" onClick={() => void stop()}>{t("track.stop")}</Button>
            </div>
          )}
        </>
      )}
    </section>
  );
}
