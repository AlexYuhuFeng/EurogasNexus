/**
 * The regas auction desk on screen (Desk → Cargoes → Regas auctions): pure helpers for the case
 * view and the case form. The server computes every figure (exact decimal text); these only
 * choose words and tones, count down, convert the auction's wall-clock times and build the
 * request body. Nothing here bids or orders (AGENTS.md rule 8).
 */
import type {
  RegasAnswerDTO,
  RegasCaseBody,
  RegasCaseInputsDTO,
  RegasChoicesDTO,
  RegasState,
} from "../../api/regasAuction.ts";

/** What re-reads the answer: a price, FX or rate change, and a mark, limit or assumption. */
export const REGAS_LIVE_TOPICS = ["prices", "book"] as const;
/** The shortest time between two re-reads on price notices (a burst of ticks reads once). */
export const REGAS_LIVE_MS = 2_000;

export type Tone = "ok" | "watch" | "breach" | "info" | "simulated" | "stale" | "neutral";

/** The state's badge tone: room to bid green, at the limit amber, stop red. */
export function stateTone(state: RegasState): Tone {
  switch (state) {
    case "room":
      return "ok";
    case "at_limit":
      return "watch";
    case "stop":
      return "breach";
    case "illustration":
      return "simulated";
    case "missing_inputs":
      return "watch";
    default:
      return "neutral";
  }
}

/** Whether the answer may be read as a bid level (a computed answer on real or entered data). */
export function isBidLevel(answer: Pick<RegasAnswerDTO, "computed" | "simulated">): boolean {
  return answer.computed && !answer.simulated;
}

/** A countdown in desk form: "2d 04:05", "04:05:09", "closed". */
export function countdownText(seconds: number | null | undefined, closedWord = "closed"): string {
  if (seconds === null || seconds === undefined || !Number.isFinite(seconds)) return "–";
  if (seconds <= 0) return closedWord;
  const whole = Math.floor(seconds);
  const days = Math.floor(whole / 86_400);
  const hours = Math.floor((whole % 86_400) / 3_600);
  const minutes = Math.floor((whole % 3_600) / 60);
  const secs = whole % 60;
  const pad = (value: number) => String(value).padStart(2, "0");
  if (days > 0) return `${days}d ${pad(hours)}:${pad(minutes)}`;
  return `${pad(hours)}:${pad(minutes)}:${pad(secs)}`;
}

/** Seconds from `nowMs` to an instant (negative once it has passed); null without one. */
export function secondsUntil(iso: string | null | undefined, nowMs: number): number | null {
  if (!iso) return null;
  const at = Date.parse(iso);
  return Number.isFinite(at) ? Math.round((at - nowMs) / 1000) : null;
}

/** The urgency of a deadline: past, within the critical lead, within the warning lead, later. */
export function deadlineTone(seconds: number | null, leadsMinutes: readonly number[] = [120, 30]): Tone {
  if (seconds === null) return "neutral";
  if (seconds <= 0) return "stale";
  const minutes = seconds / 60;
  if (minutes <= Math.min(...leadsMinutes)) return "breach";
  if (minutes <= Math.max(...leadsMinutes)) return "watch";
  return "neutral";
}

function zoneOffsetMs(ms: number, zone: string): number {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: zone,
    hourCycle: "h23",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).formatToParts(new Date(ms));
  const get = (type: string) => Number(parts.find((part) => part.type === type)?.value ?? 0);
  return Date.UTC(get("year"), get("month") - 1, get("day"), get("hour"), get("minute"), get("second")) - ms;
}

/** A wall-clock time in the auction's zone ("2026-12-02T17:00", Europe/Amsterdam) as UTC ISO. */
export function zonedToUtc(local: string, zone: string): string | null {
  const match = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/.exec(local);
  if (!match) return null;
  const [y, m, d, hh, mm] = match.slice(1).map(Number);
  const wall = Date.UTC(y, m - 1, d, hh, mm);
  let guess = wall;
  for (let i = 0; i < 3; i += 1) guess = wall - zoneOffsetMs(guess, zone);
  return new Date(guess).toISOString().replace(".000Z", "Z");
}

