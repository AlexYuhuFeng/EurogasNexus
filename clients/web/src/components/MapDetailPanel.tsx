import { useEffect } from "react";

import type { EdgeDTO, MapCargoDTO, MapSituationDTO, NodeDTO, NormalizedMarketObsDTO } from "@/api/client";
import {
  cargoVoyage,
  hubPrices,
  hubZone,
  siteFacts,
  sitePipelines,
  siteRoles,
  ZONE_HUB,
  type MapSelection,
  type Site,
} from "@/app/mapSelection";

type Translate = (key: string, options?: Record<string, unknown>) => string;

const n = (value: number | null | undefined, digits = 0) =>
  value == null || !Number.isFinite(value) ? "–" : value.toLocaleString("en-GB", { maximumFractionDigits: digits });

function when(value: string | null | undefined): string {
  if (!value) return "–";
  const date = new Date(value);
  const month = date.toLocaleString("en-GB", { month: "short", timeZone: "UTC" });
  return `${String(date.getUTCDate()).padStart(2, "0")} ${month} ${date.toISOString().slice(11, 16)} UTC`;
}

function Figure({ label, value, unit, hint }: { label: string; value: string; unit?: string; hint?: string }) {
  return (
    <div className="map-detail-figure">
      <span>{label}</span>
      <strong>{value}{unit ? <small> {unit}</small> : null}</strong>
      {hint ? <small className="muted">{hint}</small> : null}
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="map-detail-section">
      <h4>{title}</h4>
      {children}
    </section>
  );
}

function SiteDetail({ site, edges, situation, t }: { site: Site; edges: readonly EdgeDTO[]; situation: MapSituationDTO | null; t: Translate }) {
  const roles = siteRoles(site, edges, situation);
  const facts = siteFacts(site, situation);
  const pipelines = sitePipelines(site, edges);
  const isTerminal = site.members.some((member) => member.type === "lng" || member.type === "lng_terminal");
  return (
    <>
      <header className="map-detail-header">
        <h3>{site.name}</h3>
        <p className="muted">{[facts.operator, site.country].filter(Boolean).join(" · ")}</p>
        <div className="map-detail-roles">
          {roles.map((role) => (
            <span key={`${role.key}:${role.value ?? ""}`} className={`map-role is-${role.tone}`}>
              {t(`map.role.${role.key}`, { value: role.value })}
            </span>
          ))}
        </div>
      </header>
      <div className="map-detail-figures">
        {facts.flowEntryGwhD != null && (facts.flowEntryGwhD > 0 || !facts.flowExitGwhD) && (
          <Figure label={t(isTerminal ? "map.detail.send_out" : "map.detail.flow_in")} value={n(facts.flowEntryGwhD)} unit="GWh/d" hint={facts.gasDay ? t("map.detail.gas_day", { day: facts.gasDay.slice(0, 10) }) : undefined} />
        )}
        {facts.flowExitGwhD != null && facts.flowExitGwhD > 0 && (
          <Figure label={t("map.detail.flow_out")} value={n(facts.flowExitGwhD)} unit="GWh/d" hint={facts.gasDay ? t("map.detail.gas_day", { day: facts.gasDay.slice(0, 10) }) : undefined} />
        )}
        {facts.capacityGwhD != null && (
          <Figure
            label={facts.capacityPoint ? t("map.detail.capacity_at", { point: facts.capacityPoint }) : t(isTerminal ? "map.detail.send_out_capacity" : "map.detail.capacity")}
            value={n(facts.capacityGwhD)}
            unit="GWh/d"
            hint={facts.utilisation != null ? t("map.detail.utilisation", { pct: Math.round(facts.utilisation * 100) }) : undefined}
          />
        )}
        {facts.storageM3 != null && <Figure label={t("map.detail.storage")} value={n(facts.storageM3)} unit="m³ LNG" />}
        {facts.flowEntryGwhD == null && facts.capacityGwhD == null && (
          <p className="muted map-detail-none">{t("map.detail.no_figures")}</p>
        )}
      </div>
      {facts.outages.length > 0 && (
        <Section title={t("map.detail.outages")}>
          {facts.outages.map((outage) => (
            <div key={outage.event_id} className="map-detail-row">
              <span className={`map-role is-${outage.status === "active" ? "alert" : "watch"}`}>{t(`map.situation.outage_${outage.status}`)}</span>
              <strong>{n(outage.unavailable_capacity)} / {n(outage.technical_capacity)} {outage.unit}</strong>
              <small>{when(outage.start_utc)} → {outage.end_utc ? when(outage.end_utc) : t("map.detail.open_ended")}</small>
              {outage.description && <small className="muted">{outage.description}</small>}
            </div>
          ))}
        </Section>
      )}
      {facts.contracts.length > 0 && (
        <Section title={t("map.detail.your_supply")}>
          {facts.contracts.map((contract) => (
            <div key={contract.contract_id} className="map-detail-row">
              <strong>{contract.contract_name}</strong>
              <small>{n(contract.delivery_mwh_d)} MWh/d{contract.entry_capacity_mwh_d != null ? ` · ${t("map.detail.entry_capacity")} ${n(contract.entry_capacity_mwh_d)} MWh/d` : ""}{contract.book_id ? ` · ${contract.book_id}` : ""}</small>
            </div>
          ))}
        </Section>
      )}
      {facts.inbound.length > 0 && (
        <Section title={t("map.detail.inbound")}>
          {facts.inbound.map((cargo) => (
            <div key={cargo.cargo_id} className="map-detail-row">
              <strong>{cargo.vessel_name}{cargo.own ? <span className="map-role is-own">{t("map.situation.own_cargo")}</span> : null}</strong>
              <small>{cargo.load_port} · ETA {when(cargo.eta_utc)} · {cargo.energy_gwh != null ? `${n(cargo.energy_gwh)} GWh` : "–"}</small>
            </div>
          ))}
        </Section>
      )}
      {facts.slots.length > 0 && (
        <Section title={t("map.detail.your_slots")}>
          {facts.slots.map((slot) => (
            <div key={slot.slot_id} className="map-detail-row">
              <strong>{when(slot.window_start_utc)} → {when(slot.window_end_utc)}</strong>
              <small>{slot.send_out_gwh_d != null ? `${n(slot.send_out_gwh_d)} GWh/d` : "–"}{slot.cargo_id ? ` · ${slot.cargo_id}` : ""}</small>
            </div>
          ))}
        </Section>
      )}
      {pipelines.length > 0 && (
        <Section title={t("map.detail.connected")}>
          <p>{pipelines.join(" · ")}</p>
        </Section>
      )}
      <footer className="map-detail-footer muted">
        {facts.flowSource ? t("map.detail.flow_source_short", { source: facts.flowSource }) : t("map.detail.no_flow_source")}
        <br />
        {t("map.node_popup_source")} {[...new Set(site.members.map((member) => member.source).filter(Boolean))].join(", ") || "–"}
        {site.members.some((member) => member.quality === "display_approximation") ? ` · ${t("map.node_popup_approximate_coordinate")}` : ""}
      </footer>
    </>
  );
}

