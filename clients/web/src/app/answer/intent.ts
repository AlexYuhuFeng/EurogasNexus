/**
 * Tier 2 of the answer bar: the deterministic look-ups a query asks for. Parsing only; the
 * reads are in `lookups.ts`. A query is a look-up only when it matches one of these shapes
 * exactly, so a half-typed word never fires a read:
 *
 * - price: `TTF`, `NBP DA`, `TTF Dec-26`, `THE front month`, `price of PEG`, `TTF 价格`;
 * - storage: `storage`, `storage DE`, `Germany storage`, `储气 德国`;
 * - LNG send-out: `LNG`, `LNG send-out FR`; Norwegian supply: `Norway`, `Norwegian landings`;
 * - outages: `outages`, `outages NBP`, `UK outages`, `outages Haldor`, `停运`;
 * - the book (only for a caller with `portfolio.read`): `position`, `position TTF Dec-26`,
 *   `credit Rhinmark`, `Rhinmark headroom`, `contract Haldor`.
 */

import { monthLabel } from "./gasDay.ts";
import { normalizeTyped } from "./numbers.ts";
import { canonicalHub } from "../hubAliases.ts";

/** The hubs the bar recognises by name, with the balancing zone their outages carry. */
export const HUBS = ["TTF", "NBP", "THE", "PEG", "ZTP", "PSV", "CEGH", "PVB", "ETF"] as const;
export type Hub = (typeof HUBS)[number];

/** Country names and codes (EN and ZH) to the codes storage and LNG reads use. */
const COUNTRIES: Record<string, string> = {
  eu: "EU", europe: "EU", 欧盟: "EU", 欧洲: "EU",
  de: "DE", germany: "DE", german: "DE", 德国: "DE",
  nl: "NL", netherlands: "NL", dutch: "NL", holland: "NL", 荷兰: "NL",
  fr: "FR", france: "FR", french: "FR", 法国: "FR",
  it: "IT", italy: "IT", italian: "IT", 意大利: "IT",
  at: "AT", austria: "AT", 奥地利: "AT",
  be: "BE", belgium: "BE", 比利时: "BE",
  es: "ES", spain: "ES", 西班牙: "ES",
  pl: "PL", poland: "PL", 波兰: "PL",
  cz: "CZ", czechia: "CZ", 捷克: "CZ",
  sk: "SK", slovakia: "SK", 斯洛伐克: "SK",
  hu: "HU", hungary: "HU", 匈牙利: "HU",
  dk: "DK", denmark: "DK", 丹麦: "DK",
  uk: "GB", gb: "GB", britain: "GB", "great britain": "GB", "united kingdom": "GB", 英国: "GB",
};
/** A country's main hub, for outages that carry a balancing zone. */
const COUNTRY_HUB: Record<string, Hub> = { GB: "NBP", NL: "TTF", DE: "THE", FR: "PEG", BE: "ZTP", IT: "PSV", AT: "CEGH", ES: "PVB", DK: "ETF" };

export type Tenor =
  | { kind: "front" }
  | { kind: "prompt"; code: "WD" | "DA" | "WE" | "BOM" }
  | { kind: "month"; year: number; month: number; label: string };

export type LookupIntent =
  | { kind: "price"; hub: Hub; tenor: Tenor }
  | { kind: "storage"; country: string | null }
  | { kind: "lng"; country: string | null }
  | { kind: "norway" }
  | { kind: "outages"; zone: Hub | null; country: string | null; facility: string | null }
  | { kind: "position"; hub: Hub | null; month: { year: number; month: number; label: string } | null }
  | { kind: "credit"; counterparty: string }
  | { kind: "contract"; name: string }
  /** A price conversion for a future delivery period: the server converts at the forward. */
  | { kind: "convert"; value: number; from: string; to: string; period: string }
  /** Two hubs' spread, live while the bar is open ("NBP TTF spread"); `text` opens the study. */
  | { kind: "spread"; a: string; b: string; tenor: "front" | "DA"; text: string }
  /** The caller's book at a glance ("what's my portfolio"): positions, open P&L, cargoes, credit. */
  | { kind: "portfolio" };

