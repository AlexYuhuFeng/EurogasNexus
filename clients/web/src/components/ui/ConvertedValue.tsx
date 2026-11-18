import type { ConvertedText } from "@/app/time/valueFormat";

/**
 * The secondary value beside a native figure (design basis G3): the converted figure with its
 * rate, date and method. `hover` stays out of the way until the figure is hovered, focused or
 * tapped (its parent marks itself `data-converted-host`); `line` is always shown (reporting
 * contexts: totals, limits, P&L, when the reporting currency differs).
 */
export function ConvertedValue({
  converted,
  mode = "hover",
  id,
  compact = false,
}: {
  converted: ConvertedText | null;
  mode?: "hover" | "line";
  id?: string;
  /** In a table cell: just the converted figure, with the rate and method in its title. */
  compact?: boolean;
}) {
  if (!converted) return null;
  if (compact && converted.figure) {
    return (
      <small id={id} className="converted-value" data-converted="compact" title={converted.text}>
        {converted.figure}
      </small>
    );
  }
  return (
    <small
      id={id}
      title={converted.reason}
      className="converted-value"
      data-converted={mode}
      data-converted-refused={converted.refused ? "" : undefined}
      data-converted-simulated={converted.simulated ? "" : undefined}
    >
      {converted.text}
    </small>
  );
}
