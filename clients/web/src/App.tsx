import { useEffect, useMemo, useRef, useState } from "react";
import type { ChangeEvent, FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { ContractWorkbench } from "@/components/ContractWorkbench";
import type {
  ContractDraft as ContractDraftModel,
  ContractNumberKey,
  ContractTextKey,
} from "@/components/ContractWorkbench";
import { GasNetworkMap } from "@/components/GasNetworkMap";
import { GlossaryWiki } from "@/components/GlossaryWiki";
import { MarketTerminal } from "@/components/MarketTerminal";
import { ResourcePoolPathOverlay } from "@/components/ResourcePoolPathOverlay";
import type { ResourcePoolMapPath } from "@/components/ResourcePoolPathOverlay";
import { SettingsCenter } from "@/components/SettingsCenter";
import { SourceCenter } from "@/components/SourceCenter";
import { StrategyShadowRunTerminal } from "@/components/StrategyShadowRunTerminal";
import { WorkspaceTopBar, type WorkspacePageId } from "@/components/WorkspaceTopBar";
import type { EdgeDTO, SourceCategoryPostureDTO, UpstreamContractDTO } from "@/api/client";
import { useApiStore } from "@/stores/api";
import { useThemeStore } from "@/stores/theme";
import "./styles/app.css";

type ContractDraft = ContractDraftModel;
type LiveMarkNumberKey = "bid_gbp_mwh" | "ask_gbp_mwh" | "last_gbp_mwh";
const MARKET_REFRESH_INTERVAL_MS = 15_000;

const defaultContractDraft: ContractDraft = {
  contract_id: "operator-ttf-supply-2025",
  contract_name: "Operator TTF supply 2025",
  counterparty: "Operator draft counterparty",
  contract_type: "EFET physical supply",
  delivery_point_name: "TTF",
  gas_year: "2025+",
  delivery_quantity_mwh_per_day: 0,
  contract_price_gbp_mwh: 0,
  nbp_sale_price_gbp_mwh: 0,
  physical_exit_sale_price_gbp_mwh: 0,
  physical_exit_point_name: "NBP",
  title_transfer_point: "TTF virtual trading point",
  beach_delivery_point: "Bacton Beach",
  index_basis: "TTF day-ahead index",
  terminal_access: "BBL / Bacton terminal access to confirm",
  capacity_expiry: "operator to enter",
  document_name: "manual draft",
  document_status: "MANUAL_DRAFT",
  source_reference: "operator manual entry",
  governing_law: "English law / EFET master confirmation to review",
  delivery_tolerance_pct: 2,
  nomination_tolerance_pct: 1,
  tolerance_risk_allowance_gbp_mwh: 0.1,
  variable_cost_gbp_mwh: 0,
  regas_fee_gbp_mwh: 0,
  fuel_loss_allowance_pct: 0,
  settlement_frequency: "monthly",
  upstream_payment_lag_days: 20,
  screen_sale_cash_lag_days: 1,
  annual_financing_rate_pct: 6,
  owned_entry_capacity_mwh_per_day: null,
  owned_exit_capacity_mwh_per_day: null,
  allowed_exit_points: ["NBP", "TTF"],
  eligible_sale_modes: ["TARGET_MARKET_SALE", "LOCAL_MARKET_SALE", "REROUTE_SALE"],
};

function cloneDefaultContractDraft(): ContractDraft {
  return {
    ...defaultContractDraft,
    allowed_exit_points: [...defaultContractDraft.allowed_exit_points],
    eligible_sale_modes: [...defaultContractDraft.eligible_sale_modes],
  };
}

function normalizePointName(value: string | null | undefined): string {
  return (value ?? "").toLowerCase().replace(/[^a-z0-9]+/g, "");
}

function metadataText(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function routeLegLabel(leg: Record<string, unknown>, index: number): string {
  for (const key of ["point_name", "market_area", "hub_binding", "tso", "leg_id"]) {
    const value = metadataText(leg[key]);
    if (value) return value;
  }
  return `leg ${index + 1}`;
}

function routeEdgeRouteId(edge: EdgeDTO): string | null {
  return metadataText(edge.metadata_json?.route_id) ?? edge.source_record_id ?? null;
}

function routeEdgeMetadataText(edge: EdgeDTO, key: string): string | null {
  return metadataText(edge.metadata_json?.[key]);
}

export default function App() {
  const { t, i18n } = useTranslation();
  const { mode, setMode } = useThemeStore();
  const {
    nodes,
    edges,
    sources,
    markets,
    screenOrders,
    pnlSnapshots,
    portfolioSummary,
    fxRates,
    flows,
    capacity,
    storage,
    lng,
    tsoAccess,
    routes,
    routeCandidates,
    tsoTariffs,
    upstreamContracts,
    resourcePoolOptions,
    endpointMeta,
    routeRecommendation,
    resourcePoolResult,
    glossaryTerms,
    glossaryContext,
    analysisResult,
    credentialProviders,
    runtimeDb,
    dataStatus,
    meta,
    marketLastUpdatedAtUtc,
    loading,
    error,
    credentialMessage,
    contractSaveMessage,
    fetchWorkspace,
    refreshMarketData,
    saveProviderCredential,
    saveDraftContract,
    recommendRouteAllocation,
    optimizeResourcePool,
    strategyResult,
    evaluateStrategyLab,
    fetchGlossaryContext,
    askAnalysis,
    generatePortfolioReport,
  } = useApiStore();
  const [activeLayers, setActiveLayers] = useState(["network", "lng", "ips", "hubs"]);
  const [searchTerm, setSearchTerm] = useState("");
  const [credentialProvider, setCredentialProvider] = useState("GIE");
  const [credentialLabel, setCredentialLabel] = useState("default");
  const [credentialValue, setCredentialValue] = useState("");
  const [sourceCategory, setSourceCategory] = useState("all");
  const [selectedSourceId, setSelectedSourceId] = useState<string | null>(null);
  const [glossaryQuery, setGlossaryQuery] = useState("");
  const [glossaryCategory, setGlossaryCategory] = useState("all");
  const [selectedGlossaryTerm, setSelectedGlossaryTerm] = useState<string | null>(null);
  const [glossaryDurationStart, setGlossaryDurationStart] = useState("2026-05-31T06:00");
  const [glossaryDurationEnd, setGlossaryDurationEnd] = useState("2026-06-01T06:00");
  const [analysisQuestion, setAnalysisQuestion] = useState("Summarize current portfolio PnL, route, market, and strategy status.");
  const [invokeDeepSeek, setInvokeDeepSeek] = useState(false);
  const [activeWorkspace, setActiveWorkspace] = useState<WorkspacePageId>("network");
  const [workspaceMenuOpen, setWorkspaceMenuOpen] = useState(false);
  const contractImportRef = useRef<HTMLInputElement>(null);
  const [contractImportMessage, setContractImportMessage] = useState<string | null>(null);
  const selectedCredentialProvider = useMemo(
    () => credentialProviders.find((provider) => provider.provider_id === credentialProvider),
    [credentialProvider, credentialProviders],
  );
  const [contract, setContract] = useState<ContractDraft>(() => cloneDefaultContractDraft());
  const [liveMark, setLiveMark] = useState({
    venue: "ICE OCM",
    hub: "NBP",
    product: "Within-day",
    bid_gbp_mwh: null as number | null,
    ask_gbp_mwh: null as number | null,
    last_gbp_mwh: null as number | null,
    mark_time_utc: new Date().toISOString(),
    source_system: "operator-draft-live-mark",
  });
  const portfolioResources = useMemo(() => {
    return resourcePoolOptions?.portfolio_resources ?? [];
  }, [resourcePoolOptions]);

  const hasPortfolioResources = portfolioResources.length > 0;

  const totalPoolVolume = useMemo(
    () => portfolioResources.reduce((total, resource) => total + resource.available_quantity_mwh_per_day, 0),
    [portfolioResources],
  );

  const saleOptions = useMemo(() => {
    return resourcePoolOptions?.sale_options ?? [];
  }, [resourcePoolOptions]);

  const saleOptionById = useMemo(
    () => new Map(saleOptions.map((option) => [option.option_id, option])),
    [saleOptions],
  );

  const resourcePoolOptimizationRequest = useMemo(() => ({
    portfolio_id: "web-resource-pool",
    resources: portfolioResources,
    sale_options: saleOptions,
    annual_financing_rate_pct: upstreamContracts[0]?.annual_financing_rate_pct ?? contract.annual_financing_rate_pct,
    objective: "MAX_DAILY_PNL",
    research_only: true,
  }), [contract.annual_financing_rate_pct, portfolioResources, saleOptions, upstreamContracts]);
  const contractPayload = useMemo(() => ({
    contract_id: contract.contract_id.trim() || "operator-ttf-supply-2025",
    contract_name: contract.contract_name.trim() || contract.contract_id.trim() || "Operator supply contract",
    resource_type: "PIPELINE_IMPORT",
    delivery_point_name: contract.delivery_point_name.trim() || "TTF",
    gas_year: contract.gas_year.trim() || "2025+",
    delivery_quantity_mwh_per_day: contract.delivery_quantity_mwh_per_day,
    contract_price_gbp_mwh: contract.contract_price_gbp_mwh,
    settlement_frequency: contract.settlement_frequency,
    upstream_payment_lag_days: contract.upstream_payment_lag_days,
    screen_sale_cash_lag_days: contract.screen_sale_cash_lag_days,
    delivery_tolerance_pct: contract.delivery_tolerance_pct,
    nomination_tolerance_pct: contract.nomination_tolerance_pct,
    tolerance_risk_allowance_gbp_mwh: contract.tolerance_risk_allowance_gbp_mwh,
    annual_financing_rate_pct: contract.annual_financing_rate_pct,
    owned_entry_capacity_mwh_per_day: contract.owned_entry_capacity_mwh_per_day,
    owned_exit_capacity_mwh_per_day: contract.owned_exit_capacity_mwh_per_day,
    allowed_exit_points: contract.allowed_exit_points,
    eligible_sale_modes: contract.eligible_sale_modes,
    notes: JSON.stringify({
      source: "web_contract_capture",
      decision_support_only: true,
      human_review_required: true,
      counterparty: contract.counterparty,
      contract_type: contract.contract_type,
      title_transfer_point: contract.title_transfer_point,
      beach_delivery_point: contract.beach_delivery_point,
      index_basis: contract.index_basis,
      terminal_access: contract.terminal_access,
      capacity_expiry: contract.capacity_expiry,
      document_name: contract.document_name,
      document_status: contract.document_status,
      source_reference: contract.source_reference,
      governing_law: contract.governing_law,
      physical_exit_point_name: contract.physical_exit_point_name,
      variable_cost_gbp_mwh: contract.variable_cost_gbp_mwh,
      regas_fee_gbp_mwh: contract.regas_fee_gbp_mwh,
      fuel_loss_allowance_pct: contract.fuel_loss_allowance_pct,
    }),
  }), [contract]);

  const strategyScenario = useMemo(() => {
    const deliveryStart = "2026-01-16T00:00:00Z";
    const deliveryEnd = "2026-01-17T00:00:00Z";
    const ocmMid = liveMark.last_gbp_mwh ?? liveMark.bid_gbp_mwh ?? liveMark.ask_gbp_mwh ?? 0;
    const resource = portfolioResources[0];
    return {
      strategy_id: "nbp-sap-icis-ocm-window",
      strategy_name: "NBP SAP/ICIS day-ahead versus ICE OCM window",
      run_mode: "SHADOW_RUN",
      resource_contexts: [
        {
          resource_id: resource?.resource_id ?? "resource-pool-unavailable",
          resource_name: resource?.resource_name ?? "Resource pool unavailable",
          available_quantity_mwh_per_day: resource?.available_quantity_mwh_per_day ?? 0,
          all_in_cost_gbp_mwh: (resource?.contract_cost_gbp_mwh ?? 0) + (resource?.tolerance_risk_allowance_gbp_mwh ?? 0),
          delivery_tolerance_pct: resource?.delivery_tolerance_pct ?? null,
          nomination_tolerance_pct: resource?.nomination_tolerance_pct ?? null,
          booked_entry_capacity_mwh_per_day: contract.owned_entry_capacity_mwh_per_day,
          balancing_allowance_gbp_mwh: resource?.tolerance_risk_allowance_gbp_mwh ?? 0,
          required_tso_access: resource?.required_tso_access ?? [],
          company_accessible_tsos: resource?.accessible_tsos ?? null,
        },
      ],
      price_observations: [
        {
          observation_id: "operator-sap-reference",
          source_system: "operator-entered",
          venue: "SAP",
          hub: "NBP",
          product: "day-ahead",
          price_name: "SAP",
          price_gbp_mwh: Math.max((markets.find((market) => market.market_venue === "NBP")?.price ?? 0) - 0.4, 0),
          observed_at_utc: "2026-01-15T16:00:00Z",
          delivery_start_utc: deliveryStart,
          delivery_end_utc: deliveryEnd,
          bar_minutes: 5,
          source_reference: "operator:SAP",
        },
        {
          observation_id: "operator-icis-reference",
          source_system: "operator-entered",
          venue: "ICIS Heren",
          hub: "NBP",
          product: "day-ahead",
          price_name: "ICIS_HEREN_DAY_AHEAD",
          price_gbp_mwh: markets.find((market) => market.market_venue === "NBP")?.price ?? 0,
          observed_at_utc: "2026-01-15T16:30:00Z",
          delivery_start_utc: deliveryStart,
          delivery_end_utc: deliveryEnd,
          bar_minutes: 5,
          source_reference: "operator:ICIS_HEREN_DAY_AHEAD",
        },
        {
          observation_id: "operator-ocm-reference",
          source_system: liveMark.source_system,
          venue: liveMark.venue,
          hub: liveMark.hub,
          product: liveMark.product,
          price_name: "ICE_OCM",
          price_gbp_mwh: ocmMid,
          observed_at_utc: "2026-01-15T16:45:00Z",
          delivery_start_utc: deliveryStart,
          delivery_end_utc: deliveryEnd,
          bar_minutes: 5,
          source_reference: liveMark.source_system,
        },
      ],
      components: [
        {
          component_id: "sap-icis-ocm-1500-1700",
          component_type: "OCM_VS_DAY_AHEAD",
          weight: 1,
          day_ahead_price_names: ["SAP", "ICIS_HEREN_DAY_AHEAD"],
          intraday_price_names: ["ICE_OCM"],
          positive_spread_threshold_gbp_mwh: 0.2,
          negative_spread_threshold_gbp_mwh: 0.2,
          time_window_start: "15:00",
          time_window_end: "17:00",
          target_bar_minutes: 5,
        },
      ],
      risk_control: {
        max_ocm_allocation_pct: 70,
        min_day_ahead_allocation_pct: 20,
        max_single_market_volume_mwh_per_day: (portfolioResources[0]?.available_quantity_mwh_per_day ?? 0) * 0.6,
        min_expected_margin_gbp_mwh: 0,
        require_tso_access: true,
      },
      existing_shadow_pnl_gbp: 0,
      research_only: true,
    };
  }, [contract, liveMark, markets, portfolioResources]);

  useEffect(() => {
    fetchWorkspace();
  }, [fetchWorkspace]);

  useEffect(() => {
    if (activeWorkspace !== "market") return;
    void refreshMarketData();
    const intervalId = window.setInterval(() => {
      void refreshMarketData();
    }, MARKET_REFRESH_INTERVAL_MS);
    return () => window.clearInterval(intervalId);
  }, [activeWorkspace, refreshMarketData]);

  async function onCredentialSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedCredentialProvider?.credential_required || !credentialValue.trim()) return;
    await saveProviderCredential(credentialProvider, credentialValue, credentialLabel || "default");
    setCredentialValue("");
  }

  const visibleGlossaryCategories = useMemo(
    () => Array.from(new Set(glossaryTerms.map((term) => term.category))).sort(),
    [glossaryTerms],
  );

  const visibleGlossaryTerms = useMemo(() => {
    const trimmed = glossaryQuery.trim();
    const query = trimmed.toLowerCase();
    return glossaryTerms
      .filter((term) => glossaryCategory === "all" || term.category === glossaryCategory)
      .filter((term) => {
        if (!query) return true;
        return (
          term.term.toLowerCase().includes(query) ||
          term.category.toLowerCase().includes(query) ||
          term.definition_en.toLowerCase().includes(query) ||
          term.definition_zh_cn.includes(trimmed) ||
          term.aliases.some((alias) => alias.toLowerCase().includes(query))
        );
      })
      .slice(0, 40);
  }, [glossaryCategory, glossaryQuery, glossaryTerms]);

  const selectedGlossaryTermRecord = useMemo(
    () =>
      visibleGlossaryTerms.find((term) => term.term === selectedGlossaryTerm) ??
      glossaryTerms.find((term) => term.term === selectedGlossaryTerm) ??
      visibleGlossaryTerms[0] ??
      glossaryTerms[0] ??
      null,
    [glossaryTerms, selectedGlossaryTerm, visibleGlossaryTerms],
  );

  function updateContractNumber(key: ContractNumberKey, value: string) {
    setContract((current) => ({ ...current, [key]: value === "" ? 0 : Number(value) }));
  }

  function updateContractText(key: ContractTextKey, value: string) {
    setContract((current) => ({ ...current, [key]: value }));
  }

  function stringFromRecord(record: Record<string, unknown>, key: string, fallback: string): string {
    const value = record[key];
    return typeof value === "string" && value.trim() ? value.trim() : fallback;
  }

  function numberFromRecord(record: Record<string, unknown>, key: string, fallback: number): number {
    const value = record[key];
    if (typeof value === "number" && Number.isFinite(value)) return value;
    if (typeof value === "string" && value.trim() && Number.isFinite(Number(value))) return Number(value);
    return fallback;
  }

  function nullableNumberFromRecord(
    record: Record<string, unknown>,
    key: string,
    fallback: number | null,
  ): number | null {
    const value = record[key];
    if (value == null || value === "") return fallback;
    if (typeof value === "number" && Number.isFinite(value)) return value;
    if (typeof value === "string" && Number.isFinite(Number(value))) return Number(value);
    return fallback;
  }

  function stringArrayFromRecord(record: Record<string, unknown>, key: string, fallback: string[]): string[] {
    const value = record[key];
    if (Array.isArray(value)) {
      const items = value.filter((item): item is string => typeof item === "string" && item.trim().length > 0);
      return items.length > 0 ? items : fallback;
    }
    if (typeof value === "string" && value.trim()) {
      return value.split(",").map((item) => item.trim()).filter(Boolean);
    }
    return fallback;
  }

  function notesRecordFromRecord(record: Record<string, unknown>): Record<string, unknown> {
    const notes = record.notes;
    if (notes && typeof notes === "object" && !Array.isArray(notes)) return notes as Record<string, unknown>;
    if (typeof notes !== "string" || !notes.trim()) return {};
    try {
      const parsed = JSON.parse(notes) as unknown;
      return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? parsed as Record<string, unknown> : {};
    } catch {
      return {};
    }
  }

  function contractDraftFromRecord(record: Record<string, unknown>, current: ContractDraft): ContractDraft {
    const mergedRecord = { ...notesRecordFromRecord(record), ...record };
    return {
      ...current,
      contract_id: stringFromRecord(mergedRecord, "contract_id", current.contract_id),
      contract_name: stringFromRecord(mergedRecord, "contract_name", current.contract_name),
      counterparty: stringFromRecord(mergedRecord, "counterparty", current.counterparty),
      contract_type: stringFromRecord(mergedRecord, "contract_type", current.contract_type),
      delivery_point_name: stringFromRecord(mergedRecord, "delivery_point_name", current.delivery_point_name),
      physical_exit_point_name: stringFromRecord(mergedRecord, "physical_exit_point_name", current.physical_exit_point_name),
      title_transfer_point: stringFromRecord(mergedRecord, "title_transfer_point", current.title_transfer_point),
      beach_delivery_point: stringFromRecord(mergedRecord, "beach_delivery_point", current.beach_delivery_point),
      index_basis: stringFromRecord(mergedRecord, "index_basis", current.index_basis),
      terminal_access: stringFromRecord(mergedRecord, "terminal_access", current.terminal_access),
      capacity_expiry: stringFromRecord(mergedRecord, "capacity_expiry", current.capacity_expiry),
      document_name: stringFromRecord(mergedRecord, "document_name", current.document_name),
      document_status: stringFromRecord(mergedRecord, "document_status", current.document_status),
      source_reference: stringFromRecord(mergedRecord, "source_reference", current.source_reference),
      governing_law: stringFromRecord(mergedRecord, "governing_law", current.governing_law),
      gas_year: stringFromRecord(mergedRecord, "gas_year", current.gas_year),
      delivery_quantity_mwh_per_day: numberFromRecord(
        mergedRecord,
        "delivery_quantity_mwh_per_day",
        current.delivery_quantity_mwh_per_day,
      ),
      contract_price_gbp_mwh: numberFromRecord(mergedRecord, "contract_price_gbp_mwh", current.contract_price_gbp_mwh),
      delivery_tolerance_pct: numberFromRecord(mergedRecord, "delivery_tolerance_pct", current.delivery_tolerance_pct),
      nomination_tolerance_pct: numberFromRecord(mergedRecord, "nomination_tolerance_pct", current.nomination_tolerance_pct),
      tolerance_risk_allowance_gbp_mwh: numberFromRecord(
        mergedRecord,
        "tolerance_risk_allowance_gbp_mwh",
        current.tolerance_risk_allowance_gbp_mwh,
      ),
      variable_cost_gbp_mwh: numberFromRecord(mergedRecord, "variable_cost_gbp_mwh", current.variable_cost_gbp_mwh),
      regas_fee_gbp_mwh: numberFromRecord(mergedRecord, "regas_fee_gbp_mwh", current.regas_fee_gbp_mwh),
      fuel_loss_allowance_pct: numberFromRecord(
        mergedRecord,
        "fuel_loss_allowance_pct",
        current.fuel_loss_allowance_pct,
      ),
      settlement_frequency: stringFromRecord(mergedRecord, "settlement_frequency", current.settlement_frequency),
      upstream_payment_lag_days: numberFromRecord(
        mergedRecord,
        "upstream_payment_lag_days",
        current.upstream_payment_lag_days,
      ),
      screen_sale_cash_lag_days: numberFromRecord(
        mergedRecord,
        "screen_sale_cash_lag_days",
        current.screen_sale_cash_lag_days,
      ),
      annual_financing_rate_pct: numberFromRecord(
        mergedRecord,
        "annual_financing_rate_pct",
        current.annual_financing_rate_pct,
      ),
      owned_entry_capacity_mwh_per_day: nullableNumberFromRecord(
        mergedRecord,
        "owned_entry_capacity_mwh_per_day",
        current.owned_entry_capacity_mwh_per_day,
      ),
      owned_exit_capacity_mwh_per_day: nullableNumberFromRecord(
        mergedRecord,
        "owned_exit_capacity_mwh_per_day",
        current.owned_exit_capacity_mwh_per_day,
      ),
      allowed_exit_points: stringArrayFromRecord(mergedRecord, "allowed_exit_points", current.allowed_exit_points),
      eligible_sale_modes: stringArrayFromRecord(mergedRecord, "eligible_sale_modes", current.eligible_sale_modes),
    };
  }

  function contractRecordFromParsedJson(parsed: unknown): Record<string, unknown> | null {
    if (Array.isArray(parsed)) {
      return parsed.find((item): item is Record<string, unknown> => Boolean(item) && typeof item === "object") ?? null;
    }
    if (parsed && typeof parsed === "object") {
      const record = parsed as Record<string, unknown>;
      const wrapped = record.contract;
      if (wrapped && typeof wrapped === "object" && !Array.isArray(wrapped)) {
        return wrapped as Record<string, unknown>;
      }
      return record;
    }
    return null;
  }

  function parseContractTextDraft(fileName: string, text: string): Record<string, unknown> {
    const record: Record<string, unknown> = {
      document_name: fileName,
      document_status: "STAGED_REVIEW_REQUIRED",
      source_reference: fileName,
    };
    const captureText = (key: string, labels: string[]) => {
      const pattern = new RegExp(`(?:^|\\n)\\s*(?:${labels.join("|")})\\s*[:\\-]\\s*([^\\r\\n]+)`, "i");
      const value = text.match(pattern)?.[1]?.trim();
      if (value) record[key] = value;
    };
    const captureNumber = (key: string, labels: string[]) => {
      const pattern = new RegExp(`(?:^|\\n)\\s*(?:${labels.join("|")})\\s*[:\\-]\\s*([0-9]+(?:\\.[0-9]+)?)`, "i");
      const value = text.match(pattern)?.[1];
      if (value !== undefined && Number.isFinite(Number(value))) record[key] = Number(value);
    };

    captureText("contract_id", ["contract id", "agreement id", "confirmation id"]);
    captureText("contract_name", ["contract name", "agreement", "confirmation"]);
    captureText("counterparty", ["counterparty", "seller", "buyer"]);
    captureText("contract_type", ["contract type", "agreement type"]);
    captureText("gas_year", ["gas year", "term"]);
    captureText("delivery_point_name", ["delivery point", "delivery hub"]);
    captureText("title_transfer_point", ["title transfer point", "title-transfer point", "transfer point"]);
    captureText("beach_delivery_point", ["beach delivery point", "beach", "landing point"]);
    captureText("index_basis", ["index basis", "price index", "pricing basis"]);
    captureText("terminal_access", ["terminal access", "terminal", "tso access"]);
    captureText("capacity_expiry", ["capacity expiry", "capacity end", "expiry"]);
    captureText("governing_law", ["governing law", "law"]);
    captureNumber("delivery_quantity_mwh_per_day", ["quantity", "daily quantity", "mwh per day", "mwh/d"]);
    captureNumber("contract_price_gbp_mwh", ["contract price", "price", "gbp/mwh"]);
    captureNumber("delivery_tolerance_pct", ["delivery tolerance", "tolerance"]);
    captureNumber("nomination_tolerance_pct", ["nomination tolerance"]);
    captureNumber("variable_cost_gbp_mwh", ["variable cost"]);
    captureNumber("regas_fee_gbp_mwh", ["regas fee", "regasification fee"]);
    captureNumber("fuel_loss_allowance_pct", ["fuel loss", "shrinkage"]);

    return record;
  }

  function contractRecordFromImportedFile(fileName: string, text: string): Record<string, unknown> | null {
    try {
      const parsed = JSON.parse(text) as unknown;
      const record = contractRecordFromParsedJson(parsed);
      return record ? { document_name: fileName, document_status: "IMPORTED_JSON_DRAFT", ...record } : null;
    } catch {
      return parseContractTextDraft(fileName, text);
    }
  }

  function loadPersistedContract(saved: UpstreamContractDTO) {
    setContract((current) => contractDraftFromRecord(saved as unknown as Record<string, unknown>, current));
    setContractImportMessage(`${saved.contract_id} ${t("contracts.loaded_for_edit")}`);
  }

  function resetContractDraft() {
    setContract(cloneDefaultContractDraft());
    setContractImportMessage(t("contracts.new_draft_loaded"));
  }

  async function importContractDraftFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    try {
      const record = contractRecordFromImportedFile(file.name, await file.text());
      if (!record) throw new Error(t("contracts.import_invalid"));
      setContract((current) => contractDraftFromRecord(record, current));
      setContractImportMessage(`${file.name} ${t("contracts.import_loaded")}`);
    } catch (e) {
      setContractImportMessage(`${t("contracts.import_failed")}: ${String(e)}`);
    } finally {
      event.target.value = "";
    }
  }

  function updateLiveMarkNumber(key: LiveMarkNumberKey, value: string) {
    setLiveMark((current) => ({ ...current, [key]: value === "" ? null : Number(value) }));
  }

  function toggleLayer(layer: string) {
    setActiveLayers((current) =>
      current.includes(layer) ? current.filter((item) => item !== layer) : [...current, layer],
    );
  }

  function openWorkspace(page: WorkspacePageId) {
    setActiveWorkspace(page);
    setWorkspaceMenuOpen(false);
  }

  const firstStrategyTarget = strategyResult?.allocation_targets[0];
  const glossaryLang = i18n.language.startsWith("zh") ? "zh-CN" : "en";
  const glossaryShortcutTerms = ["TTF", "NBP", "ICE OCM", "Entry Capacity"];
  const routeRecommendationRequest = useMemo(() => ({
    request_id: "web-db-backed-route-allocation",
    source_point_id: portfolioResources[0]?.location_point_name ?? "RESOURCE_POOL",
    target_point_id: saleOptions[0]?.target_point_name ?? null,
    required_quantity_mwh_per_day: totalPoolVolume,
    gas_year: upstreamContracts[0]?.gas_year ?? "2025+",
    capacity_product: "ANNUAL",
    firmness: "FIRM",
    company_accessible_tsos: portfolioResources[0]?.accessible_tsos ?? null,
    candidates: saleOptions.map((option) => ({
      route_id: option.option_id,
      route_name: option.label,
      destination_market: option.target_point_name,
      sale_price: option.sale_price_gbp_mwh,
      price_currency: option.sale_price_currency ?? "EUR",
      price_unit: option.sale_price_unit ?? "EUR/MWh",
      required_tso_access: option.required_tso_access,
      available_capacity_mwh_per_day: option.capacity_limit_mwh_per_day ?? null,
      manual_cost: option.route_cost_gbp_mwh ?? 0,
      cost_currency: option.route_cost_currency ?? "EUR",
      cost_unit: option.route_cost_unit ?? "EUR/MWh",
    })),
  }), [portfolioResources, saleOptions, totalPoolVolume, upstreamContracts]);
  const analysisPayload = {
    question: analysisQuestion,
    task: "PORTFOLIO_REPORT",
    provider_id: "DEEPSEEK",
    model: "deepseek-chat",
    invoke_provider: invokeDeepSeek,
    selected_terms: ["TTF", "NBP", "ICE OCM"],
    selected_assets: ["TTF", "NBP", "BBL"],
    selected_contracts: portfolioResources.map((resource) => resource.resource_id),
    language: i18n.language.startsWith("zh") ? "zh-CN" : "en",
  };
  const workspacePages: WorkspacePageId[] = [
    "network",
    "capacity",
    "market",
    "scenario",
    "contracts",
    "strategy",
    "review",
    "orders",
    "sources",
    "glossary",
    "runtime",
    "settings",
    "manual",
  ];
  const destinationHubs = ["NBP", "TTF", "ZTP", "PEG", "THE"];
  const selectedAllocation = routeRecommendation?.allocations[0] ?? null;
  const poolAllocations = resourcePoolResult?.allocations ?? [];
  const firstPoolAllocation = poolAllocations[0] ?? null;
  const firstPortfolioResource = portfolioResources[0] ?? null;
  const firstAllocationOption = firstPoolAllocation ? saleOptionById.get(firstPoolAllocation.option_id) : null;
  const rawDecisionPnl =
    resourcePoolResult?.total_net_pnl_gbp_per_day ??
    (selectedAllocation?.netback !== undefined && selectedAllocation?.netback !== null
      ? selectedAllocation.netback * selectedAllocation.allocated_mwh_per_day
      : null) ??
    portfolioSummary?.total_indicative_pnl_gbp ??
    null;
  const decisionPnl = hasPortfolioResources ? rawDecisionPnl : null;
  const decisionMargin = firstPoolAllocation?.net_margin_gbp_mwh ?? selectedAllocation?.netback ?? null;
  const salePrice = firstPoolAllocation?.gross_sale_price_gbp_mwh ?? selectedAllocation?.sale_price ?? saleOptions[0]?.sale_price_gbp_mwh ?? null;
  const purchasePrice = firstPortfolioResource?.contract_cost_gbp_mwh ?? null;
  const routeCharge = firstAllocationOption?.route_cost_gbp_mwh ?? selectedAllocation?.route_cost ?? null;
  const activeWarning = [...(strategyResult?.warnings ?? []), ...(meta?.warnings ?? [])][0] ?? null;
  const latestOfficialFlows = useMemo(() => flows
    .filter((item) => item.source_system === "ENTSOG")
    .slice(0, 5), [flows]);
  const latestCapacityRows = useMemo(() => capacity.slice(0, 5), [capacity]);
  const latestTsoAccessRows = useMemo(() => tsoAccess.slice(0, 6), [tsoAccess]);
  const latestTariffRows = useMemo(() => tsoTariffs.slice(0, 6), [tsoTariffs]);
  const latestStorageRows = useMemo(() => storage.slice(0, 4), [storage]);
  const latestLngRows = useMemo(() => lng.slice(0, 4), [lng]);
  const reviewWarnings = useMemo(
    () => [
      ...(resourcePoolResult?.warnings ?? []),
      ...(routeRecommendation?.warnings ?? []),
      ...(strategyResult?.warnings ?? []),
      ...(analysisResult?.warnings ?? []),
      ...(meta?.warnings ?? []),
    ],
    [analysisResult, meta, resourcePoolResult, routeRecommendation, strategyResult],
  );
  const sourceStats = useMemo(() => {
    const issueStatuses = new Set(["failed", "needs_credential", "credential_disabled", "runtime_unconfigured"]);
    return {
      total: sources.length,
      active: sources.filter((source) => source.connectivity_status === "active").length,
      issues: sources.filter((source) => issueStatuses.has(source.connectivity_status)).length,
      records: sources.reduce((total, source) => total + source.live_record_count, 0),
      missingCredentials: sources.filter((source) => source.credential_state === "missing").length,
    };
  }, [sources]);
  const runtimeDbReady = runtimeDb?.database_url_present === true && runtimeDb.connectivity.ok;
  const optionBlockers = resourcePoolOptions?.blockers ?? [];
  const canRunPoolOptimizer =
    runtimeDbReady &&
    hasPortfolioResources &&
    saleOptions.length > 0 &&
    optionBlockers.length === 0;
  const poolInputBlockers = useMemo(() => {
    const blockers: string[] = [];
    if (!runtimeDbReady) blockers.push(t("home.blocker_runtime_db"));
    blockers.push(...(resourcePoolOptions?.blockers ?? []));
    return blockers;
  }, [resourcePoolOptions, runtimeDbReady, t]);
  const routeGeometryEdgesByRouteId = useMemo(() => {
    const grouped = new Map<string, EdgeDTO[]>();
    edges
      .filter((edge) => {
        const materialization = routeEdgeMetadataText(edge, "materialization");
        return edge.source_system === "route_candidate" || materialization === "route_candidate_edge";
      })
      .forEach((edge) => {
        const routeId = routeEdgeRouteId(edge);
        if (!routeId) return;
        grouped.set(routeId, [...(grouped.get(routeId) ?? []), edge]);
      });
    return grouped;
  }, [edges]);
  const routeGeometryStateForRoute = useMemo(
    () =>
      (
        routeId: string,
        _routeLegSummary: string[],
      ): ResourcePoolMapPath["routeGeometryState"] => {
        const routeEdges = routeGeometryEdgesByRouteId.get(routeId) ?? [];
        if (routeEdges.length === 0) return "directLineFallback";
        const states = new Set(
          routeEdges
            .map((edge) => routeEdgeMetadataText(edge, "route_geometry_state"))
            .filter((value): value is ResourcePoolMapPath["routeGeometryState"] =>
              value === "surveyed_pipeline_route" ||
              value === "source_derived_leg_sequence" ||
              value === "source_derived_corridor",
            ),
        );
        if (states.has("surveyed_pipeline_route")) return "surveyed_pipeline_route";
        if (states.has("source_derived_leg_sequence")) return "source_derived_leg_sequence";
        if (states.has("source_derived_corridor")) return "source_derived_corridor";
        return routeEdges.length > 1 ? "source_derived_leg_sequence" : "source_derived_corridor";
      },
    [routeGeometryEdgesByRouteId],
  );
  const routeGeometryWarningForRoute = useMemo(
    () =>
      (
        routeId: string,
        routeGeometryState: ResourcePoolMapPath["routeGeometryState"],
      ): string | null => {
        const routeEdges = routeGeometryEdgesByRouteId.get(routeId) ?? [];
        const explicitWarning = routeEdges
          .map((edge) => routeEdgeMetadataText(edge, "geometry_warning"))
          .find((warning): warning is string => Boolean(warning));
        if (explicitWarning) return explicitWarning;
        const geometryQuality = routeEdges
          .map((edge) => routeEdgeMetadataText(edge, "geometry_quality"))
          .find((quality): quality is string => Boolean(quality));
        const unmatchedRouteLegCount = routeEdges.reduce((total, edge) => {
          const metadata = edge.metadata_json ?? {};
          return total + numberFromRecord(metadata, "unmatched_route_leg_count", 0);
        }, 0);
        if (unmatchedRouteLegCount > 0) {
          return `${unmatchedRouteLegCount} route leg node(s) were not matched; map shows source-derived corridor geometry.`;
        }
        if (routeGeometryState === "source_derived_leg_sequence") {
          return "Matched route legs are displayed as source-derived corridor geometry, not surveyed pipeline geometry.";
        }
        if (routeGeometryState === "source_derived_corridor") {
          return geometryQuality === "endpoint_corridor"
            ? "Only endpoint corridor geometry is available for this route."
            : "Only source-derived corridor geometry is available for this route.";
        }
        if (routeGeometryState === "directLineFallback") {
          return "No materialized reference edge exists for this route; direct display fallback is shown.";
        }
        return null;
      },
    [routeGeometryEdgesByRouteId],
  );
  const resourcePoolMapPaths = useMemo<ResourcePoolMapPath[]>(() => {
    if (portfolioResources.length === 0 || saleOptions.length === 0) return [];
    const allocationByResourceAndOption = new Map(
      poolAllocations.map((allocation) => [`${allocation.resource_id}:${allocation.option_id}`, allocation]),
    );
    const fallbackWarnings = poolInputBlockers.length > 0 ? poolInputBlockers : [];
    return portfolioResources.flatMap((resource) =>
      saleOptions.slice(0, 3).map((option) => {
        const allocation = allocationByResourceAndOption.get(`${resource.resource_id}:${option.option_id}`) ?? null;
        const routeCandidate = routeCandidates.find((candidate) => candidate.route_id === option.option_id);
        const routeLegSummary = routeCandidate?.route_legs.map(routeLegLabel) ?? [];
        const routeGeometryState: ResourcePoolMapPath["routeGeometryState"] =
          routeGeometryStateForRoute(option.option_id, routeLegSummary);
        const routeGeometryWarning = routeGeometryWarningForRoute(option.option_id, routeGeometryState);
        const routeWarnings = [
          ...(allocation?.warnings ?? []),
          ...(option.required_tso_access ?? []).filter(
            (tso) => Array.isArray(resource.accessible_tsos) && !resource.accessible_tsos.includes(tso),
          ).map((tso) => `${t("home.missing_tso_access")}: ${tso}`),
          ...fallbackWarnings,
        ];
        const routeState: ResourcePoolMapPath["routeState"] = allocation
          ? "allocated"
          : routeWarnings.length > 0
            ? "blocked"
            : "candidate";
        return {
          pathId: `${resource.resource_id}-${option.option_id}`,
          routeId: option.option_id,
          resourceName: resource.resource_name,
          sourcePointName: resource.location_point_name,
          targetPointName: option.target_point_name,
          availableQuantityMwhPerDay: resource.available_quantity_mwh_per_day,
          allocatedQuantityMwhPerDay: allocation?.allocated_quantity_mwh_per_day ?? null,
          capacityLimitMwhPerDay: option.capacity_limit_mwh_per_day ?? null,
          routeCostGbpMwh: option.route_cost_gbp_mwh ?? null,
          salePriceGbpMwh: option.sale_price_gbp_mwh,
          netMarginGbpMwh: allocation?.net_margin_gbp_mwh ?? null,
          routeState,
          routeGeometryState,
          routeGeometryWarning,
          routeLegSummary,
          warnings: routeWarnings,
        };
      }),
    ).slice(0, 6);
  }, [
    poolAllocations,
    poolInputBlockers,
    portfolioResources,
    routeCandidates,
    routeGeometryStateForRoute,
    routeGeometryWarningForRoute,
    saleOptions,
    t,
  ]);
  const nodeIdByPointName = useMemo(() => {
    const lookup = new Map<string, string>();
    nodes.forEach((node) => {
      [
        node.id,
        node.name,
        metadataText(node.metadata_json?.market_code),
        metadataText(node.metadata_json?.eic_code),
        metadataText(node.metadata_json?.balancing_zone),
      ].forEach((value) => {
        const key = normalizePointName(value);
        if (key && !lookup.has(key)) lookup.set(key, node.id);
      });
    });
    return lookup;
  }, [nodes]);
  const resourcePoolHighlightedRoute = useMemo(() => {
    const resolvePathNodes = (path: ResourcePoolMapPath) => {
      const fromNodeId = nodeIdByPointName.get(normalizePointName(path.sourcePointName));
      const toNodeId = nodeIdByPointName.get(normalizePointName(path.targetPointName));
      return { fromNodeId, toNodeId };
    };
    const firstPath =
      resourcePoolMapPaths.find((path) => {
        const { fromNodeId, toNodeId } = resolvePathNodes(path);
        return path.routeState !== "blocked" && Boolean(fromNodeId && toNodeId && fromNodeId !== toNodeId);
      }) ??
      resourcePoolMapPaths.find((path) => {
        const { fromNodeId, toNodeId } = resolvePathNodes(path);
        return Boolean(fromNodeId && toNodeId && fromNodeId !== toNodeId);
      }) ??
      resourcePoolMapPaths[0];
    if (!firstPath) return undefined;
    const { fromNodeId, toNodeId } = resolvePathNodes(firstPath);
    if (!fromNodeId || !toNodeId || fromNodeId === toNodeId) return undefined;
    return {
      fromNodeId,
      toNodeId,
      routeId: firstPath.routeId,
      label: `${firstPath.sourcePointName} -> ${firstPath.targetPointName}`,
      pnlGbp: firstPath.netMarginGbpMwh !== null
        ? firstPath.netMarginGbpMwh * (firstPath.allocatedQuantityMwhPerDay ?? firstPath.availableQuantityMwhPerDay)
        : null,
      routeGeometryState: firstPath.routeGeometryState,
      routeLegSummary: firstPath.routeLegSummary,
    };
  }, [nodeIdByPointName, resourcePoolMapPaths]);
  const reviewEvidenceItems = useMemo(() => {
    const items: Array<{ kind: string; text: string }> = [];
    const add = (kind: string, text: string | null | undefined) => {
      if (!text || items.some((item) => item.kind === kind && item.text === text)) return;
      items.push({ kind, text });
    };

    reviewWarnings.forEach((warning) => add(t("home.evidence_warning"), warning));
    poolInputBlockers.forEach((blocker) => add(t("home.evidence_blocker"), blocker));
    (resourcePoolResult?.missing_inputs ?? []).forEach((input) => add(t("home.evidence_missing_input"), input));
    (routeRecommendation?.assumptions ?? []).forEach((assumption) => add(t("home.evidence_assumption"), assumption));
    [
      ...(resourcePoolResult?.source_refs ?? []),
      ...(meta?.source_references ?? []),
      ...Object.values(endpointMeta).flatMap((item) => item.source_references ?? []),
    ].forEach((sourceRef) => add(t("home.evidence_source"), sourceRef));

    return items.slice(0, 6);
  }, [endpointMeta, meta, poolInputBlockers, resourcePoolResult, reviewWarnings, routeRecommendation, t]);
  const networkGeometryState = useMemo(() => {
    if (!runtimeDbReady) return "runtime_missing";
    if (nodes.length === 0) return "nodes_missing";
    if (edges.length === 0) return "edges_missing";
    return "loaded";
  }, [edges.length, nodes.length, runtimeDbReady]);
  const sourceCategoryOrder = ["price", "fx", "infrastructure", "tariff", "weather", "ai"];
  const sourceCategories = ["all", ...sourceCategoryOrder];
  const sourcePostureRows = useMemo<SourceCategoryPostureDTO[]>(() => {
    const apiRows = endpointMeta.sources?.source_posture_summary?.categories;
    if (apiRows && apiRows.length > 0) {
      return apiRows
        .filter((row) => sourceCategoryOrder.includes(row.category))
        .sort((left, right) => sourceCategoryOrder.indexOf(left.category) - sourceCategoryOrder.indexOf(right.category));
    }

    const issueStatuses = new Set(["failed", "needs_credential", "credential_disabled", "runtime_unconfigured", "no_records"]);
    return sourceCategoryOrder.map((category) => {
      const categorySources = sources.filter((source) => source.category === category);
      return {
        category,
        category_label: category,
        registered_sources: categorySources.length,
        active_sources: categorySources.filter((source) => source.connectivity_status === "active").length,
        sources_needing_attention: categorySources.filter((source) => issueStatuses.has(source.connectivity_status)).length,
        missing_credentials: categorySources.filter((source) => source.credential_state === "missing").length,
        preview_substitutes_active: categorySources.filter((source) => source.preview_substitute_status === "active").length,
        runtime_records: categorySources.reduce((total, source) => total + source.live_record_count, 0),
        next_action: categorySources.some((source) => source.credential_state === "missing")
          ? "add_credentials"
          : categorySources.some((source) => source.connectivity_status === "failed")
            ? "inspect_failure"
            : categorySources.some((source) => source.connectivity_status === "active")
              ? "monitor"
              : "run_ingestion",
      };
    }).filter((row) => row.registered_sources > 0);
  }, [endpointMeta.sources?.source_posture_summary?.categories, sourceCategoryOrder, sources]);
  const filteredSources = useMemo(
    () => sourceCategory === "all"
      ? sources
      : sources.filter((source) => source.category === sourceCategory),
    [sourceCategory, sources],
  );
  const selectedSource = useMemo(
    () => sources.find((source) => source.source_id === selectedSourceId) ?? filteredSources[0] ?? sources[0] ?? null,
    [filteredSources, selectedSourceId, sources],
  );
  const selectedSourceCredentialProvider = useMemo(
    () => selectedSource?.credential_provider_id
      ? credentialProviders.find((provider) => provider.provider_id === selectedSource.credential_provider_id)
      : null,
    [credentialProviders, selectedSource],
  );
  const sourceCategoryCounts = useMemo(() => {
    const counts = new Map<string, number>();
    sources.forEach((source) => counts.set(source.category, (counts.get(source.category) ?? 0) + 1));
    return counts;
  }, [sources]);
  const sourcesByCategory = useMemo(() => {
    const grouped = new Map<string, string[]>();
    sources.forEach((source) => {
      const systems = grouped.get(source.category) ?? [];
      grouped.set(source.category, [...systems, source.source_system]);
    });
    return grouped;
  }, [sources]);
  function glossaryContextParams() {
    return {
      lang: glossaryLang,
      duration_start_utc: glossaryDurationStart ? new Date(glossaryDurationStart).toISOString() : undefined,
      duration_end_utc: glossaryDurationEnd ? new Date(glossaryDurationEnd).toISOString() : undefined,
    };
  }

  function openGlossaryContext(term: string) {
    setSelectedGlossaryTerm(term);
    fetchGlossaryContext(term, glossaryContextParams());
  }

  function onSelectGlossaryTerm(term: { term: string }) {
    openGlossaryContext(term.term);
  }

  function selectSource(sourceId: string) {
    const source = sources.find((item) => item.source_id === sourceId);
    setSelectedSourceId(sourceId);
    if (source?.credential_provider_id) {
      setCredentialProvider(source.credential_provider_id);
    }
  }

  function selectSourceCategory(category: string, nextSourceId: string | null) {
    setSourceCategory(category);
    if (nextSourceId) selectSource(nextSourceId);
  }

  function sourceLabel(prefix: string, value: string | null | undefined) {
    if (!value) return "n/a";
    const key = `${prefix}.${value}`;
    const translated = t(key);
    return translated === key ? value.replace(/_/g, " ") : translated;
  }

  function categoryProviderSummary(category: string) {
    if (category === "all") return t("sources.all_categories");
    const systems = sourcesByCategory.get(category) ?? [];
    return systems.length > 0 ? systems.join(", ") : t("sources.no_registered_feeds");
  }

  function sourceNextAction(source: typeof sources[number] | null) {
    if (!source) return t("sources.action.none");
    if (source.connectivity_status === "active") return t("sources.action.monitor");
    if (source.connectivity_status === "failed") return t("sources.action.inspect_failure");
    if (source.credential_state === "missing") return t("sources.action.add_credential");
    if (source.credential_state === "disabled") return t("sources.action.enable_credential");
    if (source.connectivity_status === "runtime_unconfigured") return t("sources.action.configure_runtime");
    if (source.connectivity_status === "no_records") return t("sources.action.run_ingestion");
    if (source.connectivity_status === "configured") return t("sources.action.run_ingestion");
    return t("sources.action.review");
  }

  function mapGeometryMessage() {
    if (networkGeometryState === "runtime_missing") return t("map.runtime_missing_body");
    if (networkGeometryState === "nodes_missing") return t("map.nodes_missing_body");
    if (networkGeometryState === "edges_missing") return t("map.network_warning_body");
    return t("map.network_ready_body");
  }

  function formatSourceTimestamp(value: string | null | undefined) {
    if (!value) return "n/a";
    return new Intl.DateTimeFormat(i18n.language, {
      month: "short",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    }).format(new Date(value));
  }

  function formatContextValue(value: unknown) {
    if (value === null || value === undefined || value === "") return "n/a";
    if (typeof value === "number") return Number.isInteger(value) ? value.toLocaleString() : value.toFixed(2);
    if (Array.isArray(value)) return value.join(", ");
    return String(value);
  }

  function contextSource(item: Record<string, unknown>) {
    return formatContextValue(item.source_reference ?? item.source_system ?? item.source_refs);
  }

  return (
    <div className={`app cockpit-app workspace-${activeWorkspace}`}>
      <WorkspaceTopBar
        activeWorkspace={activeWorkspace}
        workspaceMenuOpen={workspaceMenuOpen}
        searchTerm={searchTerm}
        dataStatus={dataStatus}
        language={i18n.language}
        mode={mode}
        t={t}
        onWorkspaceMenuToggle={() => setWorkspaceMenuOpen((current) => !current)}
        onSearchTermChange={setSearchTerm}
        onLanguageChange={(language) => i18n.changeLanguage(language)}
        onModeChange={setMode}
      />

      {workspaceMenuOpen && (
        <nav className="workspace-menu" aria-label={t("topbar.workspace_menu")}>
          {workspacePages.map((page) => (
            <button
              key={`menu-${page}`}
              type="button"
              className={activeWorkspace === page ? "workspace-menu-item active" : "workspace-menu-item"}
              onClick={() => openWorkspace(page)}
            >
              {t(`nav.${page}`)}
            </button>
          ))}
        </nav>
      )}

      <main className="app-main">
        <section className="map-container map-stage" id="map">
          <div className="map-toolbar">
            <button className="chip reset-chip" type="button" onClick={() => setSearchTerm("")}>
              {t("map.reset")}
            </button>
            {["network", "lng", "ips", "hubs"].map((layer) => (
              <button
                key={layer}
                type="button"
                className={
                  activeLayers.includes(layer)
                    ? `chip map-layer-chip compact layer-${layer} active`
                    : `chip map-layer-chip compact layer-${layer}`
                }
                aria-pressed={activeLayers.includes(layer)}
                title={t(`map.layer.${layer}`)}
                onClick={() => toggleLayer(layer)}
              >
                <span className="layer-label">{t(`map.layer.${layer}`)}</span>
              </button>
            ))}
          </div>
          <GasNetworkMap
            nodes={nodes}
            edges={edges}
            routes={routes}
            themeMode={mode}
            activeLayers={activeLayers}
            searchTerm={searchTerm}
            highlightedRoute={resourcePoolHighlightedRoute}
          />
          <ResourcePoolPathOverlay
            paths={resourcePoolMapPaths}
            blockers={poolInputBlockers}
            t={t}
          />
        </section>

        <aside className="scenario-rail">
          {error && <div className="panel alert">{error}</div>}
          {loading && <div className="panel">{t("status.loading")}</div>}

          <div className="panel scenario-intro">
            <span className="eyebrow">{t("home.resource_pool")}</span>
            <h2>{t("home.pool_cockpit")}</h2>
            <p>{t("home.pool_description")}</p>
          </div>

          <div className="panel route-selector-panel">
            <div className="section-heading">
              <span className="eyebrow">{t("home.recommended_paths")}</span>
              <strong>{t("panel.route_allocation")}</strong>
            </div>
            <div className="route-list">
              {saleOptions.length > 0 ? saleOptions.map((option) => (
                <div key={`sale-option-${option.option_id}`} className="route-row route-candidate">
                  <span>{option.label}</span>
                  <strong>{option.target_point_name}</strong>
                  <small>
                    {option.capacity_limit_mwh_per_day?.toLocaleString() ?? t("home.unlimited")} MWh/d / {(option.route_cost_gbp_mwh ?? 0).toFixed(2)} EUR/MWh
                  </small>
                </div>
              )) : (
                <div className="route-row route-candidate blocked-route">
                  <span>{t("home.no_db_contracts")}</span>
                  <strong>{t("data.partial")}</strong>
                  <small>{t("home.draft_contract_note")}</small>
                </div>
              )}
            </div>
            <div className="action-row">
              <button
                type="button"
                disabled={!canRunPoolOptimizer}
                onClick={() => optimizeResourcePool(resourcePoolOptimizationRequest)}
              >
                {t("home.optimize_pool")}
              </button>
            </div>
            {poolInputBlockers.length > 0 && (
              <div className="runtime-blocker-list">
                <strong>{t("home.optimizer_blocked")}</strong>
                {poolInputBlockers.map((blocker) => (
                  <span key={`home-blocker-${blocker}`}>{blocker}</span>
                ))}
              </div>
            )}
          </div>

          <div className="panel home-portfolio-panel">
            <div className="section-heading">
              <span className="eyebrow">{t("home.portfolio")}</span>
              <strong>{portfolioResources.length} {t("home.resources")}</strong>
            </div>
            <div className="metric-grid two-column compact-metrics">
              <div>
                <span>{t("home.pool_volume")}</span>
                <strong>{totalPoolVolume.toLocaleString()} MWh/d</strong>
              </div>
              <div>
                <span>{t("portfolio.open_orders")}</span>
                <strong>{portfolioSummary?.open_order_count ?? screenOrders.length}</strong>
              </div>
            </div>
            <div className="route-list compact-route-list">
              {portfolioResources.map((resource) => (
                <div key={`home-resource-${resource.resource_id}`} className="route-row route-candidate">
                  <span>{resource.resource_name}</span>
                  <strong>{resource.available_quantity_mwh_per_day.toLocaleString()} MWh/d</strong>
                  <small>{resource.location_point_name} / {resource.resource_type}</small>
                </div>
              ))}
              {upstreamContracts.length === 0 && (
                <div className="route-row route-candidate blocked-route">
                  <span>{t("home.no_db_contracts")}</span>
                  <strong>{t("data.partial")}</strong>
                  <small>{t("home.draft_contract_note")}</small>
                </div>
              )}
            </div>
          </div>

          <div className="panel map-data-panel">
            <div className="section-heading">
              <span className="eyebrow">{t("map.topology_status")}</span>
              <strong>{networkGeometryState === "loaded" ? t("data.runtime") : t("data.unavailable")}</strong>
            </div>
            <div className={networkGeometryState === "loaded" ? "map-network-state ready" : "map-network-state blocked"}>
              <strong>
                {networkGeometryState === "loaded"
                  ? t("map.network_dataset")
                  : t("map.network_warning_title")}
              </strong>
              <span>{mapGeometryMessage()}</span>
            </div>
            <div className="node-color-legend">
              <span><i className="node-swatch network" />{t("map.layer.network")}<strong>{edges.length}</strong></span>
              <span><i className="node-swatch lng" />{t("map.layer.lng")}<strong>{nodes.filter((node) => node.node_type === "lng").length}</strong></span>
              <span><i className="node-swatch ips" />{t("map.layer.ips")}<strong>{nodes.filter((node) => node.node_type === "interconnection").length}</strong></span>
              <span><i className="node-swatch hubs" />{t("map.layer.hubs")}<strong>{nodes.filter((node) => node.node_type === "hub").length}</strong></span>
            </div>
            <p className="coordinate-quality-note">{t("map.coordinate_quality_note")}</p>
          </div>

        </aside>

        <aside className="decision-rail">
          <div className="panel trade-result-panel">
            <div className="panel-title-row">
              <div>
                <span className="eyebrow">{t("result.eyebrow")}</span>
                <h3>{t("result.title")}</h3>
              </div>
              <span className="status-pill">{routeRecommendation ? t("result.live") : t("result.snapshot")}</span>
            </div>
            <div className="net-pnl-card">
              <span>{t("result.net_pnl")}</span>
              <strong>
                {decisionPnl === null ? t("home.pending") : `EUR ${Math.round(decisionPnl).toLocaleString()}`}
              </strong>
              <small>
                {t("home.allocated")} {resourcePoolResult?.total_allocated_mwh_per_day?.toLocaleString() ?? "n/a"} MWh/d / {t("home.unallocated")} {resourcePoolResult?.total_unallocated_mwh_per_day?.toLocaleString() ?? "n/a"} MWh/d
              </small>
            </div>
          </div>

          <div className="panel route-alpha-panel">
            <div className="panel-title-row">
              <h3>{t("result.route_alpha")}</h3>
                <span>{t("result.pool_decision")}</span>
            </div>
            {poolAllocations.length > 0 ? poolAllocations.map((allocation) => {
              const option = saleOptionById.get(allocation.option_id);
              return (
                <div key={`pool-allocation-${allocation.resource_id}-${allocation.option_id}`} className="route-alpha-card">
                  <span>{option?.target_point_name ?? allocation.option_id}</span>
                  <strong>{option?.label ?? allocation.option_id}</strong>
                      <small>
                        {allocation.allocated_quantity_mwh_per_day.toLocaleString()} MWh/d / {allocation.net_margin_gbp_mwh.toFixed(2)} EUR/MWh / EUR {Math.round(allocation.net_pnl_gbp_per_day).toLocaleString()} / {option?.sale_price_simulated ? t("market.simulated_source") : option?.sale_price_source_system ?? "n/a"}
                      </small>
                </div>
              );
            }) : (
              <div className="route-alpha-card">
                <span>{t("result.optimal")}</span>
                <strong>{hasPortfolioResources ? selectedAllocation?.route_name ?? saleOptions[0]?.label ?? t("home.pending") : t("home.no_db_contracts")}</strong>
                <small>{hasPortfolioResources ? routeRecommendation ? t("result.no_route") : t("home.run_pool_optimizer") : t("home.draft_contract_note")}</small>
              </div>
            )}
            {hasPortfolioResources && (
              <div className="destination-switcher">
                {destinationHubs.map((hub) => (
                  <button key={hub} type="button" className={hub === "NBP" ? "chip active" : "chip"}>
                    {hub}
                  </button>
                ))}
              </div>
            )}
          </div>

          <div className="panel economics-snapshot">
            <h3>{t("result.economics_snapshot")}</h3>
            <div className="metric-grid two-column">
              <div>
                <span>{t("result.purchase")}</span>
                <strong>{purchasePrice === null ? "n/a" : `EUR ${purchasePrice.toFixed(2)}/MWh`}</strong>
              </div>
              <div>
                <span>{t("result.sale")}</span>
                <strong>{salePrice === null ? "n/a" : `EUR ${salePrice.toFixed(2)}/MWh`}</strong>
              </div>
              <div>
                <span>{t("result.route_cost")}</span>
                <strong>{routeCharge === null ? "n/a" : `EUR ${routeCharge.toFixed(2)}/MWh`}</strong>
              </div>
              <div>
                <span>{t("result.cash_value")}</span>
                <strong>{firstPoolAllocation ? `EUR ${firstPoolAllocation.early_cash_value_gbp_mwh.toFixed(2)}/MWh` : "n/a"}</strong>
              </div>
            </div>
          </div>

          <div className="panel decision-signal-panel">
            <div className="panel-title-row">
              <h3>{t("home.signal")}</h3>
              <span>{firstStrategyTarget ? t("data.live") : t("result.snapshot")}</span>
            </div>
            <div className="net-pnl-card">
              <span>{t("home.strategy_process")}</span>
              <strong>
                {firstStrategyTarget ? `${firstStrategyTarget.market_bucket} ${firstStrategyTarget.target_allocation_pct.toFixed(1)}%` : t("home.not_running")}
              </strong>
              <small>{strategyResult?.candidate_action_for_review ?? t("home.signal_idle")}</small>
            </div>
            <div className="signal-warning">
              <span>{t("home.warning")}</span>
              <strong>{activeWarning ?? t("home.warning_clear")}</strong>
            </div>
          </div>

          <div className="panel evidence-stack-panel">
            <div className="panel-title-row">
              <h3>{t("home.evidence_stack")}</h3>
              <button type="button" className="text-action" onClick={() => openWorkspace("review")}>
                {t("home.review_warnings")}
              </button>
            </div>
            <div className="review-warning-list compact">
              {reviewEvidenceItems.length > 0
                ? reviewEvidenceItems.map((item) => (
                    <span key={`evidence-${item.kind}-${item.text}`}>
                      <strong>{item.kind}</strong> {item.text}
                    </span>
                  ))
                : <span>{t("home.no_evidence_warnings")}</span>}
            </div>
          </div>

        </aside>
        <section className="workspace-page" aria-label={t(`nav.${activeWorkspace}`)}>
          <div className="workspace-page-header">
            <div>
              <span className="eyebrow">{t("app.title")}</span>
              <h1>{t(`nav.${activeWorkspace}`)}</h1>
            </div>
            <span className={`status-badge status-${dataStatus}`}>{t(`data.${dataStatus}`)}</span>
          </div>

          {activeWorkspace === "capacity" && (
            <div className="workspace-grid capacity-page">
              <div className="workspace-panel span-3">
                <div className="section-heading">
                  <span className="eyebrow">{t("nav.capacity")}</span>
                  <strong>{t("capacity.title")}</strong>
                </div>
                <p className="panel-copy">{t("capacity.subtitle")}</p>
                <div className="metric-grid six-column source-kpi-grid">
                  <div><span>{t("panel.flows")}</span><strong>{flows.filter((item) => item.source_system === "ENTSOG").length}</strong></div>
                  <div><span>{t("panel.capacity")}</span><strong>{capacity.filter((item) => item.source_system === "ENTSOG").length}</strong></div>
                  <div><span>{t("panel.tso_access")}</span><strong>{tsoAccess.length}</strong></div>
                  <div><span>{t("panel.tariffs")}</span><strong>{tsoTariffs.length}</strong></div>
                  <div><span>{t("panel.storage")}</span><strong>{storage.filter((item) => item.source_system === "GIE").length}</strong></div>
                  <div><span>{t("panel.lng")}</span><strong>{lng.filter((item) => item.source_system === "GIE").length}</strong></div>
                </div>
              </div>

              <div className="workspace-panel span-2">
                <h3>{t("capacity.flows")}</h3>
                <div className="data-table">
                  <div className="data-table-row header four"><span>{t("panel.point")}</span><span>{t("panel.direction")}</span><span>mcm/d</span><span>{t("panel.status")}</span></div>
                  {latestOfficialFlows.map((row) => (
                    <div key={`capacity-flow-${row.observation_id}`} className="data-table-row four">
                      <strong>{row.point_name}</strong>
                      <span>{row.direction}</span>
                      <span>{row.flow_mcm_d.toFixed(2)}</span>
                      <span>{row.freshness ?? row.source_system ?? "ENTSOG"}</span>
                    </div>
                  ))}
                  {latestOfficialFlows.length === 0 && (
                    <div className="data-table-row four"><strong>n/a</strong><span>ENTSOG</span><span>n/a</span><span>{t("data.unavailable")}</span></div>
                  )}
                </div>
              </div>

              <div className="workspace-panel">
                <h3>{t("capacity.capacity")}</h3>
                <div className="data-table">
                  <div className="data-table-row header four"><span>{t("panel.point")}</span><span>{t("panel.direction")}</span><span>{t("panel.capacity_type")}</span><span>mcm/d</span></div>
                  {latestCapacityRows.map((row) => (
                    <div key={`capacity-row-page-${row.observation_id}`} className="data-table-row four">
                      <strong>{row.point_name}</strong>
                      <span>{row.direction}</span>
                      <span>{row.capacity_type}</span>
                      <span>{row.capacity_mcm_d.toFixed(2)}</span>
                    </div>
                  ))}
                  {latestCapacityRows.length === 0 && (
                    <div className="data-table-row four"><strong>n/a</strong><span>ENTSOG</span><span>{t("data.unavailable")}</span><span>n/a</span></div>
                  )}
                </div>
              </div>

              <div className="workspace-panel span-2">
                <h3>{t("capacity.tso_access")}</h3>
                <div className="data-table">
                  <div className="data-table-row header six"><span>{t("panel.point")}</span><span>{t("panel.country")}</span><span>TSO</span><span>{t("panel.direction")}</span><span>{t("panel.day_ahead")}</span><span>{t("panel.daily")}</span></div>
                  {latestTsoAccessRows.map((row) => (
                    <div key={`tso-access-page-${row.access_id}`} className="data-table-row six">
                      <strong>{row.point_name}</strong>
                      <span>{row.country}</span>
                      <span>{row.operator_name}</span>
                      <span>{row.direction}</span>
                      <span>{row.day_ahead_contracts_available ? t("data.live") : "n/a"}</span>
                      <span>{row.daily_contracts_available ? t("data.live") : "n/a"}</span>
                    </div>
                  ))}
                  {latestTsoAccessRows.length === 0 && (
                    <div className="data-table-row six"><strong>n/a</strong><span>TSO</span><span>{t("data.unavailable")}</span><span>n/a</span><span>n/a</span><span>n/a</span></div>
                  )}
                </div>
              </div>

              <div className="workspace-panel">
                <h3>{t("capacity.tariffs")}</h3>
                <div className="data-table tariff-table">
                  <div className="data-table-row header four"><span>{t("panel.point")}</span><span>{t("panel.direction")}</span><span>{t("panel.product")}</span><span>{t("panel.tariff")}</span></div>
                  {latestTariffRows.map((tariff) => (
                    <div key={`tariff-page-${tariff.tariff_id}`} className="data-table-row four">
                      <strong>{tariff.source_point_name}</strong>
                      <span>{tariff.direction}</span>
                      <span>{tariff.capacity_product}</span>
                      <span>{tariff.tariff_value.toFixed(4)} {tariff.currency}/MWh</span>
                    </div>
                  ))}
                  {latestTariffRows.length === 0 && (
                    <div className="data-table-row four"><strong>n/a</strong><span>TSO</span><span>{t("data.unavailable")}</span><span>n/a</span></div>
                  )}
                </div>
              </div>

              <div className="workspace-panel span-3">
                <h3>{t("capacity.storage_lng")}</h3>
                <div className="source-table-split">
                  <div className="data-table">
                    <div className="data-table-row header four"><span>{t("panel.storage")}</span><span>{t("panel.country")}</span><span>fill %</span><span>TWh</span></div>
                    {latestStorageRows.map((row) => (
                      <div key={`storage-page-${row.observation_id}`} className="data-table-row four">
                        <strong>{row.facility_name}</strong>
                        <span>{row.country ?? "n/a"}</span>
                        <span>{row.fill_pct == null ? "n/a" : row.fill_pct.toFixed(1)}</span>
                        <span>{row.inventory_twh == null ? "n/a" : row.inventory_twh.toFixed(2)}</span>
                      </div>
                    ))}
                    {latestStorageRows.length === 0 && (
                      <div className="data-table-row four"><strong>n/a</strong><span>GIE AGSI</span><span>{t("data.unavailable")}</span><span>n/a</span></div>
                    )}
                  </div>
                  <div className="data-table">
                    <div className="data-table-row header four"><span>{t("panel.lng")}</span><span>{t("panel.country")}</span><span>send-out</span><span>DTMI</span></div>
                    {latestLngRows.map((row) => (
                      <div key={`lng-page-${row.observation_id}`} className="data-table-row four">
                        <strong>{row.terminal_name}</strong>
                        <span>{row.country ?? "n/a"}</span>
                        <span>{row.send_out_twh_d == null ? "n/a" : `${row.send_out_twh_d.toFixed(2)} TWh/d`}</span>
                        <span>{row.dtmi_pct == null ? "n/a" : `${row.dtmi_pct.toFixed(1)}%`}</span>
                      </div>
                    ))}
                    {latestLngRows.length === 0 && (
                      <div className="data-table-row four"><strong>n/a</strong><span>GIE ALSI</span><span>{t("data.unavailable")}</span><span>n/a</span></div>
                    )}
                  </div>
                </div>
              </div>
            </div>
          )}

          {activeWorkspace === "market" && (
            <MarketTerminal
              markets={markets}
              fxRates={fxRates}
              sources={sources}
              lastUpdatedAtUtc={marketLastUpdatedAtUtc}
              onRefresh={refreshMarketData}
              t={t}
            />
          )}

          {activeWorkspace === "contracts" && (
            <ContractWorkbench
              contract={contract}
              contractPayload={contractPayload}
              upstreamContracts={upstreamContracts}
              portfolioResources={portfolioResources}
              totalPoolVolume={totalPoolVolume}
              firstPoolAllocation={firstPoolAllocation}
              runtimeDbReady={runtimeDbReady}
              loading={loading}
              contractImportRef={contractImportRef}
              contractImportMessage={contractImportMessage}
              contractSaveMessage={contractSaveMessage}
              t={t}
              updateContractText={updateContractText}
              updateContractNumber={updateContractNumber}
              saveDraftContract={saveDraftContract}
              resetContractDraft={resetContractDraft}
              importContractDraftFile={importContractDraftFile}
              loadPersistedContract={loadPersistedContract}
            />
          )}

          {activeWorkspace === "scenario" && (
            <div className="workspace-grid scenario-page">
              <div className="workspace-panel span-2">
                <div className="section-heading"><span className="eyebrow">{t("home.recommended_paths")}</span><strong>{t("panel.routes")}</strong></div>
                <div className="route-list">
                  {routeCandidates.map((route) => (
                    <div key={`scenario-route-${route.route_id}`} className="route-row route-candidate"><span>{route.route_name}</span><strong>{route.required_tso_access.join(", ")}</strong></div>
                  ))}
                </div>
              </div>
              <div className="workspace-panel">
                <h3>{t("result.economics_snapshot")}</h3>
                <div className="metric-grid two-column">
                  <div><span>{t("result.purchase")}</span><strong>{purchasePrice === null ? "n/a" : `EUR ${purchasePrice.toFixed(2)}/MWh`}</strong></div>
                  <div><span>{t("result.sale")}</span><strong>{salePrice === null ? "n/a" : `EUR ${salePrice.toFixed(2)}/MWh`}</strong></div>
                  <div><span>{t("result.route_cost")}</span><strong>{routeCharge === null ? "n/a" : `EUR ${routeCharge.toFixed(2)}/MWh`}</strong></div>
                  <div><span>{t("result.cash_value")}</span><strong>{routeRecommendation ? `${routeRecommendation.total_allocated_mwh_per_day.toLocaleString()} MWh/d` : "n/a"}</strong></div>
                </div>
              </div>
              <div className="workspace-panel span-3">
                <div className="section-heading"><span className="eyebrow">{t("home.resource_pool")}</span><strong>{t("panel.route_allocation")}</strong></div>
                <div className="economics-grid wide">
                  <label>{t("economics.volume")}<input type="number" value={contract.delivery_quantity_mwh_per_day} onChange={(event) => updateContractNumber("delivery_quantity_mwh_per_day", event.target.value)} /></label>
                  <label>{t("economics.contract_price")}<input type="number" value={contract.contract_price_gbp_mwh} onChange={(event) => updateContractNumber("contract_price_gbp_mwh", event.target.value)} /></label>
                  <label>{t("economics.nbp_price")}<input type="number" value={contract.nbp_sale_price_gbp_mwh} onChange={(event) => updateContractNumber("nbp_sale_price_gbp_mwh", event.target.value)} /></label>
                  <label>{t("economics.physical_price")}<input type="number" value={contract.physical_exit_sale_price_gbp_mwh} onChange={(event) => updateContractNumber("physical_exit_sale_price_gbp_mwh", event.target.value)} /></label>
                  <label>{t("economics.delivery_tolerance")}<input type="number" value={contract.delivery_tolerance_pct} onChange={(event) => updateContractNumber("delivery_tolerance_pct", event.target.value)} /></label>
                  <label>{t("economics.nomination_tolerance")}<input type="number" value={contract.nomination_tolerance_pct} onChange={(event) => updateContractNumber("nomination_tolerance_pct", event.target.value)} /></label>
                  <label>{t("economics.cash_lag")}<input type="number" value={contract.screen_sale_cash_lag_days} onChange={(event) => updateContractNumber("screen_sale_cash_lag_days", event.target.value)} /></label>
                  <label>{t("economics.finance_rate")}<input type="number" value={contract.annual_financing_rate_pct} onChange={(event) => updateContractNumber("annual_financing_rate_pct", event.target.value)} /></label>
                </div>
                <div className="action-row">
                  <button
                    type="button"
                    disabled={!canRunPoolOptimizer}
                    onClick={() => optimizeResourcePool(resourcePoolOptimizationRequest)}
                  >
                    {t("home.optimize_pool")}
                  </button>
                  <button
                    type="button"
                    disabled={!hasPortfolioResources || saleOptions.length === 0}
                    onClick={() => recommendRouteAllocation(routeRecommendationRequest)}
                  >
                    {t("economics.compare")}
                  </button>
                </div>
                {poolInputBlockers.length > 0 && (
                  <div className="runtime-blocker-list compact">
                    <strong>{t("home.optimizer_blocked")}</strong>
                    {poolInputBlockers.map((blocker) => (
                      <span key={`scenario-blocker-${blocker}`}>{blocker}</span>
                    ))}
                  </div>
                )}
                {resourcePoolResult && (
                  <div className="route-list compact-route-list">
                    {resourcePoolResult.allocations.map((allocation) => {
                      const option = saleOptionById.get(allocation.option_id);
                      return (
                        <div key={`scenario-pool-${allocation.resource_id}-${allocation.option_id}`} className="route-row route-candidate">
                          <span>{option?.label ?? allocation.option_id}</span>
                          <strong>{allocation.allocated_quantity_mwh_per_day.toLocaleString()} MWh/d</strong>
                          <small>{allocation.net_margin_gbp_mwh.toFixed(2)} EUR/MWh / EUR {Math.round(allocation.net_pnl_gbp_per_day).toLocaleString()}</small>
                        </div>
                      );
                    })}
                  </div>
                )}
                {routeRecommendation && (
                  <div className="route-list compact-route-list">
                    {routeRecommendation.allocations.map((allocation) => (
                      <div key={`allocation-${allocation.route_id}`} className="route-row route-candidate">
                        <span>{allocation.route_name}</span>
                        <strong>{allocation.allocated_mwh_per_day.toLocaleString()} MWh/d</strong>
                        <small>{allocation.destination_market ?? "market"} / {allocation.netback == null ? "n/a" : `${allocation.netback.toFixed(2)} EUR/MWh`}</small>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}

          {activeWorkspace === "strategy" && (
            <StrategyShadowRunTerminal
              strategyScenario={strategyScenario}
              strategyResult={strategyResult}
              portfolioResources={portfolioResources}
              marketObservations={markets}
              fxRates={fxRates}
              language={i18n.language}
              loading={loading}
              t={t}
              onEvaluate={() => evaluateStrategyLab(strategyScenario)}
            />
          )}

          {activeWorkspace === "review" && (
            <div className="workspace-grid review-page">
              <div className="workspace-panel span-2">
                <div className="section-heading">
                  <span className="eyebrow">{t("nav.review")}</span>
                  <strong>{t("review.title")}</strong>
                </div>
                <p className="panel-copy">{t("review.subtitle")}</p>
                <div className="data-table">
                  <div className="data-table-row header four"><span>{t("result.optimal")}</span><span>{t("home.allocated")}</span><span>{t("result.route_cost")}</span><span>PnL</span></div>
                  {poolAllocations.map((allocation) => {
                    const option = saleOptionById.get(allocation.option_id);
                    return (
                      <div key={`review-pool-${allocation.resource_id}-${allocation.option_id}`} className="data-table-row four">
                        <strong>{option?.label ?? allocation.option_id}</strong>
                        <span>{allocation.allocated_quantity_mwh_per_day.toLocaleString()} MWh/d</span>
                        <span>{allocation.total_cost_gbp_mwh.toFixed(2)} EUR/MWh</span>
                        <span>EUR {Math.round(allocation.net_pnl_gbp_per_day).toLocaleString()}</span>
                      </div>
                    );
                  })}
                  {poolAllocations.length === 0 && (
                    <div className="data-table-row four"><strong>{t("home.pending")}</strong><span>n/a</span><span>n/a</span><span>{t("home.run_pool_optimizer")}</span></div>
                  )}
                </div>
              </div>
              <div className="workspace-panel">
                <h3>{t("review.warning_register")}</h3>
                <div className="review-warning-list">
                  {reviewWarnings.length > 0
                    ? reviewWarnings.slice(0, 6).map((warning) => <span key={`review-warning-${warning}`}>{warning}</span>)
                    : <span>{t("review.no_warnings")}</span>}
                </div>
              </div>
              <div className="workspace-panel span-3 analysis-panel review-report-panel">
                <h3>{t("panel.analysis")}</h3>
                <textarea value={analysisQuestion} onChange={(event) => setAnalysisQuestion(event.target.value)} rows={4} />
                <label className="checkbox-row"><input type="checkbox" checked={invokeDeepSeek} onChange={(event) => setInvokeDeepSeek(event.target.checked)} />{t("analysis.invoke_deepseek")}</label>
                <div className="action-row"><button type="button" onClick={() => askAnalysis(analysisPayload)}>{t("analysis.ask")}</button><button type="button" onClick={() => generatePortfolioReport(analysisPayload)}>{t("analysis.report")}</button></div>
                {analysisResult && <div className="analysis-result"><strong>{analysisResult.provider_id}: {analysisResult.provider_status}</strong><p>{i18n.language.startsWith("zh") ? analysisResult.answer_zh_cn : analysisResult.answer_en}</p></div>}
              </div>
            </div>
          )}

          {activeWorkspace === "orders" && (
            <div className="workspace-grid orders-page">
              <div className="workspace-panel span-3">
                <div className="section-heading">
                  <span className="eyebrow">{t("nav.orders")}</span>
                  <strong>{t("orders.title")}</strong>
                </div>
                <p className="panel-copy">{t("orders.subtitle")}</p>
                <div className="metric-grid four-column">
                  <div><span>{t("portfolio.indicative_pnl")}</span><strong>{portfolioSummary ? `GBP ${Math.round(portfolioSummary.total_indicative_pnl_gbp).toLocaleString()}` : "n/a"}</strong></div>
                  <div><span>{t("portfolio.cash_value")}</span><strong>{portfolioSummary ? `GBP ${Math.round(portfolioSummary.total_cash_value_gbp).toLocaleString()}` : "n/a"}</strong></div>
                  <div><span>{t("portfolio.open_orders")}</span><strong>{portfolioSummary?.open_order_count ?? screenOrders.length}</strong></div>
                  <div><span>{t("orders.filled_orders")}</span><strong>{portfolioSummary?.filled_order_count ?? "n/a"}</strong></div>
                </div>
              </div>
              <div className="workspace-panel span-3">
                <h3>{t("orders.screen_orders")}</h3>
                <div className="data-table orders-table">
                  <div className="data-table-row header six"><span>Venue</span><span>Side</span><span>Hub</span><span>Qty</span><span>Price</span><span>Status</span></div>
                  {screenOrders.map((order) => (
                    <div key={`orders-${order.order_observation_id}`} className="data-table-row six">
                      <span>{order.venue}</span><span>{order.side}</span><span>{order.hub}</span><strong>{order.remaining_quantity_mwh.toLocaleString()} MWh</strong><span>{order.price.toFixed(2)} {order.unit}</span><span>{order.status}</span>
                    </div>
                  ))}
                  {screenOrders.length === 0 && (
                    <div className="data-table-row six"><span>n/a</span><span>n/a</span><span>n/a</span><strong>0 MWh</strong><span>n/a</span><span>{t("data.unavailable")}</span></div>
                  )}
                </div>
              </div>
              <div className="workspace-panel span-3">
                <h3>{t("orders.pnl_snapshots")}</h3>
                <div className="data-table">
                  <div className="data-table-row header six"><span>Portfolio</span><span>Valuation</span><span>Quantity</span><span>Indicative</span><span>Cash</span><span>Basis</span></div>
                  {pnlSnapshots.slice(0, 8).map((snapshot) => (
                    <div key={`pnl-${snapshot.pnl_snapshot_id}`} className="data-table-row six">
                      <strong>{snapshot.portfolio_id}</strong>
                      <span>{formatSourceTimestamp(snapshot.valuation_time_utc)}</span>
                      <span>{snapshot.quantity_mwh.toLocaleString()} MWh</span>
                      <span>GBP {Math.round(snapshot.indicative_pnl_gbp).toLocaleString()}</span>
                      <span>GBP {Math.round(snapshot.cash_value_gbp).toLocaleString()}</span>
                      <span>{snapshot.valuation_basis}</span>
                    </div>
                  ))}
                  {pnlSnapshots.length === 0 && (
                    <div className="data-table-row six"><strong>n/a</strong><span>n/a</span><span>0 MWh</span><span>n/a</span><span>n/a</span><span>{t("data.unavailable")}</span></div>
                  )}
                </div>
              </div>
            </div>
          )}

          {activeWorkspace === "sources" && (
            <SourceCenter
              t={t}
              sources={sources}
              sourceCategories={sourceCategories}
              sourceCategory={sourceCategory}
              sourceCategoryCounts={sourceCategoryCounts}
              sourceStats={sourceStats}
              sourcePostureRows={sourcePostureRows}
              filteredSources={filteredSources}
              selectedSource={selectedSource}
              selectedCredentialProvider={selectedCredentialProvider}
              selectedSourceCredentialProvider={selectedSourceCredentialProvider ?? null}
              credentialProviders={credentialProviders}
              credentialProvider={credentialProvider}
              credentialLabel={credentialLabel}
              credentialValue={credentialValue}
              credentialMessage={credentialMessage}
              flows={flows}
              capacity={capacity}
              storage={storage}
              lng={lng}
              tsoAccessCount={tsoAccess.length}
              tsoTariffs={tsoTariffs}
              latestCapacityRows={latestCapacityRows}
              onSourceCategoryChange={selectSourceCategory}
              onSourceSelect={selectSource}
              onCredentialProviderChange={setCredentialProvider}
              onCredentialLabelChange={setCredentialLabel}
              onCredentialValueChange={setCredentialValue}
              onCredentialSubmit={onCredentialSubmit}
              sourceLabel={sourceLabel}
              categoryProviderSummary={categoryProviderSummary}
              sourceNextAction={sourceNextAction}
              formatSourceTimestamp={formatSourceTimestamp}
            />
          )}

          {activeWorkspace === "glossary" && (
            <GlossaryWiki
              terms={visibleGlossaryTerms}
              context={glossaryContext}
              selectedTerm={selectedGlossaryTermRecord}
              categories={visibleGlossaryCategories}
              activeCategory={glossaryCategory}
              query={glossaryQuery}
              language={i18n.language}
              durationStart={glossaryDurationStart}
              durationEnd={glossaryDurationEnd}
              shortcutTerms={glossaryShortcutTerms}
              loading={loading}
              t={t}
              onCategoryChange={setGlossaryCategory}
              onQueryChange={setGlossaryQuery}
              onDurationStartChange={setGlossaryDurationStart}
              onDurationEndChange={setGlossaryDurationEnd}
              onSelectTerm={onSelectGlossaryTerm}
              onOpenContext={openGlossaryContext}
              formatContextValue={formatContextValue}
            />
          )}

          {activeWorkspace === "runtime" && (
            <div className="workspace-grid runtime-page">
              <div className="workspace-panel"><h3>{t("panel.governance")}</h3>{meta && <div className="metric-grid"><div><span>{t("status.research_only")}</span><strong>{String(meta.research_only)}</strong></div><div><span>{t("status.human_review_required")}</span><strong>{String(meta.human_review_required)}</strong></div><div><span>{t("status.source")}</span><strong>{meta.source_references.join(", ")}</strong></div></div>}</div>
              <div className="workspace-panel span-2"><h3>{t("status.db")}</h3>{runtimeDb && <div className="metric-grid three-column"><div><span>{t("status.db")}</span><strong>{runtimeDb.connectivity.ok ? "ok" : "failed"}</strong></div><div><span>{t("status.alembic")}</span><strong>{runtimeDb.alembic_revision ?? "unavailable"}</strong></div><div><span>{t("status.missing_tables")}</span><strong>{runtimeDb.missing_tables.length}</strong></div></div>}</div>
            </div>
          )}

          {activeWorkspace === "settings" && (
            <SettingsCenter
              t={t}
              language={i18n.language}
              mode={mode}
              dataStatus={dataStatus}
              runtimeDb={runtimeDb}
              sources={sources}
              credentialProviders={credentialProviders}
              counts={{ nodes: nodes.length, edges: edges.length, routes: routes.length }}
              onLanguageChange={(language) => i18n.changeLanguage(language)}
              onModeChange={setMode}
              onOpenSources={() => openWorkspace("sources")}
            />
          )}

          {activeWorkspace === "manual" && (
            <div className="workspace-grid manual-page">
              <div className="workspace-panel span-3">
                <div className="section-heading">
                  <span className="eyebrow">{t("nav.manual")}</span>
                  <strong>{t("manual.title")}</strong>
                </div>
                <p className="panel-copy">{t("manual.subtitle")}</p>
              </div>
              <div className="workspace-panel span-2">
                <h3>{t("manual.workspace_map")}</h3>
                <div className="manual-step-list">
                  <div><strong>{t("nav.network")}</strong><span>{t("manual.network")}</span></div>
                  <div><strong>{t("nav.capacity")}</strong><span>{t("manual.capacity")}</span></div>
                  <div><strong>{t("nav.market")}</strong><span>{t("manual.market")}</span></div>
                  <div><strong>{t("nav.contracts")}</strong><span>{t("manual.contracts")}</span></div>
                  <div><strong>{t("nav.strategy")}</strong><span>{t("manual.strategy")}</span></div>
                  <div><strong>{t("nav.review")}</strong><span>{t("manual.review")}</span></div>
                  <div><strong>{t("nav.orders")}</strong><span>{t("manual.orders")}</span></div>
                  <div><strong>{t("nav.sources")}</strong><span>{t("manual.sources")}</span></div>
                </div>
              </div>
              <div className="workspace-panel">
                <h3>{t("manual.operating_boundary")}</h3>
                <p className="panel-copy">{t("manual.boundary_copy")}</p>
                <div className="review-warning-list">
                  <span>{t("manual.api_only")}</span>
                  <span>{t("manual.no_execution")}</span>
                  <span>{t("manual.no_client_db")}</span>
                </div>
              </div>
              <div className="workspace-panel span-3">
                <h3>{t("manual.release_readiness")}</h3>
                <div className="metric-grid four-column">
                  <div><span>{t("status.db")}</span><strong>{runtimeDb?.connectivity.ok ? "ok" : "check"}</strong></div>
                  <div><span>{t("sources.active_sources")}</span><strong>{sourceStats.active}</strong></div>
                  <div><span>{t("panel.tariffs")}</span><strong>{tsoTariffs.length}</strong></div>
                  <div><span>{t("portfolio.open_orders")}</span><strong>{portfolioSummary?.open_order_count ?? screenOrders.length}</strong></div>
                </div>
              </div>
            </div>
          )}
        </section>
      </main>
    </div>
  );
}