function HubDetail({ hub, rows, situation, nodes, edges, t }: { hub: string; rows: readonly NormalizedMarketObsDTO[]; situation: MapSituationDTO | null; nodes: readonly NodeDTO[]; edges: readonly EdgeDTO[]; t: Translate }) {
  const prices = hubPrices(hub, rows);
  const zone = hubZone(hub, situation, { nodes, edges });
  const countries = Object.entries(ZONE_HUB).filter(([, code]) => code === hub).map(([country]) => country);
  return (
    <>
      <header className="map-detail-header">
        <h3>{hub}</h3>
        <p className="muted">{t("map.detail.hub_subtitle", { zone: countries.join(", ") || "–" })}</p>
      </header>
      <div className="map-detail-figures">
        {prices.map((price) => (
          <Figure
            key={price.tenor}
            label={t(price.tenor === "day-ahead" ? "map.detail.day_ahead" : "map.detail.month_ahead")}
            value={n(price.price, 3)}
            unit={price.unit}
            hint={price.change != null ? `${price.change >= 0 ? "+" : "−"}${n(Math.abs(price.change), 3)} · ${when(price.observedAt)}` : when(price.observedAt)}
          />
        ))}
        {prices.length === 0 && <p className="muted map-detail-none">{t("map.detail.no_prices")}</p>}
      </div>
      <Section title={t("map.detail.zone_today")}>
        <div className="map-detail-row">
          <span className={`map-role is-${zone.outagesNow ? "alert" : "neutral"}`}>{t("map.detail.outages_now", { count: zone.outagesNow })}</span>
          {zone.outagesPlanned > 0 && <span className="map-role is-watch">{t("map.detail.outages_planned", { count: zone.outagesPlanned })}</span>}
          {zone.unavailableGwhD > 0 && <small>{t("map.detail.unavailable", { value: n(zone.unavailableGwhD) })}</small>}
        </div>
        {zone.entryGwhD != null && (
          <div className="map-detail-row">
            <small>{t("map.detail.zone_flows", { entry: n(zone.entryGwhD), exit: n(zone.exitGwhD) })}</small>
          </div>
        )}
        {zone.upstream.map((outage) => (
          <div key={outage.event_id} className="map-detail-row">
            <span className={`map-role is-${outage.status === "active" ? "alert" : "watch"}`}>{t("map.detail.upstream_outage", { name: outage.facility_name })}</span>
            <small>{n(outage.unavailable_capacity)} / {n(outage.technical_capacity)} {outage.unit} · {outage.description || "–"}</small>
          </div>
        ))}
        {zone.contracts > 0 && (
          <div className="map-detail-row">
            <span className="map-role is-own">{t("map.role.own_supply")}</span>
            <small>{t("map.detail.zone_supply", { count: zone.contracts, value: n(zone.supplyMwhD) })}</small>
          </div>
        )}
      </Section>
      <footer className="map-detail-footer muted">
        {prices[0]?.source ? t("map.detail.price_source", { source: prices[0].source }) : t("map.detail.same_as_board")}
      </footer>
    </>
  );
}

