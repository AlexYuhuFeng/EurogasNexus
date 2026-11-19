/**
 * Research → Fundamentals (CP-17; design basis 2, D.2): "Where is the system against normal,
 * by country, and what moved?" Tabs inside the task: Storage · LNG · Flows · Balance · Gas for
 * power.
 *
 * - Storage: the Today panel (region first, the season chart with its history, the country
 *   table) and then every country's season as small multiples on one scale.
 * - LNG: send-out by country against history (`LngByCountryPanel`).
 * - Flows: Norwegian and UK pipeline landings against history, and the supply shares
 *   (`FlowsPanel`).
 * - Balance and Gas for power: the existing panels, re-homed here from Today.
 */
import { useEffect, useMemo, useState } from "react";

import "./fundamentals.css";

import { api, type StorageEntityDTO } from "@/api/client";
import { headline, sparkOf } from "@/app/model/storageByCountry";
import { GasForPowerPanel } from "@/components/GasForPowerPanel";
import { NweBalancePanel } from "@/components/NweBalancePanel";
import { StorageByCountryPanel } from "@/components/StorageByCountryPanel";
import { Tabs } from "@/components/ui";
import { CountryMultiples } from "./CountryMultiples";
import { FundamentalsNextSteps } from "./FundamentalsNextSteps";
import { FlowsPanel } from "./FlowsPanel";
import { LngByCountryPanel } from "./LngByCountryPanel";

type Translate = (key: string, options?: Record<string, unknown>) => string;
type Tab = "storage" | "lng" | "flows" | "balance" | "power";
const TABS: Tab[] = ["storage", "lng", "flows", "balance", "power"];

function tabFromLocation(): Tab {
  if (typeof window === "undefined") return "storage";
  const value = new URLSearchParams(window.location.search).get("view");
  return TABS.includes(value as Tab) ? (value as Tab) : "storage";
}

/**
 * The balance panel marks simulated rows when its inputs are simulated; the server decides
 * that in the Today read (`fundamentals.balance.latest.simulated`), read here the same way.
 */
function BalanceTab({ t }: { t: Translate }) {
  const [simulated, setSimulated] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    api
      .deskToday({ signal: controller.signal })
      .then((response) => {
        const row = response.data.rows.find((item) => item && "balance" in item) as { balance?: { latest?: { simulated?: boolean } } } | undefined;
        setSimulated(Boolean(row?.balance?.latest?.simulated));
      })
      .catch(() => undefined);
    return () => controller.abort();
  }, []);
  return <NweBalancePanel t={t} simulated={simulated} />;
}

function StorageMultiples({ t }: { t: Translate }) {
  const [countries, setCountries] = useState<StorageEntityDTO[]>([]);
  useEffect(() => {
    const controller = new AbortController();
    api
      .fundamentalsStorage({ region: "eu", season: ["AT", "BE", "BG", "CZ", "DE", "DK", "ES", "FR", "HR", "HU", "IT", "LV", "NL", "PL", "PT", "RO", "SE", "SK"] }, { signal: controller.signal })
      .then((response) => setCountries(response.data.countries))
      .catch(() => undefined);
    return () => controller.abort();
  }, []);
  const words = useMemo(() => (count: number) => t("storage_panel.vs_avg_short", { count }), [t]);
  return (
    <CountryMultiples
      id="storage-multiples"
      title={t("fundamentals.storage_all")}
      entities={countries}
      unit="%"
      headline={(entity) => headline(entity, words, t("storage_panel.per_day"))}
      spark={sparkOf}
      t={t}
    />
  );
}

export function FundamentalsWorkbench({ t, language }: { t: Translate; language: string }) {
  const [tab, setTab] = useState<Tab>(tabFromLocation);
  const choose = (next: Tab) => {
    setTab(next);
    if (typeof window !== "undefined") {
      const url = new URL(window.location.href);
      url.searchParams.set("view", next);
      window.history.replaceState(window.history.state, "", url);
    }
  };
  return (
    <div className="fundamentals-workbench" data-fundamentals={tab}>
      <FundamentalsNextSteps t={t} />
      <Tabs
        idPrefix="fundamentals-tab"
        label={t("fundamentals.tabs")}
        tabs={TABS.map((id) => ({ id, label: t(`fundamentals.tab.${id}`) }))}
        activeId={tab}
        panelId="fundamentals-panel"
        onChange={choose}
      />
      <section id="fundamentals-panel" role="tabpanel" aria-labelledby={`fundamentals-tab-${tab}`} className="workspace-panel fundamentals-panel">
        {tab === "storage" && (
          <>
            <StorageByCountryPanel t={t} language={language} />
            <StorageMultiples t={t} />
          </>
        )}
        {tab === "lng" && <LngByCountryPanel t={t} language={language} />}
        {tab === "flows" && <FlowsPanel t={t} language={language} />}
        {tab === "balance" && <BalanceTab t={t} />}
        {tab === "power" && <GasForPowerPanel t={t} />}
      </section>
    </div>
  );
}
