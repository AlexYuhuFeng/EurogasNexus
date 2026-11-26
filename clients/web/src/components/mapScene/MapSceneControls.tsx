/**
 * The map's own controls (MAP-1), in one stack beside the zoom: 2D or 3D, fit to our positions,
 * and the key. The key holds symbology only (what each mark means), for the layers on the map;
 * counts, site lists and source notes are not the key's job (owner review 2026-11-26). The
 * flow-day bar shows only while flows are drawn.
 */
import { useId, useState, type ReactNode } from "react";

import { Icon } from "@/components/ui/Icon";
import { scrubberIndex, type SceneDimension } from "@/app/mapScene";
import type { Translate } from "@/app/mapSceneCards";

export interface MapSceneControlsProps {
  dimension: SceneDimension;
  onDimension: (value: SceneDimension) => void;
  /** The stored closed gas days, oldest first. */
  flowDays: string[];
  /** null: latest (each point's newest closed day). */
  flowDay: string | null;
  onFlowDay: (value: string | null) => void;
  t: Translate;
  /** The flow-day bar shows only while flows are drawn. */
  showFlowDay: boolean;
  /** The layers on the map: the key lists only their marks. */
  activeLayers: readonly string[];
  /** Fit the map to our positions; absent when we hold none on the map. */
  onFitPositions?: () => void;
  /** The page's own key lines (pipelines, links, our flows), above the scene's. */
  keyExtra?: ReactNode;
}

export function MapSceneControls({
  dimension,
  onDimension,
  flowDays,
  flowDay,
  onFlowDay,
  t,
  showFlowDay,
  activeLayers,
  onFitPositions,
  keyExtra,
}: MapSceneControlsProps) {
  const [open, setOpen] = useState(false);
  const keyId = useId();
  const scrubberId = useId();
  const index = scrubberIndex(flowDays, flowDay);
  const dayText = flowDay ?? t("map.scene.flow_day_latest");
  const sites = activeLayers.includes("lng") || activeLayers.includes("network");

  return (
    <>
      {/* One quiet stack in the map's corner, beside the zoom: the map's own controls. */}
      <div className="map-control-stack" role="group" aria-label={t("map.scene.controls")}>
        <button
          type="button"
          className="map-control-button"
          aria-pressed={dimension === "3d"}
          title={t(dimension === "3d" ? "map.control.view_2d" : "map.control.view_3d")}
          aria-label={t(dimension === "3d" ? "map.control.view_2d" : "map.control.view_3d")}
          onClick={() => onDimension(dimension === "3d" ? "2d" : "3d")}
        >
          {dimension === "3d" ? <span className="map-control-text">2D</span> : <span className="map-control-text">3D</span>}
        </button>
        {onFitPositions && (
          <button
            type="button"
            className="map-control-button"
            title={t("map.control.fit_positions")}
            aria-label={t("map.control.fit_positions")}
            onClick={onFitPositions}
          >
            <Icon name="locate-positions" />
          </button>
        )}
        <button
          type="button"
          className="map-control-button"
          aria-expanded={open}
          aria-controls={keyId}
          title={t("map.control.key")}
          aria-label={t("map.control.key")}
          onClick={() => setOpen((value) => !value)}
        >
          <Icon name="info" />
        </button>
      </div>
      {showFlowDay && flowDays.length > 0 && (
        <div className="map-flow-day-bar">
          <label htmlFor={scrubberId}>{t("map.scene.flow_day")}</label>
          <input
            id={scrubberId}
            type="range"
            min={0}
            max={flowDays.length}
            step={1}
            value={index}
            aria-valuetext={dayText}
            onChange={(event) => {
              const next = Number(event.target.value);
              onFlowDay(next >= flowDays.length ? null : flowDays[next]);
            }}
          />
          <output htmlFor={scrubberId} aria-live="polite">{dayText}</output>
        </div>
      )}
      {open && (
        <div id={keyId} className="map-scene-key" role="region" aria-label={t("map.scene.key")}>
          {keyExtra}
          <ul className="map-scene-legend">
            {sites && <li><span className="map-scene-swatch is-column" aria-hidden="true" />{t("map.scene.legend.column")}</li>}
            {sites && <li><span className="map-scene-swatch is-stub" aria-hidden="true" />{t("map.scene.legend.stub")}</li>}
            {activeLayers.includes("flows") && <li><span className="map-scene-swatch is-flow" aria-hidden="true" />{t("map.scene.legend.flow")}</li>}
            {dimension === "3d" && <li><span className="map-scene-swatch is-pillar" aria-hidden="true" />{t("map.scene.legend.pillar")}</li>}
            {dimension === "3d" && (activeLayers.includes("cargoes") || activeLayers.includes("vessels")) && (
              <li><span className="map-scene-swatch is-hull" aria-hidden="true" />{t("map.scene.legend.hull")}</li>
            )}
          </ul>
        </div>
      )}
    </>
  );
}