function CargoDetail({ cargo, situation, t }: { cargo: MapCargoDTO; situation: MapSituationDTO | null; t: Translate }) {
  const voyage = cargoVoyage(cargo, situation);
  return (
    <>
      <header className="map-detail-header">
        <h3>{cargo.vessel_name}</h3>
        <p className="muted">{cargo.vessel_imo ? `IMO ${cargo.vessel_imo}` : cargo.cargo_id}</p>
        <div className="map-detail-roles">
          <span className={`map-role is-${cargo.own ? "own" : "neutral"}`}>{t(cargo.own ? "map.situation.own_cargo" : "map.situation.market_cargo")}</span>
          <span className="map-role is-neutral">{t(`map.situation.cargo_${cargo.status}`)}</span>
        </div>
      </header>
      <div className="map-detail-voyage">
        <span>{cargo.load_port}</span>
        {voyage.progress != null ? (
          <div className="map-detail-progress" aria-hidden="true">
            <i style={{ width: `${Math.round(voyage.progress * 100)}%` }} />
          </div>
        ) : <span className="muted" aria-hidden="true">→</span>}
        <span>{cargo.destination_terminal ?? t("map.situation.destination_unknown")}</span>
      </div>
      <div className="map-detail-figures">
        <Figure label="ETA" value={when(cargo.eta_utc)} hint={voyage.etaDays == null ? undefined : voyage.etaDays >= 0 ? t("map.detail.in_days", { days: n(voyage.etaDays, 1) }) : t("map.detail.overdue_days", { days: n(-voyage.etaDays, 1) })} />
        <Figure label={t("map.situation.cargo_size")} value={cargo.energy_gwh != null ? n(cargo.energy_gwh) : "–"} unit="GWh" hint={cargo.volume_m3 != null ? `${n(cargo.volume_m3)} m³ LNG` : undefined} />
        {cargo.departed_at_utc && <Figure label={t("map.detail.departed")} value={when(cargo.departed_at_utc)} />}
      </div>
      {voyage.slot && (
        <Section title={t("map.detail.slot_waiting")}>
          <div className="map-detail-row">
            <strong>{voyage.slot.terminal_name}</strong>
            <small>{when(voyage.slot.window_start_utc)} → {when(voyage.slot.window_end_utc)}{voyage.slot.send_out_gwh_d != null ? ` · ${n(voyage.slot.send_out_gwh_d)} GWh/d` : ""}</small>
          </div>
        </Section>
      )}
      <footer className="map-detail-footer muted">
        {t("map.detail.position_at", { at: when(cargo.position_at_utc), source: cargo.source_system })}
        {cargo.status === "laden" && cargo.destination ? ` · ${t("map.situation.indicative_leg")}` : ""}
      </footer>
    </>
  );
}

/**
 * The selected object's card, docked on the map's right edge. One selection at a time;
 * Escape or the close button clears it, as does clicking empty map.
 */
export function MapDetailPanel({
  selection,
  sites,
  edges,
  situation,
  marketRows,
  nodes,
  onClose,
  onInspect,
  t,
}: {
  selection: MapSelection;
  sites: readonly Site[];
  edges: readonly EdgeDTO[];
  situation: MapSituationDTO | null;
  marketRows: readonly NormalizedMarketObsDTO[];
  nodes: readonly NodeDTO[];
  onClose: () => void;
  /** Hand a network point to the canonical Inspector for full detail and provenance. */
  onInspect?: (nodeId: string, label: string) => void;
  t: Translate;
}) {
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  let body: React.ReactNode = null;
  if (selection.kind === "site") {
    const site = sites.find((item) => item.id === selection.id);
    if (site) body = <SiteDetail site={site} edges={edges} situation={situation} t={t} />;
  } else if (selection.kind === "hub") {
    body = <HubDetail hub={selection.id} rows={marketRows} situation={situation} nodes={nodes} edges={edges} t={t} />;
  } else {
    const cargo = situation?.cargoes.find((item) => item.cargo_id === selection.id);
    if (cargo) body = <CargoDetail cargo={cargo} situation={situation} t={t} />;
  }
  if (!body) return null;
  const site = selection.kind === "site" ? sites.find((item) => item.id === selection.id) : null;
  const node = site?.members.find((member) => member.kind === "node");
  return (
    <aside className="map-detail-panel" aria-label={t("map.detail.title")}>
      <button type="button" className="map-detail-close link-button" onClick={onClose} aria-label={t("map.detail.close")}>×</button>
      {body}
      {onInspect && node && site && (
        <button type="button" className="secondary-button map-detail-inspect" onClick={() => onInspect(node.id, site.name)}>
          {t("map.inspect_node")}
        </button>
      )}
    </aside>
  );
}
