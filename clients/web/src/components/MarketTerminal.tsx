import { useEffect, useMemo, useState } from "react";
import "@/styles/prices.css";
import { api } from "@/api/client";
import { catalogueFromDTO, type PickerCatalogue } from "@/app/model/instrumentPicker";
import { inQuoteUnit, quoteUnit } from "@/app/model/priceCharts";
import {
  BOARD_DEFAULT_HUBS,
  boardReportingRequest,
  readBoardHubs,
  reportingByHub,
  withHub,
  withoutHub,
  writeBoardHubs,
  type ReportingValue,
} from "@/app/model/priceBoard";
import { displayTime } from "@/app/time/displayTime";
import { formatSigned, Sparkline } from "@/components/ui/charts";
import { SimulatedScope, simulatedScopeOf } from "@/components/SimulatedScope";
import {
  PREFERENCES_APPLIED_EVENT,
  readBoardLayout,
  writeLocalBoardLayout,
} from "@/app/preferences/remotePreferences";
import { boardTenorFromSearch, boardTenorToSearch, openingBoardTenor } from "@/app/model/marketCockpitModel";
import {
  createHubSpreadResolver,
  type ResolvedHubSpread,
} from "@/app/marketSpread";
import type {
  FxRateDTO,
  MarketQuoteDTO,
  MarketSpreadDTO,
  NormalizedMarketObsDTO,
  SourceSystemDTO,
} from "@/api/client";
import { MarketLadder } from "@/components/MarketLadder";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { Button, DataGrid, InstrumentPicker, Segmented, Toolbar, type DataGridColumn } from "@/components/ui";
import { sumRecordCounts } from "@/app/workspaceDerivedData";
import { ReferenceIndexEvidence } from "@/components/ReferenceIndexEvidence";

type Translate = (key: string, options?: Record<string, unknown>) => string;

interface MarketTerminalProps {
  markets: NormalizedMarketObsDTO[];
  marketSpreads: MarketSpreadDTO[];
  marketQuotes: MarketQuoteDTO[];
  fxRates: FxRateDTO[];
  sources: SourceSystemDTO[];
  lastUpdatedAtUtc: string | null;
  focusedHub: string | null;
  onHubChange: (hubId: string | null) => void;
  /** Hand a priced hub's observation (quote or normalised observation id) to the inspector. */
  onInspect?: (recordId: string, label: string) => void;
  onRefresh: () => Promise<void>;
  t: Translate;
}

interface HubDefinition {
  hub: string;
  region: string;
  label: string;
}

interface HubTerminalRow extends HubDefinition {
  latest: NormalizedMarketObsDTO | null;
  history: NormalizedMarketObsDTO[];
  spreadToTtf: ResolvedHubSpread | null;
  tenor: string;
  sourceLabel: string;
  simulated: boolean;
}

/** One row of the hub board: a hub at the active tenor, with what the board shows of it. */
interface BoardRow {
  hub: string;
  /** The bid/offer as printed, in the hub's quotation (NBP in p/th). */
  bidAskText: string;
  tenor: string;
  quote: MarketQuoteDTO | null;
  latest: NormalizedMarketObsDTO | null;
  priced: boolean;
  pricedSlice: "quotes" | "normalized_quotes" | null;
  recordId: string | null;
  unit: string | null;
  mid: number | null;
  delta: number | null;
  premium: number | null;
  simulated: boolean;
  sourceLabel: string;
  ageSeconds: number | null;
  lane: (number | null)[];
}

function activeTenorOf(rows: readonly BoardRow[], hub: string): string {
  return rows.find((row) => row.hub === hub)?.tenor ?? "";
}

interface SourceMatrixRow {
  sourceSystem: string;
  latestObservedAtUtc: string | null;
  hubs: string[];
  priceTiming: string;
  updateIntervalSeconds: number | null;
  simulated: boolean;
}

const MAJOR_HUBS: HubDefinition[] = [
  { hub: "TTF", region: "Netherlands", label: "TTF" },
  { hub: "NBP", region: "Great Britain", label: "NBP" },
  { hub: "THE", region: "Germany", label: "THE" },
  { hub: "PEG", region: "France", label: "PEG" },
  { hub: "ZTP", region: "Belgium", label: "ZTP" },
  { hub: "PSV", region: "Italy", label: "PSV" },
];

const marketTenorOrder = ["within-day", "day-ahead", "weekend", "month-ahead"];
const simulatedPriceSourceSystems = ["EEX_Sim", "ICE_OCM_Sim", "Trayport_Sim", "ICIS_Sim"];
const marketSourceOrder = [
  "ICE_OCM_Sim",
  "EEX_Sim",
  "Trayport_Sim",
  "ICIS_Sim",
  "ICE_OCM",
  "EEX",
  "TRAYPORT",
  "ICIS",
];

const gasPriceSources = new Set([
  "EEX",
  "ICE_OCM",
  "TRAYPORT",
  "PLATTS",
  "ICIS",
  "ARGUS",
  "KPLER",
  ...simulatedPriceSourceSystems.map((source) => source.toUpperCase()),
]);

const compareObservedDesc = (
  left: { observed_at_utc: string },
  right: { observed_at_utc: string },
): number => Date.parse(right.observed_at_utc) - Date.parse(left.observed_at_utc);

const isLaterTimestamp = (candidate: string, current: string | null | undefined): boolean => (
  !current || Date.parse(candidate) > Date.parse(current)
);

/** "GBp/th" as the desk writes it. */
const deskUnit = (unit: string): string => unit.replace(/^GBp\/th$/, "p/th");

/**
 * A price in the hub's own quotation (G1, native first): NBP's stored GBP/MWh is printed in
 * pence per therm with the authority's factor; a price already in the quotation, or one that
 * cannot be put in it without FX, keeps its stored unit.
 */
const inNative = (hub: string, value: number | null | undefined, currency: string, unit: string): { value: number | null; unit: string } => {
  const stored = displayPriceUnit(currency, unit);
  if (value == null || !Number.isFinite(value)) return { value: null, unit: stored };
  const converted = inQuoteUnit(hub, value, stored);
  return converted === null ? { value, unit: stored } : { value: converted, unit: deskUnit(quoteUnit(hub)) };
};

