import { useState } from "react";

export function useCockpitControls() {
  const [activeLayers, setActiveLayers] = useState(["routes", "hubs", "lng", "ips", "network", "outages", "positions", "flows"]);
  const [searchTerm, setSearchTerm] = useState("");

  function toggleLayer(layer: string) {
    setActiveLayers((current) =>
      current.includes(layer) ? current.filter((item) => item !== layer) : [...current, layer],
    );
  }

  return {
    activeLayers,
    searchTerm,
    setSearchTerm,
    toggleLayer,
  };
}