/** A UTC instant as the auction's wall-clock time ("2026-12-02T17:00"), for the form. */
export function utcToZoned(iso: string | null | undefined, zone: string): string {
  if (!iso) return "";
  const ms = Date.parse(iso);
  if (!Number.isFinite(ms)) return "";
  // The form's value string ("YYYY-MM-DDTHH:mm", the picker's datetime value), not display text.
  const wall = new Date(ms + zoneOffsetMs(ms, zone));
  const pad = (value: number) => String(value).padStart(2, "0");
  return `${wall.getUTCFullYear()}-${pad(wall.getUTCMonth() + 1)}-${pad(wall.getUTCDate())}T${pad(wall.getUTCHours())}:${pad(wall.getUTCMinutes())}`;
}

/** One line per missing input, prices grouped by hub ("TTF: 4 days"), in the order given. */
export function missingSummary(missing: readonly string[]): { kind: string; what: string; count: number }[] {
  const out: { kind: string; what: string; count: number }[] = [];
  for (const key of missing) {
    const [kind, ...rest] = key.split(":");
    const what = kind === "price" ? rest[0] : rest.join(":") || kind;
    const held = out.find((item) => item.kind === kind && item.what === what);
    if (held) held.count += 1;
    else out.push({ kind, what, count: 1 });
  }
  return out;
}

export interface RegasDraft {
  book_id: string;
  title: string;
  terminal_id: string;
  terminal_name: string;
  hub: string;
  notice_key: string;
  first_day: string;
  last_day: string;
  quantity: string;
  unit: string;
  factor: string;
  format: string;
  time_zone: string;
  opens_local: string;
  closes_local: string;
  quotation: "per_mwh" | "per_slot";
  level: string;
  owner_id: string;
  owner_name: string;
  kind: "fixed" | "formula";
  price: string;
  price_unit: string;
  index_hub: string;
  pricing: "send_out_days" | "month";
  pricing_month: string;
  slope: string;
  constant: string;
  tolerance_pct: string;
  expires_local: string;
  costs: Record<string, { value: string; link: string }>;
  price_by_hand: string;
  rate_pct: string;
}

/** A new case's form, filled from what exists: the first book, the desk's defaults. */
export function emptyDraft(choices: RegasChoicesDTO | undefined): RegasDraft {
  const definition = choices?.definition;
  return {
    book_id: choices?.books[0]?.book_id ?? "",
    title: "",
    terminal_id: "",
    terminal_name: "",
    hub: "TTF",
    notice_key: "",
    first_day: "",
    last_day: "",
    quantity: "",
    unit: "GWh",
    factor: "",
    format: definition?.default_format ?? "sealed_bid",
    time_zone: definition?.default_time_zone ?? "Europe/Amsterdam",
    opens_local: "",
    closes_local: "",
    quotation: definition?.quotation ?? "per_mwh",
    level: "",
    owner_id: "",
    owner_name: "",
    kind: "fixed",
    price: "",
    price_unit: "EUR/MWh",
    index_hub: "",
    pricing: (definition?.default_pricing as RegasDraft["pricing"]) ?? "send_out_days",
    pricing_month: "",
    slope: "1",
    constant: "0",
    tolerance_pct: definition?.default_tolerance_pct ?? "5",
    expires_local: "",
    costs: {},
    price_by_hand: "",
    rate_pct: "",
  };
}

/**
 * A case form filled from a capacity notice the operator published (window, slot days), and,
 * when the notice names a terminal the desk knows (a slot offer fetched from Zeebrugge, Grain
 * or DET), that terminal and its hub; the size in its own unit (m³ LNG for Fluxys).
 */
