import type { ButtonHTMLAttributes, ReactNode } from "react";
import { Spinner } from "./Spinner";

/**
 * The one button (UX-02). Four meanings, two heights:
 *
 * - `primary`   the page's commit (one per page; the WorkspaceHeader slot)
 * - `secondary` an ordinary action
 * - `quiet`     an action that should not compete with the content (Refresh, Desk brief)
 * - `danger`    the confirm step of a destructive action (quiet until then: see COMPONENTS.md)
 *
 * `sm` is 28 px (tables, toolbars, panel headers); `md` is 32 px (forms). Disabled and loading
 * look disabled, never like a live grey button; loading also shows the busy ring (Spinner) in
 * place of the label, which stays in the button for its width and its accessible name. The emitted class names are the ones the rest of
 * the stylesheet already knows (`button-primary`, `secondary-button`, `danger`), so a migrated
 * call site keeps its selectors and acceptance hooks.
 */
export type ButtonVariant = "primary" | "secondary" | "quiet" | "danger";
export type ControlSize = "sm" | "md";

const VARIANT_CLASS: Record<ButtonVariant, string> = {
  primary: "button-primary",
  secondary: "secondary-button",
  quiet: "quiet-button",
  danger: "danger",
};

export interface ButtonProps extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, "type"> {
  variant?: ButtonVariant;
  size?: ControlSize;
  /** Busy: the button keeps its label and width, says it is busy and cannot be pressed again. */
  loading?: boolean;
  type?: "button" | "submit" | "reset";
  children: ReactNode;
}

export function buttonClass(variant: ButtonVariant, size: ControlSize, extra?: string): string {
  return ["ds-button", VARIANT_CLASS[variant], `ds-size-${size}`, extra].filter(Boolean).join(" ");
}

export function Button({
  variant = "secondary",
  size = "sm",
  loading = false,
  type = "button",
  className,
  disabled,
  children,
  ...rest
}: ButtonProps) {
  return (
    <button
      {...rest}
      // A button inside a form never submits it by accident: the type is always explicit.
      type={type}
      className={buttonClass(variant, size, className)}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      data-loading={loading ? "" : undefined}
    >
      {loading && <Spinner className="ds-button-spinner" />}
      {children}
    </button>
  );
}

export interface IconButtonProps extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, "type" | "children" | "aria-label"> {
  /** The accessible name, also shown as the tooltip: an icon alone names nothing. */
  label: string;
  /** The glyph or SVG; hidden from assistive technology, which reads `label`. */
  icon: ReactNode;
  size?: ControlSize;
  variant?: Exclude<ButtonVariant, "primary" | "danger">;
  type?: "button" | "submit" | "reset";
}

/** A square button with an icon and an accessible name; the same heights as Button. */
export function IconButton({
  label,
  icon,
  size = "sm",
  variant = "quiet",
  type = "button",
  className,
  title,
  ...rest
}: IconButtonProps) {
  return (
    <button
      {...rest}
      type={type}
      className={buttonClass(variant, size, ["ds-icon-button", className].filter(Boolean).join(" "))}
      aria-label={label}
      title={title ?? label}
    >
      <span className="ds-icon" aria-hidden="true">{icon}</span>
    </button>
  );
}
