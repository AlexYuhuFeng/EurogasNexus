/**
 * "Our book" on the live map: the firm's own deals, by what still needs a decision.
 *
 * A trader looking at the map for their book wants what is moving now and what comes next,
 * not what is done: a delivered cargo or an ended regas window changes no decision. So
 * every own item is placed in one phase:
 *
 * - **in progress**: a cargo loading, at sea or discharging; a regas window open now; a
 *   supply contract inside its delivery period;
 * - **next 7 days**: starts within a week (a cargo not yet sailed, a slot opening, a
 *   contract whose gas year begins);
 * - **later**: starts after that;
 * - **completed**: delivered, ended or expired. Kept for looking back (and replaying a
 *   cargo along its timed track), never drawn in the live picture.
 *
 * Within a phase, the item that needs attention first comes first: the soonest ETA,
 * window or start.
 */
import type { MapCargoDTO, MapContractDTO, MapRegasSlotDTO, MapSituationDTO } from "../api/client";

export type BookPhase = "in_progress" | "next_7_days" | "later" | "completed";

export interface BookItem {
  kind: "cargo" | "slot" | "contract";
  id: string;
  label: string;
  phase: BookPhase;
  /** The moment that orders the item inside its phase (ETA, window, start), ms. */
  when: number | null;
  /** Network point or facility the item is located at, for selecting its place. */
  refId: string | null;
  cargo?: MapCargoDTO;
  slot?: MapRegasSlotDTO;
  contract?: MapContractDTO;
}

export const BOOK_PHASES: readonly BookPhase[] = ["in_progress", "next_7_days", "later", "completed"];

const DAY_MS = 86_400_000;