export function draftFromNotice(draft: RegasDraft, notice: RegasChoicesDTO["notices"][number], terminals: RegasChoicesDTO["terminals"] = []): RegasDraft {
  const terminal = notice.facility_id ? terminals.find((item) => item.terminal_id === notice.facility_id) : undefined;
  const unit = notice.quantity != null && notice.quantity_unit === "m3_lng" ? "m3_lng" : draft.unit;
  return {
    ...draft,
    ...(terminal ? { terminal_id: terminal.terminal_id, terminal_name: terminal.name, hub: terminal.hub } : {}),
    unit,
    notice_key: notice.notice_key,
    title: draft.title || notice.title,
    first_day: notice.offers_from ?? draft.first_day,
    last_day: notice.offers_to ?? draft.last_day,
    opens_local: utcToZoned(notice.opens_at_utc, draft.time_zone),
    closes_local: notice.closes_at_utc ? utcToZoned(notice.closes_at_utc, draft.time_zone) : draft.closes_local,
    quantity: notice.quantity != null ? String(notice.quantity) : draft.quantity,
  };
}

/** What the form still needs before it can be sent (keys of the missing fields). */
export function draftGaps(draft: RegasDraft): string[] {
  const gaps: string[] = [];
  if (!draft.book_id) gaps.push("book");
  if (!draft.terminal_name || !draft.hub) gaps.push("terminal");
  if (!draft.first_day || !draft.last_day) gaps.push("slot_days");
  if (!draft.quantity) gaps.push("quantity");
  if (!draft.closes_local) gaps.push("closes");
  if (!draft.owner_name) gaps.push("owner");
  if (draft.kind === "fixed" && !draft.price) gaps.push("price");
  if (draft.kind === "formula" && !draft.slope) gaps.push("slope");
  return gaps;
}

/** The request body for a new case from the form (times converted from the auction's zone). */
export function draftToBody(draft: RegasDraft): RegasCaseBody {
  const zone = draft.time_zone;
  const costs: Record<string, { value: string; link?: string }> = {};
  for (const [key, entry] of Object.entries(draft.costs)) {
    if (entry.value.trim()) costs[key] = { value: entry.value.trim(), ...(entry.link.trim() ? { link: entry.link.trim() } : {}) };
  }
  return {
    book_id: draft.book_id,
    title: draft.title || undefined,
    terminal: { terminal_id: draft.terminal_id || undefined, name: draft.terminal_name, hub: draft.hub },
    slot: { first_day: draft.first_day, last_day: draft.last_day, quantity: draft.quantity, unit: draft.unit, factor: draft.unit === "m3_lng" && draft.factor ? draft.factor : null },
    auction: {
      format: draft.format,
      opens_at: draft.opens_local ? zonedToUtc(draft.opens_local, zone) : null,
      closes_at: zonedToUtc(draft.closes_local, zone) ?? "",
      time_zone: zone,
      quotation: draft.quotation,
      level: draft.level || null,
      notice_key: draft.notice_key || null,
    },
    owner: { counterparty_id: draft.owner_id || null, name: draft.owner_name },
    offer:
      draft.kind === "fixed"
        ? { kind: "fixed", price: draft.price, price_unit: draft.price_unit, tolerance_pct: draft.tolerance_pct, expires_at: draft.expires_local ? zonedToUtc(draft.expires_local, zone) : null }
        : {
            kind: "formula",
            index_hub: draft.index_hub || draft.hub,
            pricing: draft.pricing,
            pricing_month: draft.pricing === "month" ? draft.pricing_month : undefined,
            slope: draft.slope,
            constant: draft.constant || "0",
            tolerance_pct: draft.tolerance_pct,
            expires_at: draft.expires_local ? zonedToUtc(draft.expires_local, zone) : null,
          },
    costs,
    prices: draft.price_by_hand.trim() ? { [draft.hub]: { all: draft.price_by_hand.trim() } } : undefined,
    rate_pct: draft.rate_pct.trim() || undefined,
  };
}