/**
 * The unit string a price is displayed with.
 *
 * The payload owns the currency and the unit; the client only decides how to print them together: a
 * unit that already names its currency (`EUR/MWh`) is printed as it is, and a bare quantity is
 * qualified with the payload's currency (`EUR/MWh`). Both the price text and the hub cards' unit
 * declaration come from this one rule, so the browser sweep can hold what a card displays to the
 * currency and unit of the row it priced.
 */
const displayPriceUnit = (currency: string, unit: string): string => {
  const currencyCode = String(currency ?? "");
  const unitName = String(unit ?? "");
  return unitName.toUpperCase().includes(currencyCode.toUpperCase())
    ? unitName
    : `${currencyCode}/${unitName}`;
};

const formatPrice = (row: NormalizedMarketObsDTO | null): string => {
  if (!row) return "n/a";
  return `${row.price.toFixed(2)} ${displayPriceUnit(row.currency, row.unit)}`;
};

const formatSpread = (value: number | null, unit?: string): string => {
  if (value == null) return "n/a";
  const prefix = value > 0 ? "+" : "";
  return `${prefix}${value.toFixed(2)} ${unit ?? "MWh"}`;
};

const getObservedTime = (row: NormalizedMarketObsDTO): string =>
  row.observed_at_utc ?? row.period_end_utc ?? row.period_start_utc;

const metadataValue = (row: NormalizedMarketObsDTO, key: string): string | null => {
  const value = row.metadata_json?.[key];
  return typeof value === "string" && value.trim() ? value.trim() : null;
};

const metadataNumber = (row: NormalizedMarketObsDTO, key: string): number | null => {
  const value = row.metadata_json?.[key];
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && Number.isFinite(Number(value))) return Number(value);
  return null;
};

const tenorLabel = (tenor: string, t: Translate): string => {
  if (tenor === "within-day") return t("market.tenor_within_day");
  if (tenor === "weekend") return t("market.tenor_weekend");
  if (tenor === "month-ahead") return t("market.tenor_month_ahead");
  return t("market.tenor_day_ahead");
};

const formatTimestamp = (value: string | null | undefined): string =>
  displayTime(value);

const formatCadence = (seconds: number | null): string => {
  if (seconds == null) return "n/a";
  if (seconds < 60) return `${seconds.toFixed(0)}s`;
  if (seconds < 3600) return `${Math.round(seconds / 60)}m`;
  return `${Math.round(seconds / 3600)}h`;
};

const sourceLabel = (row: NormalizedMarketObsDTO | null): string => {
  if (!row) return "n/a";
  return row.source_system ?? row.market_venue;
};

const sourceSystemRank = (sourceSystem: string): number => {
  const index = marketSourceOrder.indexOf(sourceSystem);
  return index === -1 ? marketSourceOrder.length : index;
};

const isSimulatedSource = (row: NormalizedMarketObsDTO | null): boolean => {
  if (!row) return false;
  return row.source_system?.toLowerCase().includes("_sim") === true || row.metadata_json?.simulated === true;
};

const sortNewestFirst = (left: NormalizedMarketObsDTO, right: NormalizedMarketObsDTO): number =>
  Date.parse(getObservedTime(right)) - Date.parse(getObservedTime(left));

/**
 * A hub's recent prices beside its quote: the shared sparkline (date and price on hover, focus
 * or touch; the full chart below on click). Prices keep their native unit.
 */
function MarketSparkline({
  points,
  label,
  unit,
  simulated,
  t,
}: {
  points: { at: string; value: number }[];
  label: string;
  unit: string;
  simulated: boolean;
  t: (key: string, options?: Record<string, unknown>) => string;
}) {
  if (points.length < 2) {
    // `role="img"` keeps the label permitted on a non-interactive element (axe: aria-prohibited-attr).
    return <div className="market-sparkline empty" role="img" aria-label={label} />;
  }
  // F.3 #3: the last value's change is in the sparkline's name (and its hover title).
  const change = points[points.length - 1].value - points[points.length - 2].value;
  const named = t("market.spark_change", { label, change: formatSigned(change, 3), unit });
  return (
    <Sparkline
      axis="time"
      values={points.map((point) => point.value)}
      days={points.map((point) => point.at)}
      label={named}
      unit={unit}
      decimals={3}
      simulated={simulated}
      t={t}
      onOpen={() => {
        const charts = document.querySelector<HTMLElement>("[data-price-charts]");
        if (!charts) return;
        charts.scrollIntoView({ block: "start", behavior: "smooth" });
        if (!charts.hasAttribute("tabindex")) charts.setAttribute("tabindex", "-1");
        charts.focus({ preventScroll: true });
      }}
    />
  );
}

const quoteMid = (quote: MarketQuoteDTO | null | undefined): number | null => {
  if (!quote) return null;
  if (quote.last_price != null && Number.isFinite(quote.last_price)) return quote.last_price;
  if (
    quote.bid_price != null && Number.isFinite(quote.bid_price) &&
    quote.ask_price != null && Number.isFinite(quote.ask_price)
  ) {
    return (quote.bid_price + quote.ask_price) / 2;
  }
  if (quote.bid_price != null && Number.isFinite(quote.bid_price)) return quote.bid_price;
  if (quote.ask_price != null && Number.isFinite(quote.ask_price)) return quote.ask_price;
  return null;
};

const quoteIdentityKey = (quote: MarketQuoteDTO): string => [
  quote.source_system,
  quote.venue,
  quote.instrument_id,
  quote.hub.toUpperCase(),
  quote.product.toLowerCase(),
  quote.currency,
  quote.unit,
].join(":");

const quoteAgeSeconds = (quote: MarketQuoteDTO | null | undefined): number | null => {
  if (!quote) return null;
  const observedAtMs = new Date(quote.observed_at_utc).getTime();
  if (!Number.isFinite(observedAtMs)) return null;
  return Math.max((Date.now() - observedAtMs) / 1_000, 0);
};

const formatAge = (seconds: number | null): string => {
  if (seconds == null) return "n/a";
  if (seconds < 60) return `${Math.round(seconds)}s`;
  if (seconds < 3_600) return `${Math.round(seconds / 60)}m`;
  if (seconds < 86_400) return `${Math.round(seconds / 3_600)}h`;
  return `${Math.round(seconds / 86_400)}d`;
};

