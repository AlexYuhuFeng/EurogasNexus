import { useEffect, useMemo, useState } from "react";
import { BreakingTicker } from "@/components/BreakingTicker";
import { buildTickerItems, type TickerItem, type TickerOutage } from "@/app/model/tickerItems";
import { api, type MonitoringAlertDTO } from "@/api/client";

const OUTAGE_REFRESH_MS = 120_000;

type Translate = (key: string, options?: Record<string, unknown>) => string;

/**
 * The shell's ticker, fed by the open monitoring alerts and, for commercial users, the
 * outages active now. It reads the full outage list, not the map's, because the map leaves
 * out assets it cannot place and the ticker must not. An administrator without a commercial
 * role is never asked for outages.
 */
export function ShellTicker({
  alerts,
  language,
  commercial,
  t,
  onOpenOutages,
}: {
  alerts: readonly MonitoringAlertDTO[];
  language: string;
  commercial: boolean;
  t: Translate;
  onOpenOutages: () => void;
}) {
  const [outages, setOutages] = useState<TickerOutage[]>([]);
  useEffect(() => {
    if (!commercial) return undefined;
    let live = true;
    const load = () =>
      api
        .outages(14)
        .then((response) => {
          if (live) setOutages(Array.isArray(response.data) ? (response.data as unknown as TickerOutage[]) : []);
        })
        .catch(() => undefined);
    load();
    const timer = window.setInterval(load, OUTAGE_REFRESH_MS);
    return () => {
      live = false;
      window.clearInterval(timer);
    };
  }, [commercial]);
  const items = useMemo(
    () => buildTickerItems(alerts, outages, language, t),
    [alerts, outages, language, t],
  );
  const open = (item: TickerItem) => {
    if (item.kind === "outage") {
      onOpenOutages();
      return;
    }
    // Alerts open in the alert centre, where they are acknowledged and analysed.
    document.querySelector<HTMLButtonElement>(".alert-center .alert-trigger")?.click();
  };
  return <BreakingTicker items={items} t={t} onOpen={open} />;
}
