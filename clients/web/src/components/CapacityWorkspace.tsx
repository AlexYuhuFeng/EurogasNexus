import { useMemo, useState } from "react";
import type {
  CapacityObsDTO,
  FlowObsDTO,
  LngObsDTO,
  StorageObsDTO,
  TsoAccessPointDTO,
  TsoTariffDTO,
} from "@/api/client";

type Translate = (key: string) => string;
type CapacityView = "network" | "storage" | "lng";
type CapacityPosture = "all" | "constrained" | "available" | "stale" | "incomplete";
type CapacitySort = "attention" | "utilization" | "headroom" | "point";

interface CapacityWorkspaceProps {
  flows: FlowObsDTO[];
  capacity: CapacityObsDTO[];
  tsoAccess: TsoAccessPointDTO[];
  tsoTariffs: TsoTariffDTO[];
  storage: StorageObsDTO[];
  lng: LngObsDTO[];
  t: Translate;
}

interface OperatingRow {
  key: string;
  pointId: string;
  pointName: string;
  country: string;
  operator: string;
  direction: string;
  flowMcmD: number | null;
  technicalCapacityMcmD: number | null;
  bookedCapacityMcmD: number | null;
  nominationMcmD: number | null;
  utilizationPct: number | null;
  bookingPct: number | null;
  physicalHeadroomMcmD: number | null;
  observedAtUtc: string | null;
  sourceReference: string | null;
  posture: Exclude<CapacityPosture, "all">;
}

const PAGE_SIZE = 50;
const STALE_AFTER_HOURS = 24;

function normalize(value: string): string {
  return value.trim().toLowerCase().replace(/[^a-z0-9]/g, "");
}

function observationTimestamp(row: { observed_at_utc?: string; period_end_utc?: string }): string | null {
  return row.observed_at_utc ?? row.period_end_utc ?? null;
}

function latestTimestamp(...values: Array<string | null | undefined>): string | null {
  return values.filter((value): value is string => Boolean(value)).sort().at(-1) ?? null;
}

function formatNumber(value: number | null | undefined, digits = 2): string {
  return value == null ? "n/a" : value.toLocaleString(undefined, { maximumFractionDigits: digits, minimumFractionDigits: digits });
}

function formatTimestamp(value: string | null): string {
  return value ? new Date(value).toLocaleString() : "n/a";
}

function isStale(timestamp: string | null): boolean {
  if (!timestamp) return true;
  return Date.now() - new Date(timestamp).getTime() > STALE_AFTER_HOURS * 60 * 60 * 1000;
}

function capacityRole(capacityType: string): "technical" | "booked" | "nomination" | "other" {
  const normalized = capacityType.toLowerCase();
  if (normalized.includes("firm") && normalized.includes("technical")) return "technical";
  if (normalized.includes("firm") && normalized.includes("booked")) return "booked";
  if (normalized.includes("nomination")) return "nomination";
  return "other";
}

