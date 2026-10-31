/**
 * Infrastructure icons for the live map, drawn once on a canvas and registered with MapLibre.
 *
 * Shape tells the kind of asset at a glance, colour its family, the way a ride-hailing map
 * tells a pickup from a drop-off: production (triangle, platform; ring, field; hexagon,
 * processing), LNG (rounded square), storage (square), compression (diamond) and gas-fired
 * power (circle). Drawn locally so no icon font or sprite service is needed, which keeps
 * the map working offline and in mainland China.
 */

export type IconShape = "triangle" | "ring" | "hexagon" | "rounded-square" | "square" | "diamond" | "circle";

export const FACILITY_ICON: Record<string, { shape: IconShape; family: "production" | "lng" | "storage" | "network" | "power" }> = {
  production_platform: { shape: "triangle", family: "production" },
  field: { shape: "ring", family: "production" },
  processing_plant: { shape: "hexagon", family: "production" },
  liquefaction: { shape: "rounded-square", family: "lng" },
  lng_terminal: { shape: "rounded-square", family: "lng" },
  storage: { shape: "square", family: "storage" },
  compressor: { shape: "diamond", family: "network" },
  border_point: { shape: "diamond", family: "network" },
  power_plant: { shape: "circle", family: "power" },
};

export const ICON_FAMILY_COLOURS = {
  light: { production: "#b45309", lng: "#7c3aed", storage: "#0f766e", network: "#52525b", power: "#be123c", halo: "#ffffff" },
  dark: { production: "#fbbf24", lng: "#a78bfa", storage: "#2dd4bf", network: "#a1a1aa", power: "#fb7185", halo: "#0a0a0a" },
} as const;

/** MapLibre image id for a facility type in a theme. */
export function facilityIconId(facilityType: string, theme: "light" | "dark"): string {
  return `infra-${FACILITY_ICON[facilityType] ? facilityType : "power_plant"}-${theme}`;
}

const SIZE = 28; // logical px; registered at pixelRatio 2 for crisp edges

function path(context: CanvasRenderingContext2D, shape: IconShape, c: number, r: number): void {
  context.beginPath();
  const polygon = (points: Array<[number, number]>) => {
    points.forEach(([x, y], index) => (index ? context.lineTo(x, y) : context.moveTo(x, y)));
    context.closePath();
  };
  if (shape === "triangle") polygon([[c, c - r], [c + r * 0.95, c + r * 0.7], [c - r * 0.95, c + r * 0.7]]);
  else if (shape === "diamond") polygon([[c, c - r], [c + r, c], [c, c + r], [c - r, c]]);
  else if (shape === "square") polygon([[c - r * 0.8, c - r * 0.8], [c + r * 0.8, c - r * 0.8], [c + r * 0.8, c + r * 0.8], [c - r * 0.8, c + r * 0.8]]);
  else if (shape === "hexagon") polygon(Array.from({ length: 6 }, (_, i) => [c + r * Math.cos((Math.PI / 3) * i), c + r * Math.sin((Math.PI / 3) * i)] as [number, number]));
  else if (shape === "rounded-square") context.roundRect(c - r * 0.85, c - r * 0.85, r * 1.7, r * 1.7, r * 0.45);
  else context.arc(c, c, r * 0.85, 0, Math.PI * 2);
}

/** Draw one icon; returns ImageData or null where no canvas exists (tests, SSR). */
export function drawFacilityIcon(facilityType: string, theme: "light" | "dark"): ImageData | null {
  if (typeof document === "undefined") return null;
  const spec = FACILITY_ICON[facilityType] ?? FACILITY_ICON.power_plant;
  const colours = ICON_FAMILY_COLOURS[theme];
  const scale = 2;
  const canvas = document.createElement("canvas");
  canvas.width = SIZE * scale;
  canvas.height = SIZE * scale;
  const context = canvas.getContext("2d");
  if (!context) return null;
  context.scale(scale, scale);
  const c = SIZE / 2;
  // Halo first so the icon stays legible on any basemap.
  path(context, spec.shape, c, 11);
  context.fillStyle = colours.halo;
  context.fill();
  path(context, spec.shape, c, 8.5);
  if (spec.shape === "ring") {
    context.lineWidth = 3;
    context.strokeStyle = colours[spec.family];
    context.stroke();
  } else {
    context.fillStyle = colours[spec.family];
    context.fill();
  }
  return context.getImageData(0, 0, SIZE * scale, SIZE * scale);
}
