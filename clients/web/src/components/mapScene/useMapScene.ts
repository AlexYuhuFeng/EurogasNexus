/**
 * The map scene's layers on the live map (MAP-1), flat: terminal and storage points sized by
 * their published capacity, and flow lines moving in the gas's direction. Models in
 * app/mapScene.ts; cards in app/mapSceneCards.ts. The map has no 3D (owner, 2026-11-26): it is
 * flat and north-up, and a cargo is drawn once, by the map's situation layers.
 *
 * - Data arrives with the map's situation, which the change stream keeps current
 *   (useMapSituation: `map` notices answered with a conditional read).
 * - Motion: flow dashes step along the line while the page is visible; none under
 *   prefers-reduced-motion (a static line with a chevron).
 * - Frame behaviour is sampled while the flows animate and written to
 *   `data-map-scene-frame-p95` on the map element, for measurement in a real browser.
 */
import { useEffect, useMemo, useRef } from "react";
import { GeoJSONSource, Popup, type Map as MapLibreMap, type MapLayerMouseEvent } from "maplibre-gl";

import type { EdgeDTO, MapSituationDTO, NodeDTO } from "@/api/client";
import {
  SCENE_COLOURS,
  assetPoints,
  flowDashAt,
  flowLayers,
  flowMotion,
  flowsForDay,
  type FlowLayers,
  type Project,
} from "@/app/mapScene";
import { assetCard, flowCard, type CardText, type Translate } from "@/app/mapSceneCards";
import { prefersReducedMotion } from "@/app/mapMotion";
import { frameSummary } from "@/app/mapSceneFrames";

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
  /** null: each point's newest closed day; a gas day: that stored day. */
  flowDay: string | null;
  activeLayers: string[];
  t: Translate;
  /** Select the site under a clicked point (the map's own selection). */
  onSelectRef?: (refId: string) => void;
}

const SOURCES = ["scene-asset-points", "scene-flow-lines", "scene-flow-chevrons"] as const;
const HOVER_LAYERS = ["scene-asset-points", "scene-flow-lines"] as const;
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

function kindColour(colours: (typeof SCENE_COLOURS)["light" | "dark"]) {
  return ["case", ["!", ["get", "published"]], colours.noCapacity, ["match", ["get", "asset_kind"], "lng_terminal", colours.lng, colours.storage]];
}

export function useMapScene(options: MapSceneOptions): { flows: Pick<FlowLayers, "oriented" | "unoriented"> } {
  const { map, ready, enabled, situation, nodes, edges, theme, flowColour, project, flowDay, activeLayers } = options;
  const live = Boolean(map && ready && enabled);

  const assets = useMemo(() => assetPoints(situation?.assets, project), [project, situation?.assets]);
  const flows = useMemo(
    () => flowLayers(flowsForDay(situation, flowDay), nodes, edges, project),
    [edges, flowDay, nodes, project, situation],
  );

  const optionsRef = useRef(options);
  optionsRef.current = options;
  const situationRef = useRef(situation);
  situationRef.current = situation;

  // Sources and layers, once per map; then fed with setData.
  useEffect(() => {
    if (!live || !map) return undefined;
    for (const id of SOURCES) if (!map.getSource(id)) map.addSource(id, { type: "geojson", data: EMPTY });
    const colours = SCENE_COLOURS[theme];
    const add = (layer: Parameters<MapLibreMap["addLayer"]>[0]) => {
      if (!map.getLayer(layer.id)) map.addLayer(layer);
    };
    add({ id: "scene-flow-lines", type: "line", source: "scene-flow-lines", layout: { "line-cap": "butt", "line-join": "round" }, paint: { "line-color": flowColour, "line-width": ["get", "width"], "line-opacity": 0.7, "line-dasharray": flowDashAt(0, "static") } });
    add({ id: "scene-flow-chevrons", type: "line", source: "scene-flow-chevrons", layout: { "line-cap": "round", "line-join": "round" }, paint: { "line-color": flowColour, "line-width": 1.5, "line-opacity": 0.85 } });
    add({ id: "scene-asset-points", type: "circle", source: "scene-asset-points", paint: { "circle-radius": ["get", "radius"], "circle-color": kindColour(colours) as never, "circle-opacity": 0.28, "circle-stroke-color": kindColour(colours) as never, "circle-stroke-width": 1.4 } });

    // Hover cards, and a site point selects its site.
    const popup = new Popup({ closeButton: false, closeOnClick: false, maxWidth: "320px", className: "map-scene-popup" });
    const cardFor = (layer: string, props: Record<string, unknown>): CardText | null => {
      const { t: tr } = optionsRef.current;
      if (layer === "scene-asset-points") {
        const asset = situationRef.current?.assets?.find((item) => item.asset_id === props.id);
        return asset ? assetCard(asset, new Date(), tr) : null;
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
    for (const layer of HOVER_LAYERS) {
      map.on("mousemove", layer, onMove);
      map.on("mouseleave", layer, onLeave);
    }
    map.on("click", "scene-asset-points", onClick);
    return () => {
      for (const layer of HOVER_LAYERS) {
        map.off("mousemove", layer, onMove);
        map.off("mouseleave", layer, onLeave);
      }
      map.off("click", "scene-asset-points", onClick);
      popup.remove();
    };
  }, [live, map]);

  // Theme: recolour in place.
  useEffect(() => {
    if (!live || !map || !map.getLayer("scene-asset-points")) return;
    const colours = SCENE_COLOURS[theme];
    for (const [layer, property, value] of [
      ["scene-asset-points", "circle-color", kindColour(colours)],
      ["scene-asset-points", "circle-stroke-color", kindColour(colours)],
      ["scene-flow-lines", "line-color", flowColour],
      ["scene-flow-chevrons", "line-color", flowColour],
    ] as const) {
      map.setPaintProperty(layer, property, value as never);
    }
  }, [flowColour, live, map, theme]);

  // Data replaces in place.
  useEffect(() => {
    if (!live || !map) return;
    setData(map, "scene-asset-points", assets as GeoData);
    setData(map, "scene-flow-lines", flows.lines as GeoData);
    setData(map, "scene-flow-chevrons", flows.chevrons as GeoData);
  }, [assets, flows, live, map]);

  // What shows: terminals with "LNG terminals", storage with "Storage and other points"; flows
  // with "Flows".
  useEffect(() => {
    if (!live || !map || !map.getLayer("scene-asset-points")) return;
    const kinds = [
      ...(activeLayers.includes("lng") ? ["lng_terminal"] : []),
      ...(activeLayers.includes("network") ? ["storage"] : []),
    ];
    map.setFilter("scene-asset-points", ["in", ["get", "asset_kind"], ["literal", kinds]] as never);
    const show = (layer: string, visible: boolean) => map.setLayoutProperty(layer, "visibility", visible ? "visible" : "none");
    show("scene-flow-lines", activeLayers.includes("flows"));
    show("scene-flow-chevrons", activeLayers.includes("flows"));
  }, [activeLayers, live, map]);

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

  return { flows: { oriented: flows.oriented, unoriented: flows.unoriented } };
}