function buildOperatingRows(
  flows: FlowObsDTO[],
  capacities: CapacityObsDTO[],
  accessRows: TsoAccessPointDTO[],
): OperatingRow[] {
  const accessByPoint = new Map<string, TsoAccessPointDTO>();
  accessRows.forEach((row) => {
    if (row.point_id) accessByPoint.set(row.point_id, row);
    accessByPoint.set(normalize(row.point_name), row);
  });

  const latestFlows = new Map<string, FlowObsDTO>();
  [...flows]
    .sort((left, right) => String(observationTimestamp(right)).localeCompare(String(observationTimestamp(left))))
    .forEach((row) => {
      const key = `${row.point_id}:${row.direction}`;
      if (!latestFlows.has(key)) latestFlows.set(key, row);
    });

  const latestCapacities = new Map<string, Map<string, CapacityObsDTO>>();
  [...capacities]
    .sort((left, right) => String(observationTimestamp(right)).localeCompare(String(observationTimestamp(left))))
    .forEach((row) => {
      const key = `${row.point_id}:${row.direction}`;
      const role = capacityRole(row.capacity_type);
      const byRole = latestCapacities.get(key) ?? new Map<string, CapacityObsDTO>();
      if (!byRole.has(role)) byRole.set(role, row);
      latestCapacities.set(key, byRole);
    });

  const keys = new Set([...latestFlows.keys(), ...latestCapacities.keys()]);
  return [...keys].map((key) => {
    const flow = latestFlows.get(key);
    const capacityByRole = latestCapacities.get(key);
    const technical = capacityByRole?.get("technical");
    const booked = capacityByRole?.get("booked");
    const nomination = capacityByRole?.get("nomination");
    const representative = technical ?? booked ?? nomination ?? capacityByRole?.get("other");
    const pointId = flow?.point_id ?? representative?.point_id ?? key.split(":")[0];
    const pointName = flow?.point_name ?? representative?.point_name ?? pointId;
    const access = accessByPoint.get(pointId) ?? accessByPoint.get(normalize(pointName));
    const flowMcmD = flow?.flow_mcm_d ?? null;
    const technicalCapacityMcmD = technical?.capacity_mcm_d ?? null;
    const bookedCapacityMcmD = booked?.capacity_mcm_d ?? null;
    const nominationMcmD = nomination?.capacity_mcm_d ?? null;
    const utilizationPct = flowMcmD !== null && technicalCapacityMcmD !== null && technicalCapacityMcmD > 0
      ? Math.abs(flowMcmD) / technicalCapacityMcmD * 100
      : null;
    const bookingPct = bookedCapacityMcmD !== null && technicalCapacityMcmD !== null && technicalCapacityMcmD > 0
      ? bookedCapacityMcmD / technicalCapacityMcmD * 100
      : null;
    const requiredTimestamps = [observationTimestamp(flow ?? {}), observationTimestamp(technical ?? {})];
    const observedAtUtc = latestTimestamp(...requiredTimestamps, observationTimestamp(booked ?? {}));
    const incomplete = flowMcmD === null || technicalCapacityMcmD === null || technicalCapacityMcmD <= 0;
    const stale = !incomplete && requiredTimestamps.some((value) => isStale(value));
    const posture = incomplete
      ? "incomplete"
      : stale
        ? "stale"
        : (utilizationPct ?? 0) >= 85
          ? "constrained"
          : "available";

    return {
      key,
      pointId,
      pointName,
      country: access?.country ?? "n/a",
      operator: access?.operator_name ?? "n/a",
      direction: flow?.direction ?? representative?.direction ?? "n/a",
      flowMcmD,
      technicalCapacityMcmD,
      bookedCapacityMcmD,
      nominationMcmD,
      utilizationPct,
      bookingPct,
      physicalHeadroomMcmD: flowMcmD !== null && technicalCapacityMcmD !== null
        ? Math.max(technicalCapacityMcmD - Math.abs(flowMcmD), 0)
        : null,
      observedAtUtc,
      sourceReference: flow?.source_reference ?? technical?.source_reference ?? null,
      posture,
    };
  });
}

function sortOperatingRows(rows: OperatingRow[], sort: CapacitySort): OperatingRow[] {
  return [...rows].sort((left, right) => {
    if (sort === "utilization") return (right.utilizationPct ?? -1) - (left.utilizationPct ?? -1);
    if (sort === "headroom") return (left.physicalHeadroomMcmD ?? Number.MAX_VALUE) - (right.physicalHeadroomMcmD ?? Number.MAX_VALUE);
    if (sort === "point") return left.pointName.localeCompare(right.pointName);
    const leftAttention = (left.utilizationPct ?? 0) >= 85
      ? 0
      : left.utilizationPct !== null
        ? 1
        : left.flowMcmD !== null
          ? 2
          : left.technicalCapacityMcmD !== null
            ? 3
            : 4;
    const rightAttention = (right.utilizationPct ?? 0) >= 85
      ? 0
      : right.utilizationPct !== null
        ? 1
        : right.flowMcmD !== null
          ? 2
          : right.technicalCapacityMcmD !== null
            ? 3
            : 4;
    return leftAttention - rightAttention
      || (right.utilizationPct ?? -1) - (left.utilizationPct ?? -1)
      || left.pointName.localeCompare(right.pointName);
  });
}

