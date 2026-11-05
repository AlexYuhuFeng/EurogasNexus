/**
 * The map's "Our book" list and the replay bar.
 *
 * The list orders the firm's own deals by what needs a decision: in progress, next 7 days,
 * later; completed deals sit under "History", folded, for looking back. Clicking an item
 * selects it on the map; a completed cargo with a timed track can be replayed.
 */
import { useEffect, useRef, useState } from "react";
import { BOOK_PHASES, replayAt, replayTrack, type BookItem, type BookPhase, type ReplayTrack } from "@/app/mapBook";
import type { MapCargoDTO } from "@/api/client";

type Translate = (key: string, options?: Record<string, unknown>) => string;

function shortDate(value: number | null): string {
  if (value === null) return "";
  return new Date(value).toISOString().slice(5, 10).split("-").reverse().join("/");
}

function itemDetail(item: BookItem, t: Translate): string {
  if (item.cargo) {
    const cargo = item.cargo;
    const where = cargo.destination_terminal ?? "";
    const energy = cargo.energy_gwh != null ? ` · ${Math.round(cargo.energy_gwh).toLocaleString()} GWh` : "";
    const when = item.when !== null ? ` · ${item.phase === "completed" ? t("map.book.arrived") : "ETA"} ${shortDate(item.when)}` : "";
    return `${t("map.book.kind.cargo")} → ${where}${energy}${when}`;
  }
  if (item.slot) {
    const slot = item.slot;
    const rate = slot.send_out_gwh_d != null ? ` · ${slot.send_out_gwh_d} GWh/d` : "";
    return `${t("map.book.kind.slot")} ${shortDate(Date.parse(slot.window_start_utc))}–${shortDate(Date.parse(slot.window_end_utc))}${rate}`;
  }
  const contract = item.contract!;
  return `${t("map.book.kind.contract")} · ${contract.delivery_point} · ${Math.round(contract.delivery_mwh_d).toLocaleString()} MWh/d · ${contract.gas_year}`;
}

export function MapBookPanel({
  items,
  t,
  onFocus,
  onReplay,
  replayingId,
}: {
  items: BookItem[];
  t: Translate;
  onFocus: (item: BookItem) => void;
  onReplay: (cargo: MapCargoDTO) => void;
  replayingId: string | null;
}) {
  const [historyOpen, setHistoryOpen] = useState(false);
  const groups = BOOK_PHASES.map((phase) => [phase, items.filter((item) => item.phase === phase)] as const);
  const live = items.filter((item) => item.phase !== "completed").length;
  return (
    <aside className="map-book-panel" aria-label={t("map.book.title")}>
      <header>
        <strong>{t("map.book.title")}</strong>
        <small>{t("map.book.live_count", { count: live })}</small>
      </header>
      {live === 0 && <p className="map-book-empty">{t("map.book.empty")}</p>}
      {groups.map(([phase, members]) => {
        if (members.length === 0) return null;
        const history = phase === "completed";
        return (
          <section key={phase} className={`map-book-group is-${phase}`}>
            {history ? (
              <button type="button" className="map-book-history-toggle" aria-expanded={historyOpen} onClick={() => setHistoryOpen((open) => !open)}>
                {t("map.book.phase.completed")} <span>{members.length}</span>
              </button>
            ) : (
              <h3>{t(`map.book.phase.${phase as Exclude<BookPhase, "completed">}`)} <span>{members.length}</span></h3>
            )}
            {(!history || historyOpen) && (
              <ul>
                {members.map((item) => {
                  const replayable = item.cargo && history ? replayTrack(item.cargo) !== null : false;
                  return (
                    <li key={`${item.kind}-${item.id}`} className={replayingId === item.id ? "is-replaying" : undefined}>
                      <button type="button" className="map-book-item" onClick={() => onFocus(item)} disabled={history && !item.refId && !replayable}>
                        <strong>{item.label}</strong>
                        <small>{itemDetail(item, t)}</small>
                      </button>
                      {replayable && (
                        <button type="button" className="chip map-book-replay" onClick={() => onReplay(item.cargo!)}>
                          {t("map.book.replay")}
                        </button>
                      )}
                    </li>
                  );
                })}
              </ul>
            )}
          </section>
        );
      })}
    </aside>
  );
}

/** Plays a timed track: the whole voyage in about eight seconds, or scrubbed by hand. */
export function useReplay(track: ReplayTrack | null) {
  const [moment, setMomentState] = useState<number | null>(null);
  const [playing, setPlaying] = useState(false);
  const momentRef = useRef<number | null>(null);
  const setMoment = (value: number | null) => {
    momentRef.current = value;
    setMomentState(value);
  };

  useEffect(() => {
    if (!track) {
      setMoment(null);
      setPlaying(false);
      return;
    }
    const reduced = typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    // Under reduced motion the voyage is shown whole; the slider still scrubs it.
    setMoment(reduced ? track.end : track.start);
    setPlaying(!reduced);
  }, [track]);

  useEffect(() => {
    if (!track || !playing) return undefined;
    const span = Math.max(1, track.end - track.start);
    let last = performance.now();
    let frame = 0;
    const tick = (now: number) => {
      const next = Math.min(track.end, (momentRef.current ?? track.start) + ((now - last) / 8000) * span);
      last = now;
      setMoment(next);
      if (next >= track.end) setPlaying(false);
      else frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [playing, track]);

  const frame = track && moment !== null ? replayAt(track, moment) : null;
  return { moment, setMoment, playing, setPlaying, frame };
}

export function MapReplayBar({
  cargo,
  track,
  moment,
  playing,
  onMoment,
  onPlaying,
  onClose,
  t,
}: {
  cargo: MapCargoDTO;
  track: ReplayTrack;
  moment: number;
  playing: boolean;
  onMoment: (value: number) => void;
  onPlaying: (value: boolean) => void;
  onClose: () => void;
  t: Translate;
}) {
  const stamp = new Date(moment).toISOString().slice(0, 16).replace("T", " ");
  const atEnd = moment >= track.end;
  return (
    <div className="map-replay-bar" role="group" aria-label={t("map.replay.label", { vessel: cargo.vessel_name })}>
      <button
        type="button"
        className="chip"
        onClick={() => {
          if (atEnd) onMoment(track.start);
          onPlaying(!playing || atEnd);
        }}
      >
        {playing ? t("map.replay.pause") : atEnd ? t("map.replay.again") : t("map.replay.play")}
      </button>
      <div className="map-replay-track">
        <strong>{cargo.vessel_name}</strong>
        <small>{cargo.load_port} → {cargo.destination_terminal ?? ""} · {stamp} UTC</small>
        <input
          type="range"
          min={track.start}
          max={track.end}
          step={Math.max(1, Math.round((track.end - track.start) / 400))}
          value={moment}
          aria-label={t("map.replay.scrub")}
          onChange={(event) => {
            onPlaying(false);
            onMoment(Number(event.target.value));
          }}
        />
      </div>
      <button type="button" className="chip" onClick={onClose} aria-label={t("map.replay.close")}>
        {t("map.replay.close")}
      </button>
    </div>
  );
}
