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
  capacityMcmD: number | null;
  utilizationPct: number | null;
  headroomMcmD: number | null;
  observedAtUtc: string | null;
  freshness: string;
}

const PAGE_SIZE = 100;

function normalize(value: string): string {
  return value.trim().toLowerCase().replace(/[^a-z0-9]/g, "");
}

function latestTimestamp(...values: Array<string | null | undefined>): string | null {
  return values.filter((value): value is string => Boolean(value)).sort().at(-1) ?? null;
}

function formatNumber(value: number | null | undefined, digits = 2): string {
  return value == null ? "n/a" : value.toFixed(digits);
}

function buildOperatingRows(
  flows: FlowObsDTO[],
  capacities: CapacityObsDTO[],
  accessRows: TsoAccessPointDTO[],
): OperatingRow[] {
  const accessByPoint = new Map<string, TsoAccessPointDTO>();
  accessRows.forEach((row) => {
    accessByPoint.set(row.point_id ?? normalize(row.point_name), row);
    accessByPoint.set(normalize(row.point_name), row);
  });
  const latestFlows = new Map<string, FlowObsDTO>();
  [...flows]
    .sort((left, right) => String(right.observed_at_utc ?? right.period_end_utc).localeCompare(String(left.observed_at_utc ?? left.period_end_utc)))
    .forEach((row) => {
      const key = `${row.point_id}:${row.direction}`;
      if (!latestFlows.has(key)) latestFlows.set(key, row);
    });
  const latestCapacities = new Map<string, CapacityObsDTO>();
  [...capacities]
    .sort((left, right) => String(right.observed_at_utc ?? right.period_end_utc).localeCompare(String(left.observed_at_utc ?? left.period_end_utc)))
    .forEach((row) => {
      const key = `${row.point_id}:${row.direction}`;
      if (!latestCapacities.has(key)) latestCapacities.set(key, row);
    });
  const keys = new Set([...latestFlows.keys(), ...latestCapacities.keys()]);
  return [...keys].map((key) => {
    const flow = latestFlows.get(key);
    const capacity = latestCapacities.get(key);
    const pointId = flow?.point_id ?? capacity?.point_id ?? key.split(":")[0];
    const pointName = flow?.point_name ?? capacity?.point_name ?? pointId;
    const access = accessByPoint.get(pointId) ?? accessByPoint.get(normalize(pointName));
    const flowMcmD = flow?.flow_mcm_d ?? null;
    const capacityMcmD = capacity?.capacity_mcm_d ?? null;
    const utilizationPct = flowMcmD !== null && capacityMcmD !== null && capacityMcmD > 0
      ? Math.abs(flowMcmD) / capacityMcmD * 100
      : null;
    return {
      key,
      pointId,
      pointName,
      country: access?.country ?? "n/a",
      operator: access?.operator_name ?? "n/a",
      direction: flow?.direction ?? capacity?.direction ?? "n/a",
      flowMcmD,
      capacityMcmD,
      utilizationPct,
      headroomMcmD: flowMcmD !== null && capacityMcmD !== null
        ? Math.max(capacityMcmD - Math.abs(flowMcmD), 0)
        : null,
      observedAtUtc: latestTimestamp(flow?.observed_at_utc, capacity?.observed_at_utc),
      freshness: flow?.freshness ?? capacity?.freshness ?? "n/a",
    };
  }).sort((left, right) =>
    (right.utilizationPct ?? -1) - (left.utilizationPct ?? -1) ||
    left.pointName.localeCompare(right.pointName),
  );
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
  const [query, setQuery] = useState("");
  const [country, setCountry] = useState("all");
  const [operator, setOperator] = useState("all");
  const [posture, setPosture] = useState("all");
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
    return operatingRows.filter((row) => {
      const queryMatch = !normalizedQuery || [row.pointName, row.country, row.operator, row.direction]
        .some((value) => value.toLowerCase().includes(normalizedQuery));
      const countryMatch = country === "all" || row.country === country;
      const operatorMatch = operator === "all" || row.operator === operator;
      const postureMatch = posture === "all" ||
        (posture === "constrained" && (row.utilizationPct ?? 0) >= 85) ||
        (posture === "available" && row.utilizationPct !== null && row.utilizationPct < 85) ||
        (posture === "incomplete" && row.utilizationPct === null);
      return queryMatch && countryMatch && operatorMatch && postureMatch;
    });
  }, [country, operatingRows, operator, posture, query]);
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
  const constrainedCount = operatingRows.filter((row) => (row.utilizationPct ?? 0) >= 85).length;
  const incompleteCount = operatingRows.filter((row) => row.utilizationPct === null).length;
  const latestOperationalAt = latestTimestamp(...operatingRows.map((row) => row.observedAtUtc));
  const selectedReadiness = !selected || selected.utilizationPct === null
    ? "incomplete"
    : selected.utilizationPct >= 85
      ? "constrained"
      : "available";

  const resetPage = () => setPage(0);

  return (
    <div className="workspace-grid capacity-page capacity-operations">
      <div className="workspace-panel span-3 capacity-command-panel">
        <div className="section-heading">
          <span className="eyebrow">{t("nav.capacity")}</span>
          <strong>{t("capacity.title")}</strong>
        </div>
        <p className="panel-copy">{t("capacity.subtitle")}</p>
        <div className="capacity-command-bar">
          <input value={query} onChange={(event) => { setQuery(event.target.value); resetPage(); }} placeholder={t("capacity.search_points")} />
          <select value={country} onChange={(event) => { setCountry(event.target.value); resetPage(); }} aria-label={t("panel.country")}>
            <option value="all">{t("capacity.all_countries")}</option>
            {countries.map((value) => <option key={value} value={value}>{value}</option>)}
          </select>
          <select value={operator} onChange={(event) => { setOperator(event.target.value); resetPage(); }} aria-label="TSO">
            <option value="all">{t("capacity.all_tsos")}</option>
            {operators.map((value) => <option key={value} value={value}>{value}</option>)}
          </select>
          <div className="segmented-control capacity-posture-control" role="group" aria-label={t("capacity.posture")}>
            {["all", "constrained", "available", "incomplete"].map((value) => (
              <button key={value} type="button" className={posture === value ? "active" : ""} onClick={() => { setPosture(value); resetPage(); }}>
                {t(`capacity.${value}`)}
              </button>
            ))}
          </div>
        </div>
        <div className="capacity-kpi-strip">
          <div><span>{t("capacity.monitored_directions")}</span><strong>{operatingRows.length}</strong></div>
          <div className={constrainedCount > 0 ? "issue" : ""}><span>{t("capacity.constrained")}</span><strong>{constrainedCount}</strong></div>
          <div className={incompleteCount > 0 ? "warning" : ""}><span>{t("capacity.incomplete")}</span><strong>{incompleteCount}</strong></div>
          <div><span>{t("capacity.tso_coverage")}</span><strong>{operators.length}</strong></div>
          <div><span>{t("capacity.latest_update")}</span><strong>{latestOperationalAt ? new Date(latestOperationalAt).toLocaleString() : "n/a"}</strong></div>
        </div>
      </div>

      <div className="workspace-panel span-2 capacity-board-panel">
        <div className="panel-title-row"><h3>{t("capacity.operating_board")}</h3><span>{filteredRows.length} / {operatingRows.length}</span></div>
        <div className="capacity-operating-table" role="table">
          <div className="capacity-operating-row header" role="row">
            <span>{t("panel.point")}</span><span>TSO</span><span>{t("panel.direction")}</span><span>{t("capacity.flow")}</span><span>{t("panel.capacity")}</span><span>{t("capacity.utilization")}</span><span>{t("capacity.headroom")}</span>
          </div>
          {visibleRows.map((row) => (
            <button key={row.key} type="button" className={selected?.key === row.key ? "capacity-operating-row active" : "capacity-operating-row"} onClick={() => setSelectedKey(row.key)}>
              <span><strong>{row.pointName}</strong><small>{row.country}</small></span>
              <span>{row.operator}</span>
              <span>{row.direction}</span>
              <span>{formatNumber(row.flowMcmD)}</span>
              <span>{formatNumber(row.capacityMcmD)}</span>
              <span className={`capacity-utilization-cell ${(row.utilizationPct ?? 0) >= 85 ? "utilization-critical" : ""}`}>
                <span>{formatNumber(row.utilizationPct, 1)}{row.utilizationPct === null ? "" : "%"}</span>
                {row.utilizationPct !== null && (
                  <span className="capacity-utilization-track" aria-hidden="true">
                    <span style={{ width: `${Math.min(row.utilizationPct, 100)}%` }} />
                  </span>
                )}
              </span>
              <span>{formatNumber(row.headroomMcmD)}</span>
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
      </div>

      <div className="workspace-panel capacity-point-inspector">
        <div className="panel-title-row"><h3>{t("capacity.point_inspector")}</h3><span>{selected?.freshness ?? "n/a"}</span></div>
        {selected ? (
          <>
            <div className="capacity-point-heading">
              <div><strong>{selected.pointName}</strong><span className={`capacity-readiness capacity-readiness-${selectedReadiness}`}>{t(`capacity.${selectedReadiness}`)}</span></div>
              <span>{selected.country} / {selected.operator}</span>
            </div>
            <p className="capacity-readiness-note">{t(`capacity.readiness_${selectedReadiness}`)}</p>
            <dl className="capacity-point-metrics">
              <div><dt>{t("capacity.utilization")}</dt><dd>{formatNumber(selected.utilizationPct, 1)}{selected.utilizationPct === null ? "" : "%"}</dd></div>
              <div><dt>{t("capacity.headroom")}</dt><dd>{formatNumber(selected.headroomMcmD)} mcm/d</dd></div>
              <div><dt>{t("capacity.products")}</dt><dd>{selectedAccess.length}</dd></div>
              <div><dt>{t("panel.tariffs")}</dt><dd>{selectedTariffs.length}</dd></div>
            </dl>
            <div className="capacity-inspector-section">
              <span>{t("capacity.booking_products")}</span>
              {selectedAccess.slice(0, 5).map((row) => (
                <div key={row.access_id}><strong>{row.direction}</strong><span>{row.booking_platform ?? "n/a"}</span><small>{row.day_ahead_contracts_available ? t("capacity.day_ahead_available") : t("capacity.day_ahead_unavailable")}</small></div>
              ))}
              {selectedAccess.length === 0 && <p>{t("capacity.no_access_record")}</p>}
            </div>
            <div className="capacity-inspector-section">
              <span>{t("capacity.tariffs")}</span>
              {selectedTariffs.slice(0, 5).map((row) => (
                <div key={row.tariff_id}><strong>{row.capacity_product}</strong><span>{row.tariff_value.toFixed(4)} {row.currency}/{row.unit}</span><small>{row.effective_from}</small></div>
              ))}
              {selectedTariffs.length === 0 && <p>{t("capacity.no_tariff_record")}</p>}
            </div>
          </>
        ) : <div className="capacity-empty-state">{t("capacity.no_matching_points")}</div>}
      </div>

      <div className="workspace-panel span-3 capacity-assets-panel">
        <div className="panel-title-row"><h3>{t("capacity.storage_lng")}</h3><span>GIE AGSI / ALSI</span></div>
        <div className="capacity-asset-tables">
          <div className="data-table">
            <div className="data-table-row header four"><span>{t("panel.storage")}</span><span>{t("panel.country")}</span><span>{t("capacity.fill")}</span><span>{t("capacity.inventory")}</span></div>
            {storage.slice(0, 8).map((row) => <div key={row.observation_id} className="data-table-row four"><strong>{row.facility_name}</strong><span>{row.country ?? "n/a"}</span><span>{formatNumber(row.fill_pct, 1)}%</span><span>{formatNumber(row.inventory_twh)} TWh</span></div>)}
          </div>
          <div className="data-table">
            <div className="data-table-row header four"><span>{t("panel.lng")}</span><span>{t("panel.country")}</span><span>{t("capacity.send_out")}</span><span>DTMI</span></div>
            {lng.slice(0, 8).map((row) => <div key={row.observation_id} className="data-table-row four"><strong>{row.terminal_name}</strong><span>{row.country ?? "n/a"}</span><span>{formatNumber(row.send_out_twh_d)} TWh/d</span><span>{formatNumber(row.dtmi_pct, 1)}%</span></div>)}
          </div>
        </div>
      </div>
    </div>
  );
}
