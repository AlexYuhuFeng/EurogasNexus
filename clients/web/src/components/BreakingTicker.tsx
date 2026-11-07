/**
 * The breaking-news bar under the top menu: the latest alerts and outages scroll past, like
 * a news channel's ticker, so a trader sees what changed without leaving the board.
 *
 * - It is absent when there is nothing to say (an empty bar would be noise).
 * - With anything critical it reads "Breaking" and flashes once when a new critical item
 *   arrives: a badge on the alerts button is too easy to miss in a busy session.
 * - It pauses on hover or keyboard focus and has its own pause button; with "reduce motion"
 *   set in the operating system it does not move at all and can be scrolled instead.
 * - Screen readers hear a new critical item once, not every scroll.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import type { TickerItem } from "@/app/model/tickerItems";

type Translate = (key: string, options?: Record<string, unknown>) => string;

const SECONDS_PER_ITEM = 7;

export function BreakingTicker({
  items,
  t,
  onOpen,
}: {
  items: readonly TickerItem[];
  t: Translate;
  onOpen: (item: TickerItem) => void;
}) {
  const [paused, setPaused] = useState(false);
  const [flash, setFlash] = useState(false);
  const [announce, setAnnounce] = useState("");
  const seenCritical = useRef<Set<string> | null>(null);
  const critical = useMemo(() => items.filter((item) => item.severity === "critical"), [items]);

  useEffect(() => {
    const ids = new Set(critical.map((item) => item.id));
    if (seenCritical.current === null) {
      // The first read is the state the user signed in to, not news.
      seenCritical.current = ids;
      return undefined;
    }
    const fresh = critical.filter((item) => !seenCritical.current?.has(item.id));
    seenCritical.current = ids;
    if (!fresh.length) return undefined;
    setFlash(true);
    setAnnounce(`${t("ticker.breaking")}: ${fresh[0].text}`);
    const timer = window.setTimeout(() => setFlash(false), 6000);
    return () => window.clearTimeout(timer);
  }, [critical, t]);

  if (!items.length) return null;
  const duration = Math.max(20, items.length * SECONDS_PER_ITEM);
  const row = (copy: number) =>
    items.map((item) => (
      <li key={`${copy}-${item.id}`} className={`ticker-item is-${item.severity}`} aria-hidden={copy > 0 || undefined}>
        <button type="button" tabIndex={copy > 0 ? -1 : 0} onClick={() => onOpen(item)}>
          <i aria-hidden="true" />
          {item.text}
        </button>
      </li>
    ));

  return (
    <section
      className={`breaking-ticker${critical.length ? " has-critical" : ""}${flash ? " is-flash" : ""}${paused ? " is-paused" : ""}`}
      aria-label={t("ticker.label")}
      data-shell-region="ticker"
    >
      <strong className="ticker-tag">{t(critical.length ? "ticker.breaking" : "ticker.latest")}</strong>
      <div className="ticker-viewport">
        <ul className="ticker-track" style={{ animationDuration: `${duration}s` }}>
          {row(0)}
          {row(1)}
        </ul>
      </div>
      <button
        type="button"
        className="ticker-pause"
        aria-pressed={paused}
        aria-label={t(paused ? "ticker.resume" : "ticker.pause")}
        title={t(paused ? "ticker.resume" : "ticker.pause")}
        onClick={() => setPaused((value) => !value)}
      >
        {paused ? "▶" : "❚❚"}
      </button>
      <span className="visually-hidden" role="status" aria-live="assertive">{announce}</span>
    </section>
  );
}
