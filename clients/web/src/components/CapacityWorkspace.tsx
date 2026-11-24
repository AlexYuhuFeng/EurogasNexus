import { useMemo, useState } from "react";
import { displayTime } from "@/app/time/displayTime";
import { DataGrid, EvidenceBlock, Segmented, type DataGridColumn, type SortState } from "@/components/ui";
import { sortRows } from "@/components/ui/dataGridModel";
import type { CapacityOperatingBoardReadSurface } from "@/app/model/capacityOperatingBoardRead";
import { inspectorSubjectFor } from "@/app/model/inspectorDetail";
import { useInspectorStore } from "@/stores/inspector";
import type {
  CapacityObsDTO,
  FlowObsDTO,
  LngObsDTO,
  StorageObsDTO,
  TsoAccessPointDTO,
  TsoTariffDTO,
} from "@/api/client";
import { formatMeasure } from "@/app/time/valueFormat";

type Translate = (key: string) => string;
type CapacityView = "network" | "storage" | "lng";
type CapacityPosture = "all" | "constrained" | "available" | "stale" | "incomplete";
type CapacitySort = "attention" | "utilization" | "headroom" | "point";

export interface CapacityWorkspaceProps {
  flows: FlowObsDTO[];
  capacity: CapacityObsDTO[];
  tsoAccess: TsoAccessPointDTO[];
  tsoTariffs: TsoTariffDTO[];
  storage: StorageObsDTO[];
  lng: LngObsDTO[];
  /**
   * The operating board's own read state, derived by the cockpit from the store's facts
   * (`app/model/capacityOperatingBoardRead.ts`): the board joins two reads, so it states which of
   * them answered instead of presenting a joined zero.
   */
  boardRead: CapacityOperatingBoardReadSurface;
  /** The store's existing bounded retry, offered for this board's own reads. */
  onRetryBoardRead: () => void;
  t: Translate;
  /**
   * The Network panel's filter (the map selection, or the map's view with "Follow map"): a
   * point outside it is not listed. Omitted, every point is.
   */
  scope?: (row: OperatingRow) => boolean;
  /** The point selected on the page (shared with the map), and how a row selects or hovers. */
  selectedKey?: string | null;
  onSelectPoint?: (row: OperatingRow | null) => void;
}

