/**
 * The map scene's layers on the live map (MAP-1): terminal and storage columns (3D) or points
 * (2D), flow lines moving in the gas's direction, and LNG voyages with estimated positions
 * drawn hollow on a dashed leg. Models in app/mapScene.ts; cards in app/mapSceneCards.ts.
 *
 * - Data arrives with the map's situation, which the change stream keeps current
 *   (useMapSituation: `map` notices answered with a conditional read). A vessel or estimate
 *   that moved between two reads eases to its new place over `--ds-duration-map`; estimates
 *   also advance with the clock, once a minute.
 * - Motion: flow dashes step along the line while the page is visible; none under
 *   prefers-reduced-motion (a static line with a chevron), and no easing either.
 * - Frame behaviour is sampled while the scene animates and written to
 *   `data-map-scene-frame-p95` on the map element, for measurement in a real browser.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import { GeoJSONSource, Popup, type Map as MapLibreMap, type MapLayerMouseEvent } from "maplibre-gl";

import type { EdgeDTO, MapSituationDTO, NodeDTO } from "@/api/client";
import {
  SCENE_COLOURS,
  assetLayers,
  flowDashAt,
  flowLayers,
  flowMotion,
  flowsForDay,
  pointIndex,
  sceneCamera,
  tweenPoints,
  voyageLayers,
  type FC,
  type FlowLayers,
  type Project,
  type SceneDimension,
} from "@/app/mapScene";
import { assetCard, estimateCard, flowCard, voyageCard, type CardText, type FormatInstant, type Translate } from "@/app/mapSceneCards";
import { durationToken, easeOut, prefersReducedMotion } from "@/app/mapMotion";
import { frameSummary } from "@/app/mapSceneFrames";
import { SCENE_LIGHT, shipMarks, shipSolids, siteSolids, tweenShips, type ShipMark } from "@/app/mapSceneSolids";

type GeoData = Parameters<GeoJSONSource["setData"]>[0];

export interface MapSceneOptions {
  map: MapLibreMap | null;
  ready: boolean;
  /** Off for the compact preview map. */
  enabled: boolean;
  situation: MapSituationDTO | null;
  nodes: NodeDTO[];
  edges: EdgeDTO[];
  theme: "light" | "dark";
  flowColour: string;
  project: Project;
  dimension: SceneDimension;
  /** null: each point's newest closed day; a gas day: that stored day. */
  flowDay: string | null;
  activeLayers: string[];
  t: Translate;
  /** Writes an instant in the reader's zone and language (app/time/useInstant.ts). */
  when: FormatInstant;
  /** Select the site under a clicked column or pillar (the map's own selection). */
  onSelectRef?: (refId: string) => void;
  /** Select the cargo under a clicked hull. */
  onSelectCargo?: (cargoId: string) => void;
  /** The network points shown (the map's own filter): hubs and points stand as pillars in 3D. */
  pillarNodes?: NodeDTO[];
  /** Pillar colours: the map's own hub and point colours. */
  pointColours?: { hub: string; point: string };
  /** Hull colours: our positions and market vessels, as the map's dots. */
  shipColours?: { own: string; market: string };
}

const SOURCES = [
  "scene-asset-columns",
  "scene-asset-fills",
  "scene-asset-points",
  "scene-flow-lines",
  "scene-flow-chevrons",
  "scene-voyage-arcs",
  "scene-estimate-legs",
  "scene-voyage-estimated",
  "scene-site-solids",
  "scene-ship-solids",
] as const;
/** The 3D solids' layers (hidden in 2D): two ground-shadow fills and two extrusions. */
const SOLID_LAYERS = ["scene-site-shadows", "scene-ship-shadows", "scene-site-solids", "scene-ship-solids"] as const;
const HOVER_LAYERS = [
  "scene-asset-columns",
  "scene-asset-points",
  "scene-flow-lines",
  "scene-voyage-estimated",
  "scene-voyage-arcs",
  "scene-ship-solids",
] as const;
const EMPTY: GeoData = { type: "FeatureCollection", features: [] };

function setData(map: MapLibreMap, id: string, data: GeoData) {
  const source = map.getSource(id) as GeoJSONSource | undefined;
  if (source) source.setData(data);
  else map.addSource(id, { type: "geojson", data });
}

