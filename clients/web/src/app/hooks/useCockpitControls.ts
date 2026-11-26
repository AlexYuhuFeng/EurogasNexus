import { useState } from "react";

export function useCockpitControls() {
  // A calm first view: pipelines, hubs, LNG, what is out and where we are. Points, interconnection
  // markers, vessels and flows are one click away in the Layers menu.
  const [activeLayers, setActiveLayers] = useState(["routes", "hubs", "lng", "outages", "positions"]);
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
