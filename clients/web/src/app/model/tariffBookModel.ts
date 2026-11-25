/**
 * The tariff book's pure logic (TAR-1): which facilities have tariffs, the status a row shows
 * (indicative and final are never merged), the version trail of one tariff, and how far off a
 * capacity window is.
 */
import type { CapacityNoticeDTO, TariffPublisherDTO, TariffVersionDTO } from "../../api/client.ts";

export type Tone = "ok" | "watch" | "breach" | "info" | "simulated" | "stale" | "neutral";

export interface FacilityChoice {
  id: string;
  name: string;
  kind: TariffVersionDTO["facility_kind"];
  final: number;
  indicative: number;
}

/** Facilities in the current rows, those with indicative tariffs first, then by name. */
export function facilities(rows: readonly TariffVersionDTO[]): FacilityChoice[] {
  const byId = new Map<string, FacilityChoice>();
  for (const row of rows) {
    const held = byId.get(row.facility_id) ?? {
      id: row.facility_id,
      name: row.facility_name,
      kind: row.facility_kind,
      final: 0,
      indicative: 0,
    };
    if (row.status === "FINAL") held.final += 1;
    else held.indicative += 1;
    byId.set(row.facility_id, held);
  }
  return [...byId.values()].sort(
    (a, b) => Number(b.indicative > 0) - Number(a.indicative > 0) || a.name.localeCompare(b.name),
  );
}

/** Final reads as settled; indicative as "watch" so it is never mistaken for final. */
export function statusTone(row: Pick<TariffVersionDTO, "status" | "withdrawn">): Tone {
  if (row.withdrawn) return "stale";
  return row.status === "FINAL" ? "ok" : "watch";
}

/** The figure as published: one value, or one per cargo class. */
export function tariffFigure(row: Pick<TariffVersionDTO, "value" | "by_class" | "unit">): string {
  const number = new Intl.NumberFormat("en-GB", { maximumFractionDigits: 6 });
  if (row.value !== null) return `${number.format(row.value)} ${row.unit}`;
  const classes = Object.entries(row.by_class ?? {})
    .map(([name, value]) => `${name} ${number.format(value)}`)
    .join(" · ");
  return classes ? `${classes} ${row.unit}` : "—";
}

/** The period a tariff applies to, as dates (open-ended shows an arrow). */
export function periodText(row: Pick<TariffVersionDTO, "period_from" | "period_to">): string {
  return `${row.period_from} → ${row.period_to ?? "…"}`;
}

export interface TrailStep {
  version: number;
  status: TariffVersionDTO["status"];
  change: TariffVersionDTO["change_kind"];
  statusChange: string | null;
  figure: string;
  recorded: string;
  current: boolean;
  /** The figure moved against the version before (null for the first). */
  delta: number | null;
}

/** One tariff's versions, oldest first, each with what changed against the one before. */
export function versionTrail(rows: readonly TariffVersionDTO[]): TrailStep[] {
  const ordered = [...rows].sort((a, b) => a.version - b.version);
  return ordered.map((row, index) => {
    const previous = index > 0 ? ordered[index - 1] : null;
    const delta =
      previous && previous.value !== null && row.value !== null && !row.withdrawn
        ? row.value - previous.value
        : null;
    return {
      version: row.version,
      status: row.status,
      change: row.change_kind,
      statusChange: row.status_change,
      figure: row.withdrawn ? "—" : tariffFigure(row),
      recorded: row.recorded_at_utc,
      current: row.superseded_at_utc === null,
      delta,
    };
  });
}

/** Whole days from ``now`` to a window's opening (0 = today), in UTC days. */
export function daysUntil(opensAtUtc: string, now: Date): number {
  const opens = Date.parse(opensAtUtc);
  const startOf = (ms: number) => Math.floor(ms / 86_400_000);
  return startOf(opens) - startOf(now.getTime());
}

/** Soon (three days or less) is what the capacity alert also says. */
export function noticeTone(notice: Pick<CapacityNoticeDTO, "opens_at_utc" | "state">, now: Date): Tone {
  if (notice.state === "cancelled") return "stale";
  const days = daysUntil(notice.opens_at_utc, now);
  if (days < 0) return "neutral";
  return days <= 3 ? "info" : "neutral";
}

/** A publisher's read state as a badge tone. */
export function publisherTone(state: TariffPublisherDTO["state"]): Tone {
  switch (state) {
    case "current":
      return "ok";
    case "stale":
    case "never_read":
      return "watch";
    case "excluded":
      return "breach";
    default:
      return "neutral";
  }
}

/** Publishers worth a look first: stale, then never read, excluded, then the rest by name. */
export function publisherOrder(rows: readonly TariffPublisherDTO[]): TariffPublisherDTO[] {
  const rank: Record<string, number> = { stale: 0, never_read: 1, current: 2, manual: 3, excluded: 4 };
  return [...rows].sort(
    (a, b) => (rank[a.state] ?? 5) - (rank[b.state] ?? 5) || a.name.localeCompare(b.name),
  );
}
