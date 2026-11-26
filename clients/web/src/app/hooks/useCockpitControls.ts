import { useState } from "react";
import { DEFAULT_MAP_LAYERS } from "@/app/mapSituation";

export function useCockpitControls() {
  // A calm first view: hubs with their price, our positions, our cargoes and the outages that
  // touch the book. Everything else is one click away in the Layers menu (app/mapSituation.ts).
  const [activeLayers, setActiveLayers] = useState<string[]>(() => [...DEFAULT_MAP_LAYERS]);
  const [searchTerm, setSearchTerm] = useState("");

  function toggleLayer(layer: string) {
    setActiveLayers((current) =>
      current.includes(layer) ? current.filter((item) => item !== layer) : [...current, layer],
    );
  }

  function resetLayers() {
    setActiveLayers([...DEFAULT_MAP_LAYERS]);
  }

  return {
    activeLayers,
    searchTerm,
    setSearchTerm,
    toggleLayer,
    resetLayers,
  };
}
