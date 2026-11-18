/**
 * The instrument picker's model (design basis 2, D.2): two levels, hub first, then product kind
 * and tenor; desk-shorthand search; presets; recent picks. Pure functions and a keyboard
 * reducer, so the component (`components/ui/InstrumentPicker.tsx`) only renders.
 *
 * - **Catalogue**: built from `GET /api/market/instruments` (hub → product kind → tenor, what
 *   the caller's store holds), or from a plain hub list when only a hub is being chosen.
 * - **Search grammar**: `ttf jan27`, `nbp m+1`, `the q1-27`, `ztp da`, `peg cal-28`, `英国 次月`,
 *   `荷兰 27年1月`. A hub word (code, name, or its Chinese country name) and a tenor clause in the
 *   product grammar the answer bar uses (`app/answer/period.ts`, which mirrors
 *   `domain/market/products.py`). A relative code (`m+1`) also finds the absolute month it
 *   delivers today when the store holds months, not the rolling series.
 * - **Presets**: front month, next quarter, next season, next calendar year, day-ahead; each
 *   resolves to what the hub holds, or is absent.
 * - **Levels never list more than {@link MAX_VISIBLE} items**; the rest is reached by search.
 */

import { parsePeriod } from "../answer/period.ts";
import type {
  InstrumentCatalogueDTO,
  InstrumentProductKind,
  InstrumentSourceClass,
} from "../../api/comparablePrices.ts";

/** At most this many options are shown at one level. */
export const MAX_VISIBLE = 12;
/** Recent picks kept per browser. */
export const MAX_RECENT = 5;
export const RECENT_STORAGE_KEY = "egn.instrument-picker.recent";

export interface PickerInstrument {
  id: string;
  hub: string;
  code: string;
  label: string;
  productKind: InstrumentProductKind;
  /** The stored tenor key a spread-analysis leg names. */
  tenor: string;
  nativeUnit: string;
  sourceClass: InstrumentSourceClass;
  simulated: boolean;
  observations: number;
  thin: boolean;
  lastAsOf: string | null;
  expired: boolean;
  firstGasDay: string | null;
}

export interface PickerHub {
  hub: string;
  name: string;
  nativeUnit: string;
  simulated: boolean;
  lastAsOf: string | null;
  kinds: Array<{ kind: InstrumentProductKind; instruments: PickerInstrument[] }>;
}

export interface PickerCatalogue {
  hubs: PickerHub[];
}

export type PickerSelection = { hub: string; instrument: PickerInstrument | null };

/** The catalogue from the server read. */
export function catalogueFromDTO(dto: InstrumentCatalogueDTO | null | undefined): PickerCatalogue {
  return {
    hubs: (dto?.hubs ?? []).map((hub) => ({
      hub: hub.hub,
      name: hub.name,
      nativeUnit: hub.native_unit,
      simulated: hub.simulated,
      lastAsOf: hub.last_as_of,
      kinds: hub.kinds.map((kind) => ({
        kind: kind.kind,
        instruments: kind.instruments.map((item) => ({
          id: item.id,
          hub: item.hub,
          code: item.code,
          label: item.label,
          productKind: item.product_kind,
          tenor: item.tenor,
          nativeUnit: item.native_unit,
          sourceClass: item.source_class,
          simulated: item.simulated,
          observations: item.observations,
          thin: item.thin,
          lastAsOf: item.last_as_of,
          expired: item.expired,
          firstGasDay: item.delivery?.first_gas_day ?? null,
        })),
      })),
    })),
  };
}

/** A hub-only catalogue (a chart that picks a hub, not a tenor). */
export function catalogueFromHubs(
  hubs: Array<{ hub: string; name?: string; nativeUnit: string; simulated?: boolean; lastAsOf?: string | null }>,
): PickerCatalogue {
  return {
    hubs: hubs.map((hub) => ({
      hub: hub.hub,
      name: hub.name ?? hub.hub,
      nativeUnit: hub.nativeUnit,
      simulated: Boolean(hub.simulated),
      lastAsOf: hub.lastAsOf ?? null,
      kinds: [],
    })),
  };
}

