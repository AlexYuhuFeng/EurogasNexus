/**
 * Popover (UX-02): a small panel anchored to the button that opened it ("Why", "Method", the
 * list of stale figures).
 *
 * - The panel follows its trigger in the DOM, so Tab goes from the trigger into the panel and
 *   on to whatever comes after the trigger; it is drawn in the top layer (the native `popover`
 *   attribute) so a table that scrolls inside its box never clips it.
 * - Placement is collision-aware (`popoverPosition.ts`): under the trigger, flipped above when
 *   there is no room, kept inside the viewport, scrolling when taller than the room; it follows
 *   the trigger on scroll and resize instead of closing.
 * - Opening moves focus into the panel; Escape closes it and returns focus to the trigger; a
 *   click elsewhere or focus leaving both trigger and panel closes it.
 */
import {
  useCallback,
  useEffect,
  useId,
  useLayoutEffect,
  useRef,
  useState,
  type FocusEvent,
  type KeyboardEvent,
  type ReactElement,
  type ReactNode,
  type RefObject,
} from "react";

import { useCloseOnNavigation } from "@/app/shell/navigationKey";
import { placePopover, type PopoverPlacement } from "./popoverPosition";
import { usePresence } from "./usePresence";

export interface PopoverTriggerProps {
  ref: RefObject<HTMLButtonElement | null>;
  "aria-expanded": boolean;
  "aria-controls": string | undefined;
  "aria-haspopup": "dialog";
  onClick: () => void;
}

export interface PopoverProps {
  /** The panel's accessible name ("Why: Rhinmark credit"). */
  label: string;
  /** Renders the trigger button with the props the popover needs. */
  trigger: (props: PopoverTriggerProps) => ReactElement;
  children: ReactNode | ((close: () => void) => ReactNode);
  placement?: PopoverPlacement;
  /** `sm` 280 px, `md` 360 px wide (narrower on a phone). */
  width?: "sm" | "md";
  className?: string;
  /** Told when the popover opens or closes (to load its content on open). */
  onOpenChange?: (open: boolean) => void;
  /** Marker for acceptance checks. */
  id?: string;
}

type TopLayer = HTMLElement & { showPopover?: () => void; hidePopover?: () => void };

export function Popover({
  label,
  trigger,
  children,
  placement = "bottom-start",
  width = "md",
  className,
  onOpenChange,
  id,
}: PopoverProps) {
  const [open, setOpenState] = useState(false);
  const triggerRef = useRef<HTMLButtonElement | null>(null);
  const panelRef = useRef<HTMLDivElement | null>(null);
  const panelId = useId();
  // The panel stays mounted while it plays its exit after hidePopover (UX R10).
  const present = usePresence(open, panelRef);

  const setOpen = useCallback(
    (next: boolean) => {
      setOpenState(next);
      onOpenChange?.(next);
    },
    [onOpenChange],
  );

  const close = useCallback(
    (returnFocus = true) => {
      setOpen(false);
      if (returnFocus) triggerRef.current?.focus({ preventScroll: true });
    },
    [setOpen],
  );

  // A floating panel never outlives the page it was opened on (UX_REFERENCE rule 22).
  useCloseOnNavigation(open, () => close(false));

  // Position without a React render: read the two boxes once per frame and write the style.
  const place = useCallback(() => {
    const anchor = triggerRef.current;
    const panel = panelRef.current;
    if (!anchor || !panel) return;
    const box = anchor.getBoundingClientRect();
    panel.style.maxHeight = "";
    const spot = placePopover(
      { top: box.top, left: box.left, width: box.width, height: box.height },
      { width: panel.offsetWidth, height: panel.scrollHeight },
      { width: window.innerWidth, height: window.innerHeight },
      placement,
    );
    panel.style.top = `${spot.top}px`;
    panel.style.left = `${spot.left}px`;
    panel.style.maxHeight = `${spot.maxHeight}px`;
    panel.dataset.side = spot.side;
  }, [placement]);

  useLayoutEffect(() => {
    if (!open) return undefined;
    const panel = panelRef.current as TopLayer | null;
    if (!panel) return undefined;
    try {
      panel.showPopover?.();
    } catch {
      /* already shown, or no top layer: the fixed position still works */
    }
    place();
    panel.focus({ preventScroll: true });
    return () => {
      try {
        panel.hidePopover?.();
      } catch {
        /* removed */
      }
    };
  }, [open, place]);

  // Content that arrives after opening (a note loading) changes the height: place again.
  useEffect(() => {
    if (!open || typeof ResizeObserver === "undefined" || !panelRef.current) return undefined;
    const observer = new ResizeObserver(() => place());
    observer.observe(panelRef.current);
    return () => observer.disconnect();
  }, [open, place]);

  useEffect(() => {
    if (!open) return undefined;
    let frame = 0;
    const follow = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(place);
    };
    const onPointerDown = (event: PointerEvent) => {
      const target = event.target as Node;
      if (panelRef.current?.contains(target) || triggerRef.current?.contains(target)) return;
      close(false);
    };
    const onKeyDown = (event: globalThis.KeyboardEvent) => {
      if (event.key !== "Escape") return;
      const target = event.target as Node;
      if (panelRef.current?.contains(target) || triggerRef.current?.contains(target) || target === document.body) {
        event.preventDefault();
        close(true);
      }
    };
    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    window.addEventListener("resize", follow);
    window.addEventListener("scroll", follow, true);
    return () => {
      cancelAnimationFrame(frame);
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
      window.removeEventListener("resize", follow);
      window.removeEventListener("scroll", follow, true);
    };
  }, [open, place, close]);

  const onPanelKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key === "Escape") {
      event.preventDefault();
      event.stopPropagation();
      close(true);
    }
  };

  const onPanelBlur = (event: FocusEvent<HTMLDivElement>) => {
    const next = event.relatedTarget as Node | null;
    if (!next) return; // focus went to the page itself (a click); pointerdown decides
    if (panelRef.current?.contains(next) || triggerRef.current?.contains(next)) return;
    setOpen(false);
  };

  const classes = ["ds-popover", `ds-popover-${width}`, className].filter(Boolean).join(" ");
  return (
    <>
      {trigger({
        ref: triggerRef,
        "aria-expanded": open,
        "aria-controls": open ? panelId : undefined,
        "aria-haspopup": "dialog",
        onClick: () => (open ? close(false) : setOpen(true)),
      })}
      {present && (
        <div
          ref={panelRef}
          id={panelId}
          className={classes}
          role="dialog"
          aria-label={label}
          tabIndex={-1}
          {...{ popover: "manual" }}
          data-popover={id}
          onKeyDown={onPanelKeyDown}
          onBlur={onPanelBlur}
        >
          {typeof children === "function" ? children(() => close(true)) : children}
        </div>
      )}
    </>
  );
}
