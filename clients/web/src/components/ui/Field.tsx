/**
 * Field and Select (UX-02): one way to label a form control.
 *
 * Field renders the label, the control, a hint and an error, and wires them together: the
 * label's `for`, the control's `aria-describedby` (hint and error) and `aria-invalid`. The
 * control is passed as the only child and receives those attributes, so a native input,
 * textarea or Select all take part.
 *
 * Select is the native `<select>`: in a desktop webview and on a phone the platform list is
 * the most robust and accessible choice there is. It is styled to the control heights
 * (28 dense, 32 forms) and takes typed options.
 */
import {
  Children,
  cloneElement,
  isValidElement,
  useId,
  type ReactElement,
  type ReactNode,
  type SelectHTMLAttributes,
} from "react";

import type { ControlSize } from "./Button";

export interface FieldProps {
  label: ReactNode;
  /** One control: an input, textarea or Select. */
  children: ReactElement;
  hint?: ReactNode;
  error?: ReactNode;
  /** Label beside the control (toolbars) instead of above it (forms). */
  inline?: boolean;
  className?: string;
}

export function Field({ label, children, hint, error, inline = false, className }: FieldProps) {
  const generated = useId();
  const only = Children.only(children);
  const props = (isValidElement(only) ? only.props : {}) as { id?: string; "aria-describedby"?: string };
  const id = props.id ?? generated;
  const hintId = hint ? `${id}-hint` : undefined;
  const errorId = error ? `${id}-error` : undefined;
  const describedBy = [props["aria-describedby"], hintId, errorId].filter(Boolean).join(" ") || undefined;
  const control = cloneElement(only as ReactElement<Record<string, unknown>>, {
    id,
    "aria-describedby": describedBy,
    "aria-invalid": error ? true : undefined,
  });
  const classes = ["ds-field", inline ? "ds-field-inline" : "", error ? "ds-field-invalid" : "", className]
    .filter(Boolean)
    .join(" ");
  return (
    <div className={classes}>
      <label className="ds-field-label" htmlFor={id}>
        {label}
      </label>
      {control}
      {hint ? (
        <small id={hintId} className="ds-field-hint">
          {hint}
        </small>
      ) : null}
      {error ? (
        <small id={errorId} className="ds-field-error" role="alert">
          {error}
        </small>
      ) : null}
    </div>
  );
}

export interface SelectOption<T extends string> {
  value: T;
  label: ReactNode;
  disabled?: boolean;
}

export interface SelectProps<T extends string>
  extends Omit<SelectHTMLAttributes<HTMLSelectElement>, "value" | "onChange" | "size"> {
  value: T;
  options: readonly SelectOption<T>[];
  onChange: (value: T) => void;
  size?: ControlSize;
}

export function Select<T extends string>({
  value,
  options,
  onChange,
  size = "sm",
  className,
  ...rest
}: SelectProps<T>) {
  return (
    <select
      {...rest}
      className={["ds-select", `ds-size-${size}`, className].filter(Boolean).join(" ")}
      value={value}
      onChange={(event) => onChange(event.target.value as T)}
    >
      {options.map((option) => (
        <option key={option.value} value={option.value} disabled={option.disabled}>
          {typeof option.label === "string" || typeof option.label === "number" ? option.label : String(option.value)}
        </option>
      ))}
    </select>
  );
}