/** Words that make an outage query a question for Ask rather than a facility name. */
const QUESTION_WORDS = /^(?:the|all|any|summari[sz]e|summary|what|why|how|which|show|list|explain|recent|current|today'?s|major|big)\b/;

const PORTFOLIO_EN = /^(?:(?:what'?s|whats|what\s+is|how'?s|hows|how\s+is|show(?:\s+me)?|give\s+me|summari[sz]e)\s+)?(?:(?:my|our|the)\s+)?(?:portfolio|book|holdings)(?:\s+(?:like|summary|overview|at\s+a\s+glance|now|today|doing|looking(?:\s+like)?|look(?:\s+like)?))*$/;
const PORTFOLIO_ZH = /^(?:我的|我们的)?(?:投资组合|组合|持仓|交易簿)(?:概况|情况|总览|摘要|怎么样|如何)?$/;

const MONTH_WORDS = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"];

function parseTenor(raw: string, now: Date): Tenor | null {
  const text = raw.trim().toLowerCase();
  if (!text || /^(?:front(?:[\s-]?month)?|fm|ma|m\s*\+\s*1|month[\s-]ahead|近月|月度)$/.test(text)) return { kind: "front" };
  const prompt: Record<string, "WD" | "DA" | "WE" | "BOM"> = {
    wd: "WD", "within-day": "WD", "within day": "WD", da: "DA", "day-ahead": "DA", "day ahead": "DA",
    we: "WE", weekend: "WE", bom: "BOM", "balance of month": "BOM", 日前: "DA", 日内: "WD", 周末: "WE",
  };
  if (prompt[text]) return { kind: "prompt", code: prompt[text] };
  const named = /^([a-z]{3,9})[\s-]?'?(\d{2}|\d{4})$/.exec(text);
  const iso = /^(\d{4})-(\d{2})$/.exec(text);
  let year = -1;
  let month = -1;
  if (named) {
    month = MONTH_WORDS.indexOf(named[1].slice(0, 3));
    if (named[1].length > 3 && !"january february march april may june july august september october november december".split(" ").includes(named[1])) return null;
    year = named[2].length === 2 ? 2000 + Number(named[2]) : Number(named[2]);
  } else if (iso) {
    year = Number(iso[1]);
    month = Number(iso[2]) - 1;
  }
  if (month < 0 || month > 11 || year < 2000) return null;
  void now;
  return { kind: "month", year, month, label: monthLabel(year, month) };
}

function hubIn(word: string, typed: string): Hub | null {
  const upper = word.toUpperCase();
  // "the" is a word long before it is a hub: only the capitalised code reads as THE.
  if (upper === "THE" && typed !== "THE") return null;
  // A hub's other name is that hub: "GTF" reads as ETF, "VTP" as CEGH.
  const code = canonicalHub(upper);
  return (HUBS as readonly string[]).includes(code) ? (code as Hub) : null;
}

function country(text: string): string | null {
  const clean = text.trim().toLowerCase();
  return clean ? COUNTRIES[clean] ?? null : null;
}

/** The look-up `raw` asks for, or null. `bookAllowed` is the caller's `portfolio.read`. */
export function lookupIntent(raw: string, options: { bookAllowed: boolean; now?: Date }): LookupIntent | null {
  const now = options.now ?? new Date();
  const typed = normalizeTyped(raw).trim().replace(/[?？]$/, "").trim();
  if (!typed) return null;
  const text = typed.toLowerCase().replace(/\s+/g, " ");

  // Prices: "TTF", "TTF Dec-26", "price of NBP DA", "TTF 价格".
  const priceTyped = typed
    .replace(/^(?:price|prices|quote)\s+(?:of\s+|for\s+)?/i, "")
    .replace(/\s*(?:price|prices|quote|价格|报价)$/i, "")
    .trim();
  const [first = "", ...tenorWords] = priceTyped.split(/\s+/);
  const priceHub = hubIn(first, first);
  if (priceHub) {
    const tenor = parseTenor(tenorWords.join(" "), now);
    if (tenor) return { kind: "price", hub: priceHub, tenor };
  }

  // Storage: "storage", "storage DE", "German storage", "储气 德国".
  const storage =
    /^(?:gas\s+)?(?:storage|stocks|inventory|fill)(?:\s+(?:fill|level|levels))?(?:\s+(?:in|for)?\s*(.+))?$/.exec(text) ??
    /^(?:储气|库存|储气库)(?:\s*(.+))?$/.exec(text);
  const storageAfter = /^(.+?)\s+(?:gas\s+)?(?:storage|stocks|储气|库存)(?:\s+(?:fill|level))?$/.exec(text);
  if (storage) {
    const code = storage[1] ? country(storage[1]) : null;
    if (!storage[1] || code) return { kind: "storage", country: code };
  }
  if (storageAfter && country(storageAfter[1])) return { kind: "storage", country: country(storageAfter[1]) };

  // LNG send-out.
  const lng =
    /^lng(?:\s+(?:send[\s-]?out|sendout|regas|imports?))?(?:\s+(?:in|for)?\s*(.+))?$/.exec(text) ??
    /^(?:液化天然气|lng)\s*(?:外输|气化)?(?:\s*(.+))?$/.exec(text);
  if (lng) {
    const code = lng[1] ? country(lng[1]) : null;
    if (!lng[1] || code) return { kind: "lng", country: code };
  }

  // Norwegian supply.
  if (/^(?:norway|norwegian(?:\s+(?:supply|flows?|landings?|exports?))?|nor(?:wegian)?\s+landings?|挪威(?:供应|管道气|来气)?)$/.test(text)) {
    return { kind: "norway" };
  }

  // Outages: "outages", "outages NBP", "UK outages", "outages Haldor".
  const outage =
    /^(?:outages?|maintenance|remit|umm|停运|检修)(?:\s+(?:at|in|for|on)?\s*(.+))?$/.exec(text) ??
    /^(.+?)\s+(?:outages?|maintenance|停运|检修)$/.exec(text);
  if (outage) {
    const subject = outage[1]?.trim() ?? "";
    if (!subject) return { kind: "outages", zone: null, country: null, facility: null };
    const typedSubject = typed.slice(typed.toLowerCase().indexOf(subject)).slice(0, subject.length);
    const hub = hubIn(subject, typedSubject);
    if (hub) return { kind: "outages", zone: hub, country: null, facility: null };
    const code = country(subject);
    if (code) return { kind: "outages", zone: COUNTRY_HUB[code] ?? null, country: code, facility: null };
    // A facility name, not a question about outages ("summarise the outages").
    if (subject.length >= 3 && !QUESTION_WORDS.test(subject)) {
      return { kind: "outages", zone: null, country: null, facility: subject };
    }
  }

  if (!options.bookAllowed) return null;

  // The book at a glance: "portfolio", "what's my portfolio like", "how's my book", "我的投资组合".
  if (PORTFOLIO_EN.test(text) || PORTFOLIO_ZH.test(text)) return { kind: "portfolio" };

  // Book: position, credit, contract.
  const position = /^(?:(?:my|our|net|the)\s+)*(?:position|positions|book|头寸|净头寸)(?:\s+(.+))?$/.exec(text);
  if (position) {
    const words = (position[1] ?? "").split(" ").filter(Boolean);
    const hub = words.length ? hubIn(words[0], typed.split(/\s+/).find((w) => w.toUpperCase() === words[0].toUpperCase()) ?? words[0]) : null;
    if (words.length === 0) return { kind: "position", hub: null, month: null };
    if (hub) {
      const tenor = parseTenor(words.slice(1).join(" "), now);
      if (tenor?.kind === "month") return { kind: "position", hub, month: tenor };
      if (tenor?.kind === "front" && words.length === 1) return { kind: "position", hub, month: null };
    }
  }
  const credit =
    /^(?:credit|headroom|credit\s+line|exposure|信用|授信|敞口)\s+(?:of\s+|for\s+|with\s+)?(.{3,})$/.exec(text) ??
    /^(.{3,}?)\s+(?:credit|headroom|exposure|信用|授信)$/.exec(text);
  if (credit) return { kind: "credit", counterparty: credit[1].trim() };
  const contract = /^(?:contract|合同|合约)\s+(.{3,})$/.exec(text);
  if (contract) return { kind: "contract", name: contract[1].trim() };
  return null;
}

/** A stable key for an intent, so an identical look-up is not repeated while typing. */
export function intentKey(intent: LookupIntent): string {
  return JSON.stringify(intent);
}
