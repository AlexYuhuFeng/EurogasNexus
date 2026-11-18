/**
 * Dialog and Sheet (UX-02): one implementation over the native `<dialog>` element.
 *
 * - `showModal()` puts the dialog in the top layer and makes the page behind it inert, so
 *   pointer and assistive technology cannot reach it; Tab additionally wraps inside the
 *   dialog (a desktop webview has no browser chrome to Tab into).
 * - Labelled by its title; Escape (the native `cancel`) and a click on the backdrop call
 *   `onClose`; the caller owns `open`.
 * - Focus goes to `initialFocus`, else the first control, and returns to whatever had it
 *   before when the dialog closes.
 * - A Sheet is the same dialog docked to the end edge, the bottom, or the whole screen (the
 *   inspector on a phone).
 */
import {
  useEffect,
  useId,
  useRef,
  type KeyboardEvent,
  type MouseEvent,
  type ReactNode,
  type RefObject,
} from "react";

import { useCloseOnNavigation } from "@/app/shell/navigationKey";
import { IconButton } from "./Button";

export interface DialogProps {
  open: boolean;
  onClose: () => void;
  /** The visible title; also the dialog's accessible name. */
  title: ReactNode;
  /** Accessible name when the title is not plain text. */
  label?: string;
  /** A small line above the title (the object kind). */
  eyebrow?: ReactNode;
  /** Controls in the header between the title and Close (a segmented choice). */
  headerActions?: ReactNode;
  /** A control before the title (Back on a phone sheet). */
  headerStart?: ReactNode;
  /** Label of the close button (translated). */
  closeLabel: string;
  /** Hide the close button (a sheet whose header carries Back). */
  hideClose?: boolean;
  children: ReactNode;
  footer?: ReactNode;
  /** `sm` 400, `md` 560, `lg` 760 px wide. */
  size?: "sm" | "md" | "lg";
  initialFocus?: RefObject<HTMLElement | null>;
  className?: string;
  /** Marker for acceptance checks. */
  id?: string;
  /** Internal: sheet placement. */
  sheet?: "end" | "bottom" | "full";
  /** Extra attributes on the dialog element. */
  dataAttributes?: Record<string, string | undefined>;
}

const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

function focusables(root: HTMLElement): HTMLElement[] {
  return [...root.querySelectorAll<HTMLElement>(FOCUSABLE)].filter(
    (element) => !element.hasAttribute("hidden") && element.getClientRects().length > 0,
  );
}

export function Dialog({
  open,
  onClose,
  title,
  label,
  eyebrow,
  headerActions,
  headerStart,
  closeLabel,
  hideClose = false,
  children,
  footer,
  size = "md",
  initialFocus,
  className,
  id,
  sheet,
  dataAttributes,
}: DialogProps) {
  const ref = useRef<HTMLDialogElement>(null);
  const opener = useRef<Element | null>(null);
  const titleId = useId();
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;
  // A dialog or sheet opened on one page closes when the reader moves to another (rule 22).
  useCloseOnNavigation(open, () => onCloseRef.current());

  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return undefined;
    if (!open) {
      if (dialog.open) dialog.close();
      return undefined;
    }
    opener.current = document.activeElement;
    if (!dialog.open) {
      if (typeof dialog.showModal === "function") dialog.showModal();
      else dialog.setAttribute("open", "");
    }
    const target = initialFocus?.current ?? focusables(dialog)[0] ?? dialog;
    target.focus({ preventScroll: true });
    return () => {
      if (dialog.open) dialog.close();
      const previous = opener.current;
      if (previous instanceof HTMLElement && previous.isConnected) previous.focus({ preventScroll: true });
    };
  }, [open, initialFocus]);

  const onKeyDown = (event: KeyboardEvent<HTMLDialogElement>) => {
    if (event.key !== "Tab" || !ref.current) return;
    const items = focusables(ref.current);
    if (items.length === 0) {
      event.preventDefault();
      return;
    }
    const first = items[0]!;
    const last = items[items.length - 1]!;
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  };

  // The dialog box has no padding of its own (the frame inside it does), so a click whose
  // target is the dialog element itself landed on the backdrop.
  const onBackdrop = (event: MouseEvent<HTMLDialogElement>) => {
    if (event.target === event.currentTarget) onCloseRef.current();
  };

  const classes = [
    sheet ? "ds-sheet" : "ds-dialog",
    sheet ? `ds-sheet-${sheet}` : `ds-dialog-${size}`,
    className,
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <dialog
      ref={ref}
      className={classes}
      aria-labelledby={label ? undefined : titleId}
      aria-label={label}
      data-dialog={id}
      onCancel={(event) => {
        event.preventDefault();
        onCloseRef.current();
      }}
      onClose={() => {
        if (open) onCloseRef.current();
      }}
      onKeyDown={onKeyDown}
      onClick={onBackdrop}
      {...dataAttributes}
    >
      {open && (
        <div className="ds-dialog-frame">
          <header className="ds-dialog-head">
            {headerStart}
            <div className="ds-dialog-title">
              {eyebrow ? <span className="ds-dialog-eyebrow">{eyebrow}</span> : null}
              <h2 id={titleId}>{title}</h2>
            </div>
            {headerActions ? <div className="ds-dialog-head-actions">{headerActions}</div> : null}
            {hideClose ? null : (
              <IconButton className="ds-dialog-close" size="md" label={closeLabel} icon="×" onClick={() => onCloseRef.current()} />
            )}
          </header>
          <div className="ds-dialog-body">{children}</div>
          {footer ? <footer className="ds-dialog-foot">{footer}</footer> : null}
        </div>
      )}
    </dialog>
  );
}

export type SheetProps = Omit<DialogProps, "sheet" | "size"> & {
  /** `end` docks to the right edge, `bottom` to the bottom, `full` covers the screen (phone). */
  side?: "end" | "bottom" | "full";
};

export function Sheet({ side = "end", ...props }: SheetProps) {
  return <Dialog {...props} sheet={side} />;
}
