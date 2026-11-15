/**
 * Segmented (UX-02): one choice among two to six views of the same data (Board | Ladder,
 * WD | DA | WE | MA, Morning | End of day). It replaces `.segmented-control` and the ad-hoc
 * `aria-pressed` button groups.
 *
 * - A labelled `group` of toggle buttons; the chosen one is `aria-pressed="true"` (the hook the
 *   acceptance sweep reads).
 * - One Tab stop (the chosen option); Left/Right/Home/End move focus within the group, and
 *   Enter or Space chooses. Moving does not choose, so a view that loads data does not load
 *   every option on the way past.
 */
import { useRef, useState, type KeyboardEvent, type ReactNode } from "react";

import type { ControlSize } from "./Button";
import { rovingIndex } from "./keyboard";

export interface SegmentedOption<T extends string> {
  value: T;
  label: ReactNode;
  /** Tooltip and accessible description (a full name for an abbreviation). */
  title?: string;
  disabled?: boolean;
  /** Extra class on the option button (an existing acceptance hook). */
  className?: string;
  /** Extra attributes on the option button (`data-tenor`). */
  dataAttributes?: Record<string, string | undefined>;
}

export interface SegmentedProps<T extends string> {
  label: string;
  options: readonly SegmentedOption<T>[];
  value: T | null;
  onChange: (value: T) => void;
  size?: ControlSize;
  className?: string;
}

export function Segmented<T extends string>({
  label,
  options,
  value,
  onChange,
  size = "sm",
  className,
}: SegmentedProps<T>) {
  const chosen = Math.max(0, options.findIndex((option) => option.value === value));
  const [focusIndex, setFocusIndex] = useState<number | null>(null);
  const buttons = useRef<(HTMLButtonElement | null)[]>([]);
  const stop = focusIndex ?? chosen;

  const onKeyDown = (event: KeyboardEvent<HTMLButtonElement>, index: number) => {
    const next = rovingIndex(index, options.length, event.key);
    if (next === null) return;
    event.preventDefault();
    setFocusIndex(next);
    buttons.current[next]?.focus();
  };

  return (
    <div
      className={["ds-segmented", `ds-size-${size}`, className].filter(Boolean).join(" ")}
      role="group"
      aria-label={label}
      onBlur={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setFocusIndex(null);
      }}
    >
      {options.map((option, index) => {
        const pressed = option.value === value;
        return (
          <button
            key={option.value}
            ref={(element) => {
              buttons.current[index] = element;
            }}
            type="button"
            aria-pressed={pressed}
            className={[option.className, pressed ? "active" : ""].filter(Boolean).join(" ") || undefined}
            tabIndex={index === stop ? 0 : -1}
            title={option.title}
            disabled={option.disabled}
            onClick={() => {
              setFocusIndex(index);
              onChange(option.value);
            }}
            onKeyDown={(event) => onKeyDown(event, index)}
            {...option.dataAttributes}
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
}