/** Hub words a desk types, English and Chinese, beyond the code itself. */
const HUB_WORDS: Record<string, string> = {
  dutch: "TTF", netherlands: "TTF", 荷兰: "TTF", 荷兰ttf: "TTF",
  uk: "NBP", britain: "NBP", british: "NBP", 英国: "NBP", 英国nbp: "NBP",
  german: "THE", germany: "THE", 德国: "THE", 德国the: "THE",
  french: "PEG", france: "PEG", 法国: "PEG",
  belgian: "ZTP", belgium: "ZTP", zeebrugge: "ZTP", 比利时: "ZTP", 泽布吕赫: "ZTP",
  italian: "PSV", italy: "PSV", 意大利: "PSV",
  austrian: "CEGH", austria: "CEGH", baumgarten: "CEGH", 奥地利: "CEGH",
  spanish: "PVB", spain: "PVB", 西班牙: "PVB",
  danish: "ETF", denmark: "ETF", 丹麦: "ETF",
  henry: "HH", "henry hub": "HH", 亨利港: "HH", 亨利中心: "HH", 美国: "HH",
};

/** The hub a word names among `hubs`, or null. */
export function hubForWord(word: string, hubs: readonly string[]): string | null {
  const text = word.trim().toLowerCase();
  if (!text) return null;
  const code = hubs.find((hub) => hub.toLowerCase() === text);
  if (code) return code;
  const named = HUB_WORDS[text];
  return named && hubs.includes(named) ? named : null;
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

function addMonths(year: number, month: number, offset: number): [number, number] {
  const index = year * 12 + month + offset;
  return [Math.floor(index / 12), index % 12];
}

/**
 * Absolute codes a relative code delivers on `today` (`M+1` on 17 Nov 2026 is `Dec-26`), so a
 * store holding months answers `nbp m+1`. Season and year use the gas-product calendar's rules.
 */
export function absoluteCodes(code: string, today: Date): string[] {
  const match = /^(M|Q|S|GY|Cal)\+(\d{1,2})$/.exec(code);
  if (!match) return [];
  const n = Number(match[2]);
  const year = today.getUTCFullYear();
  const month = today.getUTCMonth();
  const yy = (value: number) => String(value % 100).padStart(2, "0");
  switch (match[1]) {
    case "M": {
      const [y, m] = addMonths(year, month, n);
      return [`${MONTHS[m]}-${yy(y)}`];
    }
    case "Q": {
      const index = year * 4 + Math.floor(month / 3) + n;
      return [`Q${(index % 4) + 1}-${yy(Math.floor(index / 4))}`];
    }
    case "S": {
      const current = month >= 9 ? 2 * year + 1 : month >= 3 ? 2 * year : 2 * (year - 1) + 1;
      const index = current + n;
      return [`${index % 2 === 0 ? "Sum" : "Win"}-${yy(Math.floor(index / 2))}`];
    }
    case "GY":
      return [`GY-${yy((month >= 9 ? year : year - 1) + n)}`];
    default:
      return [`Cal-${yy(year + n)}`];
  }
}

function allInstruments(hub: PickerHub): PickerInstrument[] {
  return hub.kinds.flatMap((kind) => kind.instruments);
}

function sameCode(a: string, b: string): boolean {
  return a.toLowerCase() === b.toLowerCase();
}

/** The instruments of `hub` a product code names: exactly, else what a relative code delivers. */
export function instrumentsForCode(hub: PickerHub, code: string, today: Date): PickerInstrument[] {
  const items = allInstruments(hub);
  const exact = items.filter((item) => sameCode(item.code, code));
  if (exact.length) return exact;
  // "spot" and "DA": a hub that quotes a spot index (HH) answers DA with it.
  if (sameCode(code, "DA")) return items.filter((item) => sameCode(item.code, "Spot"));
  const absolute = absoluteCodes(code, today);
  if (absolute.length) return items.filter((item) => absolute.some((value) => sameCode(item.code, value)));
  // An absolute month the rolling series delivers today (`jan27` when only M+1 is held is not
  // the same instrument: not offered).
  return [];
}

export type SearchResult =
  | { kind: "hub"; hub: PickerHub }
  | { kind: "instrument"; hub: PickerHub; instrument: PickerInstrument };

/**
 * What a typed query finds, best first, at most {@link MAX_VISIBLE}. `hub` restricts the search
 * to one hub (level 2).
 */
export function searchCatalogue(
  query: string,
  catalogue: PickerCatalogue,
  { today = new Date(), hub: within = null }: { today?: Date; hub?: string | null } = {},
): SearchResult[] {
  const text = query.trim().toLowerCase().replace(/\s+/g, " ");
  if (!text) return [];
  const hubs = within ? catalogue.hubs.filter((item) => item.hub === within) : catalogue.hubs;
  const codes = hubs.map((item) => item.hub);
  const byCode = new Map(hubs.map((item) => [item.hub, item]));

  // Hub word first ("ttf jan27", "荷兰 27年1月"); a Chinese hub word may be glued on ("英国次月").
  let hubCode: string | null = null;
  let rest = text;
  const words = text.split(" ");
  for (const take of [2, 1]) {
    if (words.length < take) continue;
    const found = hubForWord(words.slice(0, take).join(" "), codes);
    if (found) {
      hubCode = found;
      rest = words.slice(take).join(" ");
      break;
    }
  }
  if (!hubCode) {
    for (const [word, code] of Object.entries(HUB_WORDS)) {
      if (/[一-鿿]/.test(word) && text.startsWith(word) && codes.includes(code)) {
        hubCode = code;
        rest = text.slice(word.length).trim();
        break;
      }
    }
  }
  if (within && !hubCode) hubCode = within;

  const results: SearchResult[] = [];
  const period = rest ? parsePeriod(rest) : null;
  if (hubCode && !rest) {
    const hub = byCode.get(hubCode);
    if (hub) results.push({ kind: "hub", hub });
  } else if (period) {
    for (const hub of hubCode ? [byCode.get(hubCode)!] : hubs) {
      for (const instrument of instrumentsForCode(hub, period.code, today)) {
        results.push({ kind: "instrument", hub, instrument });
      }
    }
  } else if (rest) {
    // Free text: a code, label or hub name that starts with what is typed.
    const scope = hubCode ? [byCode.get(hubCode)!] : hubs;
    for (const hub of scope) {
      if (!hubCode && (hub.hub.toLowerCase().startsWith(rest) || hub.name.toLowerCase().includes(rest))) {
        results.push({ kind: "hub", hub });
      }
      for (const instrument of allInstruments(hub)) {
        const code = instrument.code.toLowerCase();
        if (code.startsWith(rest) || code.replace(/[-+]/g, "").startsWith(rest.replace(/[-+\s]/g, ""))) {
          results.push({ kind: "instrument", hub, instrument });
        }
      }
    }
  }
  return results.slice(0, MAX_VISIBLE);
}

export type PresetKey = "front_month" | "next_quarter" | "next_season" | "next_cal" | "day_ahead";
export const PRESETS: readonly PresetKey[] = ["front_month", "next_quarter", "next_season", "next_cal", "day_ahead"];

const PRESET_CODES: Record<PresetKey, string[]> = {
  front_month: ["M+1"],
  next_quarter: ["Q+1"],
  next_season: ["S+1"],
  next_cal: ["Cal+1"],
  day_ahead: ["DA", "Spot"],
};

/** The instrument a preset picks at `hub`, or null when the hub holds nothing for it. */
export function presetInstrument(hub: PickerHub, preset: PresetKey, today: Date): PickerInstrument | null {
  for (const code of PRESET_CODES[preset]) {
    const found = instrumentsForCode(hub, code, today).filter((item) => !item.expired);
    if (found.length) return found[0];
  }
  return null;
}

/** Hubs in the order shown: recent hubs first, then the catalogue's (desk) order. */
export function orderedHubs(catalogue: PickerCatalogue, recent: readonly string[]): PickerHub[] {
  const recentHubs = recent.map((id) => id.split(":")[0]);
  const rank = (hub: string) => {
    const index = recentHubs.indexOf(hub);
    return index < 0 ? Number.MAX_SAFE_INTEGER : index;
  };
  return catalogue.hubs
    .map((hub, index) => ({ hub, index }))
    .sort((a, b) => rank(a.hub.hub) - rank(b.hub.hub) || a.index - b.index)
    .map((item) => item.hub);
}

/** The product kinds a hub holds, in catalogue order. */
export function hubKinds(hub: PickerHub | null): InstrumentProductKind[] {
  return hub ? hub.kinds.filter((kind) => kind.instruments.length > 0).map((kind) => kind.kind) : [];
}

/** Recent picks that still exist in the catalogue, newest first. */
export function recentInstruments(catalogue: PickerCatalogue, recent: readonly string[]): Array<{ hub: PickerHub; instrument: PickerInstrument }> {
  const found: Array<{ hub: PickerHub; instrument: PickerInstrument }> = [];
  for (const id of recent) {
    for (const hub of catalogue.hubs) {
      const instrument = allInstruments(hub).find((item) => item.id === id);
      if (instrument) found.push({ hub, instrument });
    }
  }
  return found;
}

/** The recent list after a pick: the id first, no duplicates, at most {@link MAX_RECENT}. */
export function withRecent(recent: readonly string[], id: string): string[] {
  return [id, ...recent.filter((item) => item !== id)].slice(0, MAX_RECENT);
}

export function readRecent(storage: Pick<Storage, "getItem"> | null | undefined): string[] {
  try {
    const raw = storage?.getItem(RECENT_STORAGE_KEY);
    const parsed = raw ? (JSON.parse(raw) as unknown) : [];
    return Array.isArray(parsed) ? parsed.filter((item): item is string => typeof item === "string").slice(0, MAX_RECENT) : [];
  } catch {
    return [];
  }
}

export function writeRecent(storage: Pick<Storage, "setItem"> | null | undefined, recent: readonly string[]): void {
  try {
    storage?.setItem(RECENT_STORAGE_KEY, JSON.stringify(recent.slice(0, MAX_RECENT)));
  } catch {
    /* private window or blocked storage: recent picks are a convenience */
  }
}

// --- the options one level shows, and the keyboard ------------------------------------------

export type PickerOption =
  | { type: "hub"; id: string; hub: PickerHub; recent: boolean }
  | { type: "instrument"; id: string; hub: PickerHub; instrument: PickerInstrument; recent: boolean };

export interface PickerState {
  open: boolean;
  /** `hub` = level 1; `tenor` = level 2 for `hub`. */
  level: "hub" | "tenor";
  hub: string | null;
  kind: InstrumentProductKind | null;
  query: string;
  active: number;
}

export const CLOSED: PickerState = { open: false, level: "hub", hub: null, kind: null, query: "", active: 0 };

export interface OptionsResult {
  options: PickerOption[];
  /** Items the level holds beyond what is shown (reach them by search). */
  hidden: number;
}

/** The options the current level (or search) shows, at most {@link MAX_VISIBLE}. */
export function pickerOptions(
  state: PickerState,
  catalogue: PickerCatalogue,
  { recent = [], today = new Date(), scope = "instrument" }: { recent?: readonly string[]; today?: Date; scope?: "hub" | "instrument" } = {},
): OptionsResult {
  const cap = (options: PickerOption[]): OptionsResult => ({
    options: options.slice(0, MAX_VISIBLE),
    hidden: Math.max(0, options.length - MAX_VISIBLE),
  });
  if (state.query.trim()) {
    const found = searchCatalogue(state.query, catalogue, { today, hub: state.level === "tenor" ? state.hub : null });
    return cap(
      found
        .filter((item) => scope === "instrument" || item.kind === "hub")
        .map((item) =>
          item.kind === "hub"
            ? { type: "hub" as const, id: `hub:${item.hub.hub}`, hub: item.hub, recent: false }
            : { type: "instrument" as const, id: item.instrument.id, hub: item.hub, instrument: item.instrument, recent: false },
        ),
    );
  }
  if (state.level === "hub" || scope === "hub") {
    const recentPicks = scope === "instrument" ? recentInstruments(catalogue, recent).slice(0, 3) : [];
    const options: PickerOption[] = [
      ...recentPicks.map(({ hub, instrument }) => ({ type: "instrument" as const, id: `recent:${instrument.id}`, hub, instrument, recent: true })),
      ...orderedHubs(catalogue, scope === "hub" ? recent.map((id) => `${id}:`) : recent).map((hub) => ({ type: "hub" as const, id: `hub:${hub.hub}`, hub, recent: false })),
    ];
    return cap(options);
  }
  const hub = catalogue.hubs.find((item) => item.hub === state.hub);
  if (!hub) return { options: [], hidden: 0 };
  const kind = state.kind ?? hubKinds(hub)[0] ?? null;
  const instruments = hub.kinds.find((item) => item.kind === kind)?.instruments ?? [];
  return cap(instruments.map((instrument) => ({ type: "instrument" as const, id: instrument.id, hub, instrument, recent: false })));
}

export type PickerEffect =
  | { type: "none" }
  | { type: "close" }
  | { type: "choose"; option: PickerOption };

/**
 * One key in the search box. `options` are what is shown; `kinds` the level-2 tabs. Returns the
 * next state and what the component must do (choose an option, close).
 */
export function pickerKey(
  state: PickerState,
  key: string,
  { options, kinds }: { options: readonly PickerOption[]; kinds: readonly InstrumentProductKind[] },
): { state: PickerState; effect: PickerEffect } {
  const none = { type: "none" } as const;
  const count = options.length;
  const queryEmpty = state.query.length === 0;
  switch (key) {
    case "ArrowDown":
      if (!state.open) return { state: { ...state, open: true, active: 0 }, effect: none };
      return { state: { ...state, active: count ? Math.min(state.active + 1, count - 1) : 0 }, effect: none };
    case "ArrowUp":
      return { state: { ...state, active: Math.max(state.active - 1, 0) }, effect: none };
    case "Home":
    case "End":
      if (!queryEmpty) return { state, effect: none }; // the caret moves in the text instead
      return { state: { ...state, active: key === "Home" ? 0 : Math.max(count - 1, 0) }, effect: none };
    case "PageDown":
      return { state: { ...state, active: Math.min(state.active + 5, Math.max(count - 1, 0)) }, effect: none };
    case "PageUp":
      return { state: { ...state, active: Math.max(state.active - 5, 0) }, effect: none };
    case "ArrowRight":
    case "ArrowLeft": {
      if (!queryEmpty || state.level !== "tenor" || kinds.length === 0) return { state, effect: none };
      const current = Math.max(0, kinds.indexOf(state.kind ?? kinds[0]));
      const next = key === "ArrowRight" ? (current + 1) % kinds.length : (current - 1 + kinds.length) % kinds.length;
      return { state: { ...state, kind: kinds[next], active: 0 }, effect: none };
    }
    case "Enter": {
      const option = options[state.active];
      return option ? { state, effect: { type: "choose", option } } : { state, effect: none };
    }
    case "Escape":
      if (!queryEmpty) return { state: { ...state, query: "", active: 0 }, effect: none };
      if (state.level === "tenor") return { state: { ...state, level: "hub", hub: null, kind: null, active: 0 }, effect: none };
      return { state: CLOSED, effect: { type: "close" } };
    case "Backspace":
      if (queryEmpty && state.level === "tenor") {
        return { state: { ...state, level: "hub", hub: null, kind: null, active: 0 }, effect: none };
      }
      return { state, effect: none };
    default:
      return { state, effect: none };
  }
}

/** The state after typing in the search box: the first match becomes active. */
export function withQuery(state: PickerState, query: string): PickerState {
  return { ...state, open: true, query, active: 0 };
}

/** The state after choosing a hub at level 1: its first kind, its first tenor. */
export function enterHub(state: PickerState, hub: PickerHub): PickerState {
  return { ...state, level: "tenor", hub: hub.hub, kind: hubKinds(hub)[0] ?? null, query: "", active: 0 };
}

/** The selection an option makes, or null when it opens a level instead. */
export function selectionOf(option: PickerOption, scope: "hub" | "instrument"): PickerSelection | null {
  if (option.type === "instrument") return { hub: option.hub.hub, instrument: option.instrument };
  return scope === "hub" ? { hub: option.hub.hub, instrument: null } : null;
}

/** How a desk writes a unit: `p/th` for pence per therm. */
export function unitLabel(unit: string): string {
  return unit.replace(/^GBp\/th$/, "p/th");
}