/** The body that changes a stored case, from its inputs, with the version it was read at. */
export function bodyFromInputs(inputs: RegasCaseInputsDTO, version: number): RegasCaseBody {
  const costs: Record<string, { value: string; link?: string }> = {};
  for (const [key, entry] of Object.entries(inputs.costs ?? {})) {
    costs[key] = { value: entry.value, ...(entry.link ? { link: entry.link } : {}) };
  }
  const prices: Record<string, { all?: string; days?: Record<string, string> }> = {};
  for (const [hub, entry] of Object.entries(inputs.prices ?? {})) {
    prices[hub] = {
      ...(entry.all ? { all: entry.all.value } : {}),
      ...(entry.days ? { days: Object.fromEntries(Object.entries(entry.days).map(([day, item]) => [day, item.value])) } : {}),
    };
  }
  const { offer } = inputs;
  return {
    version,
    title: inputs.title,
    terminal: inputs.terminal.by_hand
      ? { name: inputs.terminal.name, hub: inputs.terminal.hub }
      : { terminal_id: inputs.terminal.terminal_id, name: inputs.terminal.name, hub: inputs.terminal.hub },
    slot: { first_day: inputs.slot.first_day, last_day: inputs.slot.last_day, quantity: inputs.slot.quantity, unit: inputs.slot.unit, factor: inputs.slot.factor_source === "desk default" ? null : inputs.slot.factor },
    auction: {
      format: inputs.auction.format,
      opens_at: inputs.auction.opens_at,
      closes_at: inputs.auction.closes_at,
      time_zone: inputs.auction.time_zone,
      quotation: inputs.auction.quotation,
      level: inputs.auction.level?.value ?? null,
      notice_key: inputs.auction.notice_key,
      link: inputs.auction.link,
    },
    owner: { counterparty_id: inputs.owner.counterparty_id, name: inputs.owner.name },
    offer: { ...offer, expires_at: offer.expires_at },
    profile: inputs.profile,
    delay_days: inputs.delay_days,
    costs,
    prices,
    ...(inputs.fx ? { fx: inputs.fx.value } : {}),
    ...(inputs.rate_pct ? { rate_pct: inputs.rate_pct.value } : {}),
  };
}

/** A stored case's body with the trader's new auction level ("" clears it). */
export function withLevel(body: RegasCaseBody, level: string): RegasCaseBody {
  return { ...body, auction: { ...body.auction, level: level.trim() || null } };
}

/** A stored case's body with one cost line entered by hand (with the operator's link). */
export function withCost(body: RegasCaseBody, key: string, value: string, link = ""): RegasCaseBody {
  const costs = { ...(body.costs ?? {}) };
  if (value.trim()) costs[key] = { value: value.trim(), ...(link.trim() ? { link: link.trim() } : {}) };
  else delete costs[key];
  return { ...body, costs };
}

/** A stored case's body with a hub price entered by hand for the slot's days ("" clears it). */
export function withHandPrice(body: RegasCaseBody, hub: string, value: string): RegasCaseBody {
  const prices = { ...(body.prices ?? {}) };
  if (value.trim()) prices[hub] = { ...(prices[hub] ?? {}), all: value.trim() };
  else if (prices[hub]) {
    const { all: _all, ...rest } = prices[hub];
    prices[hub] = rest;
  }
  return { ...body, prices };
}

/** The benchmark rate entered by hand (for a currency with no rate held). */
export function withRate(body: RegasCaseBody, value: string): RegasCaseBody {
  const next = { ...body };
  if (value.trim()) next.rate_pct = value.trim();
  else delete next.rate_pct;
  return next;
}

/** The quoted unit of the answer: "EUR/MWh" per MWh, "EUR" per slot. */
export function quotedUnit(answer: Pick<RegasAnswerDTO, "currency" | "quotation">): string {
  return answer.quotation === "per_mwh" ? `${answer.currency}/MWh` : answer.currency;
}

/** An input key of the answer ("cost:berthing", "price:TTF:2027-01-10", "auction_level") as the
 *  desk names it: the cost line's label, the hub's price, the input's word (never the key). */
export function inputLabel(
  key: string,
  costLabels: Readonly<Record<string, string>>,
  t: (key: string, options?: Record<string, unknown>) => string,
): string {
  const [kind, first, second] = key.split(":");
  if (kind === "cost") return costLabels[first] ?? first;
  if (kind === "price") return t("regas.input.price", { hub: first, day: second ?? "" });
  return t(`regas.missing.${kind}`, { defaultValue: kind });
}
