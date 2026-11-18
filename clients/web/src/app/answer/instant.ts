/**
 * Tier 1 answers as the row shows them: computed in the client, synchronously, no network.
 */

import type { AnswerView } from "./answerModel.ts";
import type { Route } from "./route.ts";
import { clipboardNumber, formatAnswerNumber } from "./numbers.ts";

function day(iso: string, withWeekday = true): string {
  return new Date(`${iso.slice(0, 10)}T00:00:00Z`).toLocaleDateString("en-GB", {
    weekday: withWeekday ? "short" : undefined,
    day: "numeric",
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  });
}

function utcTime(iso: string): string {
  return `${iso.slice(11, 16)} UTC`;
}

/** The answer row for a tier 1 route, or null for any other tier. */
export function instantAnswer(route: Route): AnswerView | null {
  if (route.tier !== 1) return null;
  switch (route.kind) {
    case "calc": {
      const value = formatAnswerNumber(route.calc.value);
      return {
        kind: "calc",
        label: route.calc.expression,
        value,
        lines: [],
        copy: { value: clipboardNumber(route.calc.value), withUnit: clipboardNumber(route.calc.value) },
      };
    }
    case "convert": {
      const { conversion } = route;
      const label = `${formatAnswerNumber(conversion.input.value)} ${conversion.input.unit}`;
      if (conversion.value === null) {
        return { kind: "convert", label, value: null, unit: conversion.unit, sentence: conversion.notes[0], lines: [] };
      }
      const decimals = conversion.kind === "price" ? 4 : 6;
      return {
        kind: "convert",
        label,
        value: formatAnswerNumber(conversion.value, decimals),
        unit: conversion.unit,
        lines: conversion.notes,
        copy: {
          value: clipboardNumber(conversion.value, decimals),
          withUnit: `${clipboardNumber(conversion.value, decimals)} ${conversion.unit}`,
        },
      };
    }
    case "gasday": {
      const answer = route.answer;
      if (answer.kind === "gas-day") {
        return {
          kind: "gasday",
          label: { key: answer.offset === 0 ? "answer.gasday.today" : "answer.gasday.offset", values: { offset: `${answer.offset > 0 ? "+" : "−"}${Math.abs(answer.offset)}` } },
          value: day(answer.gasDay),
          lines: [{ key: "answer.gasday.window", values: { start: `${utcTime(answer.startUtc)} ${day(answer.startUtc, false)}`, end: `${utcTime(answer.endUtc)} ${day(answer.endUtc, false)}` } }],
          copy: { value: answer.gasDay, withUnit: answer.gasDay },
        };
      }
      if (answer.kind === "days-to") {
        return {
          kind: "gasday",
          label: { key: "answer.gasday.days_to", values: { target: day(answer.target) } },
          value: String(answer.days),
          unit: { key: "answer.gasday.days_unit" },
          lines: [{ key: "answer.gasday.days_from", values: { from: day(answer.from) } }],
          copy: { value: String(answer.days), withUnit: String(answer.days) },
        };
      }
      return {
        kind: "gasday",
        label: { key: "answer.gasday.front_month" },
        value: answer.label,
        lines: [{ key: "answer.gasday.delivery", values: { start: day(answer.start, false), end: day(answer.end, false) } }],
        copy: { value: answer.label, withUnit: answer.label },
      };
    }
    case "glossary":
      return {
        kind: "glossary",
        label: route.answer.term,
        value: null,
        sentence: route.answer.definition,
        lines: [],
        target: { kind: "glossary", term: route.answer.term },
      };
    case "spreads":
      return {
        kind: "spreads",
        label: route.text,
        value: null,
        sentence: { key: "answer.spreads.open" },
        lines: [],
        target: { kind: "task", mode: "research", task: "spreads", params: { describe: route.text } },
      };
    case "not-calc":
      return { kind: "not-calc", label: route.text, value: null, sentence: { key: "answer.calc.not" }, lines: [] };
  }
}
