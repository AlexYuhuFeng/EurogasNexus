import { useEffect, useState } from "react";
import { api, type FacilityDTO, type MapSituationDTO } from "@/api/client";

/** How often the live map re-reads the situation; sources update daily or intraday. */
export const MAP_SITUATION_REFRESH_MS = 5 * 60 * 1000;

/**
 * The live map's situation and located infrastructure. A failed read keeps the last good
 * picture and reports the error, so the map never blanks on a transient fault.
 */
export function useMapSituation(enabled = true, historyDays = 0) {
  const [situation, setSituation] = useState<MapSituationDTO | null>(null);
  const [facilities, setFacilities] = useState<FacilityDTO[]>([]);
  const [error, setError] = useState<string | null>(null);
  // When the picture on screen was last read: a wall display has to say how fresh it is.
  const [readAt, setReadAt] = useState<Date | null>(null);

  useEffect(() => {
    if (!enabled) return undefined;
    let live = true;
    const load = () => {
      api
        .mapSituation(14, undefined, historyDays)
        .then((response) => {
          if (!live) return;
          setSituation(response.data && "outages" in response.data ? response.data : null);
          setError(null);
          setReadAt(new Date());
        })
        .catch((caught: unknown) => live && setError(caught instanceof Error ? caught.message : String(caught)));
    };
    load();
    api
      .facilities()
      .then((response) => live && setFacilities(Array.isArray(response.data) ? response.data : []))
      .catch(() => undefined);
    const timer = window.setInterval(load, MAP_SITUATION_REFRESH_MS);
    return () => {
      live = false;
      window.clearInterval(timer);
    };
  }, [enabled, historyDays]);

  return { situation, facilities, error, readAt };
}
