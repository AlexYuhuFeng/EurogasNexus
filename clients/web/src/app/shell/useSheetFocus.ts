/**
 * Focus and dismissal for a full-screen sheet on a phone (ADAPTIVE_CLIENT.md A4): focus moves
 * into the sheet when it opens and returns to whatever opened it when it closes; Escape closes.
 * Pure UI behaviour - no data is read here.
 */
import { type RefObject, useEffect, useRef } from "react";

export function useSheetFocus(
  active: boolean,
  focusTarget: RefObject<HTMLElement | null>,
  onClose: () => void,
): void {
  const openerRef = useRef<Element | null>(null);
  useEffect(() => {
    if (!active) return;
    openerRef.current = document.activeElement;
    focusTarget.current?.focus();
    return () => {
      const opener = openerRef.current;
      if (opener instanceof HTMLElement && opener.isConnected) opener.focus();
    };
  }, [active, focusTarget]);
  useEffect(() => {
    if (!active) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [active, onClose]);
}
