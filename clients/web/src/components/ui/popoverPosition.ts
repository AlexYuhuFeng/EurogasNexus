/**
 * Where a popover goes (UX-02): under its trigger, aligned to the trigger's start or end edge,
 * flipped above when there is not room below and there is more room above, kept inside the
 * viewport with a gutter, and given a max height so a long note scrolls instead of leaving
 * the screen. Pure, so collision cases are tested without a browser.
 */
export interface Box {
  top: number;
  left: number;
  width: number;
  height: number;
}

export type PopoverPlacement = "bottom-start" | "bottom-end";

export interface PopoverPlace {
  top: number;
  left: number;
  maxHeight: number;
  side: "bottom" | "top";
}

export const POPOVER_GAP = 4;
export const POPOVER_GUTTER = 8;

export function placePopover(
  anchor: Box,
  panel: { width: number; height: number },
  viewport: { width: number; height: number },
  placement: PopoverPlacement = "bottom-start",
  gap = POPOVER_GAP,
  gutter = POPOVER_GUTTER,
): PopoverPlace {
  const width = Math.min(panel.width, Math.max(0, viewport.width - 2 * gutter));
  const preferredLeft = placement === "bottom-end" ? anchor.left + anchor.width - width : anchor.left;
  const left = Math.max(gutter, Math.min(preferredLeft, viewport.width - width - gutter));

  const roomBelow = viewport.height - (anchor.top + anchor.height) - gap - gutter;
  const roomAbove = anchor.top - gap - gutter;
  const side: "bottom" | "top" = panel.height <= roomBelow || roomBelow >= roomAbove ? "bottom" : "top";
  const room = Math.max(0, side === "bottom" ? roomBelow : roomAbove);
  const height = Math.min(panel.height, room);
  const top = side === "bottom" ? anchor.top + anchor.height + gap : anchor.top - gap - height;
  return { top: Math.round(top), left: Math.round(left), maxHeight: Math.floor(room), side };
}
