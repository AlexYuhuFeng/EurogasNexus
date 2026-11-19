/**
 * Fundamentals → Spreads → Cargo: the line that takes the physical picture to the price
 * structure (owner, 2026-11-19). EU storage against its 5-yr mean leads to the Win − Sum spread
 * on the spread board; LNG leads to a cargo priced into the TTF terminals.
 */
import { useEffect, useState } from "react";

import { api } from "@/api/client";
import { cargoSearch, storageStep } from "@/app/model/spreadsBoard";
import { NextSteps, type NextStep } from "./NextSteps";

type Translate = (key: string, options?: Record<string, unknown>) => string;

export function FundamentalsNextSteps({ t }: { t: Translate }) {
  const [diff, setDiff] = useState<number | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    api
      .fundamentalsStorage({ region: "eu" }, { signal: controller.signal })
      .then((response) => setDiff(response.data.region?.vs_average?.diff_pts ?? null))
      .catch(() => undefined);
    return () => controller.abort();
  }, []);
  const search = typeof window === "undefined" ? "" : window.location.search;
  const storage = storageStep(diff);
  const board = (() => {
    const next = new URLSearchParams(search);
    for (const key of ["view", "spec", "describe", "hub"]) next.delete(key);
    next.set("workspace", "research");
    next.set("task", "spreads");
    return `?${next.toString()}#board-time-TTF`;
  })();
  const steps: NextStep[] = [
    {
      id: "spreads",
      lead: storage ? t(`research.next.storage_${storage.tone}`, { pts: storage.pts }) : undefined,
      label: t("research.next.win_sum"),
      href: board,
    },
    { id: "cargo", label: t("research.next.lng_cargo"), href: cargoSearch(search, "TTF") },
  ];
  return <NextSteps label={t("research.next.label")} steps={steps} />;
}
