/**
 * The answer row for a price conversion with a future delivery period, from
 * `POST /api/market/normalise`: the server converts with the units authority and the FX for
 * that period (forward by interest parity, a licensed forward, or spot), and states the rate,
 * its method and dates. The client shows what it is given and computes nothing.
 */

import type { NormalisedValueDTO, NormaliseRequestDTO, NormaliseResponseDTO } from "../../api/comparablePrices.ts";
import type { AnswerText, AnswerView } from "./answerModel.ts";
import type { LookupIntent } from "./intent.ts";
import { clipboardNumber, formatAnswerNumber } from "./numbers.ts";
import { deskUnitLabel } from "./units.ts";

export type ForwardIntent = Extract<LookupIntent, { kind: "convert" }>;

/** The UTC day of a date or instant as an ISO date: answerText writes it in the reader's
 * language, as the price and spread answers do. */
function shortDay(iso: string | null | undefined): string {
  return iso ? iso.slice(0, 10) : "";
}

/** The request the bar sends for one typed conversion. */
export function forwardRequest(intent: ForwardIntent): NormaliseRequestDTO {
  return {
    to_unit: intent.to,
    values: [{ value: intent.value, unit: intent.from, product: intent.period }],
  };
}

function fxLines(item: NormalisedValueDTO, period: string): AnswerText[] {
  const fx = item.normalisation?.fx;
  if (!fx) return [];
  // The pair as a desk quotes it, turned by the server (the client does no FX arithmetic).
  const shown = fx.desk_quote;
  const lines: AnswerText[] = [];
  if (fx.method === "derived: covered interest parity") {
    const benchmarks = (fx.rates ?? []).map((item) => item.label.split(" (")[0]).join(", ");
    lines.push({ key: "answer.convert.fx_forward_derived", values: { pair: shown.pair, period, rate: shown.rate.toFixed(4), benchmarks } });
  } else if (fx.method === "licensed") {
    lines.push({ key: "answer.convert.fx_forward_licensed", values: { pair: shown.pair, period, rate: shown.rate.toFixed(4), vendor: fx.licensed?.source_system ?? "" } });
  } else {
    lines.push({ key: "answer.convert.fx_forward_spot", values: { pair: shown.pair, rate: shown.rate.toFixed(4), date: shortDay(fx.spot?.value_date) } });
  }
  if (fx.spot && shown.spot_rate !== null && fx.method !== "spot: ECB reference rate") {
    lines.push({
      key: fx.spot.simulated ? "answer.convert.fx_spot_reference_sim" : "answer.convert.fx_spot_reference",
      values: { rate: shown.spot_rate.toFixed(4), date: shortDay(fx.spot.value_date) },
    });
  }
  if (item.tolerance && item.tolerance.absolute > 0 && item.unit) {
    lines.push({
      key: "answer.convert.fx_tolerance",
      values: { value: formatAnswerNumber(item.tolerance.absolute, 4), unit: deskUnitLabel(item.unit), pct: item.tolerance.relative_pct },
    });
  }
  return lines;
}

/** The answer row for the server's normalisation of one typed conversion. */
export function forwardAnswer(intent: ForwardIntent, response: NormaliseResponseDTO): AnswerView {
  const item = response.values[0];
  const label = `${formatAnswerNumber(intent.value)} ${deskUnitLabel(intent.from)} · ${intent.period}`;
  const unit = deskUnitLabel(intent.to);
  if (!item || item.value === null || item.value === undefined) {
    return {
      kind: "convert",
      label,
      value: null,
      unit,
      sentence: {
        key: item?.refused?.code === "beyond_horizon" ? "answer.convert.forward_beyond_horizon" : "answer.convert.forward_refused",
        values: { reason: item?.refused?.message ?? "" },
      },
      lines: [],
    };
  }
  const decimals = 4;
  return {
    kind: "convert",
    label,
    value: formatAnswerNumber(item.value, decimals),
    unit,
    simulated: item.simulated,
    lines: fxLines(item, intent.period),
    copy: { value: clipboardNumber(item.value, decimals), withUnit: `${clipboardNumber(item.value, decimals)} ${unit}` },
  };
}