function ms(value: string | null | undefined): number | null {
  if (!value) return null;
  const parsed = Date.parse(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function upcoming(start: number | null, now: number): BookPhase {
  if (start === null) return "in_progress";
  return start - now <= 7 * DAY_MS ? "next_7_days" : "later";
}

/**
 * The delivery period of a gas year as recorded: "2026" is 1 Oct 2026 to 1 Oct 2027, "2026+"
 * runs from 1 Oct 2026 with no end, "2026/27" as "2026". Null when the text names no year.
 */
export function gasYearWindow(gasYear: string): { start: number; end: number | null } | null {
  const match = /^(\d{4})(\+|\/\d{2,4})?$/.exec(gasYear.trim());
  if (!match) return null;
  const year = Number(match[1]);
  const start = Date.UTC(year, 9, 1, 5);
  return { start, end: match[2] === "+" ? null : Date.UTC(year + 1, 9, 1, 5) };
}

export function cargoPhase(cargo: MapCargoDTO, now: number): BookPhase {
  if (cargo.status === "delivered" || cargo.status === "ballast") return "completed";
  if (cargo.status === "loading" || cargo.status === "discharging") return "in_progress";
  const departed = ms(cargo.departed_at_utc);
  if (departed !== null && departed > now) return upcoming(departed, now);
  return "in_progress";
}

export function slotPhase(slot: MapRegasSlotDTO, now: number): BookPhase {
  const start = ms(slot.window_start_utc);
  const end = ms(slot.window_end_utc);
  if (end !== null && end < now) return "completed";
  if (slot.active || (start !== null && start <= now)) return "in_progress";
  return upcoming(start, now);
}

export function contractPhase(contract: MapContractDTO, now: number): BookPhase {
  const window = gasYearWindow(contract.gas_year);
  if (!window) return "in_progress";
  if (window.end !== null && window.end <= now) return "completed";
  if (window.start <= now) return "in_progress";
  return upcoming(window.start, now);
}

/** The firm's own items with their phase, attention order first. */
export function bookItems(situation: MapSituationDTO | null, now: number): BookItem[] {
  if (!situation) return [];
  const items: BookItem[] = [];
  for (const cargo of situation.cargoes) {
    if (!cargo.own) continue;
    const phase = cargoPhase(cargo, now);
    items.push({
      kind: "cargo",
      id: cargo.cargo_id,
      label: cargo.vessel_name,
      phase,
      when: phase === "completed" ? ms(cargo.eta_utc) : ms(cargo.eta_utc) ?? ms(cargo.departed_at_utc),
      refId: cargo.destination?.ref_id ?? null,
      cargo,
    });
  }
  for (const slot of situation.regas_slots) {
    const phase = slotPhase(slot, now);
    items.push({
      kind: "slot",
      id: slot.slot_id,
      label: slot.terminal_name,
      phase,
      when: phase === "in_progress" || phase === "completed" ? ms(slot.window_end_utc) : ms(slot.window_start_utc),
      refId: slot.location.ref_id ?? null,
      slot,
    });
  }
  for (const contract of situation.contracts) {
    const phase = contractPhase(contract, now);
    const window = gasYearWindow(contract.gas_year);
    items.push({
      kind: "contract",
      id: contract.contract_id,
      label: contract.contract_name,
      phase,
      when: phase === "in_progress" ? window?.end ?? null : window?.start ?? null,
      refId: contract.location.ref_id ?? null,
      contract,
    });
  }
  const order = (item: BookItem) => BOOK_PHASES.indexOf(item.phase);
  return items.sort((a, b) => {
    if (order(a) !== order(b)) return order(a) - order(b);
    // Completed: the most recent first. Otherwise: the soonest first, undated last.
    const sign = a.phase === "completed" ? -1 : 1;
    if (a.when === b.when) return a.label.localeCompare(b.label);
    if (a.when === null) return 1;
    if (b.when === null) return -1;
    return sign * (a.when - b.when);
  });
}

/**
 * The live picture of the book: only items still in play. Market items (outages, other
 * companies' cargoes, flows) are left to the network view; outages in force stay, since
 * they can stop a delivery.
 */
export function bookSituation(situation: MapSituationDTO | null, now: number): MapSituationDTO | null {
  if (!situation) return null;
  return {
    ...situation,
    flows: [],
    outages: situation.outages.filter((outage) => outage.status === "active"),
    cargoes: situation.cargoes.filter((cargo) => cargo.own && cargoPhase(cargo, now) !== "completed"),
    regas_slots: situation.regas_slots.filter((slot) => slotPhase(slot, now) !== "completed"),
    contracts: situation.contracts.filter((contract) => contractPhase(contract, now) !== "completed"),
  };
}

/** The network picture leaves completed deals out too: they are history, not situation. */
export function liveSituation(situation: MapSituationDTO | null, now: number): MapSituationDTO | null {
  if (!situation) return null;
  return {
    ...situation,
    cargoes: situation.cargoes.filter((cargo) => !cargo.own || cargoPhase(cargo, now) !== "completed"),
    regas_slots: situation.regas_slots.filter((slot) => slotPhase(slot, now) !== "completed"),
    contracts: situation.contracts.filter((contract) => contractPhase(contract, now) !== "completed"),
  };
}

export interface ReplayTrack {
  coords: Array<[number, number]>;
  times: number[];
  start: number;
  end: number;
}

/**
 * A cargo's voyage as a timed track: the reported points with their times, from the load
 * port to the terminal. Null when fewer than two points carry a time (nothing to replay
 * honestly: the path between untimed points is not known).
 */
export function replayTrack(cargo: MapCargoDTO): ReplayTrack | null {
  const coords: Array<[number, number]> = [];
  const times: number[] = [];
  cargo.track.forEach((point, index) => {
    const when = ms(cargo.track_times?.[index] ?? null);
    if (when === null) return;
    coords.push([point[0], point[1]]);
    times.push(when);
  });
  if (cargo.status === "delivered" && cargo.destination && ms(cargo.eta_utc) !== null) {
    const arrived = ms(cargo.eta_utc)!;
    if (times.length === 0 || arrived > times[times.length - 1]) {
      coords.push([cargo.destination.lon, cargo.destination.lat]);
      times.push(arrived);
    }
  }
  if (coords.length < 2) return null;
  return { coords, times, start: times[0], end: times[times.length - 1] };
}

/** Where the vessel was at ``moment`` (linear between reported points) and the path so far. */
export function replayAt(track: ReplayTrack, moment: number): { at: [number, number]; sailed: Array<[number, number]> } {
  const { coords, times } = track;
  if (moment <= times[0]) return { at: coords[0], sailed: [coords[0]] };
  for (let index = 1; index < times.length; index += 1) {
    if (moment === times[index]) return { at: coords[index], sailed: coords.slice(0, index + 1) };
    if (moment < times[index]) {
      const share = (moment - times[index - 1]) / Math.max(1, times[index] - times[index - 1]);
      const [x0, y0] = coords[index - 1];
      const [x1, y1] = coords[index];
      const at: [number, number] = [x0 + (x1 - x0) * share, y0 + (y1 - y0) * share];
      return { at, sailed: [...coords.slice(0, index), at] };
    }
  }
  return { at: coords[coords.length - 1], sailed: coords };
}