const quoteHistoryPoints = (quotes: MarketQuoteDTO[]): { at: string; value: number }[] => quotes
  .slice()
  .sort((left, right) => Date.parse(left.observed_at_utc) - Date.parse(right.observed_at_utc))
  .map((quote) => ({ at: quote.observed_at_utc, value: quoteMid(quote) }))
  .filter((point): point is { at: string; value: number } => point.value !== null)
  .slice(-40);

const observationHistoryPoints = (rows: NormalizedMarketObsDTO[]): { at: string; value: number }[] => rows
  .slice()
  .sort((left, right) => Date.parse(getObservedTime(left)) - Date.parse(getObservedTime(right)))
  .map((row) => ({ at: getObservedTime(row), value: row.price }))
  .filter((point) => Number.isFinite(point.value))
  .slice(-40);

const quoteHistoryValues = (quotes: MarketQuoteDTO[]): number[] => quotes
  .slice()
  .sort((left, right) => Date.parse(left.observed_at_utc) - Date.parse(right.observed_at_utc))
  .map(quoteMid)
  .filter((price): price is number => price !== null)
  .slice(-40);

const quoteDelta = (quotes: MarketQuoteDTO[]): number | null => {
  const values = quoteHistoryValues(quotes);
  if (values.length < 2) return null;
  return values[values.length - 1] - values[values.length - 2];
};

const formatDelta = (value: number | null): string => {
  if (value == null) return "n/a";
  return `${value > 0 ? "+" : ""}${value.toFixed(3)}`;
};

type BoardView = "board" | "ladder";
function readBoardView(): BoardView {
  return readBoardLayout();
}