function capacityBarWidth(value: number | null, technical: number | null): string {
  if (value === null || technical === null || technical <= 0) return "0%";
  return `${Math.min(Math.abs(value) / technical * 100, 100)}%`;
}

function latestRowsByKey<T extends { observed_at_utc?: string; period_end_utc?: string }>(
  rows: T[],
  keyFor: (row: T) => string,
): T[] {
  const latest = new Map<string, T>();
  [...rows]
    .sort((left, right) => String(observationTimestamp(right)).localeCompare(String(observationTimestamp(left))))
    .forEach((row) => {
      const key = keyFor(row);
      if (!latest.has(key)) latest.set(key, row);
    });
  return [...latest.values()];
}

export function CapacityWorkspace({
  flows,
  capacity,
  tsoAccess,
  tsoTariffs,
  storage,
  lng,
  t,
}: CapacityWorkspaceProps) {
  const [activeView, setActiveView] = useState<CapacityView>("network");
  const [query, setQuery] = useState("");
  const [country, setCountry] = useState("all");
  const [operator, setOperator] = useState("all");
  const [posture, setPosture] = useState<CapacityPosture>("all");
  const [sort, setSort] = useState<CapacitySort>("attention");
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const [page, setPage] = useState(0);

  const operatingRows = useMemo(
    () => buildOperatingRows(flows, capacity, tsoAccess),
    [capacity, flows, tsoAccess],
  );
  const countries = useMemo(
    () => [...new Set(operatingRows.map((row) => row.country).filter((value) => value !== "n/a"))].sort(),
    [operatingRows],
  );
  const operators = useMemo(
    () => [...new Set(operatingRows.map((row) => row.operator).filter((value) => value !== "n/a"))].sort(),
    [operatingRows],
  );
  const filteredRows = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase();
    const matching = operatingRows.filter((row) => {
      const queryMatch = !normalizedQuery || [row.pointName, row.country, row.operator, row.direction]
        .some((value) => value.toLowerCase().includes(normalizedQuery));
      const postureMatch = posture === "all"
        || (posture === "constrained" && (row.utilizationPct ?? 0) >= 85)
        || (posture === "available" && row.utilizationPct !== null && row.utilizationPct < 85)
        || (posture === "stale" && row.posture === "stale")
        || (posture === "incomplete" && row.posture === "incomplete");
      return queryMatch
        && (country === "all" || row.country === country)
        && (operator === "all" || row.operator === operator)
        && postureMatch;
    });
    return sortOperatingRows(matching, sort);
  }, [country, operatingRows, operator, posture, query, sort]);

  const pageCount = Math.max(Math.ceil(filteredRows.length / PAGE_SIZE), 1);
  const activePage = Math.min(page, pageCount - 1);
  const pageStart = activePage * PAGE_SIZE;
  const visibleRows = filteredRows.slice(pageStart, pageStart + PAGE_SIZE);
  const selected = operatingRows.find((row) => row.key === selectedKey) ?? filteredRows[0] ?? null;
  const selectedAccess = selected
    ? tsoAccess.filter((row) => row.point_id === selected.pointId || normalize(row.point_name) === normalize(selected.pointName))
    : [];
  const selectedTariffs = selected
    ? tsoTariffs.filter((row) => normalize(row.source_point_name) === normalize(selected.pointName) || row.point_id === selected.pointId)
    : [];
  const counts = useMemo(() => ({
    constrained: operatingRows.filter((row) => (row.utilizationPct ?? 0) >= 85).length,
    stale: operatingRows.filter((row) => row.posture === "stale").length,
    incomplete: operatingRows.filter((row) => row.posture === "incomplete").length,
    complete: operatingRows.filter((row) => row.utilizationPct !== null).length,
    flowPublished: operatingRows.filter((row) => row.flowMcmD !== null).length,
    technicalPublished: operatingRows.filter((row) => row.technicalCapacityMcmD !== null).length,
  }), [operatingRows]);
  const latestOperationalAt = latestTimestamp(...operatingRows.map((row) => row.observedAtUtc));
  const resetPage = () => setPage(0);

  const latestStorage = useMemo(
    () => latestRowsByKey(storage, (row) => row.facility_id).sort((left, right) => left.facility_name.localeCompare(right.facility_name)),
    [storage],
  );
  const latestLng = useMemo(
    () => latestRowsByKey(lng, (row) => row.terminal_id).sort((left, right) => left.terminal_name.localeCompare(right.terminal_name)),
    [lng],
  );
  const storageFillValues = latestStorage.map((row) => row.fill_pct).filter((value): value is number => value !== null);
  const storageInventory = latestStorage.reduce((total, row) => total + (row.inventory_twh ?? 0), 0);
  const lngInventory = latestLng.reduce((total, row) => total + (row.inventory_twh ?? 0), 0);
  const lngSendOut = latestLng.reduce((total, row) => total + (row.send_out_twh_d ?? 0), 0);
  const lngDtmi = latestLng.reduce((total, row) => total + (row.dtmi_twh ?? 0), 0);

  return (
    <div className="capacity-page capacity-operations">
      <section className="workspace-panel capacity-command-panel">
        <div className="capacity-view-header">
          <div>
            <strong>{t("capacity.title")}</strong>
            <p>{t("capacity.subtitle")}</p>
          </div>
          <div className="segmented-control capacity-view-control" role="tablist" aria-label={t("capacity.views")}>
            {(["network", "storage", "lng"] as CapacityView[]).map((view) => (
              <button key={view} type="button" role="tab" aria-selected={activeView === view} className={activeView === view ? "active" : ""} onClick={() => setActiveView(view)}>
                {t(`capacity.view_${view}`)}
              </button>
            ))}
          </div>
        </div>

        {activeView === "network" && (
          <>
            <div className="capacity-command-bar">
              <input value={query} onChange={(event) => { setQuery(event.target.value); resetPage(); }} placeholder={t("capacity.search_points")} aria-label={t("capacity.search_points")} />
              <select value={country} onChange={(event) => { setCountry(event.target.value); resetPage(); }} aria-label={t("panel.country")}>
                <option value="all">{t("capacity.all_countries")}</option>
                {countries.map((value) => <option key={value} value={value}>{value}</option>)}
              </select>
              <select value={operator} onChange={(event) => { setOperator(event.target.value); resetPage(); }} aria-label="TSO">
                <option value="all">{t("capacity.all_tsos")}</option>
                {operators.map((value) => <option key={value} value={value}>{value}</option>)}
              </select>
              <select value={sort} onChange={(event) => setSort(event.target.value as CapacitySort)} aria-label={t("capacity.sort_by")}>
                {(["attention", "utilization", "headroom", "point"] as CapacitySort[]).map((value) => <option key={value} value={value}>{t(`capacity.sort_${value}`)}</option>)}
              </select>
            </div>
            <div className="segmented-control capacity-posture-control" role="group" aria-label={t("capacity.posture")}>
              {(["all", "constrained", "available", "stale", "incomplete"] as CapacityPosture[]).map((value) => (
                <button key={value} type="button" className={posture === value ? "active" : ""} onClick={() => { setPosture(value); resetPage(); }}>
                  {t(`capacity.${value}`)}
                </button>
              ))}
            </div>
            <div className="capacity-kpi-strip">
              <div><span>{t("capacity.physical_flow_records")}</span><strong>{counts.flowPublished}</strong></div>
              <div><span>{t("capacity.technical_records")}</span><strong>{counts.technicalPublished}</strong></div>
              <div><span>{t("capacity.comparable_records")}</span><strong>{counts.complete}</strong></div>
              <div className={counts.constrained > 0 ? "issue" : ""}><span>{t("capacity.constrained")}</span><strong>{counts.constrained}</strong></div>
              <div className={counts.incomplete > 0 ? "warning" : ""}><span>{t("capacity.incomplete")}</span><strong>{counts.incomplete}</strong></div>
              <div><span>{t("capacity.latest_update")}</span><strong>{formatTimestamp(latestOperationalAt)}</strong></div>
            </div>
            {counts.complete === 0 && (
              <div className="capacity-data-warning" role="status">
                <strong>{t("capacity.no_comparable_title")}</strong>
                <span>{t("capacity.no_comparable_body")}</span>
              </div>
            )}
          </>
        )}

        {activeView === "storage" && (
          <div className="capacity-kpi-strip capacity-asset-kpis">
            <div><span>{t("capacity.storage_sites")}</span><strong>{latestStorage.length}</strong></div>
            <div><span>{t("capacity.average_fill")}</span><strong>{storageFillValues.length ? `${formatNumber(storageFillValues.reduce((a, b) => a + b, 0) / storageFillValues.length, 1)}%` : "n/a"}</strong></div>
            <div><span>{t("capacity.total_inventory")}</span><strong>{formatNumber(storageInventory)} TWh</strong></div>
            <div><span>{t("capacity.latest_update")}</span><strong>{formatTimestamp(latestTimestamp(...latestStorage.map((row) => row.observed_at_utc)))}</strong></div>
          </div>
        )}

        {activeView === "lng" && (
          <div className="capacity-kpi-strip capacity-asset-kpis">
            <div><span>{t("capacity.lng_terminals")}</span><strong>{latestLng.length}</strong></div>
            <div><span>{t("capacity.total_inventory")}</span><strong>{formatNumber(lngInventory)} TWh</strong></div>
            <div><span>{t("capacity.total_send_out")}</span><strong>{formatNumber(lngSendOut)} TWh/d</strong></div>
            <div><span>{t("capacity.total_dtmi")}</span><strong>{formatNumber(lngDtmi)} TWh</strong></div>
            <div><span>{t("capacity.latest_update")}</span><strong>{formatTimestamp(latestTimestamp(...latestLng.map((row) => row.observed_at_utc)))}</strong></div>
          </div>
        )}
      </section>

      {activeView === "network" && (
        <div className="capacity-network-layout">
          <section className="workspace-panel capacity-board-panel">
            <div className="panel-title-row">
              <div><h3>{t("capacity.operating_board")}</h3><p>{t("capacity.operating_board_note")}</p></div>
              <span>{filteredRows.length} / {operatingRows.length}</span>
            </div>
            <div className="capacity-operating-table" role="table">
              <div className="capacity-operating-row header" role="row">
                <span>{t("panel.point")}</span><span>{t("panel.direction")}</span><span>{t("capacity.flow")}</span><span>{t("capacity.technical")}</span><span>{t("capacity.utilization")}</span><span>{t("capacity.booked")}</span><span>{t("capacity.headroom_short")}</span><span>{t("capacity.posture")}</span>
              </div>
              {visibleRows.map((row) => (
                <button key={row.key} type="button" className={selected?.key === row.key ? "capacity-operating-row active" : "capacity-operating-row"} onClick={() => setSelectedKey(row.key)}>
                  <span><strong>{row.pointName}</strong><small>{row.country} · {row.operator}</small></span>
                  <span>{row.direction}</span>
                  <span>{formatNumber(row.flowMcmD)}</span>
                  <span>{formatNumber(row.technicalCapacityMcmD)}</span>
                  <span className={`capacity-utilization-cell ${(row.utilizationPct ?? 0) >= 85 ? "utilization-critical" : ""}`}>
                    <span>{formatNumber(row.utilizationPct, 1)}{row.utilizationPct === null ? "" : "%"}</span>
                    {row.utilizationPct !== null && <span className="capacity-utilization-track" aria-hidden="true"><span style={{ width: `${Math.min(row.utilizationPct, 100)}%` }} /></span>}
                  </span>
                  <span>{formatNumber(row.bookedCapacityMcmD)}</span>
                  <span>{formatNumber(row.physicalHeadroomMcmD)}</span>
                  <span><span className={`capacity-readiness capacity-readiness-${row.posture}`}>{t(`capacity.${row.posture}`)}</span></span>
                </button>
              ))}
              {filteredRows.length === 0 && <div className="capacity-empty-state">{t("capacity.no_matching_points")}</div>}
            </div>
            {filteredRows.length > 0 && (
              <div className="capacity-pagination" aria-label={t("capacity.pagination")}>
                <span>{t("capacity.showing")} {pageStart + 1}-{Math.min(pageStart + PAGE_SIZE, filteredRows.length)} {t("capacity.of")} {filteredRows.length}</span>
                <div>
                  <button type="button" onClick={() => setPage(Math.max(activePage - 1, 0))} disabled={activePage === 0}>{t("capacity.previous")}</button>
                  <strong>{activePage + 1} / {pageCount}</strong>
                  <button type="button" onClick={() => setPage(Math.min(activePage + 1, pageCount - 1))} disabled={activePage >= pageCount - 1}>{t("capacity.next")}</button>
                </div>
              </div>
            )}
          </section>

          <aside className="workspace-panel capacity-point-inspector">
            <div className="panel-title-row"><h3>{t("capacity.point_inspector")}</h3><span>{selected ? formatTimestamp(selected.observedAtUtc) : "n/a"}</span></div>
            {selected ? (
              <>
                <div className="capacity-point-heading">
                  <div><strong>{selected.pointName}</strong><span className={`capacity-readiness capacity-readiness-${selected.posture}`}>{t(`capacity.${selected.posture}`)}</span></div>
                  <span>{selected.country} · {selected.operator} · {selected.direction}</span>
                </div>
                <p className="capacity-readiness-note">{t(`capacity.readiness_${selected.posture}`)}</p>
                <div className="capacity-stack" aria-label={t("capacity.capacity_stack")}>
                  <div className="capacity-stack-row technical"><span>{t("capacity.technical")}</span><strong>{formatNumber(selected.technicalCapacityMcmD)} mcm/d</strong><i><b style={{ width: selected.technicalCapacityMcmD ? "100%" : "0%" }} /></i></div>
                  <div className="capacity-stack-row booked"><span>{t("capacity.booked")}</span><strong>{formatNumber(selected.bookedCapacityMcmD)} mcm/d</strong><i><b style={{ width: capacityBarWidth(selected.bookedCapacityMcmD, selected.technicalCapacityMcmD) }} /></i></div>
                  <div className="capacity-stack-row nomination"><span>{t("capacity.nomination")}</span><strong>{formatNumber(selected.nominationMcmD)} mcm/d</strong><i><b style={{ width: capacityBarWidth(selected.nominationMcmD, selected.technicalCapacityMcmD) }} /></i></div>
                  <div className="capacity-stack-row flow"><span>{t("capacity.physical_flow")}</span><strong>{formatNumber(selected.flowMcmD)} mcm/d</strong><i><b style={{ width: capacityBarWidth(selected.flowMcmD, selected.technicalCapacityMcmD) }} /></i></div>
                </div>
                <dl className="capacity-point-metrics">
                  <div><dt>{t("capacity.utilization")}</dt><dd>{formatNumber(selected.utilizationPct, 1)}{selected.utilizationPct === null ? "" : "%"}</dd></div>
                  <div><dt>{t("capacity.booking_occupancy")}</dt><dd>{formatNumber(selected.bookingPct, 1)}{selected.bookingPct === null ? "" : "%"}</dd></div>
                  <div><dt>{t("capacity.physical_headroom")}</dt><dd>{formatNumber(selected.physicalHeadroomMcmD)} mcm/d</dd></div>
                  <div><dt>{t("capacity.products")}</dt><dd>{selectedAccess.length}</dd></div>
                </dl>
                <div className="capacity-evidence-line"><span>{t("capacity.source_record")}</span><strong>{selected.sourceReference ?? "ENTSOG"}</strong></div>
                <div className="capacity-inspector-section">
                  <span>{t("capacity.booking_products")}</span>
                  {selectedAccess.slice(0, 5).map((row) => (
                    <div key={row.access_id}>
                      <strong>{row.booking_platform ?? "n/a"}</strong><span>{row.direction}</span>
                      <small>{[row.annual_contracts_available && t("capacity.annual"), row.monthly_contracts_available && t("capacity.monthly"), row.daily_contracts_available && t("capacity.daily"), row.day_ahead_contracts_available && t("capacity.day_ahead")].filter(Boolean).join(" · ") || t("capacity.no_published_products")}</small>
                    </div>
                  ))}
                  {selectedAccess.length === 0 && <p>{t("capacity.no_access_record")}</p>}
                </div>
                <div className="capacity-inspector-section">
                  <span>{t("capacity.tariffs")}</span>
                  {selectedTariffs.slice(0, 5).map((row) => (
                    <div key={row.tariff_id}><strong>{row.capacity_product}</strong><span>{row.tariff_value.toFixed(4)} {row.currency}/{row.unit}</span><small>{row.effective_from} · {row.tariff_status}</small></div>
                  ))}
                  {selectedTariffs.length === 0 && <p>{t("capacity.no_tariff_record")}</p>}
                </div>
              </>
            ) : <div className="capacity-empty-state">{t("capacity.no_matching_points")}</div>}
          </aside>
        </div>
      )}

      {activeView === "storage" && (
        <section className="workspace-panel capacity-assets-panel">
          <div className="panel-title-row"><div><h3>{t("capacity.storage_title")}</h3><p>{t("capacity.storage_note")}</p></div><span>GIE AGSI</span></div>
          <div className="data-table capacity-asset-table">
            <div className="data-table-row header five"><span>{t("panel.storage")}</span><span>{t("panel.country")}</span><span>{t("capacity.fill")}</span><span>{t("capacity.inventory")}</span><span>{t("capacity.net_cycle")}</span></div>
            {latestStorage.map((row) => <div key={row.observation_id} className="data-table-row five"><strong>{row.facility_name}</strong><span>{row.country ?? "n/a"}</span><span>{formatNumber(row.fill_pct, 1)}%</span><span>{formatNumber(row.inventory_twh)} TWh</span><span>{formatNumber((row.injection_twh_d ?? 0) - (row.withdrawal_twh_d ?? 0))} TWh/d</span></div>)}
          </div>
        </section>
      )}

      {activeView === "lng" && (
        <section className="workspace-panel capacity-assets-panel">
          <div className="panel-title-row"><div><h3>{t("capacity.lng_title")}</h3><p>{t("capacity.lng_note")}</p></div><span>GIE ALSI</span></div>
          <div className="data-table capacity-asset-table">
            <div className="data-table-row header five"><span>{t("panel.lng")}</span><span>{t("panel.country")}</span><span>{t("capacity.inventory")}</span><span>{t("capacity.send_out")}</span><span>DTMI TWh</span></div>
            {latestLng.map((row) => <div key={row.observation_id} className="data-table-row five"><strong>{row.terminal_name}</strong><span>{row.country ?? "n/a"}</span><span>{formatNumber(row.inventory_twh)} TWh</span><span>{formatNumber(row.send_out_twh_d)} TWh/d</span><span>{formatNumber(row.dtmi_twh)} TWh</span></div>)}
          </div>
        </section>
      )}
    </div>
  );
}