export interface OperatingRow {
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
  capacityObservationId: string | null;
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
  return displayTime(value);
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

export function buildOperatingRows(
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
      // The observation the point's figures were read from, when the runtime served one:
      // the Inspector needs a reference, not the derived row.
      capacityObservationId: representative?.observation_id ?? null,
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

/**
 * What the board knows about its own two reads, stated in the board.
 *
 * A failure renders whenever a required read did not answer, and the unread/pending states render
 * while no reading exists at all - the same rule the Source Center's registry notice follows. The
 * KPI strip, the row count and the filter sentence are drawn only for a measured board (both
 * required reads answered), so a read that did not answer is never presented as a board of zero;
 * rows the answered read holds stay on screen with the incompleteness stated. The failure keeps
 * the shared endpoint vocabulary and the store's bounded retry, disabled exactly while an attempt
 * is in flight.
 */
export function CapacityBoardStateNotice({
  read,
  t,
  onRetry,
}: {
  read: CapacityOperatingBoardReadSurface;
  t: Translate;
  onRetry: () => void;
}) {
  const failed = read.state === "failed" || read.state === "partial";
  if (!failed && read.hasReading) return null;
  if (read.noticeKey === null) return null;
  return (
    <div
      className={failed ? "capacity-board-state is-failed" : "capacity-board-state"}
      data-capacity-notice={read.state}
      role={failed ? "alert" : "status"}
    >
      <strong>{t("capacity.board.title")}</strong>
      <p>{t(read.noticeKey)}</p>
      {failed && (
        <p className="capacity-board-vocabulary">
          {read.failedReads
            .map((failedRead) => `${t(failedRead.labelKey)} · ${t(failedRead.messageKey)}`)
            .join(" · ")}
        </p>
      )}
      {failed && (
        <div className="capacity-board-retry">
          <button
            type="button"
            data-capacity-board-retry="true"
            disabled={read.retry.disabled}
            aria-busy={read.retry.busy}
            onClick={onRetry}
          >
            {t("capacity.board.retry")}
          </button>
          {(read.retry.busy || read.retry.attempts > 0) && (
            <span className="capacity-board-retry-meta">
              {read.retry.attemptsLabel}
              {read.retry.lastAttemptLabel ? ` · ${read.retry.lastAttemptLabel}` : ""}
              {read.retry.runningLabel ? ` · ${read.retry.runningLabel}` : ""}
            </span>
          )}
        </div>
      )}
    </div>
  );
}

export function CapacityWorkspace({
  flows,
  capacity,
  tsoAccess,
  tsoTariffs,
  storage,
  lng,
  boardRead,
  onRetryBoardRead,
  t,
  scope,
  selectedKey = null,
  onSelectPoint,
}: CapacityWorkspaceProps) {
  const inspector = useInspectorStore();
  const [activeView, setActiveView] = useState<CapacityView>("network");
  const [query, setQuery] = useState("");
  const [country, setCountry] = useState("all");
  const [operator, setOperator] = useState("all");
  const [posture, setPosture] = useState<CapacityPosture>("all");
  const [sort, setSort] = useState<CapacitySort>("attention");
  // A column the user sorted by; choosing a preset order clears it.
  const [columnSort, setColumnSort] = useState<SortState | null>(null);
  const [page, setPage] = useState(0);

  const allRows = useMemo(
    () => buildOperatingRows(flows, capacity, tsoAccess),
    [capacity, flows, tsoAccess],
  );
  // The panel's own scope (map selection or view) first; the board's filters inside it.
  const operatingRows = useMemo(() => (scope ? allRows.filter(scope) : allRows), [allRows, scope]);
  const countries = useMemo(
    () => [...new Set(operatingRows.map((row) => row.country).filter((value) => value !== "n/a"))].sort(),
    [operatingRows],
  );
  const operators = useMemo(
    () => [...new Set(operatingRows.map((row) => row.operator).filter((value) => value !== "n/a"))].sort(),
    [operatingRows],
  );
  const columns = useMemo<DataGridColumn<OperatingRow>[]>(
    () => [
      {
        id: "point",
        header: t("panel.point"),
        rowHeader: true,
        sortable: true,
        value: (row) => row.pointName,
        render: (row) => (
          <span className="network-panel-cell-stack">
            <strong>{row.pointName}</strong>
            <small>{[row.direction, row.operator !== "n/a" ? row.operator : null].filter(Boolean).join(" · ")}</small>
          </span>
        ),
      },
      { id: "flow", header: t("capacity.flow"), unit: "mcm/d", type: "number", sortable: true, value: (row) => row.flowMcmD, format: (value) => formatCell(value) },
      { id: "technical", header: t("capacity.technical"), unit: "mcm/d", type: "number", sortable: true, value: (row) => row.technicalCapacityMcmD, format: (value) => formatCell(value) },
      {
        id: "utilization",
        header: t("capacity.utilization"),
        unit: "%",
        type: "number",
        sortable: true,
        value: (row) => row.utilizationPct,
        format: (value) => formatCell(value, 0),
        cellClassName: (row) => ((row.utilizationPct ?? 0) >= 85 ? "utilization-critical" : undefined),
      },
      { id: "headroom", header: t("capacity.headroom_short"), unit: "mcm/d", type: "number", sortable: true, value: (row) => row.physicalHeadroomMcmD, format: (value) => formatCell(value) },
      {
        id: "posture",
        header: t("capacity.posture"),
        value: (row) => row.posture,
        render: (row) => <span className={`capacity-readiness capacity-readiness-${row.posture}`}>{t(`capacity.${row.posture}`)}</span>,
      },
    ],
    [t],
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
    const preset = sortOperatingRows(matching, sort);
    if (!columnSort) return preset;
    const column = columns.find((item) => item.id === columnSort.columnId);
    return sortRows(preset, column?.value, columnSort.direction);
  }, [columnSort, columns, country, operatingRows, operator, posture, query, sort]);

  const pageCount = Math.max(Math.ceil(filteredRows.length / PAGE_SIZE), 1);
  const activePage = Math.min(page, pageCount - 1);
  const pageStart = activePage * PAGE_SIZE;
  const visibleRows = filteredRows.slice(pageStart, pageStart + PAGE_SIZE);
  const filtersApplied =
    query.trim() !== "" || country !== "all" || operator !== "all" || posture !== "all";
  // A filter claim is made only for a fully measured board, and a measured board whose two reads
  // served no row states that instead: "the filters matched nothing" and "the runtime served
  // nothing" are different answers, and a read that did not answer is neither.
  const boardEmptyState = !boardRead.hasReading
    ? null
    : allRows.length === 0
      ? { key: "capacity.board.empty", marker: "capacity-operating-points" }
      // Points exist, none in the panel's scope (the map's view or selection).
      : operatingRows.length === 0
        ? { key: "network.panel.none_in_view", marker: "capacity-none-in-scope" }
        : boardRead.measured && filtersApplied && filteredRows.length === 0
        ? { key: "capacity.no_matching_points", marker: "capacity-filter-no-match" }
        : null;
  // The runtime served no point at all: filters, zero counts and an empty inspector would only
  // repeat that, so the board is one line until data arrives (#69).
  const boardEmpty = boardRead.measured && allRows.length === 0;
  // The point inspector shows the point chosen on the page (a row, or the map), never a
  // first row standing in for one.
  const selected = selectedKey ? allRows.find((row) => row.key === selectedKey) ?? null : null;
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

  // The filter, sort and page markers are nonvisual evidence: the acceptance sweep captures the
  // context this board was compared under instead of driving its controls (readToRender.mjs).
  return (
    <div
      className="capacity-page capacity-operations capacity-in-panel"
      data-capacity-read-state={boardRead.state}
      data-capacity-board-filters={filtersApplied ? "applied" : "none"}
      data-capacity-board-sort={sort}
    >
      {/* Points, storage and LNG: one choice inside the Capacity tab, not tabs inside tabs. */}
      <Segmented
        className="capacity-view-control"
        label={t("capacity.views")}
        options={(["network", "storage", "lng"] as CapacityView[]).map((view) => ({ value: view, label: t(`capacity.view_${view}`) }))}
        value={activeView}
        onChange={setActiveView}
      />

      {activeView === "network" && selected && (
        <section className="capacity-point-inspector" aria-label={t("capacity.point_inspector")} data-capacity-point={selected.key}>
          <div className="capacity-point-heading">
            <div>
              <strong>{selected.pointName}</strong>
              <span className={`capacity-readiness capacity-readiness-${selected.posture}`}>{t(`capacity.${selected.posture}`)}</span>
            </div>
            <span>{selected.country} · {selected.operator} · {selected.direction} · {formatTimestamp(selected.observedAtUtc)}</span>
            <p className="capacity-readiness-note">{t(`capacity.readiness_${selected.posture}`)}</p>
            <span className="capacity-point-actions">
              {/* Wave 9: the panel keeps its aggregate analysis (utilisation, booking,
                  headroom, access and tariffs); the point's own observation record is
                  handed to the canonical Inspector rather than shown a second time. */}
              {selected?.capacityObservationId && (
                <button
                  type="button"
                  className="link-button"
                  onClick={() => {
                    const subject = inspectorSubjectFor(
                      "capacity",
                      selected.capacityObservationId,
                      selected.pointName,
                      "capacity",
                    );
                    if (subject) inspector.open(subject);
                  }}
                >
                  {t("capacity.inspect_point")}
                </button>
              )}
              {onSelectPoint && (
                <button type="button" className="link-button" onClick={() => onSelectPoint(null)}>
                  {t("network.panel.clear")}
                </button>
              )}
            </span>
          </div>
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
              <div key={row.tariff_id}><strong>{row.capacity_product}</strong><span>{formatMeasure("tariff", row.tariff_value, { unit: `${row.currency}/${row.unit}` })}</span><small>{row.effective_from} · {row.tariff_status}</small></div>
            ))}
            {selectedTariffs.length === 0 && <p>{t("capacity.no_tariff_record")}</p>}
          </div>
          {/* Provenance on demand. */}
          <details className="network-panel-provenance">
            <summary>{t("capacity.source_record")}</summary>
            <EvidenceBlock
              className="capacity-evidence-block"
              ariaLabel={t("capacity.source_record")}
              items={[
                {
                  label: t("capacity.source_record"),
                  value: selected.sourceReference ?? t("data.unavailable"),
                },
                {
                  label: t("capacity.latest_update"),
                  value: formatTimestamp(selected.observedAtUtc),
                },
                {
                  label: t("capacity.posture"),
                  value: t(`capacity.${selected.posture}`),
                  detail: t(`capacity.readiness_${selected.posture}`),
                },
              ]}
            />
          </details>
        </section>
      )}

      {/* A measured empty board still states its measurement, in one line: the runtime
          answered with no point, which is not the same as a read that did not answer. */}
      {activeView === "network" && boardEmpty && (
        <div className="capacity-kpi-strip metric-inline">
          <div><span>{t("capacity.physical_flow_records")}</span><strong>{counts.flowPublished}</strong></div>
          <div><span>{t("capacity.technical_records")}</span><strong>{counts.technicalPublished}</strong></div>
          <div><span>{t("capacity.latest_update")}</span><strong>{formatTimestamp(latestOperationalAt)}</strong></div>
        </div>
      )}
      {activeView === "network" && !boardEmpty && (
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
            <select value={sort} onChange={(event) => { setSort(event.target.value as CapacitySort); setColumnSort(null); }} aria-label={t("capacity.sort_by")}>
              {(["attention", "utilization", "headroom", "point"] as CapacitySort[]).map((value) => <option key={value} value={value}>{t(`capacity.sort_${value}`)}</option>)}
            </select>
          </div>
          <Segmented
            className="capacity-posture-control"
            label={t("capacity.posture")}
            options={(["all", "constrained", "available", "stale", "incomplete"] as CapacityPosture[]).map((value) => ({ value, label: t(`capacity.${value}`) }))}
            value={posture}
            onChange={(value) => { setPosture(value); resetPage(); }}
          />
          {/* Counts and their latest-update instant are a measurement of both required reads:
              one that has not answered is not a zero, and the rows held from one read are not
              the joined board. */}
          {boardRead.measured && (
          <div className="capacity-kpi-strip">
            <div className={counts.constrained > 0 ? "issue" : ""}><span>{t("capacity.constrained")}</span><strong>{counts.constrained}</strong></div>
            <div><span>{t("capacity.comparable_records")}</span><strong>{counts.complete}</strong></div>
            <div className={counts.incomplete > 0 ? "warning" : ""}><span>{t("capacity.incomplete")}</span><strong>{counts.incomplete}</strong></div>
            <div><span>{t("capacity.latest_update")}</span><strong>{formatTimestamp(latestOperationalAt)}</strong></div>
          </div>
          )}
          {boardRead.measured && counts.complete === 0 && operatingRows.length > 0 && (
            <div className="capacity-data-warning" role="status">
              <strong>{t("capacity.no_comparable_title")}</strong>
              <span>{t("capacity.no_comparable_body")}</span>
            </div>
          )}
        </>
      )}

      {activeView === "network" && (
        <section className="capacity-board-panel" aria-label={t("capacity.operating_board")}>
          <CapacityBoardStateNotice read={boardRead} t={t} onRetry={onRetryBoardRead} />
          {boardRead.measured && (
            <span
              className="visually-hidden"
              data-capacity-board-count={`${filteredRows.length}/${operatingRows.length}`}
              // Points the panel's scope (map view or selection) leaves out of the board.
              data-capacity-board-scoped-out={allRows.length - operatingRows.length}
            >
              {filteredRows.length} / {operatingRows.length}
            </span>
          )}
          {boardRead.hasReading && visibleRows.length > 0 && (
            <div className="capacity-operating-table">
              <DataGrid
                id="capacity-points"
                label={t("capacity.operating_board")}
                columns={columns}
                rows={visibleRows}
                rowKey={(row) => row.key}
                density="compact"
                sort={columnSort}
                onSortChange={setColumnSort}
                selectedKey={selectedKey}
                onRowAction={(row) => onSelectPoint?.(row)}
                rowAttributes={(row) => ({ "data-record": "capacity-point", "data-record-id": row.key, "data-panel-row": row.key })}
              />
            </div>
          )}
          {boardEmptyState && (
            <div className="capacity-empty-state" data-empty-state={boardEmptyState.marker}>
              {t(boardEmptyState.key)}
            </div>
          )}
          {filteredRows.length > PAGE_SIZE && (
            <div
              className="capacity-pagination"
              aria-label={t("capacity.pagination")}
              data-capacity-page-start={pageStart}
            >
              <span>{t("capacity.showing")} {pageStart + 1}-{Math.min(pageStart + PAGE_SIZE, filteredRows.length)} {t("capacity.of")} {filteredRows.length}</span>
              <div>
                <button type="button" onClick={() => setPage(Math.max(activePage - 1, 0))} disabled={activePage === 0}>{t("capacity.previous")}</button>
                <strong>{activePage + 1} / {pageCount}</strong>
                <button type="button" onClick={() => setPage(Math.min(activePage + 1, pageCount - 1))} disabled={activePage >= pageCount - 1}>{t("capacity.next")}</button>
              </div>
            </div>
          )}
        </section>
      )}

      {activeView === "storage" && (
        <section className="capacity-assets-panel" aria-label={t("capacity.storage_title")}>
          <div className="capacity-kpi-strip capacity-asset-kpis">
            <div><span>{t("capacity.storage_sites")}</span><strong>{latestStorage.length}</strong></div>
            <div><span>{t("capacity.average_fill")}</span><strong>{storageFillValues.length ? `${formatNumber(storageFillValues.reduce((a, b) => a + b, 0) / storageFillValues.length, 1)}%` : "n/a"}</strong></div>
            <div><span>{t("capacity.total_inventory")}</span><strong>{formatNumber(storageInventory)} TWh</strong></div>
            <div><span>{t("capacity.latest_update")}</span><strong>{formatTimestamp(latestTimestamp(...latestStorage.map((row) => row.observed_at_utc)))}</strong></div>
          </div>
          <DataGrid
            id="capacity-storage"
            label={t("capacity.storage_title")}
            density="compact"
            rows={latestStorage}
            rowKey={(row) => row.observation_id}
            defaultSort={{ columnId: "inventory", direction: "descending" }}
            columns={[
              { id: "site", header: t("panel.storage"), rowHeader: true, sortable: true, value: (row) => row.facility_name },
              { id: "country", header: t("panel.country"), sortable: true, value: (row) => row.country ?? "" },
              { id: "fill", header: t("capacity.fill"), unit: "%", type: "number", sortable: true, value: (row) => row.fill_pct, format: (value) => formatCell(value, 1) },
              { id: "inventory", header: t("capacity.inventory"), unit: "TWh", type: "number", sortable: true, value: (row) => row.inventory_twh, format: (value) => formatCell(value) },
              { id: "net", header: t("capacity.net_cycle"), unit: "TWh/d", type: "number", sortable: true, value: (row) => (row.injection_twh_d ?? 0) - (row.withdrawal_twh_d ?? 0), format: (value) => formatCell(value) },
            ]}
          />
          <p className="network-panel-source">GIE AGSI · {t("capacity.storage_note")}</p>
        </section>
      )}

      {activeView === "lng" && (
        <section className="capacity-assets-panel" aria-label={t("capacity.lng_title")}>
          <div className="capacity-kpi-strip capacity-asset-kpis">
            <div><span>{t("capacity.lng_terminals")}</span><strong>{latestLng.length}</strong></div>
            <div><span>{t("capacity.total_inventory")}</span><strong>{formatNumber(lngInventory)} TWh</strong></div>
            <div><span>{t("capacity.total_send_out")}</span><strong>{formatNumber(lngSendOut)} TWh/d</strong></div>
            <div><span>{t("capacity.total_dtmi")}</span><strong>{formatNumber(lngDtmi)} TWh</strong></div>
          </div>
          <DataGrid
            id="capacity-lng"
            label={t("capacity.lng_title")}
            density="compact"
            rows={latestLng}
            rowKey={(row) => row.observation_id}
            defaultSort={{ columnId: "sendout", direction: "descending" }}
            columns={[
              { id: "terminal", header: t("panel.lng"), rowHeader: true, sortable: true, value: (row) => row.terminal_name },
              { id: "country", header: t("panel.country"), sortable: true, value: (row) => row.country ?? "" },
              { id: "inventory", header: t("capacity.inventory"), unit: "TWh", type: "number", sortable: true, value: (row) => row.inventory_twh, format: (value) => formatCell(value) },
              { id: "sendout", header: t("capacity.send_out"), unit: "TWh/d", type: "number", sortable: true, value: (row) => row.send_out_twh_d, format: (value) => formatCell(value) },
              { id: "dtmi", header: "DTMI", unit: "TWh", type: "number", sortable: true, value: (row) => row.dtmi_twh, format: (value) => formatCell(value) },
            ]}
          />
          <p className="network-panel-source">GIE ALSI · {t("capacity.lng_note")}</p>
        </section>
      )}

    </div>
  );
}

/** A figure cell: "–" when missing, grouped thousands, fixed decimals. */
function formatCell(value: unknown, digits = 1): string {
  return typeof value === "number" && Number.isFinite(value)
    ? value.toLocaleString("en-GB", { maximumFractionDigits: digits, minimumFractionDigits: digits })
    : "–";
}
