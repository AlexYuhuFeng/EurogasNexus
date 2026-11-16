/**
 * The answer bar's calculator: a small recursive-descent parser over + − × ÷ ^, brackets and
 * percent. No `eval`, no `Function`: the grammar below is the whole of what it reads.
 *
 *   sum     := product (("+" | "-") product)*
 *   product := power (("*" | "/") power)*
 *   power   := unary ("^" power)?
 *   unary   := ("-" | "+") unary | percent
 *   percent := primary "%"?
 *   primary := number | "(" sum ")"
 *
 * Percent follows a desk calculator: `200 + 15%` is 230 and `200 - 15%` is 170 (a percent
 * added to or taken off the left side), `15% of 200` and `200 * 15%` are 30, and `15%` alone
 * is 0.15.
 *
 * Strictness: the input is read as a calculation only when it is nothing but numbers,
 * operators and brackets, and it has at least one operator or percent. `2026`, `-5`, a date
 * such as `2026-11-16`, a gas year `26-27` or `2026/27`, `TTF`, `Dec-26` and anything with a
 * letter in it give no answer. `=` in front forces the calculator (`=2026`, `=-5`).
 */

import { normalizeTyped, readNumber } from "./numbers.ts";

export interface Calculation {
  value: number;
  /** The expression as read, spaced: `(42.5 − 39.8) × 30`. */
  expression: string;
}

type Token =
  | { kind: "num"; value: number; text: string }
  | { kind: "op"; op: "+" | "-" | "*" | "/" | "^" | "%" | "(" | ")" };

function tokenize(text: string): Token[] | null {
  const tokens: Token[] = [];
  let index = 0;
  while (index < text.length) {
    const char = text[index];
    if (char === " ") {
      index += 1;
      continue;
    }
    if ("+-*/^%()".includes(char)) {
      tokens.push({ kind: "op", op: char as "+" });
      index += 1;
      continue;
    }
    const number = readNumber(text.slice(index));
    if (!number) return null;
    tokens.push({ kind: "num", value: number.value, text: text.slice(index, index + number.length) });
    index += number.length;
  }
  return tokens;
}

interface Value {
  value: number;
  /** A bare percent (`15%`), which `+` and `-` apply to the left side. */
  percent: boolean;
}

class Parser {
  private position = 0;
  private readonly tokens: Token[];
  constructor(tokens: Token[]) {
    this.tokens = tokens;
  }

  parse(): number | null {
    const result = this.sum();
    if (!result || this.position !== this.tokens.length) return null;
    return Number.isFinite(result.value) ? result.value : null;
  }

  private peekOp(): string | null {
    const token = this.tokens[this.position];
    return token?.kind === "op" ? token.op : null;
  }

  private sum(): Value | null {
    let left = this.product();
    while (left && (this.peekOp() === "+" || this.peekOp() === "-")) {
      const op = this.peekOp();
      this.position += 1;
      const right = this.product();
      if (!right) return null;
      const amount = right.percent ? left.value * right.value : right.value;
      left = { value: op === "+" ? left.value + amount : left.value - amount, percent: false };
    }
    return left;
  }

  private product(): Value | null {
    let left = this.power();
    while (left && (this.peekOp() === "*" || this.peekOp() === "/")) {
      const op = this.peekOp();
      this.position += 1;
      const right = this.power();
      if (!right) return null;
      if (op === "/" && right.value === 0) return null;
      left = { value: op === "*" ? left.value * right.value : left.value / right.value, percent: false };
    }
    return left;
  }

  private power(): Value | null {
    const base = this.unary();
    if (!base || this.peekOp() !== "^") return base;
    this.position += 1;
    const exponent = this.power();
    if (!exponent) return null;
    return { value: base.value ** exponent.value, percent: false };
  }

  private unary(): Value | null {
    const op = this.peekOp();
    if (op === "-" || op === "+") {
      this.position += 1;
      const inner = this.unary();
      return inner ? { value: op === "-" ? -inner.value : inner.value, percent: inner.percent } : null;
    }
    return this.percent();
  }

  private percent(): Value | null {
    const inner = this.primary();
    if (inner && this.peekOp() === "%") {
      this.position += 1;
      return { value: inner.value / 100, percent: true };
    }
    return inner;
  }

  private primary(): Value | null {
    const token = this.tokens[this.position];
    if (!token) return null;
    if (token.kind === "num") {
      this.position += 1;
      return { value: token.value, percent: false };
    }
    if (token.op === "(") {
      this.position += 1;
      const inner = this.sum();
      if (!inner || this.peekOp() !== ")") return null;
      this.position += 1;
      return { value: inner.value, percent: false };
    }
    return null;
  }
}

/** Dates and gas years typed into a search bar are not subtractions. */
function dateLike(text: string): boolean {
  const compact = text.replace(/\s+/g, "");
  if (/^\d{4}-\d{1,2}(-\d{1,2})?$/.test(compact)) return true;
  if (/^\d{1,2}\/\d{1,2}(\/\d{2,4})?$/.test(compact)) return true;
  const gasYear = /^(\d{2}|\d{4})[-/](\d{2})$/.exec(compact);
  if (gasYear) {
    const first = Number(gasYear[1].slice(-2));
    return Number(gasYear[2]) === (first + 1) % 100;
  }
  return false;
}

const SPACED: Record<string, string> = { "+": " + ", "-": " − ", "*": " × ", "/": " ÷ ", "^": "^", "%": "%", "(": "(", ")": ")" };

function spaced(tokens: Token[]): string {
  let out = "";
  tokens.forEach((token, index) => {
    if (token.kind === "num") out += token.text;
    else {
      const previous = tokens[index - 1];
      // A leading or post-operator minus is a sign, written without spaces.
      const unary = (token.op === "-" || token.op === "+") &&
        (!previous || (previous.kind === "op" && previous.op !== ")" && previous.op !== "%"));
      out += unary ? (token.op === "-" ? "−" : "+") : SPACED[token.op];
    }
  });
  return out.replace(/\s+/g, " ").trim();
}

/**
 * The calculation `raw` asks for, or null when it is not clearly one. `force` (the `=`
 * prefix) accepts a bare number or a signed number too.
 */
export function calculate(raw: string, force = false): Calculation | null {
  const text = normalizeTyped(raw)
    .trim()
    // "15% of 200": "of" after a percent is a multiplication.
    .replace(/%\s*of\s+/gi, "% * ")
    .replace(/%\s*的\s*/g, "% * ");
  if (!text || !/^[\d\s.,+\-*/^%()]+$/.test(text)) return null;
  // A date is typed without spaces; "10 / 4" and "10÷4" are divisions.
  if (!force && !/\s/.test(text) && !raw.includes("÷") && dateLike(text)) return null;
  const tokens = tokenize(text);
  if (!tokens || tokens.length === 0) return null;
  const operands = tokens.filter((token) => token.kind === "num").length;
  const binary = tokens.some((token, index) =>
    token.kind === "op" && ["+", "-", "*", "/", "^"].includes(token.op) && index > 0 &&
    (tokens[index - 1].kind === "num" || (tokens[index - 1] as { op?: string }).op === ")" ||
      (tokens[index - 1] as { op?: string }).op === "%"));
  const percent = tokens.some((token) => token.kind === "op" && token.op === "%");
  if (!force && !(binary && operands >= 2) && !percent) return null;
  const value = new Parser(tokens).parse();
  if (value === null) return null;
  return { value, expression: spaced(tokens) };
}
