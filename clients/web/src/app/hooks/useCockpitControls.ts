import { useState } from "react";
import { DEFAULT_GAS_DAY } from "@/app/index";

export function useCockpitControls() {
  const [activeLayers, setActiveLayers] = useState(["hubs"]);
  const [gasDay, setGasDay] = useState(DEFAULT_GAS_DAY);
  const [deliveryProduct, setDeliveryProduct] = useState("all");
  const [searchTerm, setSearchTerm] = useState("");

  function toggleLayer(layer: string) {
    setActiveLayers((current) =>
      current.includes(layer) ? current.filter((item) => item !== layer) : [...current, layer],
    );
  }

  return {
    activeLayers,
    gasDay,
    deliveryProduct,
    searchTerm,
    setGasDay,
    setDeliveryProduct,
    setSearchTerm,
    toggleLayer,
  };
}
