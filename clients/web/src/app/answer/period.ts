/**
 * A delivery period typed after a price conversion: `78 p/th in eur/mwh jan27`,
 * `12 $/mmbtu to €/mwh for Q1-27`, `40 eur/mwh in p/th cal-27`, `… m+1`, `… 27年1月`.
 *
 * Parsing only. The period is sent to the server as a desk product code (`Jan-27`, `Q1-27`,
 * `Sum-27`, `Win-27`, `Cal-27`, `GY-27`, `M+1`…) and resolved there against the gas-day calendar
 * (`domain/market/products.py`); the client neither computes a delivery window nor a forward.
 * A prompt product (DA, WD, WE, BOM, spot) keeps the instant spot conversion.
 */

import { normalizeTyped } from "./numbers.ts";

export interface TypedPeriod {
  /** The product code the server resolves. */
  code: string;
  /** How the answer names it. */
  label: string;
  /** Prompt products settle at spot. */
  prompt: boolean;
}

const MONTHS = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"];
const MONTH_NAMES = "january february march april may june july august september october november december".split(" ");
const ZH_DIGITS: Record<string, number> = { 一: 1, 二: 2, 三: 3, 四: 4, 五: 5, 六: 6, 七: 7, 八: 8, 九: 9, 十: 10, 十一: 11, 十二: 12 };

function yy(text: string): string | null {
  if (/^\d{2}$/.test(text)) return text;
  if (/^20\d{2}$/.test(text)) return text.slice(2);
  return null;
}

function title(word: string): string {
  return word.charAt(0).toUpperCase() + word.slice(1);
}

function zhNumber(text: string): number | null {
  if (/^\d{1,2}$/.test(text)) return Number(text);
  return ZH_DIGITS[text] ?? null;
}

