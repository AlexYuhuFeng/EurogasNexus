/**
 * The Opportunities page kept live (M7). The tab's live connection (app/data/liveStream.ts, which
 * carries the opportunity engine's events) publishes a notice when an opportunity opens or is
 * withdrawn and when an evaluation finishes; the page re-reads its list on it
 * (coalesced), re-reads every five minutes as a safety net while the stream is open, and polls
 * every minute while it is down. A tab that is not visible reads nothing until it is shown again.
 */
import { useEffect, useRef, useState } from "react";

import { liveIsUp, onLiveStatus, subscribeLiveEvent } from "@/app/data/liveStream";
import {
  OPPORTUNITY_FALLBACK_MS,
  OPPORTUNITY_NOTICE_COALESCE_MS,
  OPPORTUNITY_REFRESH_MS,
  readOpportunityNotice,
  type OpportunityStreamNotice,
} from "@/app/model/opportunitiesModel";

export function useOpportunityStream(reload: () => void, active = true) {
  const [live, setLive] = useState(liveIsUp);
  const [notices, setNotices] = useState<OpportunityStreamNotice[]>([]);
  const reloadRef = useRef(reload);
  reloadRef.current = reload;

  useEffect(() => {
    if (!active) return undefined;
    const recheck = () => {
      if (document.visibilityState === "visible") reloadRef.current();
    };
    let streamOpen = liveIsUp();
    let timer = 0;
    const schedule = () => {
      window.clearTimeout(timer);
      timer = window.setTimeout(() => {
        recheck();
        schedule();
      }, streamOpen ? OPPORTUNITY_REFRESH_MS : OPPORTUNITY_FALLBACK_MS);
    };
    schedule();
    let pending = 0;
    const onNotice = (event: "opportunity" | "evaluated") => (payload: unknown) => {
      const notice = readOpportunityNotice({ event, ...(payload && typeof payload === "object" ? payload : {}) });
      if (!notice) return;
      if (notice.status === "withdrawn") setNotices((current) => [...current.slice(-19), notice]);
      window.clearTimeout(pending);
      pending = window.setTimeout(recheck, OPPORTUNITY_NOTICE_COALESCE_MS);
    };
    const stopOpportunity = subscribeLiveEvent("opportunity", onNotice("opportunity"));
    const stopEvaluated = subscribeLiveEvent("evaluated", onNotice("evaluated"));
    const stopNotices = () => {
      stopOpportunity();
      stopEvaluated();
    };
    const stopStatus = onLiveStatus(() => {
      const open = liveIsUp();
      if (open === streamOpen) return;
      streamOpen = open;
      setLive(open);
      if (open) recheck(); // whatever changed while it was down
      schedule();
    });
    document.addEventListener("visibilitychange", recheck);
    return () => {
      stopNotices();
      stopStatus();
      window.clearTimeout(timer);
      window.clearTimeout(pending);
      document.removeEventListener("visibilitychange", recheck);
    };
  }, [active]);

  return { live, notices, clearNotices: () => setNotices([]) };
}
