/**
 * The adaptive client's two layout axes (docs/product/ADAPTIVE_CLIENT.md, #40).
 *
 * Width class comes from the window, not the device: a narrow desktop window is compact too.
 * Input comes from the primary pointer. Both are published on <html> as `data-width-class` and
 * `data-pointer`, so CSS and components read one source instead of inventing breakpoints.
 * Layout never grants anything.
 */
import { useEffect, useState } from "react";

export type WidthClass = "compact" | "medium" | "wide";
export type PointerKind = "coarse" | "fine";

export const COMPACT_MAX_PX = 719;
export const MEDIUM_MAX_PX = 1199;

export function widthClassFor(width: number): WidthClass {
  if (width <= COMPACT_MAX_PX) return "compact";
  if (width <= MEDIUM_MAX_PX) return "medium";
  return "wide";
}

function read(): { widthClass: WidthClass; pointer: PointerKind } {
  if (typeof window === "undefined") return { widthClass: "wide", pointer: "fine" };
  const pointer: PointerKind = window.matchMedia?.("(pointer: coarse)").matches ? "coarse" : "fine";
  return { widthClass: widthClassFor(window.innerWidth), pointer };
}

function publish(layout: { widthClass: WidthClass; pointer: PointerKind }): void {
  if (typeof document === "undefined") return;
  document.documentElement.dataset.widthClass = layout.widthClass;
  document.documentElement.dataset.pointer = layout.pointer;
}

export function useShellLayout(): { widthClass: WidthClass; pointer: PointerKind } {
  const [layout, setLayout] = useState(read);
  useEffect(() => {
    if (typeof window === "undefined") return;
    const update = () => {
      const next = read();
      publish(next);
      setLayout((current) =>
        current.widthClass === next.widthClass && current.pointer === next.pointer ? current : next,
      );
    };
    update();
    window.addEventListener("resize", update);
    const coarse = window.matchMedia?.("(pointer: coarse)");
    coarse?.addEventListener?.("change", update);
    return () => {
      window.removeEventListener("resize", update);
      coarse?.removeEventListener?.("change", update);
    };
  }, []);
  return layout;
}