/** The period one clause names, or null. `clause` is already lower-cased and trimmed. */
export function parsePeriod(clause: string): TypedPeriod | null {
  const text = clause.trim().toLowerCase().replace(/\s+/g, " ");
  if (!text) return null;
  const prompt: Record<string, string> = {
    da: "DA", "day ahead": "DA", "day-ahead": "DA", dayahead: "DA", 日前: "DA",
    wd: "WD", "within day": "WD", "within-day": "WD", 日内: "WD",
    we: "WE", weekend: "WE", 周末: "WE",
    bom: "BOM", "balance of month": "BOM",
    spot: "DA", 现货: "DA", 即期: "DA",
  };
  if (prompt[text]) return { code: prompt[text], label: prompt[text], prompt: true };

  const rolling = /^(m|q|s|gy|cal)\s*\+\s*(\d{1,2})$/.exec(text);
  if (rolling) {
    const family = rolling[1] === "cal" ? "Cal" : rolling[1].toUpperCase();
    const code = `${family}+${Number(rolling[2])}`;
    return { code, label: code, prompt: false };
  }
  const relativeWords: Record<string, string> = {
    "front month": "M+1", "month ahead": "M+1", "month-ahead": "M+1", "next month": "M+1", ma: "M+1",
    "next quarter": "Q+1", "quarter ahead": "Q+1", "next season": "S+1", "season ahead": "S+1",
    "next year": "Cal+1", "year ahead": "Cal+1",
    次月: "M+1", 下月: "M+1", 近月: "M+1", 下季度: "Q+1", 下季: "Q+1", 下一季: "S+1", 明年: "Cal+1",
  };
  if (relativeWords[text]) return { code: relativeWords[text], label: relativeWords[text], prompt: false };

  // Months: jan27, jan-27, jan 27, jan 2027, january 2027, 2027-01, 27年1月, 2027年一月.
  const named = /^([a-z]{3,9})[\s-]?'?(\d{2}|20\d{2})$/.exec(text);
  if (named) {
    const word = named[1];
    const index = MONTHS.indexOf(word.slice(0, 3));
    const year = yy(named[2]);
    if (index >= 0 && year && (word.length === 3 || MONTH_NAMES.includes(word) || word === "sept")) {
      const code = `${title(MONTHS[index])}-${year}`;
      return { code, label: code, prompt: false };
    }
  }
  const iso = /^(20\d{2})-(\d{2})$/.exec(text);
  if (iso && Number(iso[2]) >= 1 && Number(iso[2]) <= 12) {
    const code = `${title(MONTHS[Number(iso[2]) - 1])}-${iso[1].slice(2)}`;
    return { code, label: code, prompt: false };
  }
  const zhMonth = /^(\d{2}|20\d{2})年(\d{1,2}|十[一二]?|[一二三四五六七八九])月(?:份)?$/.exec(text);
  if (zhMonth) {
    const month = zhNumber(zhMonth[2]);
    const year = yy(zhMonth[1]);
    if (month && month >= 1 && month <= 12 && year) {
      const code = `${title(MONTHS[month - 1])}-${year}`;
      return { code, label: code, prompt: false };
    }
  }

  // Quarters: q1-27, q1 27, q127, 27年一季度, 2027年第1季度.
  const quarter = /^q([1-4])[\s-]?(\d{2}|20\d{2})$/.exec(text);
  if (quarter && yy(quarter[2])) {
    const code = `Q${quarter[1]}-${yy(quarter[2])}`;
    return { code, label: code, prompt: false };
  }
  const zhQuarter = /^(\d{2}|20\d{2})年第?([1-4一二三四])季度?$/.exec(text);
  if (zhQuarter && yy(zhQuarter[1])) {
    const q = zhNumber(zhQuarter[2]);
    if (q && q <= 4) {
      const code = `Q${q}-${yy(zhQuarter[1])}`;
      return { code, label: code, prompt: false };
    }
  }

  // Seasons: sum-27, summer 27, win-27, winter 2027, 27年夏季, 27年冬季.
  const season = /^(sum|summer|win|winter)[\s-]?(\d{2}|20\d{2})$/.exec(text);
  if (season && yy(season[2])) {
    const code = `${season[1].startsWith("s") ? "Sum" : "Win"}-${yy(season[2])}`;
    return { code, label: code, prompt: false };
  }
  const zhSeason = /^(\d{2}|20\d{2})年?(夏季|冬季|夏|冬)$/.exec(text);
  if (zhSeason && yy(zhSeason[1])) {
    const code = `${zhSeason[2].startsWith("夏") ? "Sum" : "Win"}-${yy(zhSeason[1])}`;
    return { code, label: code, prompt: false };
  }

  // Years: cal-27, cal 27, cal27, gy-27, 27年日历年.
  const year = /^(cal|gy)[\s-]?(\d{2}|20\d{2})$/.exec(text);
  if (year && yy(year[2])) {
    const code = `${year[1] === "cal" ? "Cal" : "GY"}-${yy(year[2])}`;
    return { code, label: code, prompt: false };
  }
  const zhYear = /^(\d{2}|20\d{2})年?(?:日历年|全年)$/.exec(text);
  if (zhYear && yy(zhYear[1])) {
    const code = `Cal-${yy(zhYear[1])}`;
    return { code, label: code, prompt: false };
  }
  return null;
}

/**
 * Split a trailing delivery period off a typed line: `"78 p/th in eur/mwh jan27"` →
 * `{ rest: "78 p/th in eur/mwh", period: Jan-27 }`. Up to three trailing words are tried, with
 * an optional `for`, `delivery`, `del` or `交割` before them. Null when no period ends the line.
 */
export function splitTrailingPeriod(raw: string): { rest: string; period: TypedPeriod } | null {
  const text = normalizeTyped(raw).trim().replace(/[?？]$/, "").trim();
  // A Chinese period may be written without a space before it: "…换算成欧元/兆瓦时27年1月".
  const zh = /^(.*?)\s*((?:\d{2}|20\d{2})年[^\s]*|次月|下月|近月|下季度|下季|日前|日内|周末|现货|即期)$/.exec(text);
  if (zh && zh[1].trim()) {
    const period = parsePeriod(zh[2]);
    if (period) return { rest: stripConnector(zh[1]), period };
  }
  const words = text.split(/\s+/);
  for (let take = Math.min(3, words.length - 1); take >= 1; take -= 1) {
    const clause = words.slice(words.length - take).join(" ");
    const period = parsePeriod(clause);
    if (period) return { rest: stripConnector(words.slice(0, words.length - take).join(" ")), period };
  }
  return null;
}

function stripConnector(text: string): string {
  return text.replace(/\s*(?:,|\bfor\b|\bdelivery\b|\bdel\b|交割|的)\s*$/i, "").trim();
}