function escapeHtml(value: unknown): string {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "\"": "&quot;", "'": "&#39;" }[char] ?? char));
}

export function cardHtml(card: CardText): string {
  return `<div class="node-popup situation-card map-scene-card"><strong>${escapeHtml(card.title)}</strong>`
    + card.lines.map((line) => `<span>${escapeHtml(line)}</span>`).join("")
    + (card.note ? `<small class="muted">${escapeHtml(card.note)}</small>` : "")
    + "</div>";
}

/** Ground shadows: --ds-text-1 (light) and --ds-on-ink (dark), kept faint. */
const SHADOW = {
  light: { colour: "#18181b", opacity: 0.12 },
  dark: { colour: "#131316", opacity: 0.32 },
} as const;

/** A height that rises from regional zoom for points; hubs and sites stand at every zoom. */
const RISING_HEIGHT = ["interpolate", ["linear"], ["zoom"], 4.5, ["*", ["get", "height"], ["get", "overview"]], 6, ["get", "height"]];
const risingOpacity = (opacity: number) => ["interpolate", ["linear"], ["zoom"], 4.5, ["*", opacity, ["get", "overview"]], 6, opacity];

function shipColour(options: MapSceneOptions, colours: (typeof SCENE_COLOURS)["light" | "dark"]) {
  const own = options.shipColours?.own ?? colours.lng;
  const market = options.shipColours?.market ?? colours.estimate;
  return ["case", ["==", ["get", "basis"], "estimated"], colours.estimate, ["get", "own"], own, market];
}
function pillarColour(options: MapSceneOptions, colours: (typeof SCENE_COLOURS)["light" | "dark"]) {
  return ["match", ["get", "node_type"], "hub", options.pointColours?.hub ?? colours.lng, options.pointColours?.point ?? colours.estimate];
}

