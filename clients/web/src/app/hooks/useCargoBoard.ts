/**
 * The cargo board's read, kept live (QA-L-05).
 *
 * There is no cargo channel of its own: what reaches the browser is the tab's live connection
 * (app/data/liveStream.ts), whose `cargoes` and `slots` notices fire when a cargo row or a regas
 * slot is written (an ETRM or vessel-feed import, or a `cargo.changed` market event). The board
 * re-reads on those notices, and polls on the read cache's pattern while the stream is down. A hedge recorded here is a write, which
 * marks every kept read stale (app/data/readCache.ts), so the board reads again after it.
 */
import { useEffect, useRef } from "react";

import { api, type CargoPlanBoardLineDTO } from "@/api/client";
import { liveIsUp, onLiveStatus, subscribeLive } from "@/app/data/liveStream";
import { DEFAULT_FRESH_MS, loadRead, readKey, useCachedRead } from "@/app/data/readCache";

export const CARGO_BOARD_KEY = readKey("/lng/cargoes/plans");
/** With the stream open, a safety re-read; with it down, the poll. */
export const CARGO_BOARD_REFRESH_MS = 5 * 60_000;
export const CARGO_BOARD_FALLBACK_MS = 60_000;
const NOTICE_COALESCE_MS = 800;
const CARGO_GROUPS = new Set(["cargoes", "slots"]);
const CARGO_TOPICS = ["cargoes", "slots"] as const;

export function readCargoBoard(signal: AbortSignal): Promise<CargoPlanBoardLineDTO[]> {
  return api.cargoPlans({ signal }).then((response) => response.data ?? []);
}

/** Whether a change notice is about cargoes or slots (a topic and a time, no row). */
export function isCargoNotice(payload: unknown): boolean {
  const item = payload && typeof payload === "object" ? (payload as { topic?: unknown; group?: unknown }) : null;
  const topic = item?.topic ?? item?.group;
  return typeof topic === "string" && CARGO_GROUPS.has(topic);
}

export function useCargoBoard(active = true) {
  const read = useCachedRead(active ? CARGO_BOARD_KEY : null, readCargoBoard);
  const activeRef = useRef(active);
  activeRef.current = active;

  useEffect(() => {
    if (!active) return undefined;
    const recheck = (freshMs = 0) => {
      if (document.visibilityState !== "visible") return;
      void loadRead(CARGO_BOARD_KEY, readCargoBoard, { freshMs, force: freshMs === 0 });
    };
    const onVisible = () => recheck(DEFAULT_FRESH_MS);
    document.addEventListener("visibilitychange", onVisible);
    let streamOpen = liveIsUp();
    let timer = 0;
    const schedule = () => {
      window.clearTimeout(timer);
      timer = window.setTimeout(() => {
        recheck();
        schedule();
      }, streamOpen ? CARGO_BOARD_REFRESH_MS : CARGO_BOARD_FALLBACK_MS);
    };
    schedule();
    let pending = 0;
    const onNotice = (payload: unknown) => {
      if (!isCargoNotice(payload)) return;
      window.clearTimeout(pending);
      pending = window.setTimeout(() => recheck(), NOTICE_COALESCE_MS);
    };
    const stops = CARGO_TOPICS.map((topic) => subscribeLive(topic, onNotice));
    const stopNotices = () => stops.forEach((stop) => stop());
    const stopStatus = onLiveStatus(() => {
      const open = liveIsUp();
      if (open === streamOpen) return;
      streamOpen = open;
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
  }, [active]);

  return {
    lines: read.data ?? null,
    error: read.error,
    loading: read.loading,
    updating: read.updating,
    readAt: read.at ? new Date(read.at) : null,
    live: liveIsUp(),
    refresh: read.refresh,
  };
}
