/**
 * The heavy first-screen reads a signed-in user's tabs make, in the order a user tends to open
 * them (see warmUp.ts). Each is the exact read its page sends, so the server's kept answer is
 * the one the page asks for.
 */
import { api } from "@/api/client";
import { DAILY_BALANCE_FIRST } from "@/components/DailyBalancePanel";
import { LANDING_CODES, SHARE_DAYS } from "@/components/research/FlowsPanel";
import { STORAGE_MULTIPLE_CODES } from "@/components/research/FundamentalsWorkbench";
import { LNG_COUNTRY_CODES } from "@/components/research/LngByCountryPanel";
import { focusHubs } from "@/app/model/spreadsBoard";
import type { WarmUpStep } from "@/app/data/warmUp";

export function warmUpSteps(language: string): WarmUpStep[] {
  const market = ["market.read"];
  const book = ["portfolio.read"];
  return [
    // Desk -> Today (the landing page reads it too; a repeat is answered from what was kept).
    { id: "desk.today", permissions: market, read: (signal) => api.deskToday({ signal }) },
    { id: "today.forward", permissions: market, read: (signal) => api.fundamentalsForwardBalance({ summary: true }, { signal }) },
    // Desk -> Prices, Research -> Spreads.
    { id: "market.instruments", permissions: market, read: (signal) => api.marketInstruments({ signal }) },
    // Book -> Position and Limits; Deals -> Contracts.
    { id: "book.ladder", permissions: book, read: (signal) => api.positionLadder(12, { signal }, { groupBy: "hub" }) },
    { id: "book.credit", permissions: book, read: (signal) => api.creditExposure({ signal }) },
    { id: "book.mandates", permissions: book, read: (signal) => api.mandateUsage({ signal }) },
    { id: "book.hedges", permissions: book, read: (signal) => api.hedgeApprovals({ signal }) },
    // Book -> Delivery.
    { id: "book.daily", permissions: book, read: (signal) => api.dailyBalance({ ...DAILY_BALANCE_FIRST }, { signal }) },
    // Research -> Spreads: the board for the user's focus hubs, as the page asks for it.
    {
      id: "research.spreads",
      permissions: market,
      read: async (signal) => {
        const hubs = await api.myPreferences({ signal }).then((response) => focusHubs(response.data?.effective?.strip_focus_hubs), () => [] as string[]);
        return api.spreadsBoard(hubs, { signal });
      },
    },
    // Research -> Fundamentals.
    { id: "research.balance", permissions: market, read: (signal) => api.fundamentalsForwardBalance({}, { signal }) },
    { id: "research.flows", permissions: market, read: (signal) => api.fundamentalsFlows(LANDING_CODES, { signal }) },
    { id: "research.storage", permissions: market, read: (signal) => api.fundamentalsStorage({ region: "eu", season: STORAGE_MULTIPLE_CODES }, { signal }) },
    { id: "research.storage.eu", permissions: market, read: (signal) => api.fundamentalsStorage({ region: "eu" }, { signal }) },
    { id: "research.lng", permissions: market, read: (signal) => api.fundamentalsLng(LNG_COUNTRY_CODES, { signal }) },
    { id: "research.nwe", permissions: market, read: (signal) => api.nweBalance(14, { signal }) },
    { id: "research.nwe.share", permissions: market, read: (signal) => api.nweBalanceHistory(SHARE_DAYS, { signal }) },
    { id: "research.power", permissions: market, read: (signal) => api.gasForPower("DE_LU", 14, { signal }) },
    // Research -> Reports: the catalogue probes every section, the heaviest read of all.
    { id: "research.reports", permissions: market, read: (signal) => api.reportCatalogue(language.startsWith("zh") ? "zh-CN" : "en", { signal }) },
  ];
}
