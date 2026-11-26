/**
 * The map's own controls (MAP-1), in one stack beside the zoom: fit to our positions and the key.
 * The map is flat and north-up (owner, 2026-11-26). The key holds symbology only (what each
 * mark means) for the layers on the map; counts, site lists and source notes are not its job.
 * The flows' gas day is chosen in the page's toolbar while flows are drawn, not over the map.
 */
import { useId, useState, type ReactNode } from "react";

import { Icon } from "@/components/ui/Icon";
import type { Translate } from "@/app/mapSceneCards";

export interface MapSceneControlsProps {
  t: Translate;
  /** The layers on the map: the key lists only their marks. */
  activeLayers: readonly string[];
  /** Fit the map to our positions; absent when we hold none on the map. */
  onFitPositions?: () => void;
  /** The page's own key lines (pipelines, links, our flows), above the scene's. */
  keyExtra?: ReactNode;
}

export function MapSceneControls({
  t,
  activeLayers,
  onFitPositions,
  keyExtra,
}: MapSceneControlsProps) {
  const [open, setOpen] = useState(false);
  const keyId = useId();
  const sites = activeLayers.includes("lng") || activeLayers.includes("network");
  // The scene's own marks, for what is on the map now.
  const legend = [
    sites && <li key="site"><span className="map-scene-swatch is-site" aria-hidden="true" />{t("map.scene.legend.site")}</li>,
    sites && <li key="site_none"><span className="map-scene-swatch is-site-none" aria-hidden="true" />{t("map.scene.legend.site_none")}</li>,
    activeLayers.includes("flows") && <li key="flow"><span className="map-scene-swatch is-flow" aria-hidden="true" />{t("map.scene.legend.flow")}</li>,
  ].filter(Boolean);

  return (
    <>
      {/* One quiet stack in the map's corner, beside the zoom: the map's own controls. */}
      <div className="map-control-stack" role="group" aria-label={t("map.scene.controls")}>
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
      {open && (
        <div id={keyId} className="map-scene-key" role="region" aria-label={t("map.scene.key")}>
          {keyExtra}
          {legend.length > 0 && <ul className="map-scene-legend">{legend}</ul>}
        </div>
      )}
    </>
  );
}
