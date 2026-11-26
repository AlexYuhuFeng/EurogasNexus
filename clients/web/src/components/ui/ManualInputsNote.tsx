/**
 * Manual inputs note (AGENTS.md rule 19): "N inputs entered by hand", folded.
 *
 * Every calculation response states `meta.manual_inputs` (backend
 * `application/manual_inputs.py`): the inputs a person typed rather than read from a live,
 * public or firm record. A result shows this one line beneath its figures; the fold lists
 * each input with its value, unit, who entered it and when. Nothing is shown when the list
 * is empty or absent, so a result built only from records reads as it is.
 */
import { useTranslation } from "react-i18next";

import { formattingLocale } from "../../app/time/timeFormat";

export interface ManualInputDTO {
  readonly name: string;
  readonly value: unknown;
  readonly unit?: string | null;
  readonly entered_by?: string | null;
  readonly entered_at?: string | null;
}

/** The list a response's meta carries, or [] when it carries none. */
export function manualInputsOf(meta: unknown): readonly ManualInputDTO[] {
  const list = (meta as { manual_inputs?: unknown } | null | undefined)?.manual_inputs;
  return Array.isArray(list)
    ? list.filter((item): item is ManualInputDTO => typeof (item as ManualInputDTO)?.name === "string")
    : [];
}

function shown(value: unknown, language: string): string {
  if (value === null || value === undefined) return "–";
  if (typeof value === "number") {
    return new Intl.NumberFormat(formattingLocale(language), { maximumFractionDigits: 6 }).format(value);
  }
  if (typeof value === "string" || typeof value === "boolean") return String(value);
  return JSON.stringify(value);
}

export function ManualInputsNote({ meta, inputs }: { meta?: unknown; inputs?: readonly ManualInputDTO[] }) {
  const { t, i18n } = useTranslation();
  const items = inputs ?? manualInputsOf(meta);
  if (items.length === 0) return null;
  return (
    <details className="manual-inputs-note" data-manual-inputs={items.length}>
      <summary>{t("manualInputs.summary", { count: items.length })}</summary>
      <ul>
        {items.map((item) => (
          <li key={item.name}>
            <span className="manual-inputs-note__name">{item.name}</span>{" "}
            <span className="manual-inputs-note__value">
              {shown(item.value, i18n.language)}
              {item.unit ? ` ${item.unit}` : ""}
            </span>
            {item.entered_by ? (
              <span className="manual-inputs-note__by"> · {t("manualInputs.enteredBy", { who: item.entered_by })}</span>
            ) : null}
          </li>
        ))}
      </ul>
    </details>
  );
}