export function MarketTerminal({
  markets,
  marketSpreads,
  marketQuotes,
  fxRates,
  sources,
  lastUpdatedAtUtc,
  focusedHub,
  onHubChange,
  onInspect,
  onRefresh,
  t,
}: MarketTerminalProps) {
  // The hubs on the board: the six majors unless this browser chose others with the picker.
  const [boardHubCodes, setBoardHubCodes] = useState<string[]>(() => readBoardHubs());
  const marketMajorHubs = useMemo<HubDefinition[]>(
    () => boardHubCodes.map((code) => MAJOR_HUBS.find((item) => item.hub === code) ?? { hub: code, region: "", label: code }),
    [boardHubCodes],
  );
  const changeBoardHubs = (codes: string[]) => {
    setBoardHubCodes(codes);
    writeBoardHubs(codes);
  };
  const [catalogue, setCatalogue] = useState<PickerCatalogue | null>(null);
  useEffect(() => {
    let live = true;
    api.marketInstruments().then((response) => { if (live) setCatalogue(catalogueFromDTO(response.data)); }).catch(() => undefined);
    return () => { live = false; };
  }, []);
  // The tenor is in the URL once the user chooses one (a link or a refresh keeps it); until then
  // the board opens on the first tenor this desk has prices for.
  const [chosenTenor, setChosenTenor] = useState<string | null>(() =>
    typeof window === "undefined" ? null : boardTenorFromSearch(window.location.search),
  );
  useEffect(() => {
    const onPop = () => setChosenTenor(boardTenorFromSearch(window.location.search));
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);
  const pricedTenors = useMemo(() => {
    const majors = new Set(marketMajorHubs.map((definition) => definition.hub));
    const priced = new Set<string>();
    for (const row of markets) if (row.is_gas_price && row.hub && majors.has(row.hub)) priced.add(row.tenor);
    for (const quote of marketQuotes) if (majors.has(quote.hub.toUpperCase())) priced.add(quote.product.toLowerCase());
    return priced;
  }, [markets, marketQuotes, marketMajorHubs]);
  const activeTenor = openingBoardTenor(chosenTenor, pricedTenors);
  const setActiveTenor = (tenor: string) => {
    setChosenTenor(tenor);
    const url = new URL(window.location.href);
    url.search = boardTenorToSearch(url.search, tenor);
    window.history.replaceState(window.history.state, "", url);
  };
  const [boardView, setBoardView] = useState<BoardView>(readBoardView);
  const chooseBoardView = (view: BoardView) => {
    setBoardView(view);
    writeLocalBoardLayout(view);
  };
  // The server copy of the preference can arrive after the board mounted.
  useEffect(() => {
    const onApplied = () => setBoardView(readBoardView());
    window.addEventListener(PREFERENCES_APPLIED_EVENT, onApplied);
    return () => window.removeEventListener(PREFERENCES_APPLIED_EVENT, onApplied);
  }, []);

  const quoteHistoryByIdentity = useMemo(() => {
    const result = new Map<string, MarketQuoteDTO[]>();
    marketQuotes.forEach((quote) => {
      const key = quoteIdentityKey(quote);
      result.set(key, [...(result.get(key) ?? []), quote]);
    });
    result.forEach((quotes) => quotes.sort(compareObservedDesc));
    return result;
  }, [marketQuotes]);

  const quoteHistoryByHubTenor = useMemo(() => {
    const result = new Map<string, MarketQuoteDTO[]>();
    marketQuotes.forEach((quote) => {
      const key = `${quote.hub.toUpperCase()}:${quote.product.toLowerCase()}`;
      result.set(key, [...(result.get(key) ?? []), quote]);
    });
    result.forEach((quotes) => quotes.sort(compareObservedDesc));
    return result;
  }, [marketQuotes]);

  const latestQuoteByHubTenor = useMemo(() => new Map(
    Array.from(quoteHistoryByHubTenor.entries()).map(([key, quotes]) => [key, quotes[0]]),
  ), [quoteHistoryByHubTenor]);

  const sourceQuoteRows = useMemo(() => Array.from(quoteHistoryByIdentity.entries())
    .filter(([, quotes]) => quotes[0]?.product.toLowerCase() === activeTenor)
    .map(([key, history]) => ({ key, history, latest: history[0] }))
    .filter((row): row is { key: string; history: MarketQuoteDTO[]; latest: MarketQuoteDTO } => (
      Boolean(row.latest)
    ))
    .sort((left, right) => {
      const leftHubRank = marketMajorHubs.findIndex((hub) => hub.hub === left.latest.hub);
      const rightHubRank = marketMajorHubs.findIndex((hub) => hub.hub === right.latest.hub);
      const hubDelta = (leftHubRank < 0 ? marketMajorHubs.length : leftHubRank)
        - (rightHubRank < 0 ? marketMajorHubs.length : rightHubRank);
      if (hubDelta !== 0) return hubDelta;
      const sourceDelta = sourceSystemRank(left.latest.source_system)
        - sourceSystemRank(right.latest.source_system);
      if (sourceDelta !== 0) return sourceDelta;
      return compareObservedDesc(left.latest, right.latest);
    }), [activeTenor, quoteHistoryByIdentity, marketMajorHubs]);

  // One resolver for the whole response. It ranks a directly-quoted direction above a
  // value derived by negating the opposite one and breaks ties by a published venue
  // order, so the figure no longer depends on which row the API returned last. The
  // previous implementation keyed on hub pair and period only, so the seeded day-ahead
  // TTF/NBP pair — quoted six times, once per venue — collapsed to the final row and its
  // sign followed that row's direction.
  const resolveHubSpread = useMemo(
    () => createHubSpreadResolver(marketSpreads),
    [marketSpreads],
  );

  /**
   * The hub's premium over TTF: `price(hub) - price(TTF)`.
   *
   * Distinct from the directional `hub -> TTF` spread, which is the same magnitude with
   * the opposite sign. The strip below is labelled "spread to TTF", so it needs this
   * one; using the directional value made a dearer-than-TTF hub read as negative.
   */
  const premiumOverTtfFor = (hub: string, tenor: string): ResolvedHubSpread | null => {
    if (hub.toUpperCase() === "TTF") return null;
    return resolveHubSpread(hub, "TTF", tenor);
  };

  const groupedByTenor = useMemo(() => {
    const grouped = new Map<string, NormalizedMarketObsDTO[]>();
    markets
      .filter((row) => row.is_gas_price && Boolean(row.hub))
      .forEach((row) => {
        const key = `${row.hub}:${row.tenor}`;
        grouped.set(key, [...(grouped.get(key) ?? []), row]);
      });
    return grouped;
  }, [markets]);

  const spreadToTtfFor = (hub: string, tenor: string): ResolvedHubSpread | null =>
    premiumOverTtfFor(hub, tenor);

  const marketRowsByTenor = useMemo(() => {
    const result = new Map<string, HubTerminalRow[]>();
    marketTenorOrder.forEach((tenor) => {
      result.set(tenor, marketMajorHubs.map((definition): HubTerminalRow => {
        const history = (groupedByTenor.get(`${definition.hub}:${tenor}`) ?? []).slice().sort(sortNewestFirst);
        const latest = history[0] ?? null;
        return {
          ...definition,
          latest,
          history,
          spreadToTtf: spreadToTtfFor(definition.hub, tenor),
          tenor,
          sourceLabel: sourceLabel(latest),
          simulated: isSimulatedSource(latest),
        };
      }));
    });
    return result;
  }, [groupedByTenor, resolveHubSpread, marketMajorHubs]);

  const marketRows = marketRowsByTenor.get(activeTenor) ?? [];
  const curveLanes = marketMajorHubs.map((definition) => {
    const tenorRows = marketTenorOrder.map((tenor) => marketRowsByTenor.get(tenor)?.find((row) => row.hub === definition.hub));
    return {
      ...definition,
      tenorRows,
    };
  });

  const allTenorRows = Array.from(marketRowsByTenor.values()).flat();
  const terminalRows = marketRows.length > 0 ? marketRows : allTenorRows;
  const priceRowsForStrip = terminalRows.length > 0
    ? terminalRows
    : marketMajorHubs.map((definition): HubTerminalRow => ({
        ...definition,
        latest: null,
        history: [],
        spreadToTtf: null,
        tenor: "day-ahead",
        sourceLabel: "n/a",
        simulated: false,
      }));

  const sourceMatrixRows = useMemo<SourceMatrixRow[]>(() => {
    const grouped = new Map<string, SourceMatrixRow>();
    markets
      .filter((row) => row.is_gas_price && Boolean(row.hub))
      .forEach((row) => {
        if (row.tenor !== activeTenor) return;
        const sourceSystem = row.source_system ?? row.market_venue;
        const current = grouped.get(sourceSystem);
        const observedAt = getObservedTime(row);
        const isNewer = isLaterTimestamp(observedAt, current?.latestObservedAtUtc);
        grouped.set(sourceSystem, {
          sourceSystem,
          latestObservedAtUtc: isNewer ? observedAt : current?.latestObservedAtUtc ?? observedAt,
          hubs: Array.from(new Set([...(current?.hubs ?? []), row.hub])).sort(),
          priceTiming: isNewer
            ? metadataValue(row, "price_timing") ?? row.tenor
            : current?.priceTiming ?? row.tenor,
          updateIntervalSeconds: isNewer
            ? metadataNumber(row, "update_interval_seconds")
            : current?.updateIntervalSeconds ?? null,
          simulated: (current?.simulated ?? false) || isSimulatedSource(row),
        });
      });
    marketQuotes.forEach((quote) => {
      if (quote.product.toLowerCase() !== activeTenor) return;
      const sourceSystem = quote.source_system || quote.venue;
      const current = grouped.get(sourceSystem);
      const isNewer = isLaterTimestamp(quote.observed_at_utc, current?.latestObservedAtUtc);
      grouped.set(sourceSystem, {
        sourceSystem,
        latestObservedAtUtc: isNewer
          ? quote.observed_at_utc
          : current?.latestObservedAtUtc ?? quote.observed_at_utc,
        hubs: Array.from(new Set([...(current?.hubs ?? []), quote.hub])).sort(),
        priceTiming: isNewer
          ? String(quote.metadata_json?.price_level ?? "L1 bid/ask")
          : current?.priceTiming ?? "L1 bid/ask",
        updateIntervalSeconds: isNewer
          ? Number(quote.metadata_json?.update_interval_seconds ?? 0) || null
          : current?.updateIntervalSeconds ?? null,
        simulated: (current?.simulated ?? false) || quote.simulated,
      });
    });
    return Array.from(grouped.values())
      .sort((left, right) => {
        const rankDelta = sourceSystemRank(left.sourceSystem) - sourceSystemRank(right.sourceSystem);
        if (rankDelta !== 0) return rankDelta;
        return left.sourceSystem.localeCompare(right.sourceSystem);
      });
  }, [activeTenor, marketQuotes, markets]);

  const priceSourceSummary = useMemo(() => {
    const priceSources = sources.filter((source) => source.category === "price");
    return {
      registered: priceSources.length,
      active: priceSources.filter((source) => source.connectivity_status === "active").length,
      missingCredentials: priceSources.filter((source) => source.credential_state === "missing").length,
      runtimeRecords: sumRecordCounts(priceSources.map((source) => source.live_record_count)),
      feeds: priceSources.filter((source) => gasPriceSources.has(source.source_system.toUpperCase())),
    };
  }, [sources]);

  const marketUnavailableRows = priceRowsForStrip.filter((row) => (
    row.latest === null && !latestQuoteByHubTenor.has(`${row.hub}:${row.tenor}`)
  ));
  const activeFeedLabels = priceSourceSummary.feeds
    .filter((source) => source.connectivity_status === "active")
    .map((source) => source.source_system);
  const displayFeeds = activeFeedLabels.length > 0
    ? activeFeedLabels.join(" / ")
    : priceSourceSummary.feeds.slice(0, 4).map((source) => source.source_system).join(" / ");

  /** The hub's premium over TTF for one tenor: live mid-to-mid, else the persisted spread. */
  const premiumOverTtf = (hub: string, tenor: string, row: HubTerminalRow | undefined) => {
    const quote = latestQuoteByHubTenor.get(`${hub}:${tenor}`);
    if (hub === "TTF") {
      // TTF over itself is zero only when there is a TTF price to be zero against; with no
      // quote and no mark it is not computable, not 0.00 (#29).
      const ttfPrice = quoteMid(quote) ?? row?.latest?.price ?? null;
      if (ttfPrice === null || !Number.isFinite(ttfPrice)) return { value: null, unit: undefined };
      return { value: 0, unit: quote ? `${quote.currency}/${quote.unit}` : row?.latest?.unit };
    }
    const ttfQuote = latestQuoteByHubTenor.get(`TTF:${tenor}`);
    // A spread is only a difference of like with like: an NBP row in GBP next to TTF in EUR
    // is not subtracted (the backend spread, which converts with a declared FX, is used instead).
    const sameUnit = Boolean(quote && ttfQuote && quote.currency === ttfQuote.currency && quote.unit === ttfQuote.unit);
    const liveMid = sameUnit ? quoteMid(quote) : null;
    const ttfMid = sameUnit ? quoteMid(ttfQuote) : null;
    const value = liveMid !== null && ttfMid !== null
      ? liveMid - ttfMid
      : row?.spreadToTtf?.value_eur_mwh ?? null;
    return { value, unit: quote ? `${quote.currency}/${quote.unit}` : row?.latest?.unit };
  };

  const activeQuoteCount = sourceQuoteRows.length;
  // A simulated price must never be read as a market price: when any priced row on the board
  // is simulated, the board says so above the numbers, not only in a per-row pill.
  // The WD/DA/WE/MA columns show every tenor's mid, so every tenor's row counts, not only
  // the active tenor's: a simulated month-ahead mark next to an empty day-ahead is still a
  // simulated price on the board.
  const simulatedOnBoard = [...priceRowsForStrip, ...allTenorRows].some((row) => {
    const quote = latestQuoteByHubTenor.get(`${row.hub}:${row.tenor}`);
    return (quote ? quote.simulated : false) || row.simulated;
  });

  // One row per major hub for the active tenor, computed once per read, then the board's columns.
  const boardRows: BoardRow[] = priceRowsForStrip.map((row) => {
    const quote = latestQuoteByHubTenor.get(`${row.hub}:${row.tenor}`);
    const history = quoteHistoryByHubTenor.get(`${row.hub}:${row.tenor}`) ?? [];
    const priced = quote ?? row.latest;
    const lane = curveLanes.find((item) => item.hub === row.hub);
    const currency = priced?.currency ?? "";
    const unit = priced?.unit ?? "";
    const native = (value: number | null | undefined) => inNative(row.hub, value, currency, unit);
    const bid = quote ? native(quote.bid_price) : null;
    const ask = quote ? native(quote.ask_price) : null;
    const last = row.latest ? inNative(row.hub, row.latest.price, row.latest.currency, row.latest.unit) : null;
    const nativeUnit = (bid ?? last)?.unit ?? (priced ? displayPriceUnit(currency, unit) : null);
    return {
      hub: row.hub,
      bidAskText: quote
        ? `${formatPriceValue(bid?.value)} / ${formatPriceValue(ask?.value)}`
        : last
          ? (last.value === null ? "n/a" : last.value.toFixed(2))
          : "–",
      tenor: row.tenor,
      quote: quote ?? null,
      latest: row.latest,
      priced: Boolean(priced),
      pricedSlice: quote ? "quotes" : row.latest ? "normalized_quotes" : null,
      recordId: quote?.quote_id ?? row.latest?.observation_id ?? null,
      unit: nativeUnit,
      mid: native(quoteMid(quote) ?? row.latest?.price ?? null).value,
      delta: quoteDelta(history),
      premium: premiumOverTtf(row.hub, row.tenor, row).value,
      simulated: Boolean(quote?.simulated || row.simulated),
      sourceLabel: quote?.source_system ?? row.sourceLabel,
      ageSeconds: quoteAgeSeconds(quote),
      lane: marketTenorOrder.map((tenor, index) => {
        const laneQuote = latestQuoteByHubTenor.get(`${row.hub}:${tenor}`);
        const laneRow = lane?.tenorRows[index]?.latest ?? null;
        if (laneQuote) return inNative(row.hub, quoteMid(laneQuote), laneQuote.currency, laneQuote.unit).value;
        return laneRow ? inNative(row.hub, laneRow.price, laneRow.currency, laneRow.unit).value : null;
      }),
    };
  });
  // The reporting-unit value of each native price, converted on the server (spot for a prompt
  // tenor, the forward for a month), read once per set of prices.
  const reportingKey = JSON.stringify(boardRows.map((row) => [row.hub, row.tenor, row.mid, row.unit]));
  const [reportingValues, setReportingValues] = useState<Map<string, ReportingValue>>(new Map());
  useEffect(() => {
    const { body, hubs } = boardReportingRequest(boardRows.map((row) => ({ hub: row.hub, tenor: row.tenor, value: row.mid, unit: row.unit })));
    if (body.values.length === 0) {
      setReportingValues(new Map());
      return undefined;
    }
    let live = true;
    api.normaliseMarket(body)
      .then((response) => { if (live) setReportingValues(reportingByHub(hubs, response.data)); })
      .catch(() => { if (live) setReportingValues(new Map()); });
    return () => { live = false; };
    // boardRows is rebuilt each render; the prices it holds are what matter.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [reportingKey]);
  const reporting = useMemo(() => {
    const out = new Map<string, { text: string }>();
    for (const [hub, value] of reportingValues) {
      out.set(hub, {
        text: value.value === null
          ? t("prices.board.reporting_refused", { reason: value.refused ?? "" })
          : t(value.pair ? "prices.board.reporting" : "prices.board.reporting_plain", {
              value: value.value.toFixed(3),
              unit: value.unit,
              pair: value.pair ?? "",
              rate: value.rate === null ? "" : value.rate.toFixed(4),
              method: value.method === "derived: covered interest parity"
                ? t("spreads.fx.derived")
                : value.method === "licensed"
                  ? t("spreads.fx.licensed")
                  : t("spreads.fx.spot_short"),
            }) + (value.simulated ? ` · ${t("today.simulated_short")}` : ""),
      });
    }
    return out;
  }, [reportingValues, t]);
  const boardIsDefault = boardHubCodes.join() === BOARD_DEFAULT_HUBS.join();

  // What the board says once instead of on every row (the owner: "a lot that says nothing").
  const pricedRows = boardRows.filter((row) => row.priced);
  const twoSided = boardRows.some((row) => row.quote !== null);
  const boardScope = simulatedScopeOf(pricedRows.map((row) => row.simulated));
  const allSimulated = boardScope === "all";
  const anyAge = boardRows.some((row) => row.ageSeconds !== null);
  const anyTick = boardRows.some((row) => row.delta !== null);
  // Spread to TTF in one basis: TTF's EUR/MWh mid against each hub's EUR/MWh value (its own
  // mid when quoted in EUR/MWh, else the server's conversion at the stated FX).
  const ttfRow = boardRows.find((row) => row.hub === "TTF");
  const ttfEur = ttfRow && ttfRow.unit === "EUR/MWh" ? ttfRow.mid : null;
  const spreadToTtf = (row: BoardRow): number | null => {
    if (ttfEur === null || row.mid === null) return null;
    if (row.hub === "TTF") return 0;
    if (row.unit === "EUR/MWh") return row.mid - ttfEur;
    const converted = reportingValues.get(row.hub)?.value ?? null;
    return converted === null ? null : converted - ttfEur;
  };
  const anySpread = boardRows.some((row) => row.hub !== "TTF" && spreadToTtf(row) !== null);
  const heldTenors = marketTenorOrder.filter((_, index) => boardRows.some((row) => row.lane[index] !== null));

  const boardColumns: DataGridColumn<BoardRow>[] = [
    {
      id: "hub",
      header: t("market.hub"),
      rowHeader: true,
      priority: "primary",
      sortable: true,
      value: (row) => row.hub,
      render: (row) => (
        <span
          className="market-hub-focus-button"
          data-focused={focusedHub === row.hub ? "true" : "false"}
          title={allSimulated && row.priced ? `${t("market.board_note")} · ${t("market.source")}: ${row.sourceLabel}` : t("market.board_note")}
        >
          <strong data-price-hub-label>{row.hub}</strong>
          {/* With the source column folded away (one source class for every row) the source
              stays on hover and for assistive technology. */}
          {allSimulated && row.priced && <span className="ds-visually-hidden" data-price-source>{row.sourceLabel}</span>}
        </span>
      ),
    },
    {
      id: "bidask",
      header: t(twoSided ? "market.bid_ask" : "market.price"),
      state: (row: BoardRow) => (!twoSided && row.simulated && row.priced && !allSimulated ? { kind: "simulated" as const, label: t("today.simulated_short"), description: t("today.simulated_long") } : null),
      priority: "primary",
      type: "number",
      render: (row) => row.bidAskText,
      // Single-sided, the price is the mid: the reporting value is on this cell's hover.
      cellAttributes: (row) => {
        const found = twoSided ? null : reporting.get(row.hub);
        return found ? { "data-price-value": "", title: found.text, "data-reporting": found.text } : { "data-price-value": "" };
      },
    },
    // With no two-sided quote the mid is the price itself: one column, not two.
    ...(!twoSided ? [] : [{
      id: "mid",
      header: t("market.mid"),
      priority: "primary",
      type: "number",
      sortable: true,
      flash: true,
      value: (row) => row.mid,
      format: (value) => (value == null ? "–" : (value as number).toFixed(3)),
      // The reporting unit on hover (G3): converted on the server, with its rate and method.
      cellAttributes: (row) => {
        const found = reporting.get(row.hub);
        return found ? { title: found.text, "data-reporting": found.text } : {};
      },
      // A simulated price is marked beside the number itself (AGENTS.md rule 17).
      // Tagged only where it differs from the rest: when every row is simulated the banner says so.
      state: (row) => (row.simulated && row.priced && !allSimulated ? { kind: "simulated", label: t("today.simulated_short"), description: t("today.simulated_long") } : null),
    } satisfies DataGridColumn<BoardRow>]),
    ...(anyTick ? [{
      id: "tick",
      header: t("market.tick_change"),
      type: "number",
      sortable: true,
      value: (row) => row.delta,
      render: (row) => (
        <span className={`market-price-delta ${row.delta === null ? "flat" : row.delta > 0 ? "up" : row.delta < 0 ? "down" : "flat"}`}>
          {row.delta === null ? "–" : formatDelta(row.delta)}
        </span>
      ),
    } satisfies DataGridColumn<BoardRow>] : []),
    ...(anySpread ? [{
      id: "spread",
      header: t("prices.board.spread_to_ttf"),
      type: "number" as const,
      sortable: true,
      value: (row: BoardRow) => spreadToTtf(row),
      format: (value: unknown) => (value == null ? "–" : `${(value as number) >= 0 ? "+" : ""}${(value as number).toFixed(2)}`),
    } satisfies DataGridColumn<BoardRow>] : []),
    // The other tenors beside the active one, only those held and only when there is more than
    // the active tenor (otherwise the column repeats the mid).
    ...marketTenorOrder.flatMap<DataGridColumn<BoardRow>>((tenor, index) => (
      heldTenors.length > 1 && heldTenors.includes(tenor) ? [{
      id: `curve-${tenor}`,
      header: t(`market.tenor_short.${tenor}`),
      headerTitle: tenorLabel(tenor, t),
      type: "number",
      value: (row) => row.lane[index] ?? null,
      format: (value) => (value == null ? "–" : (value as number).toFixed(2)),
      cellClassName: () => (tenor === activeTenor ? "market-curve-active" : "market-curve"),
    }] : [])),
    ...(allSimulated ? [] : [{
      id: "source",
      header: t("market.source"),
      // A price names where it came from on a phone too.
      priority: "primary",
      sortable: true,
      value: (row) => row.sourceLabel,
      render: (row) => {
        if (!row.priced) return <span data-price-source>–</span>;
        const description = row.simulated ? `${row.sourceLabel} · ${t("market.simulated_source")}` : row.sourceLabel;
        return (
          <em data-price-source className={`market-source-pill ${row.simulated ? "simulated" : ""}`} aria-label={description} title={description}>
            {row.sourceLabel}
          </em>
        );
      },
    } satisfies DataGridColumn<BoardRow>]),
    {
      id: "meta",
      header: t(anyAge ? "market.unit_age" : "prices.board.unit"),
      // On a phone the price keeps its unit beside it (the rest folds into the row's Details).
      priority: "primary",
      render: (row) => (row.priced ? (anyAge ? `${row.unit} · ${formatAge(row.ageSeconds)}` : row.unit) : t("market.awaiting_feed")),
      cellAttributes: () => ({ "data-price-meta": "" }),
    },
  ];

  return (
    <div className="workspace-grid market-page market-terminal-board">
      {/* One board: a row per hub, the active tenor's bid/ask and mid, the premium over TTF and
          the other tenors' mids alongside. The earlier ticker cards, curve lanes, latest-marks
          table and regional comparison showed the same six prices four times. */}
      <div className="workspace-panel span-3 market-terminal-hero">
        <Toolbar
          label={t("market.terminal")}
          className="market-board-toolbar"
          end={
            <span className="market-live-status">
              <span>{t("market.updated")}</span>
              <strong>{formatTimestamp(lastUpdatedAtUtc)}</strong>
              <button
                type="button"
                className="ds-button quiet-button ds-size-sm"
                onClick={() => {
                  void onRefresh();
                }}
              >
                {t("market.refresh")}
              </button>
            </span>
          }
        >
          <strong className="market-board-title">{t("market.terminal")}</strong>
          <Segmented
            className="market-view-switch"
            label={t("ladder.view")}
            options={(["board", "ladder"] as const).map((view) => ({ value: view, label: t(`ladder.view.${view}`) }))}
            value={boardView}
            onChange={chooseBoardView}
          />
          {boardView === "board" && (
            <Segmented
              className="market-tenor-tabs"
              label={t("market.tenor_tabs")}
              options={marketTenorOrder.map((tenor) => ({
                value: tenor,
                label: t(`market.tenor_short.${tenor}`),
                title: tenorLabel(tenor, t),
                className: "market-tenor-tab",
                dataAttributes: { "data-tenor": tenor },
              }))}
              value={activeTenor}
              onChange={setActiveTenor}
            />
          )}
        </Toolbar>
        {/* Said once when every priced row is simulated (components/SimulatedScope.tsx, shared
            with Today and Spreads); a mixed board keeps the banner and the per-row marks. */}
        {simulatedOnBoard && boardScope !== "all" && (
          <div className="market-simulated-banner" role="alert" data-simulated-board="true">
            <strong>{t("market.simulated_banner_title")}</strong>
            <span>{t("market.simulated_banner_body")}</span>
          </div>
        )}
        <SimulatedScope scope={boardScope} notice={t("market.all_simulated")}>
        {boardView === "ladder" ? (
          <MarketLadder
            quotes={marketQuotes}
            hubs={marketMajorHubs.map((definition) => definition.hub)}
            focusedHub={focusedHub}
            onHubChange={onHubChange}
            t={t}
          />
        ) : (
        <>
        {/* The board prices one tenor at a time and one row per major hub. Both are declared on the
            elements the operator sees (`data-board-tenor`, per row `data-price-tenor`), so the
            browser sweep compares the payload's rows for the *displayed* scope instead of assuming
            the board shows every row the projection serves. */}
        {catalogue && (
          <div className="market-board-hubs" data-board-hubs={boardHubCodes.join(",")}>
            {/* One control: every hub held, the board's ticked; choosing one adds or removes it. */}
            <InstrumentPicker
              id="board-hubs"
              scope="hub"
              label={t("prices.board.hubs")}
              catalogue={catalogue}
              value={null}
              multiSelected={boardHubCodes}
              triggerLabel={t("prices.board.hubs_count", { count: boardHubCodes.length })}
              onChange={(selection) => changeBoardHubs(
                boardHubCodes.includes(selection.hub)
                  ? withoutHub(boardHubCodes, selection.hub)
                  : withHub(boardHubCodes, selection.hub),
              )}
            />
            {!boardIsDefault && (
              <Button variant="secondary" size="sm" onClick={() => changeBoardHubs([...BOARD_DEFAULT_HUBS])}>
                {t("prices.board.reset_hubs")}
              </Button>
            )}
          </div>
        )}
        <DataGrid
          id="hub-board"
          className="market-hub-board-table"
          label={t("market.terminal")}
          columns={boardColumns}
          rows={boardRows}
          rowKey={(row) => `${row.hub}-${row.tenor}`}
          density="regular"
          selectedKey={focusedHub ? boardRows.find((row) => row.hub === focusedHub) ? `${focusedHub}-${activeTenorOf(boardRows, focusedHub)}` : null : null}
          onRowAction={(row) => {
            const selecting = focusedHub !== row.hub;
            onHubChange(focusedHub === row.hub ? null : row.hub);
            // Selecting a priced hub shows its observation in the inspector.
            if (selecting && row.recordId) onInspect?.(row.recordId, `${row.hub} ${tenorLabel(row.tenor, t)}`);
          }}
          rowAttributes={(row) => ({
            "data-record": "market-hub-price",
            "data-record-slice": row.pricedSlice ?? undefined,
            "data-record-id": row.recordId ?? undefined,
            "data-price-tenor": row.tenor,
          })}
          rowClassName={(row) => (row.priced ? "is-live" : "is-waiting")}
          tableAttributes={{ "data-market-board": "hub-prices", "data-board-tenor": activeTenor }}
        />
        </>
        )}
        </SimulatedScope>
        <p className="market-terminal-note">
          {t("market.board_note")}
          {marketUnavailableRows.length > 0 && (
            <> · {t("market.no_price_rows")}: {marketUnavailableRows.map((row) => row.hub).join(", ")}</>
          )}
        </p>
        <div className="market-fx-strip" aria-label={t("market.fx")}>
          <span>{t("market.fx")}</span>
          {fxRates.length === 0
            ? <strong>{t("data.unavailable")}</strong>
            : latestFxPerPair(fxRates).slice(0, 4).map((rate) => (
              <strong key={`fx-${rate.pair}-${rate.observed_at_utc}`} title={formatTimestamp(rate.observed_at_utc)}>
                {rate.pair} {rate.rate.toFixed(4)} <small>{rate.source_system ?? t("market.ecb_source")}</small>
              </strong>
            ))}
        </div>
      </div>

      {/* Per-source detail and reference indices are evidence, not the board: one click away. */}
      <details className="workspace-panel span-3 market-source-details">
        <summary>
          {t("market.source_detail")} <small>({activeQuoteCount} · {tenorLabel(activeTenor, t)})</small>
        </summary>
        <div className="market-terminal-table" role="table" aria-label={t("market.title")}>
          <div className="market-terminal-row header" role="row">
            <span role="columnheader">{t("market.hub")}</span>
            <span role="columnheader">{t("market.venue_product")}</span>
            <span role="columnheader">{t("market.price")}</span>
            <span role="columnheader">{t("market.freshness")}</span>
            <span role="columnheader">{t("market.trend")}</span>
          </div>
          {sourceQuoteRows.map(({ key, latest, history }) => (
            <div key={`market-terminal-${key}`} className="market-terminal-row" role="row">
              <strong data-label={t("market.hub")} role="rowheader">{latest.hub}</strong>
              <span data-label={t("market.venue_product")} role="cell">
                {latest.venue} {latest.product} · {latest.source_system}
              </span>
              <span data-label={t("market.price")} role="cell">
                {formatPriceValue(latest.bid_price)} / {formatPriceValue(latest.ask_price)} {latest.currency}/{latest.unit}
              </span>
              <span data-label={t("market.freshness")} role="cell">
                {formatAge(quoteAgeSeconds(latest))} · {latest.freshness}
              </span>
              <span className="market-sparkline-cell" data-label={t("market.trend")} role="cell">
                <MarketSparkline
                  points={quoteHistoryPoints(history)}
                  label={`${latest.hub} ${latest.source_system} ${tenorLabel(activeTenor, t)} ${t("market.trend")}`}
                  unit={`${latest.currency}/${latest.unit}`}
                  simulated={latest.source_system?.toLowerCase().includes("_sim") === true}
                  t={t}
                />
              </span>
            </div>
          ))}
          {sourceQuoteRows.length === 0 && priceRowsForStrip
            .filter((row) => row.latest)
            .map((row) => (
              <div key={`market-terminal-fallback-${row.hub}`} className="market-terminal-row" role="row">
                <strong data-label={t("market.hub")} role="rowheader">{row.hub}</strong>
                <span data-label={t("market.venue_product")} role="cell">
                  {`${row.latest?.market_venue} ${row.latest?.product} · ${row.sourceLabel}`}
                </span>
                <span data-label={t("market.price")} role="cell">{formatPrice(row.latest)}</span>
                <span data-label={t("market.freshness")} role="cell">
                  {`${row.latest?.freshness ?? "n/a"} · ${(row.latest && metadataValue(row.latest, "price_timing")) ?? row.tenor}`}
                </span>
                <span className="market-sparkline-cell" data-label={t("market.trend")} role="cell">
                  <MarketSparkline
                    points={observationHistoryPoints(row.history)}
                    label={`${row.hub} ${tenorLabel(row.tenor, t)} ${t("market.trend")}`}
                    unit={row.latest ? `${row.latest.currency}/${row.latest.unit}` : ""}
                    simulated={isSimulatedSource(row.latest)}
                    t={t}
                  />
                </span>
              </div>
            ))}
        </div>
        <div className="market-source-matrix-title">
          <strong>{t("market.source_matrix")}</strong>
          <span>{displayFeeds || t("data.unavailable")}</span>
        </div>
        <div className="market-source-matrix" role="table" aria-label={t("market.source_matrix")}>
          <div className="market-source-matrix-row header" role="row">
            <span role="columnheader">{t("panel.source")}</span>
            <span role="columnheader">{t("market.timing")}</span>
            <span role="columnheader">{t("market.hubs")}</span>
            <span role="columnheader">{t("market.cadence")}</span>
          </div>
          {sourceMatrixRows.map((row) => (
            <div key={`source-matrix-${row.sourceSystem}`} className="market-source-matrix-row" role="row">
              <strong role="rowheader" className="market-source-identity">
                <span>{row.sourceSystem}</span>
                {row.simulated && (
                  <StatusBadge tone="simulated" className="market-source-pill simulated matrix-simulation-marker">
                    {t("market.simulated_source")}
                  </StatusBadge>
                )}
              </strong>
              <span role="cell">{row.priceTiming}</span>
              <span role="cell">{row.hubs.length > 0 ? row.hubs.join(" / ") : "n/a"}</span>
              <span role="cell">{formatCadence(row.updateIntervalSeconds)}</span>
            </div>
          ))}
        </div>
        <div className="market-reference-index-panel">
          <ReferenceIndexEvidence
            markets={markets}
            focusedHub={focusedHub}
            t={t}
          />
        </div>
      </details>
    </div>
  );
}

/** The newest rate per pair, so a history of fixes reads as one current rate each. */
function latestFxPerPair<T extends { pair: string; observed_at_utc: string }>(rates: readonly T[]): T[] {
  const latest = new Map<string, T>();
  for (const rate of rates) {
    const current = latest.get(rate.pair);
    if (!current || Date.parse(rate.observed_at_utc) > Date.parse(current.observed_at_utc)) {
      latest.set(rate.pair, rate);
    }
  }
  return [...latest.values()];
}

function formatPriceValue(value: number | null | undefined): string {
  return value == null || !Number.isFinite(value) ? "n/a" : value.toFixed(3);
}
