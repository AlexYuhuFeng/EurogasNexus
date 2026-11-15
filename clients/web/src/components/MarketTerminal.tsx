import { useEffect, useMemo, useState } from "react";
import {
  PREFERENCES_APPLIED_EVENT,
  readBoardLayout,
  writeLocalBoardLayout,
} from "@/app/preferences/remotePreferences";
import { formatUtcTimestamp } from "@/app/model/evidencePresentation";
import {
  createHubSpreadResolver,
  type ResolvedHubSpread,
} from "@/app/marketSpread";
import type {
  FxRateDTO,
  IntradayOpportunityDTO,
  MarketQuoteDTO,
  MarketSpreadDTO,
  NormalizedMarketObsDTO,
  SourceSystemDTO,
} from "@/api/client";
import { MarketLadder } from "@/components/MarketLadder";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { DataGrid, Segmented, Toolbar, type DataGridColumn } from "@/components/ui";
import { sumRecordCounts } from "@/app/workspaceDerivedData";
import { IntradayDecisionFeed } from "@/components/IntradayDecisionFeed";
import { ReferenceIndexEvidence } from "@/components/ReferenceIndexEvidence";

type Translate = (key: string) => string;

interface MarketTerminalProps {
  markets: NormalizedMarketObsDTO[];
  marketSpreads: MarketSpreadDTO[];
  marketQuotes: MarketQuoteDTO[];
  intradayOpportunities: IntradayOpportunityDTO[];
  fxRates: FxRateDTO[];
  sources: SourceSystemDTO[];
  lastUpdatedAtUtc: string | null;
  focusedHub: string | null;
  onHubChange: (hubId: string | null) => void;
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

const marketMajorHubs: HubDefinition[] = [
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
  formatUtcTimestamp(value);

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

function MarketSparkline({ values, label }: { values: number[]; label: string }) {
  if (values.length < 2) {
    // `role="img"` keeps the label permitted on a non-interactive element and
    // matches the populated branch below (axe: aria-prohibited-attr).
    return <div className="market-sparkline empty" role="img" aria-label={label} />;
  }

  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = Math.max(max - min, 0.01);
  const points = values.map((value, index) => {
    const x = (index / Math.max(values.length - 1, 1)) * 100;
    const y = 28 - ((value - min) / span) * 24;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(" ");

  return (
    <svg className="market-sparkline" viewBox="0 0 100 32" role="img" aria-label={label}>
      <polyline points={points} />
    </svg>
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

const quoteHistoryValues = (quotes: MarketQuoteDTO[]): number[] => quotes
  .slice()
  .sort((left, right) => Date.parse(left.observed_at_utc) - Date.parse(right.observed_at_utc))
  .map(quoteMid)
  .filter((price): price is number => price !== null)
  .slice(-40);

const observationHistoryValues = (rows: NormalizedMarketObsDTO[]): number[] => rows
  .slice()
  .sort((left, right) => Date.parse(getObservedTime(left)) - Date.parse(getObservedTime(right)))
  .map((row) => row.price)
  .filter((price) => Number.isFinite(price))
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
  intradayOpportunities,
  fxRates,
  sources,
  lastUpdatedAtUtc,
  focusedHub,
  onHubChange,
  onRefresh,
  t,
}: MarketTerminalProps) {
  const [activeTenor, setActiveTenor] = useState("day-ahead");
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
    }), [activeTenor, quoteHistoryByIdentity]);

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
  }, [groupedByTenor, resolveHubSpread]);

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
    return {
      hub: row.hub,
      tenor: row.tenor,
      quote: quote ?? null,
      latest: row.latest,
      priced: Boolean(priced),
      pricedSlice: quote ? "quotes" : row.latest ? "normalized_quotes" : null,
      recordId: quote?.quote_id ?? row.latest?.observation_id ?? null,
      unit: priced ? displayPriceUnit(priced.currency, priced.unit) : null,
      mid: quoteMid(quote) ?? row.latest?.price ?? null,
      delta: quoteDelta(history),
      premium: premiumOverTtf(row.hub, row.tenor, row).value,
      simulated: Boolean(quote?.simulated || row.simulated),
      sourceLabel: quote?.source_system ?? row.sourceLabel,
      ageSeconds: quoteAgeSeconds(quote),
      lane: marketTenorOrder.map((tenor, index) => {
        const laneQuote = latestQuoteByHubTenor.get(`${row.hub}:${tenor}`);
        return quoteMid(laneQuote) ?? lane?.tenorRows[index]?.latest?.price ?? null;
      }),
    };
  });
  const boardColumns: DataGridColumn<BoardRow>[] = [
    {
      id: "hub",
      header: t("market.hub"),
      rowHeader: true,
      sortable: true,
      value: (row) => row.hub,
      render: (row) => (
        <span className="market-hub-focus-button" data-focused={focusedHub === row.hub ? "true" : "false"} title={t("market.board_note")}>
          <strong data-price-hub-label>{row.hub}</strong>
        </span>
      ),
    },
    {
      id: "bidask",
      header: t("market.bid_ask"),
      type: "number",
      render: (row) =>
        row.quote ? `${formatPriceValue(row.quote.bid_price)} / ${formatPriceValue(row.quote.ask_price)}` : row.latest ? formatPrice(row.latest) : "–",
      cellAttributes: () => ({ "data-price-value": "" }),
    },
    {
      id: "mid",
      header: t("market.mid"),
      type: "number",
      sortable: true,
      flash: true,
      value: (row) => row.mid,
      format: (value) => (value == null ? "–" : (value as number).toFixed(3)),
      // A simulated price is marked beside the number itself (AGENTS.md rule 17).
      state: (row) => (row.simulated && row.priced ? { kind: "simulated", label: t("today.simulated_short"), description: t("today.simulated_long") } : null),
    },
    {
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
    },
    {
      id: "spread",
      header: t("market.spread_to_ttf"),
      type: "number",
      sortable: true,
      value: (row) => row.premium,
      format: (value) => (value == null ? "–" : `${(value as number) >= 0 ? "+" : ""}${(value as number).toFixed(2)}`),
    },
    ...marketTenorOrder.map<DataGridColumn<BoardRow>>((tenor, index) => ({
      id: `curve-${tenor}`,
      header: t(`market.tenor_short.${tenor}`),
      headerTitle: tenorLabel(tenor, t),
      type: "number",
      value: (row) => row.lane[index] ?? null,
      format: (value) => (value == null ? "–" : (value as number).toFixed(2)),
      cellClassName: () => (tenor === activeTenor ? "market-curve-active" : "market-curve"),
    })),
    {
      id: "source",
      header: t("market.source"),
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
    },
    {
      id: "meta",
      header: t("market.unit_age"),
      render: (row) => (row.priced ? `${row.unit} · ${formatAge(row.ageSeconds)}` : t("market.awaiting_feed")),
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
        {simulatedOnBoard && (
          <div className="market-simulated-banner" role="alert" data-simulated-board="true">
            <strong>{t("market.simulated_banner_title")}</strong>
            <span>{t("market.simulated_banner_body")}</span>
          </div>
        )}
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
        <DataGrid
          id="hub-board"
          className="market-hub-board-table"
          label={t("market.terminal")}
          columns={boardColumns}
          rows={boardRows}
          rowKey={(row) => `${row.hub}-${row.tenor}`}
          density="regular"
          selectedKey={focusedHub ? boardRows.find((row) => row.hub === focusedHub) ? `${focusedHub}-${activeTenorOf(boardRows, focusedHub)}` : null : null}
          onRowAction={(row) => onHubChange(focusedHub === row.hub ? null : row.hub)}
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

      {/* An empty scan is one line, not a 200 px panel with a badge and an empty card (#69). */}
      {intradayOpportunities.length > 0 ? (
        <div className="workspace-panel span-3 market-opportunity-panel">
          <IntradayDecisionFeed
            opportunities={intradayOpportunities}
            t={t}
          />
        </div>
      ) : (
        <p className="span-3 muted market-rail-note market-opportunity-empty">{t("market.no_opportunities")}</p>
      )}

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
                  values={quoteHistoryValues(history)}
                  label={`${latest.hub} ${latest.source_system} ${tenorLabel(activeTenor, t)} ${t("market.trend")}`}
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
                    values={observationHistoryValues(row.history)}
                    label={`${row.hub} ${tenorLabel(row.tenor, t)} ${t("market.trend")}`}
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
