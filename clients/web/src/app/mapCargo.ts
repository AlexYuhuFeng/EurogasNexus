import type { MapCargoDTO } from "@/api/client";
import { formatInstant } from "./time/timeFormat.ts";

/**
 * A cargo on the map, answered the way a trader asks (owner review 2026-11-26): where is it,
 * which terminal is it going to, how long until it gets there, and what that time rests on.
 *
 * Rule 19: nothing is invented. An ETA is the one the source reported (AIS, the master's
 * notice, the feed, the schedule, a manual entry, the confirmation's window), named as such;
 * only when no ETA was reported is one computed, from the straight-line distance still to go and
 * the speed the last two timed positions show, and it says so (straight line: a lower bound).
 * Without a destination or a position the map says that instead of drawing a guess.
 */

type Translate = (key: string, options?: Record<string, unknown>) => string;

export type EtaBasis =
  | "ais"
  | "master"
  | "feed"
  | "schedule"
  | "manual"
  | "contract"
  | "stated"
  | "computed";

export interface CargoEta {
  /** `eta`: a time to show; otherwise what is missing. */
  state: "eta" | "no_destination" | "no_eta";
  etaUtc: string | null;
  /** Milliseconds from now to the ETA (negative: the ETA has passed). */
  remainingMs: number | null;
  basis: EtaBasis | null;
  /** Who reported it (the source system), when reported. */
  source: string | null;
  /** The source's own confidence, when stated. */
  confidence: string | null;
  /** For a computed ETA: the speed (knots) and straight-line distance (nautical miles) used. */
  speedKn: number | null;
  distanceNm: number | null;
}

const REPORTED_BASIS: Record<string, EtaBasis> = {
  ais_declared: "ais",
  master_notice: "master",
  feed_estimate: "feed",
  schedule: "schedule",
  manual: "manual",
  contract_window: "contract",
};

const EARTH_RADIUS_NM = 3440.065;
/** Below this a vessel is not under way (drifting, anchored): no ETA is computed from it. */
const MIN_UNDERWAY_KN = 3;

const rad = (degrees: number) => (degrees * Math.PI) / 180;

/** Great-circle distance in nautical miles. */
export function distanceNm(from: [number, number], to: [number, number]): number {
  const [lon1, lat1] = from.map(rad);
  const [lon2, lat2] = to.map(rad);
  const a = Math.sin((lat2 - lat1) / 2) ** 2 + Math.cos(lat1) * Math.cos(lat2) * Math.sin((lon2 - lon1) / 2) ** 2;
  return 2 * EARTH_RADIUS_NM * Math.asin(Math.min(1, Math.sqrt(a)));
}

/** Initial bearing from one point to another, degrees clockwise from north (0-360). */
export function bearing(from: [number, number], to: [number, number]): number {
  const [lon1, lat1] = from.map(rad);
  const [lon2, lat2] = to.map(rad);
  const y = Math.sin(lon2 - lon1) * Math.cos(lat2);
  const x = Math.cos(lat1) * Math.sin(lat2) - Math.sin(lat1) * Math.cos(lat2) * Math.cos(lon2 - lon1);
  return ((Math.atan2(y, x) * 180) / Math.PI + 360) % 360;
}

/** The vessel's reported positions with their times, oldest first (the track, then `position`). */
function timedFixes(cargo: MapCargoDTO): Array<{ at: [number, number]; ms: number | null }> {
  const fixes = cargo.track.map((point, index) => {
    const time = cargo.track_times?.[index] ?? null;
    const ms = time ? Date.parse(time) : NaN;
    return { at: [point[0], point[1]] as [number, number], ms: Number.isFinite(ms) ? ms : null };
  });
  if (cargo.position) {
    const at: [number, number] = [cargo.position.lon, cargo.position.lat];
    const ms = cargo.position_at_utc ? Date.parse(cargo.position_at_utc) : NaN;
    const last = fixes[fixes.length - 1];
    if (!last || last.at[0] !== at[0] || last.at[1] !== at[1]) fixes.push({ at, ms: Number.isFinite(ms) ? ms : null });
    else if (last.ms === null && Number.isFinite(ms)) last.ms = ms;
  }
  return fixes;
}

/**
 * The heading the vessel was last seen on, from its last two reported positions; null when it
 * has fewer than two (the map then draws it without a direction, never pointed at its terminal).
 */
export function cargoHeading(cargo: MapCargoDTO): number | null {
  const fixes = timedFixes(cargo);
  for (let index = fixes.length - 1; index > 0; index -= 1) {
    const to = fixes[index].at;
    const from = fixes[index - 1].at;
    if (from[0] !== to[0] || from[1] !== to[1]) return Math.round(bearing(from, to));
  }
  return null;
}

/** Speed over ground (knots) between the last two timed positions; null when not known. */
export function cargoSpeedKn(cargo: MapCargoDTO): number | null {
  const fixes = timedFixes(cargo).filter((fix) => fix.ms !== null);
  if (fixes.length < 2) return null;
  const last = fixes[fixes.length - 1];
  const before = fixes[fixes.length - 2];
  const hours = (last.ms! - before.ms!) / 3_600_000;
  if (!(hours > 0)) return null;
  return distanceNm(before.at, last.at) / hours;
}

