/**
 * The Network page's information panel, beside the map (Desk → Network).
 *
 * Tabs: Outages (default) · Capacity · Flows, and Our book in the "Our book" map view for a
 * caller with book permission. One selection links panel and map (app/model/networkPanelModel):
 * a row focuses the map on its object, an object chosen on the map filters the lists, and
 * "Follow map" keeps the lists to the map's view. The selected object's detail sits at the top
 * of the panel, above its rows: one place for object detail.
 */
import { useEffect, useMemo, useState, type MouseEvent, type ReactNode } from "react";

import { api, type MapPointFlowDTO, type MapSituationDTO, type OutageEventDTO } from "@/api/client";
import {
  compareOutages,
  panelFilter,
  type LonLat,
  type MapBounds,
  type NetworkPanelTab,
  type OutageListRow,
  type OutageState,
  type SelectionScope,
  outageListRows,
} from "@/app/model/networkPanelModel";
import { timeWindow } from "@/app/model/todayModel";
import { CapacityWorkspace, buildOperatingRows, type CapacityWorkspaceProps, type OperatingRow } from "@/components/CapacityWorkspace";
import { DataGrid, Segmented, StatusBadge, WorkspaceTabs, type DataGridColumn } from "@/components/ui";
import { ReportLink } from "@/components/ReportLink";
import { WhyButton } from "@/components/WhyButton";

type Translate = (key: string, options?: Record<string, unknown>) => string;

/** How far back "Ended recently" reaches. */
export const OUTAGE_ENDED_DAYS = 7;
const OUTAGE_HORIZON_DAYS = 90;

export interface PanelRowRef {
  tab: NetworkPanelTab;
  key: string;
}

/** What a row hands the map: the object to select, else the place to fly to. */
export interface PanelRowTarget {
  refId: string | null;
  at: LonLat | null;
}

type CapacityData = Omit<CapacityWorkspaceProps, "t" | "scope" | "selectedKey" | "onSelectPoint">;

interface NetworkInfoPanelProps {
  t: Translate;
  language: string;
  tab: NetworkPanelTab;
  onTab: (tab: NetworkPanelTab) => void;
  showBookTab: boolean;
  situation: MapSituationDTO | null;
  /** Resolves a network point by id or name (capacity points carry no position of their own). */
  locatePoint: (pointId: string, pointName: string) => { at: LonLat | null; refId: string | null; country: string | null };
  scope: SelectionScope | null;
  onClearScope: () => void;
  followMap: boolean;
  onFollowMap: (on: boolean) => void;
  bounds: MapBounds | null;
  /** The selected map object's card (MapDetailPanel), shown above the rows. */
  detail: ReactNode;
  selectedRow: PanelRowRef | null;
  onSelectRow: (row: PanelRowRef | null, target: PanelRowTarget | null) => void;
  onHoverRow: (at: LonLat | null) => void;
  capacity: CapacityData;
  book: ReactNode;
  footer: ReactNode;
}

/** The outage list: one row per event, from the server's grouping. */
function useOutageEvents() {
  const [events, setEvents] = useState<OutageEventDTO[] | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let live = true;
    api
      .outages(OUTAGE_HORIZON_DAYS, undefined, { grouped: true, endedDays: OUTAGE_ENDED_DAYS })
      .then((response) => {
        if (!live) return;
        setEvents(Array.isArray(response.data) ? response.data : []);
        setNote(response.meta?.warnings?.[0] ?? null);
      })
      .catch((caught: unknown) => live && setError(caught instanceof Error ? caught.message : String(caught)));
    return () => {
      live = false;
    };
  }, []);
  return { events, note, error };
}

type OutageFilter = "live" | OutageState;

function figure(value: number | null, digits = 1): string {
  return value === null || !Number.isFinite(value)
    ? "–"
    : value.toLocaleString("en-GB", { maximumFractionDigits: digits, minimumFractionDigits: digits });
}

