/**
 * The map scene's controls (MAP-1): 2D or 3D, the stored gas day the flows show, and a key
 * that says what each mark means and lists the figures on the map as buttons that fly there,
 * so every site and estimate is reachable from the keyboard as well as by pointer.
 */
import { useId, useMemo, useState } from "react";

import type { MapSituationDTO } from "@/api/client";
import { Button, Segmented } from "@/components/ui";
import { assetFigures, cargoPositions, scrubberIndex, type LonLat, type SceneDimension } from "@/app/mapScene";
import type { Translate } from "@/app/mapSceneCards";

export interface MapSceneControlsProps {
  dimension: SceneDimension;
  onDimension: (value: SceneDimension) => void;
  /** The stored closed gas days, oldest first. */
  flowDays: string[];
  /** null: latest (each point's newest closed day). */
  flowDay: string | null;
  onFlowDay: (value: string | null) => void;
  flowCounts: { oriented: number; unoriented: number };
  situation: MapSituationDTO | null;
  now: Date;
  t: Translate;
  onFlyTo: (at: LonLat, zoom: number) => void;
}

export function MapSceneControls({
  dimension,
  onDimension,
  flowDays,
  flowDay,
  onFlowDay,
  flowCounts,
  situation,
  now,
  t,
  onFlyTo,
}: MapSceneControlsProps) {
  const [open, setOpen] = useState(false);
  const keyId = useId();
  const scrubberId = useId();
  const index = scrubberIndex(flowDays, flowDay);
  const dayText = flowDay ?? t("map.scene.flow_day_latest");

  const sites = useMemo(
    () => (situation?.assets ?? [])
      .map((asset) => ({ asset, figures: assetFigures(asset) }))
      .filter((item) => item.figures.capacityGwhD !== null || item.asset.stock)
      .sort((a, b) => (b.figures.capacityGwhD ?? 0) - (a.figures.capacityGwhD ?? 0))
      .slice(0, 12),
    [situation?.assets],
  );
  const estimates = useMemo(
    () => (situation?.cargoes ?? [])
      .map((cargo) => ({ cargo, estimate: cargoPositions(cargo, now).estimate }))
      .filter((item) => item.estimate !== null),
    [now, situation?.cargoes],
  );

  return (
    <div className="map-scene-controls" role="group" aria-label={t("map.scene.controls")}>
      <Segmented
        label={t("map.scene.dimension")}
        options={[
          { value: "2d", label: t("map.scene.2d"), title: t("map.scene.2d_hint") },
          { value: "3d", label: t("map.scene.3d"), title: t("map.scene.3d_hint") },
        ]}
        value={dimension}
        onChange={onDimension}
      />
      {flowDays.length > 0 && (
        <div className="map-scene-scrubber">
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
      <Button
        variant="quiet"
        aria-expanded={open}
        aria-controls={keyId}
        onClick={() => setOpen((value) => !value)}
      >
        {t("map.scene.key")}
      </Button>
      {open && (
        <div id={keyId} className="map-scene-key" role="region" aria-label={t("map.scene.key")}>
          <ul className="map-scene-legend">
            <li><span className="map-scene-swatch is-column" aria-hidden="true" />{t("map.scene.legend.column")}</li>
            <li><span className="map-scene-swatch is-stub" aria-hidden="true" />{t("map.scene.legend.stub")}</li>
            <li><span className="map-scene-swatch is-flow" aria-hidden="true" />{t("map.scene.legend.flow")}</li>
            <li><span className="map-scene-swatch is-estimate" aria-hidden="true" />{t("map.scene.legend.estimate")}</li>
            <li><span className="map-scene-swatch is-voyage" aria-hidden="true" />{t("map.scene.legend.voyage")}</li>
            {dimension === "3d" && (
              <>
                <li><span className="map-scene-swatch is-pillar" aria-hidden="true" />{t("map.scene.legend.pillar")}</li>
                <li><span className="map-scene-swatch is-hull" aria-hidden="true" />{t("map.scene.legend.hull")}</li>
              </>
            )}
          </ul>
          <p className="map-scene-note">
            {t("map.scene.flow_counts", { oriented: flowCounts.oriented, unoriented: flowCounts.unoriented })}
          </p>
          {sites.length > 0 && (
            <>
              <h3 className="map-scene-heading">{t("map.scene.sites")}</h3>
              <ul className="map-scene-list">
                {sites.map(({ asset, figures }) => (
                  <li key={asset.asset_id}>
                    <Button variant="quiet" onClick={() => onFlyTo([asset.location.lon, asset.location.lat], 8)}>
                      <span>{asset.name}</span>
                      <small>
                        {figures.capacityGwhD !== null
                          ? t("map.scene.site_capacity", { value: Math.round(figures.capacityGwhD) })
                          : t("map.scene.no_capacity_short")}
                      </small>
                    </Button>
                  </li>
                ))}
              </ul>
            </>
          )}
          {estimates.length > 0 && (
            <>
              <h3 className="map-scene-heading">{t("map.scene.estimates")}</h3>
              <ul className="map-scene-list">
                {estimates.map(({ cargo, estimate }) => (
                  <li key={cargo.cargo_id}>
                    <Button variant="quiet" onClick={() => estimate && onFlyTo(estimate.at, 6)}>
                      <span>{cargo.vessel_name}</span>
                      <small>{t("map.scene.estimated_position")}</small>
                    </Button>
                  </li>
                ))}
              </ul>
            </>
          )}
          <p className="map-scene-note">{t("map.scene.sources")}</p>
        </div>
      )}
    </div>
  );
}