/** When the cargo arrives, and what that rests on. */
export function cargoEta(cargo: MapCargoDTO, nowMs: number): CargoEta {
  const none: CargoEta = {
    state: "no_eta", etaUtc: null, remainingMs: null, basis: null, source: null, confidence: null, speedKn: null, distanceNm: null,
  };
  if (!cargo.destination_terminal && !cargo.destination) return { ...none, state: "no_destination" };
  if (cargo.eta_utc) {
    const ms = Date.parse(cargo.eta_utc);
    const stated = cargo.eta?.basis ? REPORTED_BASIS[cargo.eta.basis] : undefined;
    return {
      ...none,
      state: "eta",
      etaUtc: cargo.eta_utc,
      remainingMs: Number.isFinite(ms) ? ms - nowMs : null,
      basis: stated ?? "stated",
      source: cargo.eta?.source ?? cargo.source_system ?? null,
      confidence: cargo.eta?.confidence ?? null,
    };
  }
  const speed = cargoSpeedKn(cargo);
  if (cargo.position && cargo.destination && speed !== null && speed >= MIN_UNDERWAY_KN) {
    const distance = distanceNm([cargo.position.lon, cargo.position.lat], [cargo.destination.lon, cargo.destination.lat]);
    const fixedAt = cargo.position_at_utc ? Date.parse(cargo.position_at_utc) : nowMs;
    const etaMs = (Number.isFinite(fixedAt) ? fixedAt : nowMs) + (distance / speed) * 3_600_000;
    return {
      ...none,
      state: "eta",
      etaUtc: new Date(etaMs).toISOString(),
      remainingMs: etaMs - nowMs,
      basis: "computed",
      source: cargo.source_system ?? null,
      speedKn: speed,
      distanceNm: distance,
    };
  }
  return none;
}

/** "2 d 4 h", "5 h 20 min", "40 min" in the app's language. */
export function formatRemaining(ms: number, t: Translate): string {
  const minutes = Math.max(0, Math.round(Math.abs(ms) / 60_000));
  const days = Math.floor(minutes / 1440);
  const hours = Math.floor((minutes % 1440) / 60);
  const mins = minutes % 60;
  if (days > 0) return t("map.cargo.duration_dh", { days, hours });
  if (hours > 0) return t("map.cargo.duration_hm", { hours, minutes: mins });
  return t("map.cargo.duration_m", { minutes: mins });
}

/** "arrives in 2 d 4 h", "ETA passed 6 h ago", or what is missing. */
export function arrivalPhrase(eta: CargoEta, t: Translate): string {
  if (eta.state === "no_destination") return t("map.cargo.no_destination");
  if (eta.state === "no_eta" || eta.remainingMs === null) return t("map.cargo.no_eta");
  const span = formatRemaining(eta.remainingMs, t);
  return eta.remainingMs >= 0 ? t("map.cargo.arrives_in", { span }) : t("map.cargo.eta_passed", { span });
}

/** What the ETA rests on, in a sentence ("AIS-reported ETA", "computed from ..."). */
export function etaBasisPhrase(eta: CargoEta, t: Translate): string {
  if (!eta.basis) return "";
  if (eta.basis === "computed") {
    return t("map.cargo.basis.computed", {
      speed: (eta.speedKn ?? 0).toFixed(1),
      distance: Math.round(eta.distanceNm ?? 0).toLocaleString("en-GB"),
    });
  }
  const sentence = t(`map.cargo.basis.${eta.basis}`, { source: eta.source ?? "" });
  return eta.confidence ? `${sentence} · ${t(`map.cargo.confidence.${eta.confidence}`, { defaultValue: eta.confidence })}` : sentence;
}

/** The ETA instant as the desk reads it, in UTC: "28 Nov 16:00 UTC" (the app's language). */
export function etaUtcText(iso: string | null, language = "en"): string {
  return formatInstant(iso, { preference: "utc", date: "always", language })?.text ?? "–";
}

/** The compact label beside our cargo on the map: "Meridian → Zeebrugge · 2 d 4 h". */
export function cargoMapLabel(cargo: MapCargoDTO, eta: CargoEta, t: Translate): string {
  const to = cargo.destination_terminal ?? t("map.cargo.destination_unknown");
  const when = eta.state === "eta" && eta.remainingMs !== null
    ? (eta.remainingMs >= 0 ? formatRemaining(eta.remainingMs, t) : t("map.cargo.overdue_short"))
    : null;
  return [`${cargo.vessel_name} → ${to}`, when].filter(Boolean).join(" · ");
}

/**
 * Whether our cargo can be drawn: a position (or the port it is loading at, or the terminal it
 * is discharging at), and a located destination for the leg still to go. What is false is said
 * on the card instead of drawn.
 */
export function cargoDrawable(cargo: MapCargoDTO): { position: boolean; destination: boolean } {
  const position = Boolean(
    cargo.position
      || (cargo.status === "loading" && cargo.origin)
      || ((cargo.status === "discharging" || cargo.status === "delivered") && cargo.destination),
  );
  return { position, destination: Boolean(cargo.destination) };
}
