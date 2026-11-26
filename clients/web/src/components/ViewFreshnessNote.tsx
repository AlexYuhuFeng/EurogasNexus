import { observeResponseMeta } from "@/api/client";
import { noteViewMeta, useRefreshingSince } from "@/app/data/viewFreshness";
import { useInstantFormatter } from "@/app/time/useInstant";

// Every GET answer reports its meta here; the top bar is always mounted while signed in.
observeResponseMeta(noteViewMeta);

type Translate = (key: string, values?: Record<string, unknown>) => string;

/**
 * "Figures from 09:41, updating": shown while an answer on screen is a kept result the server
 * is recomputing (app/data/viewFreshness.ts). Nothing otherwise.
 */
export function ViewFreshnessNote({ t }: { t: Translate }) {
  const since = useRefreshingSince();
  const format = useInstantFormatter();
  if (!since) return null;
  const time = format(since)?.text ?? since;
  return (
    <span className="view-refreshing-note" role="status" title={t("view.refreshing.detail", { time })} data-view-refreshing={since}>
      {t("view.refreshing", { time })}
    </span>
  );
}
