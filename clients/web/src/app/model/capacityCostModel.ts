/**
 * TAR-2's pure view logic: a capacity cost in layers (contracted first, then the public tariff,
 * else not held — never zero), the sources of any resolved figure in precedence order with the
 * one used marked, and one tariff year's indicative and final versions side by side.
 */
import type {
  CapacityCostDTO,
  CapacityCostLayerDTO,
  SourceTierDTO,
  TariffVersionDTO,
  TariffYearDTO,
} from "../../api/client.ts";
import { tariffFigure, type Tone } from "./tariffBookModel.ts";

/** The status a layer shows: contracted, final, indicative or not held. */
export type LayerStatus = "contracted" | "final" | "indicative" | "not_held";

export function layerStatus(layer: Pick<CapacityCostLayerDTO, "layer" | "status">): LayerStatus {
  if (layer.layer === "not_held") return "not_held";
  if (layer.layer === "contracted") return "contracted";
  return String(layer.status ?? "").toUpperCase() === "FINAL" ? "final" : "indicative";
}

/** Contracted and final read as settled; indicative as "watch"; not held as a breach. */
export function layerTone(layer: Pick<CapacityCostLayerDTO, "layer" | "status">): Tone {
  switch (layerStatus(layer)) {
    case "contracted":
      return "info";
    case "final":
      return "ok";
    case "indicative":
      return "watch";
    default:
      return "breach";
  }
}

const money = new Intl.NumberFormat("en-GB", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const quantity = new Intl.NumberFormat("en-GB", { maximumFractionDigits: 1 });
const rate = new Intl.NumberFormat("en-GB", { maximumFractionDigits: 6 });

/** A cost with its currency, or null when it is not given (a missing cost is never shown as 0). */
export function costText(cost: number | null | undefined, currency: string | null | undefined): string | null {
  if (cost === null || cost === undefined || !Number.isFinite(cost)) return null;
  return `${money.format(cost)} ${currency ?? ""}`.trim();
}

/** A resolved FX rate as "1 USD = 0.909091 EUR", or null when no tier gave one. */
export function fxText(fx: { value: number | null; from?: string; to?: string }): string | null {
  if (fx.value === null || !Number.isFinite(fx.value)) return null;
  return `1 ${fx.from ?? ""} = ${rate.format(fx.value)} ${fx.to ?? ""}`;
}

export function quantityText(value: number, unit: string): string {
  return `${quantity.format(value)} ${unit}`;
}

export function unitCostText(layer: Pick<CapacityCostLayerDTO, "unit_cost" | "currency" | "unit">): string | null {
  if (layer.unit_cost === null || layer.unit_cost === undefined) return null;
  return `${rate.format(layer.unit_cost)} ${layer.currency ?? ""}/${layer.unit}`.replace(" /", "/");
}

/** What a layer was priced from: the booking or the tariff version, with its tariff year. */
export function layerReference(layer: CapacityCostLayerDTO): string {
  if (layer.layer === "contracted") {
    return [layer.booking_id ?? layer.reference, layer.acquired_via, layer.contracted_price].filter(Boolean).join(" · ");
  }
  if (layer.layer === "public") {
    return [layer.tariff_year, layer.public_price, layer.how_bought].filter(Boolean).join(" · ");
  }
  return layer.reason ?? "";
}

export interface SourceStep {
  position: number;
  tier: string;
  label: string;
  used: boolean;
  reason: string;
  note: string | null;
}

/** The tiers as the server ordered them (the order in force), numbered, the used ones marked. */
export function sourceSteps(sources: readonly SourceTierDTO[] | undefined): SourceStep[] {
  return (sources ?? []).map((source, index) => ({
    position: index + 1,
    tier: source.tier,
    label: source.label,
    used: Boolean(source.used),
    reason: source.used ? "used" : source.reason || "not_tried",
    note: source.note ?? null,
  }));
}

/** Where the order came from: the default, the firm's setting (and its key), or this calculation. */
export function orderOrigin(orderSource: string | undefined): { key: string; setting: string | null } {
  if (!orderSource || orderSource === "default") return { key: "default", setting: null };
  if (orderSource.startsWith("setting:")) return { key: "setting", setting: orderSource.slice("setting:".length) };
  return { key: orderSource === "calculation" ? "calculation" : "default", setting: null };
}

/** The headline of a cost: complete, partly not held, or indicative where no final is held. */
export function costHeadline(cost: Pick<CapacityCostDTO, "complete" | "indicative" | "total_cost">):
  | "complete_final"
  | "complete_indicative"
  | "incomplete" {
  if (!cost.complete || cost.total_cost === null) return "incomplete";
  return cost.indicative ? "complete_indicative" : "complete_final";
}

export interface YearCell {
  status: "INDICATIVE" | "FINAL";
  held: boolean;
  used: boolean;
  figure: string;
  version: number | null;
  /** The publisher's stated date, or null when none is stated (the record time stands in). */
  published: string | null;
  recorded: string | null;
  sourceUrl: string | null;
  isNew: boolean;
}

function cell(status: "INDICATIVE" | "FINAL", row: TariffVersionDTO | null, used: boolean): YearCell {
  return {
    status,
    held: row !== null,
    used: row !== null && used,
    figure: row ? tariffFigure(row) : "—",
    version: row?.version ?? null,
    published: row?.published_at_utc ?? null,
    recorded: row?.recorded_at_utc ?? null,
    sourceUrl: row?.source_url ?? null,
    isNew: Boolean(row?.new),
  };
}

/** One tariff year's two versions, indicative then final, with the one a valuation uses marked. */
export function yearCells(year: TariffYearDTO): [YearCell, YearCell] {
  return [cell("INDICATIVE", year.INDICATIVE, year.used === "INDICATIVE"), cell("FINAL", year.FINAL, year.used === "FINAL")];
}

/** Tariff years newest first, then by direction and product. */
export function orderedYears(years: readonly TariffYearDTO[]): TariffYearDTO[] {
  return [...years].sort(
    (a, b) =>
      b.tariff_year.first_gas_day.localeCompare(a.tariff_year.first_gas_day) ||
      (a.direction ?? "").localeCompare(b.direction ?? "") ||
      a.product.localeCompare(b.product),
  );
}