export function useMapScene(options: MapSceneOptions): { flows: Pick<FlowLayers, "oriented" | "unoriented">; now: Date } {
  const { map, ready, enabled, situation, nodes, edges, theme, flowColour, project, dimension, flowDay, activeLayers, t } = options;
  const live = Boolean(map && ready && enabled);
  // The clock estimates are drawn at: once a minute, so an estimate advances while watched.
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    if (!live) return undefined;
    const timer = window.setInterval(() => setNow(new Date()), 60_000);
    return () => window.clearInterval(timer);
  }, [live]);

  const assets = useMemo(() => assetLayers(situation?.assets, project), [project, situation?.assets]);
  const flows = useMemo(
    () => flowLayers(flowsForDay(situation, flowDay), nodes, edges, project),
    [edges, flowDay, nodes, project, situation],
  );
  const voyages = useMemo(() => voyageLayers(situation?.cargoes, now, project), [now, project, situation?.cargoes]);
  const pillarNodes = options.pillarNodes ?? nodes;
  const sites = useMemo(() => siteSolids(pillarNodes, situation?.assets, project), [pillarNodes, project, situation?.assets]);
  const ships = useMemo(() => shipMarks(situation?.cargoes, now), [now, situation?.cargoes]);

  const optionsRef = useRef(options);
  optionsRef.current = options;
  const situationRef = useRef(situation);
  situationRef.current = situation;
  const nowRef = useRef(now);
  nowRef.current = now;
  const dimensionRef = useRef(dimension);
  dimensionRef.current = dimension;

  // Sources and layers, once per map; then fed with setData.
  useEffect(() => {
    if (!live || !map) return undefined;
    for (const id of SOURCES) if (!map.getSource(id)) map.addSource(id, { type: "geojson", data: EMPTY });
    const colours = SCENE_COLOURS[theme];
    const kindColour = ["case", ["!", ["get", "published"]], colours.noCapacity, ["match", ["get", "asset_kind"], "lng_terminal", colours.lng, colours.storage]];
    const add = (layer: Parameters<MapLibreMap["addLayer"]>[0]) => {
      if (!map.getLayer(layer.id)) map.addLayer(layer);
    };
    add({ id: "scene-flow-lines", type: "line", source: "scene-flow-lines", layout: { "line-cap": "butt", "line-join": "round" }, paint: { "line-color": flowColour, "line-width": ["get", "width"], "line-opacity": 0.85, "line-dasharray": flowDashAt(0, "static") } });
    add({ id: "scene-flow-chevrons", type: "line", source: "scene-flow-chevrons", layout: { "line-cap": "round", "line-join": "round" }, paint: { "line-color": flowColour, "line-width": 2, "line-opacity": 0.9 } });
    add({ id: "scene-voyage-arcs", type: "line", source: "scene-voyage-arcs", layout: { "line-cap": "round" }, paint: { "line-color": colours.estimate, "line-width": 1.2, "line-opacity": 0.55, "line-dasharray": [1, 3] } });
    add({ id: "scene-estimate-legs", type: "line", source: "scene-estimate-legs", layout: { "line-cap": "butt" }, paint: { "line-color": colours.estimate, "line-width": 1.5, "line-opacity": 0.8, "line-dasharray": [2, 2] } });
    add({ id: "scene-voyage-estimated", type: "circle", source: "scene-voyage-estimated", paint: { "circle-radius": 6, "circle-color": colours.estimate, "circle-opacity": 0, "circle-stroke-color": colours.estimate, "circle-stroke-width": 2 } });
    add({ id: "scene-asset-points", type: "circle", source: "scene-asset-points", paint: { "circle-radius": ["get", "radius"], "circle-color": kindColour as never, "circle-opacity": 0.28, "circle-stroke-color": kindColour as never, "circle-stroke-width": 1.4 } });
    add({ id: "scene-asset-columns", type: "fill-extrusion", source: "scene-asset-columns", paint: { "fill-extrusion-color": kindColour as never, "fill-extrusion-height": ["get", "height"], "fill-extrusion-base": 0, "fill-extrusion-opacity": 0.38 } });
    add({ id: "scene-asset-fills", type: "fill-extrusion", source: "scene-asset-fills", paint: { "fill-extrusion-color": kindColour as never, "fill-extrusion-height": ["get", "height"], "fill-extrusion-base": 0, "fill-extrusion-opacity": 0.9 } });
    // 3D solids: ground shadows under the flows, then pillars and hulls over the columns.
    const shadow = SHADOW[theme];
    const under = map.getLayer("scene-flow-lines") ? "scene-flow-lines" : undefined;
    if (!map.getLayer("scene-site-shadows")) {
      map.addLayer({ id: "scene-site-shadows", type: "fill", source: "scene-site-solids", filter: ["==", ["get", "part"], "shadow"], layout: { visibility: "none" }, paint: { "fill-color": shadow.colour, "fill-opacity": risingOpacity(shadow.opacity) as never, "fill-antialias": false } }, under);
    }
    if (!map.getLayer("scene-ship-shadows")) {
      map.addLayer({ id: "scene-ship-shadows", type: "fill", source: "scene-ship-solids", maxzoom: 8.5, filter: ["==", ["get", "part"], "shadow"], layout: { visibility: "none" }, paint: { "fill-color": shadow.colour, "fill-opacity": shadow.opacity, "fill-antialias": false } }, under);
    }
    const current = optionsRef.current;
    add({ id: "scene-site-solids", type: "fill-extrusion", source: "scene-site-solids", filter: ["==", ["get", "part"], "solid"], layout: { visibility: "none" }, paint: { "fill-extrusion-color": pillarColour(current, colours) as never, "fill-extrusion-height": RISING_HEIGHT as never, "fill-extrusion-base": 0, "fill-extrusion-opacity": 0.85 } });
    add({ id: "scene-ship-solids", type: "fill-extrusion", source: "scene-ship-solids", maxzoom: 8.5, filter: ["==", ["get", "part"], "solid"], layout: { visibility: "none" }, paint: { "fill-extrusion-color": shipColour(current, colours) as never, "fill-extrusion-height": ["get", "height"], "fill-extrusion-base": 0, "fill-extrusion-opacity": 0.92 } });
    // One light for every extrusion, fixed to the map so lit faces agree with the shadows.
    map.setLight(SCENE_LIGHT);

    // Hover cards, and a column or site point selects its site.
    const popup = new Popup({ closeButton: false, closeOnClick: false, maxWidth: "320px", className: "map-scene-popup" });
    const cardFor = (layer: string, props: Record<string, unknown>): CardText | null => {
      const current = situationRef.current;
      const { t: tr, when } = optionsRef.current;
      if (layer === "scene-asset-columns" || layer === "scene-asset-points") {
        const asset = current?.assets?.find((item) => item.asset_id === props.id);
        return asset ? assetCard(asset, nowRef.current, tr, dimensionRef.current) : null;
      }
      const cargo = current?.cargoes.find((item) => item.cargo_id === props.id);
      if (layer === "scene-voyage-estimated") return cargo ? estimateCard(cargo, nowRef.current, tr, when) : null;
      if (layer === "scene-voyage-arcs") return cargo ? voyageCard(cargo, tr, when) : null;
      if (layer === "scene-ship-solids") {
        if (!cargo) return null;
        return props.basis === "estimated" ? estimateCard(cargo, nowRef.current, tr, when) : voyageCard(cargo, tr, when);
      }
      if (layer === "scene-flow-lines") {
        return flowCard({ name: String(props.name ?? ""), direction: String(props.direction ?? ""), gwh_d: Number(props.gwh_d ?? 0), gas_day: props.gas_day ? String(props.gas_day) : null }, tr);
      }
      return null;
    };
    const onMove = (event: MapLayerMouseEvent) => {
      const feature = event.features?.[0];
      if (!feature) return;
      const card = cardFor(feature.layer.id, feature.properties ?? {});
      if (!card) return;
      map.getCanvas().style.cursor = "pointer";
      popup.setLngLat(event.lngLat).setHTML(cardHtml(card)).addTo(map);
    };
    const onLeave = () => {
      map.getCanvas().style.cursor = "";
      popup.remove();
    };
    const onClick = (event: MapLayerMouseEvent) => {
      const id = event.features?.[0]?.properties?.id;
      if (id) optionsRef.current.onSelectRef?.(String(id));
    };
    const onShipClick = (event: MapLayerMouseEvent) => {
      const id = event.features?.[0]?.properties?.id;
      if (id) optionsRef.current.onSelectCargo?.(String(id));
    };
    for (const layer of HOVER_LAYERS) {
      map.on("mousemove", layer, onMove);
      map.on("mouseleave", layer, onLeave);
    }
    map.on("click", "scene-asset-columns", onClick);
    map.on("click", "scene-asset-points", onClick);
    map.on("click", "scene-site-solids", onClick);
    map.on("click", "scene-ship-solids", onShipClick);
    return () => {
      for (const layer of HOVER_LAYERS) {
        map.off("mousemove", layer, onMove);
        map.off("mouseleave", layer, onLeave);
      }
      map.off("click", "scene-asset-columns", onClick);
      map.off("click", "scene-asset-points", onClick);
      map.off("click", "scene-site-solids", onClick);
      map.off("click", "scene-ship-solids", onShipClick);
      popup.remove();
    };
  }, [live, map]);

  // Theme: recolour in place.
  useEffect(() => {
    if (!live || !map || !map.getLayer("scene-asset-columns")) return;
    const colours = SCENE_COLOURS[theme];
    const kindColour = ["case", ["!", ["get", "published"]], colours.noCapacity, ["match", ["get", "asset_kind"], "lng_terminal", colours.lng, colours.storage]];
    for (const [layer, property, value] of [
      ["scene-asset-columns", "fill-extrusion-color", kindColour],
      ["scene-asset-fills", "fill-extrusion-color", kindColour],
      ["scene-asset-points", "circle-color", kindColour],
      ["scene-asset-points", "circle-stroke-color", kindColour],
      ["scene-voyage-arcs", "line-color", colours.estimate],
      ["scene-estimate-legs", "line-color", colours.estimate],
      ["scene-voyage-estimated", "circle-stroke-color", colours.estimate],
      ["scene-flow-lines", "line-color", flowColour],
      ["scene-flow-chevrons", "line-color", flowColour],
      ["scene-site-solids", "fill-extrusion-color", pillarColour(optionsRef.current, colours)],
      ["scene-ship-solids", "fill-extrusion-color", shipColour(optionsRef.current, colours)],
      ["scene-site-shadows", "fill-color", SHADOW[theme].colour],
      ["scene-ship-shadows", "fill-color", SHADOW[theme].colour],
      ["scene-site-shadows", "fill-opacity", risingOpacity(SHADOW[theme].opacity)],
      ["scene-ship-shadows", "fill-opacity", SHADOW[theme].opacity],
    ] as const) {
      map.setPaintProperty(layer, property, value as never);
    }
  }, [flowColour, live, map, theme, options.pointColours?.hub, options.pointColours?.point, options.shipColours?.own, options.shipColours?.market]);

  // Data: sites and flows replace in place; vessels and estimates ease to their new place.
  const drawnVoyages = useRef<FC<{ type: "Point"; coordinates: [number, number] }> | null>(null);
  useEffect(() => {
    if (!live || !map) return undefined;
    setData(map, "scene-asset-columns", assets.columns as GeoData);
    setData(map, "scene-asset-fills", assets.fills as GeoData);
    setData(map, "scene-asset-points", assets.points as GeoData);
    setData(map, "scene-flow-lines", flows.lines as GeoData);
    setData(map, "scene-flow-chevrons", flows.chevrons as GeoData);
    setData(map, "scene-voyage-arcs", voyages.arcs as GeoData);
    setData(map, "scene-estimate-legs", voyages.estimateLegs as GeoData);
    const before = drawnVoyages.current ? pointIndex(drawnVoyages.current) : new Map<string, [number, number]>();
    drawnVoyages.current = voyages.estimated;
    const duration = prefersReducedMotion() ? 0 : durationToken("--ds-duration-map", 400);
    if (duration <= 0 || before.size === 0) {
      setData(map, "scene-voyage-estimated", voyages.estimated as GeoData);
      return undefined;
    }
    const start = performance.now();
    let frame = 0;
    const step = (time: number) => {
      const k = Math.min(1, (time - start) / duration);
      setData(map, "scene-voyage-estimated", tweenPoints(before, voyages.estimated, easeOut(k)) as GeoData);
      if (k < 1) frame = requestAnimationFrame(step);
    };
    frame = requestAnimationFrame(step);
    return () => cancelAnimationFrame(frame);
  }, [assets, flows, live, map, voyages]);

  // Pillars and site shadows replace in place.
  useEffect(() => {
    if (!live || !map) return;
    setData(map, "scene-site-solids", sites as GeoData);
  }, [live, map, sites]);

  // Hulls ease to their new place and heading with the dots (none under reduced motion).
  const drawnShips = useRef<Map<string, ShipMark> | null>(null);
  useEffect(() => {
    if (!live || !map) return undefined;
    const before = drawnShips.current;
    drawnShips.current = new Map(ships.map((mark) => [mark.key, mark]));
    const duration = prefersReducedMotion() ? 0 : durationToken("--ds-duration-map", 400);
    const moved = before !== null && ships.some((mark) => {
      const was = before.get(mark.key);
      return was !== undefined && (was.at[0] !== mark.at[0] || was.at[1] !== mark.at[1] || was.headingDeg !== mark.headingDeg);
    });
    if (duration <= 0 || !moved || !before) {
      setData(map, "scene-ship-solids", shipSolids(ships, project) as GeoData);
      return undefined;
    }
    const start = performance.now();
    let frame = 0;
    const step = (time: number) => {
      const k = Math.min(1, (time - start) / duration);
      setData(map, "scene-ship-solids", shipSolids(tweenShips(before, ships, easeOut(k)), project) as GeoData);
      if (k < 1) frame = requestAnimationFrame(step);
    };
    step(start);
    return () => cancelAnimationFrame(frame);
  }, [live, map, project, ships]);

  // What shows: 2D points or 3D columns; terminals with "LNG", storage with "Other points";
  // flows with "Flows"; our voyages with "Our positions", market ones with "LNG vessels".
  useEffect(() => {
    if (!live || !map || !map.getLayer("scene-asset-columns")) return;
    const kinds = [
      ...(activeLayers.includes("lng") ? ["lng_terminal"] : []),
      ...(activeLayers.includes("network") ? ["storage"] : []),
    ];
    const assetFilter = ["in", ["get", "asset_kind"], ["literal", kinds]];
    const owners = [
      ...(activeLayers.includes("positions") ? [true] : []),
      ...(activeLayers.includes("vessels") ? [false] : []),
    ];
    const voyageFilter = ["in", ["get", "own"], ["literal", owners]];
    const show = (layer: string, visible: boolean) => map.setLayoutProperty(layer, "visibility", visible ? "visible" : "none");
    for (const layer of ["scene-asset-columns", "scene-asset-fills", "scene-asset-points"]) map.setFilter(layer, assetFilter as never);
    show("scene-asset-columns", dimension === "3d");
    show("scene-asset-fills", dimension === "3d");
    show("scene-asset-points", dimension === "2d");
    show("scene-flow-lines", activeLayers.includes("flows"));
    show("scene-flow-chevrons", activeLayers.includes("flows"));
    for (const layer of ["scene-voyage-arcs", "scene-estimate-legs", "scene-voyage-estimated"]) map.setFilter(layer, voyageFilter as never);
    // 3D solids: pillars follow the map's own point filter; site shadows follow the columns'.
    const siteFilter = ["any", ["==", ["get", "kind"], "pillar"], ["in", ["get", "asset_kind"], ["literal", kinds]]];
    map.setFilter("scene-site-shadows", ["all", ["==", ["get", "part"], "shadow"], siteFilter] as never);
    map.setFilter("scene-site-solids", ["==", ["get", "part"], "solid"] as never);
    for (const part of ["shadow", "solid"] as const) {
      map.setFilter(part === "shadow" ? "scene-ship-shadows" : "scene-ship-solids", ["all", ["==", ["get", "part"], part], voyageFilter] as never);
    }
    for (const layer of SOLID_LAYERS) show(layer, dimension === "3d");
  }, [activeLayers, dimension, live, map]);

  // The camera between 2D and 3D, eased with the map token (a jump under reduced motion).
  const firstDimension = useRef(true);
  useEffect(() => {
    if (!live || !map) return;
    const camera = sceneCamera(dimension, prefersReducedMotion(), durationToken("--ds-duration-map", 400));
    if (firstDimension.current && dimension === "2d" && map.getPitch() === 0) {
      firstDimension.current = false;
      return;
    }
    firstDimension.current = false;
    map.easeTo({ pitch: camera.pitch, duration: camera.duration, easing: easeOut, essential: false });
  }, [dimension, live, map]);

  // Flow motion: the dash pattern steps while visible and motion is allowed. Frame intervals
  // are sampled while it runs, for measurement.
  useEffect(() => {
    if (!live || !map || !activeLayers.includes("flows")) return undefined;
    let frame = 0;
    let lastStep = -1;
    const started = performance.now();
    const intervals: number[] = [];
    let previous = started;
    const tick = (time: number) => {
      const motion = flowMotion(prefersReducedMotion(), document.visibilityState === "visible");
      if (motion === "static") {
        map.setPaintProperty("scene-flow-lines", "line-dasharray", flowDashAt(0, "static"));
        frame = 0;
        return;
      }
      intervals.push(time - previous);
      previous = time;
      if (intervals.length >= 120) {
        const summary = frameSummary(intervals.splice(0));
        map.getContainer().parentElement?.setAttribute("data-map-scene-frame-p95", String(summary.p95Ms));
      }
      const stepIndex = Math.floor((time - started) / 70);
      if (stepIndex !== lastStep) {
        lastStep = stepIndex;
        map.setPaintProperty("scene-flow-lines", "line-dasharray", flowDashAt(time - started, motion));
      }
      frame = requestAnimationFrame(tick);
    };
    const restart = () => {
      if (frame === 0 && document.visibilityState === "visible") frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    document.addEventListener("visibilitychange", restart);
    const media = typeof window.matchMedia === "function" ? window.matchMedia("(prefers-reduced-motion: reduce)") : null;
    media?.addEventListener?.("change", restart);
    return () => {
      cancelAnimationFrame(frame);
      document.removeEventListener("visibilitychange", restart);
      media?.removeEventListener?.("change", restart);
    };
  }, [activeLayers, live, map]);

  return { flows: { oriented: flows.oriented, unoriented: flows.unoriented }, now };
}
