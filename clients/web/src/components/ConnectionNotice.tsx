/**
 * The calm line under the top bar when the screen is not current (small-desk plan 3.7), and when
 * this computer's clock disagrees with the server's.
 *
 * - The server cannot be reached (or this computer is offline): one line says so, gives the time
 *   of the last known picture, and tells the desk to rely on the trading screen until it clears.
 *   It clears itself on recovery (app/data/connection.ts probes the server). Neutral surface, no
 *   alarm colour: nothing is wrong with the figures, they are only old.
 * - The browser's clock differs from the server's by more than a few seconds: one line says by
 *   how much, since ages on screen and the order of deals and prices depend on it. It can be
 *   dismissed for the session.
 *
 * Nothing here is per page: the root's `data-screen-stale` (set by the shell) mutes every figure,
 * and live values carry their own stale mark (LiveValue, KeyFigure).
 */
import { useState } from "react";

import { clockSkewed, useConnection, useScreenFreshness } from "@/app/data/connection";
import { useInstantFormatter } from "@/app/time/useInstant";
import { IconButton } from "@/components/ui";

type Translate = (key: string, options?: Record<string, unknown>) => string;

export function ConnectionNotice({ t }: { t: Translate }) {
  const freshness = useScreenFreshness();
  const connection = useConnection();
  const format = useInstantFormatter();
  const [clockDismissed, setClockDismissed] = useState(false);
  const lines = [];
  if (!freshness.current && freshness.reason !== "live_quiet") {
    const time = freshness.since !== null ? format(freshness.since, { date: "auto" })?.text ?? null : null;
    const lead = t(freshness.reason === "browser_offline" ? "connection.browser_offline" : "connection.server_unreachable");
    lines.push(
      <div key="reach" className="connection-notice" role="status" aria-live="polite" data-connection-notice={freshness.reason}>
        <p>
          <strong>{lead}</strong>{" "}
          {time ? t("connection.last_known", { time }) : t("connection.last_known_untimed")}{" "}
          {t("connection.rely_on_screen")}
        </p>
      </div>,
    );
  }
  if (!clockDismissed && clockSkewed(connection)) {
    const seconds = Math.round(Math.abs(connection.clockSkewMs ?? 0) / 1000);
    const key = (connection.clockSkewMs ?? 0) > 0 ? "connection.clock_ahead" : "connection.clock_behind";
    lines.push(
      <div key="clock" className="connection-notice" role="status" data-connection-notice="clock">
        <p>{t(key, { seconds })}</p>
        <IconButton label={t("status.notice_dismiss")} icon="close" size="sm" variant="quiet" onClick={() => setClockDismissed(true)} />
      </div>,
    );
  }
  return lines.length ? <>{lines}</> : null;
}
