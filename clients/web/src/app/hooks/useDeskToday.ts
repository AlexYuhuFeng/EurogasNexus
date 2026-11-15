/**
 * The Today read (`GET /api/desk/today`, UX-05): one request for the whole first screen. The
 * cockpit holds it and hands it to the Today screen and to the context strip (which says "Demo
 * data" once on the demo desk instead of counting stale feeds). State lives with the surface
 * that mounted it, so a change of identity, which remounts the shell, never shows another
 * caller's figures.
 */
import { useCallback, useEffect, useRef, useState } from "react";

import { api, type DeskTodayDTO } from "@/api/client";

export interface DeskTodayRead {
  today: DeskTodayDTO | null;
  loading: boolean;
  error: string | null;
  refresh: () => void;
}

export function useDeskToday(enabled = true): DeskTodayRead {
  const [today, setToday] = useState<DeskTodayDTO | null>(null);
  const [loading, setLoading] = useState(enabled);
  const [error, setError] = useState<string | null>(null);
  const generation = useRef(0);

  const refresh = useCallback(() => {
    const mine = ++generation.current;
    setLoading(true);
    api
      .deskToday()
      .then((response) => {
        if (mine !== generation.current) return;
        setToday(response.data);
        setError(null);
      })
      .catch((caught: unknown) => {
        if (mine !== generation.current) return;
        setError(caught instanceof Error ? caught.message : String(caught));
      })
      .finally(() => {
        if (mine === generation.current) setLoading(false);
      });
  }, []);

  useEffect(() => {
    if (!enabled) return undefined;
    refresh();
    return () => {
      generation.current += 1;
    };
  }, [enabled, refresh]);

  return { today, loading, error, refresh };
}
