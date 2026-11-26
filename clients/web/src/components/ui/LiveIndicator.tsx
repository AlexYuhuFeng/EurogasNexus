/**
 * The live connection's state, where a trader looks (the top bar): a quiet "Live" while
 * updates arrive; "Delayed" or "Reconnecting" with the time of the last update when they do
 * not, so a figure that stopped moving is never mistaken for a market that stopped moving
 * (app/data/liveStream.ts). Nothing is shown while no page subscribes to anything live.
 */
import { useLiveStatus } from "@/app/hooks/useLive";
import { Instant } from "./Instant";

type Translate = (key: string, options?: Record<string, unknown>) => string;

export function LiveIndicator({ t }: { t: Translate }) {
  const status = useLiveStatus();
  if (status.state === "idle") return null;
  // What is on screen is current as of the last time the server was heard from.
  const last = status.lastEventAt ?? status.lastChangeAt;
  const degraded = status.state === "stale" || status.state === "offline";
  return (
    <span
      className="ds-live-indicator"
      data-live-state={status.state}
      role="status"
      aria-live={degraded ? "polite" : "off"}
      title={t(`live.title.${status.state}`)}
    >
      <span className="ds-live-dot" aria-hidden="true" />
      <span className="ds-live-label">{t(`live.state.${status.state}`)}</span>
      {degraded && last !== null ? (
        <Instant className="ds-live-time" value={last} seconds date="auto" prefix={t("live.last_update")} />
      ) : null}
    </span>
  );
}