export function NetworkInfoPanel({
  t,
  language,
  tab,
  onTab,
  showBookTab,
  situation,
  locatePoint,
  scope,
  onClearScope,
  followMap,
  onFollowMap,
  bounds,
  detail,
  selectedRow,
  onSelectRow,
  onHoverRow,
  capacity,
  book,
  footer,
}: NetworkInfoPanelProps) {
  const { events, note, error } = useOutageEvents();
  const [outageFilter, setOutageFilter] = useState<OutageFilter>("live");
  const nowMs = Date.now();

  /* ---------------------------------------------------------------- rows and filters */
  const outageRows = useMemo(
    () => (events ? outageListRows(events, situation).sort(compareOutages) : []),
    [events, situation],
  );
  const scopedOutages = useMemo(
    () =>
      panelFilter(outageRows, {
        scope,
        followMap,
        bounds,
        describe: (row) => ({ at: row.at, refId: row.refId, name: row.asset, country: row.country, zone: row.zone }),
      }),
    [bounds, followMap, outageRows, scope],
  );
  const shownOutages = scopedOutages.filter((row) => (outageFilter === "live" ? row.state !== "ended" : row.state === outageFilter));

  const describePoint = useMemo(() => {
    const cache = new Map<string, ReturnType<typeof locatePoint>>();
    return (pointId: string, pointName: string) => {
      const key = `${pointId}|${pointName}`;
      let hit = cache.get(key);
      if (!hit) {
        hit = locatePoint(pointId, pointName);
        cache.set(key, hit);
      }
      return hit;
    };
  }, [locatePoint]);
  const pointFacts = (row: OperatingRow) => {
    const place = describePoint(row.pointId, row.pointName);
    return { at: place.at, refId: place.refId, name: row.pointName, country: place.country ?? (row.country !== "n/a" ? row.country : null) };
  };
  const capacityScope = useMemo(() => {
    const allowed = new Set(
      panelFilter(buildOperatingRows(capacity.flows, capacity.capacity, capacity.tsoAccess), {
        scope,
        followMap,
        bounds,
        describe: pointFacts,
      }).map((row) => row.key),
    );
    return { allowed, test: (row: OperatingRow) => allowed.has(row.key) };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [bounds, capacity.capacity, capacity.flows, capacity.tsoAccess, describePoint, followMap, scope]);

  const flowRows = useMemo(
    () =>
      panelFilter(situation?.flows ?? [], {
        scope,
        followMap,
        bounds,
        describe: (row) => ({
          at: [row.location.lon, row.location.lat] as LonLat,
          refId: row.location.ref_id ?? null,
          name: row.point_name,
          country: row.location.country ?? null,
        }),
      }),
    [bounds, followMap, scope, situation],
  );

  /* ---------------------------------------------------------------- columns */
  const outageColumns = useMemo<DataGridColumn<OutageListRow>[]>(
    () => [
      {
        id: "asset",
        header: t("outages.asset"),
        rowHeader: true,
        sortable: true,
        value: (row) => row.asset,
        cellTitle: (row) => [row.reason, row.messages.length > 1 ? `${t("outages.messages_count", { count: row.messages.length })}: ${row.messages.join(", ")}` : row.eventId].filter(Boolean).join("\n"),
        render: (row) => (
          <span className="network-panel-cell-stack">
            <span className="network-panel-title-line">
              <StatusBadge tone={row.state === "active" ? "watch" : "neutral"}>{t(`outages.state.${row.state}`)}</StatusBadge>
              <strong>{row.asset}</strong>
            </span>
            <small>
              {[row.zone, row.operators.join(" · "), t(`outages.type_${row.eventType}`, { defaultValue: row.eventType })].filter(Boolean).join(" · ")}
            </small>
            {row.placement !== "placed" && (
              <small className="network-panel-placement" data-outage-placement={row.placement}>
                {t(`outages.placement.${row.placement}`)}
              </small>
            )}
          </span>
        ),
      },
      {
        id: "offline",
        header: t("outages.offline"),
        unit: "GWh/d",
        type: "number",
        sortable: true,
        value: (row) => row.gwhD,
        format: (value) => figure(typeof value === "number" ? value : null),
        cellTitle: (row) => (row.gwhD === null && row.published ? t("outages.published", { value: row.published }) : undefined),
        state: (row) => (row.simulated ? { kind: "simulated", label: t("today.simulated_short"), description: t("today.simulated_long") } : null),
        width: "10ch",
      },
      {
        id: "period",
        header: t("outages.period"),
        type: "date",
        sortable: true,
        value: (row) => row.startUtc,
        // Two lines: the start, then the end, so a multi-year window keeps its years visible.
        format: (_, row) => {
          const [from, to] = timeWindow(row.startUtc, row.endUtc, nowMs).split(" – ");
          return (
            <span className="network-panel-cell-stack network-panel-period">
              <span>{from}</span>
              <span>– {to ?? ""}</span>
            </span>
          );
        },
      },
      {
        id: "actions",
        header: <span className="visually-hidden">{t("why.button")}</span>,
        render: (row) => (
          <span className="network-panel-actions network-panel-actions-stack">
            <WhyButton subject="outage" id={row.eventId} label={row.asset} language={language} t={t} />
            <ReportLink subject={{ kind: "outage", id: row.eventId }} label={row.asset} t={t} />
          </span>
        ),
      },
    ],
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [language, t],
  );
  const flowColumns = useMemo<DataGridColumn<MapPointFlowDTO>[]>(
    () => [
      {
        id: "point",
        header: t("panel.point"),
        rowHeader: true,
        sortable: true,
        value: (row) => row.point_name,
        render: (row) => (
          <span className="network-panel-cell-stack">
            <strong>{row.point_name}</strong>
            <small>{[row.direction, row.operator_key].filter(Boolean).join(" · ")}</small>
          </span>
        ),
      },
      {
        id: "flow",
        header: t("network.panel.flow"),
        unit: "GWh/d",
        type: "number",
        sortable: true,
        value: (row) => row.gwh_d,
        format: (value) => figure(typeof value === "number" ? value : null),
        cellTitle: (row) => (row.gwh_d === null && row.value !== null ? t("outages.published", { value: `${row.value} ${row.unit}` }) : undefined),
        // A simulated flow is marked in its own cell, never read as a measurement.
        state: (row) => (/sim/i.test(row.source_system) ? { kind: "simulated", label: t("today.simulated_short"), description: t("today.simulated_long") } : null),
      },
      { id: "day", header: t("network.panel.gas_day"), type: "date", sortable: true, value: (row) => row.gas_day ?? row.gas_day_start_utc?.slice(0, 10) ?? "" },
    ],
    [t],
  );

  /* ---------------------------------------------------------------- linking */
  const rowKey = (current: NetworkPanelTab) => (selectedRow?.tab === current ? selectedRow.key : null);
  const hover = {
    onMouseOver: (event: MouseEvent<HTMLElement>) => {
      const key = (event.target as HTMLElement).closest("tr[data-panel-row]")?.getAttribute("data-panel-row");
      if (!key) return;
      if (tab === "outages") onHoverRow(outageRows.find((row) => row.key === key)?.at ?? null);
      else if (tab === "flows") {
        const flow = flowRows.find((row) => flowKey(row) === key);
        onHoverRow(flow ? [flow.location.lon, flow.location.lat] : null);
      } else if (tab === "capacity") {
        const point = buildOperatingRows(capacity.flows, capacity.capacity, capacity.tsoAccess).find((row) => row.key === key);
        onHoverRow(point ? describePoint(point.pointId, point.pointName).at : null);
      }
    },
    onMouseLeave: () => onHoverRow(null),
  };

  const counts: Record<NetworkPanelTab, number | null> = {
    outages: events ? scopedOutages.filter((row) => row.state !== "ended").length : null,
    capacity: capacityScope.allowed.size,
    flows: flowRows.length,
    book: null,
  };
  const tabs = (["outages", "capacity", "flows", ...(showBookTab ? (["book"] as const) : [])] as NetworkPanelTab[]).map((id) => ({
    id,
    label: (
      <>
        {t(`network.panel.tab.${id}`)}
        {counts[id] !== null && <span className="network-panel-count" data-panel-count={id}>{counts[id]}</span>}
      </>
    ),
  }));

  return (
    <aside className="network-panel" aria-label={t("network.panel.label")} data-network-panel={tab}>
      <div className="network-panel-head">
        <WorkspaceTabs
          idPrefix="network-panel-tab"
          label={t("network.panel.label")}
          tabs={tabs}
          activeId={tab}
          panelId="network-panel-body"
          className="network-panel-tabs"
          onActivate={onTab}
        />
        <label className="network-panel-follow" title={t("network.panel.follow_map_hint")}>
          <input type="checkbox" checked={followMap} onChange={(event) => onFollowMap(event.target.checked)} data-follow-map={followMap ? "on" : "off"} />
          {t("network.panel.follow_map")}
        </label>
      </div>
      {scope && (
        <p className="network-panel-scope" data-panel-scope={scope.label}>
          <span>{t("network.panel.showing", { name: scope.kind === "zone" ? t("network.panel.zone", { hub: scope.label }) : scope.label })}</span>
          <button type="button" className="network-panel-scope-clear" onClick={onClearScope} aria-label={t("network.panel.clear_selection")} title={t("network.panel.clear_selection")}>
            ×
          </button>
        </p>
      )}
      <div
        id="network-panel-body"
        className="network-panel-body"
        role="tabpanel"
        aria-labelledby={`network-panel-tab-${tab}`}
        tabIndex={0}
        {...hover}
      >
        {detail && <div className="network-panel-detail">{detail}</div>}
        {tab === "outages" && (
          <section className="network-panel-section" aria-label={t("network.panel.tab.outages")}>
            <Segmented
              className="network-panel-filter"
              label={t("outages.filter.label")}
              options={(["live", "active", "scheduled", "ended"] as OutageFilter[]).map((value) => ({
                value,
                label: (
                  <>
                    {t(value === "live" ? "outages.filter.live" : `outages.state.${value}`)}{" "}
                    <span className="network-panel-count">
                      {scopedOutages.filter((row) => (value === "live" ? row.state !== "ended" : row.state === value)).length}
                    </span>
                  </>
                ),
              }))}
              value={outageFilter}
              onChange={setOutageFilter}
            />
            {error && <p role="alert">{error}</p>}
            <DataGrid
              id="network-outages"
              label={t("network.panel.tab.outages")}
              columns={outageColumns}
              rows={shownOutages}
              rowKey={(row) => row.key}
              density="compact"
              loading={events === null && !error}
              defaultSort={{ columnId: "offline", direction: "descending" }}
              selectedKey={rowKey("outages")}
              onRowAction={(row) => onSelectRow({ tab: "outages", key: row.key }, { refId: row.refId, at: row.at })}
              rowAttributes={(row) => ({ "data-record": "outage-row", "data-outage-status": row.state, "data-panel-row": row.key })}
              tableAttributes={{ "data-outages": "true" }}
              empty={events && events.length === 0 ? note ?? t("outages.empty") : t("network.panel.none_in_view")}
            />
          </section>
        )}
        {tab === "capacity" && (
          <CapacityWorkspace
            {...capacity}
            t={t}
            scope={capacityScope.test}
            selectedKey={rowKey("capacity")}
            onSelectPoint={(row) => {
              if (!row) {
                onSelectRow(null, null);
                return;
              }
              const place = describePoint(row.pointId, row.pointName);
              onSelectRow({ tab: "capacity", key: row.key }, { refId: place.refId, at: place.at });
            }}
          />
        )}
        {tab === "flows" && (
          <section className="network-panel-section" aria-label={t("network.panel.tab.flows")}>
            <DataGrid
              id="network-flows"
              label={t("network.panel.tab.flows")}
              columns={flowColumns}
              rows={flowRows}
              rowKey={flowKey}
              density="compact"
              defaultSort={{ columnId: "flow", direction: "descending" }}
              selectedKey={rowKey("flows")}
              onRowAction={(row) =>
                onSelectRow({ tab: "flows", key: flowKey(row) }, { refId: row.location.ref_id ?? null, at: [row.location.lon, row.location.lat] })
              }
              rowAttributes={(row) => ({ "data-record": "flow-point", "data-panel-row": flowKey(row) })}
              empty={situation ? t("network.panel.none_in_view") : t("status.loading")}
            />
            {situation?.flow_rule && <p className="network-panel-source">{situation.flow_rule}</p>}
          </section>
        )}
        {tab === "book" && showBookTab && book}
        <div className="network-panel-footer">{footer}</div>
      </div>
    </aside>
  );
}

function flowKey(row: MapPointFlowDTO): string {
  return `${row.point_id}:${row.direction}:${row.operator_key ?? ""}`;
}
