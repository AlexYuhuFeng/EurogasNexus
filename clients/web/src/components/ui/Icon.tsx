/**
 * Icon (UX R9): the one way to draw an icon. One licensed set, Lucide (ISC; the icons derived
 * from Feather are MIT; THIRD_PARTY_NOTICES.md and docs/legal/DEPENDENCY_LICENSE_REVIEW.md),
 * drawn at the design system's sizes and stroke, always hidden from assistive technology: the
 * control or the text beside it carries the name (the UI constitution bans mystery icons).
 *
 * The set is curated: a name is added here, on purpose, before any screen uses it, so the
 * product keeps one vocabulary of shapes. Status shapes are part of it, so a state never rests
 * on colour alone (R1): ok a check in a circle, watch a triangle, breach an octagon, stale a
 * clock, simulated a flask, info an "i".
 */
import {
  ArrowDown,
  ArrowUp,
  Bell,
  Calendar,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  ChevronUp,
  CircleCheck,
  Clock,
  FlaskConical,
  Info,
  Layers,
  ListFilter,
  LocateFixed,
  Maximize2,
  Minimize2,
  OctagonAlert,
  Rotate3d,
  RotateCcw,
  Search,
  TriangleAlert,
  X,
  type LucideIcon,
} from "lucide-react";

export const ICONS = {
  close: X,
  "chevron-down": ChevronDown,
  "chevron-up": ChevronUp,
  "chevron-left": ChevronLeft,
  "chevron-right": ChevronRight,
  "sort-ascending": ArrowUp,
  "sort-descending": ArrowDown,
  search: Search,
  alerts: Bell,
  calendar: Calendar,
  filter: ListFilter,
  reset: RotateCcw,
  "full-screen": Maximize2,
  "exit-full-screen": Minimize2,
  info: Info,
  layers: Layers,
  "locate-positions": LocateFixed,
  "view-3d": Rotate3d,
  "status-ok": CircleCheck,
  "status-watch": TriangleAlert,
  "status-breach": OctagonAlert,
  "status-stale": Clock,
  "status-simulated": FlaskConical,
  "status-info": Info,
} as const satisfies Record<string, LucideIcon>;

export type IconName = keyof typeof ICONS;

/** xs (12 px) is for status chips only; sm (16 px) inside controls; md (20 px) beside headings. */
export type IconSize = "xs" | "sm" | "md";

export interface IconProps {
  name: IconName;
  size?: IconSize;
  className?: string;
}

export function Icon({ name, size = "sm", className }: IconProps) {
  const Glyph = ICONS[name];
  return (
    <Glyph
      className={["ds-icon-svg", className].filter(Boolean).join(" ")}
      data-icon={name}
      data-size={size}
      aria-hidden="true"
      focusable="false"
    />
  );
}
