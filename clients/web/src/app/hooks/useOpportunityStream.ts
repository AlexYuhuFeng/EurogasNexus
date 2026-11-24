/**
 * The Opportunities page kept live (M7). The session's opportunity stream
 * (`/api/stream/opportunities`, opened in stores/api.ts) publishes a notice when an opportunity
 * opens or is withdrawn and when an evaluation finishes; the page re-reads its list on it
 * (coalesced), re-reads every five minutes as a safety net while the stream is open, and polls
 * every minute while it is down. A tab that is not visible reads nothing until it is shown again.
 */
import { useEffect, useRef, useState } from "react";

import { onChangeNotice, onTopicStreamStatus, topicStreamOpen } from "@/app/data/changeNotices";
import {
  OPPORTUNITY_FALLBACK_MS,
  OPPORTUNITY_NOTICE_COALESCE_MS,
  OPPORTUNITY_REFRESH_MS,
  readOpportunityNotice,
  type OpportunityStreamNotice,
} from "@/app/model/opportunitiesModel";

export const OPPORTUNITY_TOPIC = "opportunities";

export function useOpportunityStream(reload: () => void, active = true) {
  const [live, setLive] = useState(() => topicStreamOpen(OPPORTUNITY_TOPIC));
  const [notices, setNotices] = useState<OpportunityStreamNotice[]>([]);
  const reloadRef = useRef(reload);
  reloadRef.current = reload;

  useEffect(() => {
    if (!active) return undefined;
    const recheck = () => {
      if (document.visibilityState === "visible") reloadRef.current();
    };
    let streamOpen = topicStreamOpen(OPPORTUNITY_TOPIC);
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
    const stopNotices = onChangeNotice(OPPORTUNITY_TOPIC, (payload) => {
      const notice = readOpportunityNotice(payload);
      if (!notice) return;
      if (notice.status === "withdrawn") setNotices((current) => [...current.slice(-19), notice]);
      window.clearTimeout(pending);
      pending = window.setTimeout(recheck, OPPORTUNITY_NOTICE_COALESCE_MS);
    });
    const stopStatus = onTopicStreamStatus(OPPORTUNITY_TOPIC, (open) => {
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
