import { useEffect, useRef } from "react";
import { api, type FacilityDTO, type MapSituationDTO } from "@/api/client";
import { changeStreamOpen, onChangeNotice, onChangeStreamStatus } from "@/app/data/changeNotices";
import { DEFAULT_FRESH_MS, loadRead, readKey, useCachedRead } from "@/app/data/readCache";

/** How often the map re-checks its situation while on screen and the change stream is open. */
export const MAP_SITUATION_REFRESH_MS = 5 * 60 * 1000;
/** ... and while the change stream is down (a conditional read: 304 when nothing changed). */
export const MAP_SITUATION_FALLBACK_MS = 60 * 1000;
/** A return to the map re-checks a picture older than this. */
export const MAP_SITUATION_RETURN_MS = 30 * 1000;
/** Change notices close together are answered with one read. */
const NOTICE_COALESCE_MS = 1500;

/**
 * The map's situation and located infrastructure, cache-first (app/data/readCache.ts).
 *
 * - The last picture shows at once; a newer one is read behind it (`updating`), and a failed
 *   read keeps the last good picture and reports the error, so the map never blanks.
 * - Located infrastructure is reference data: read once per session.
 * - While the map is on screen (`active` and the browser tab visible) the situation is kept
 *   current by the server's change notices (`map` on the session's alerts stream: outages,
 *   flows, cargoes, slots, opportunities; app/data/changeNotices.ts), each answered with a conditional read that is a 304 when nothing the
 *   caller sees changed; a safety re-check runs every 5 minutes, every minute while the
 *   stream is down. Off screen nothing is read; a return re-checks a picture older than 30 s.
 */
export function useMapSituation(enabled = true, historyDays = 0, active = true) {
  const situationKey = enabled ? readKey("/portfolio/map-situation", { days: 14, history: historyDays }) : null;
  const situationRead = (signal: AbortSignal) =>
    api.mapSituation(14, { signal }, historyDays).then((response) =>
      response.data && "outages" in response.data ? (response.data as MapSituationDTO) : null,
    );
  const situation = useCachedRead<MapSituationDTO | null>(situationKey, situationRead, { freshMs: MAP_SITUATION_RETURN_MS });
  const facilities = useCachedRead<FacilityDTO[]>(
    enabled ? readKey("/reference-network/facilities") : null,
    () => api.facilities().then((response) => (Array.isArray(response.data) ? response.data : [])),
    { freshMs: Number.POSITIVE_INFINITY },
  );
  const readRef = useRef(situationRead);
  readRef.current = situationRead;

  useEffect(() => {
    if (!situationKey || !active) return undefined;
    const recheck = (freshMs = 0) => {
      if (document.visibilityState !== "visible") return;
      void loadRead(situationKey, (signal) => readRef.current(signal), { freshMs, force: freshMs === 0 });
    };
    // A return (to the page or to the browser tab) re-checks a picture that is not recent.
    recheck(MAP_SITUATION_RETURN_MS);
    const onVisible = () => recheck(MAP_SITUATION_RETURN_MS);
    document.addEventListener("visibilitychange", onVisible);
    let streamOpen = changeStreamOpen();
    let timer = 0;
    const schedule = () => {
      window.clearTimeout(timer);
      timer = window.setTimeout(() => {
        recheck();
        schedule();
      }, streamOpen ? MAP_SITUATION_REFRESH_MS : MAP_SITUATION_FALLBACK_MS);
    };
    schedule();
    let pending = 0;
    const stopNotices = onChangeNotice("map", () => {
      window.clearTimeout(pending);
      pending = window.setTimeout(() => recheck(), NOTICE_COALESCE_MS);
    });
    const stopStatus = onChangeStreamStatus((open) => {
      streamOpen = open;
      // Back on the stream after a gap: re-check once, then the long interval.
      if (open) recheck(DEFAULT_FRESH_MS);
      schedule();
    });
    return () => {
      stopNotices();
      stopStatus();
      window.clearTimeout(timer);
      window.clearTimeout(pending);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [active, situationKey]);

  const error = situation.error ? (situation.error instanceof Error ? situation.error.message : String(situation.error)) : null;
  return {
    situation: situation.data ?? null,
    facilities: facilities.data ?? EMPTY_FACILITIES,
    error,
    /** When the picture on screen was last read or confirmed unchanged. */
    readAt: situation.at ? new Date(situation.at) : null,
    /** A newer picture is being read behind the one shown. */
    updating: situation.updating,
  };
}

const EMPTY_FACILITIES: FacilityDTO[] = [];
