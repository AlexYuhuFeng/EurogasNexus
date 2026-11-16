/**
 * The Eurogas Nexus mark and its two lock-ups (docs/product/BRAND_MARK.md).
 *
 * - `variant`: `mark` alone, `monogram` (mark + "EN") or `wordmark` (mark + "Eurogas Nexus").
 *   The name is live text in the interface face, never outlines, and stays "Eurogas Nexus" in
 *   every language.
 * - `tone`: `mono` draws in `currentColor` and is the default in the application chrome (it
 *   follows the theme); `colour` is navy and blue for light grounds (sign-in, reports, print);
 *   `reverse` is white and light blue for the navy brand panel; `auto` is colour in the light
 *   theme and reverse in the dark one (a surface that follows the theme, such as the sign-in
 *   card).
 * - `size`: the mark's height on the type scale's steps (sm 20, md 24, lg 32, xl 40 px); the
 *   name takes the matching text step. A number sets the mark alone in px.
 *
 * Accessible name: the whole lock-up is one image named "Eurogas Nexus". Pass `decorative`
 * where the product name is already written beside it, and assistive technology skips it.
 *
 * The path data is the same as the server-side brand module that reports draw with;
 * tests/unit/test_brand_mark.py holds the two together.
 */
import type { AriaAttributes } from "react";

export type BrandVariant = "mark" | "monogram" | "wordmark";
export type BrandTone = "mono" | "colour" | "reverse" | "auto";
export type BrandSize = "sm" | "md" | "lg" | "xl";

/** A regular hexagon, point up, circumradius 14 on a 32-unit grid, broken for the wave. */
export const BRAND_HEX_UPPER = "M3.876 16.5V9L16 2L28.124 9V10.5";
export const BRAND_HEX_LOWER = "M28.124 15.5V23L16 30L3.876 23V21.5";
/** One cubic between two horizontal runs: in low on the left, out high on the right. */
export const BRAND_WAVE = "M1.5 19H5C15 19 17 13 27 13H30.5";
export const BRAND_STROKE = 2.5;
export const BRAND_NAME = "Eurogas Nexus";

const MARK_PX: Record<BrandSize, number> = { sm: 20, md: 24, lg: 32, xl: 40 };

export interface BrandMarkProps {
  variant?: BrandVariant;
  tone?: BrandTone;
  size?: BrandSize | number;
  /** Accessible name; the product name by default. */
  label?: string;
  /** Hidden from assistive technology (the product name is written beside it). */
  decorative?: boolean;
  className?: string;
}

type A11y = AriaAttributes & { role?: "img"; focusable?: "false" };

function Glyph({ px, a11y }: { px: number; a11y: A11y }) {
  return (
    <svg
      className="ds-brand-glyph"
      viewBox="0 0 32 32"
      width={px}
      height={px}
      fill="none"
      stroke="currentColor"
      strokeWidth={BRAND_STROKE}
      strokeLinejoin="round"
      strokeLinecap="butt"
      {...a11y}
    >
      <path className="ds-brand-hex" d={BRAND_HEX_UPPER} />
      <path className="ds-brand-hex" d={BRAND_HEX_LOWER} />
      <path className="ds-brand-wave" d={BRAND_WAVE} />
    </svg>
  );
}

export function BrandMark({
  variant = "mark",
  tone = "mono",
  size = "md",
  label = BRAND_NAME,
  decorative = false,
  className,
}: BrandMarkProps) {
  const step: BrandSize = typeof size === "number" ? "md" : size;
  const px = typeof size === "number" ? size : MARK_PX[size];
  const named: A11y = decorative ? { "aria-hidden": true } : { role: "img", "aria-label": label };
  const classes = ["ds-brand", `ds-brand-${variant}`, `ds-brand-${tone}`, `ds-brand-${step}`, className]
    .filter(Boolean)
    .join(" ");

  if (variant === "mark") {
    return (
      <span className={classes}>
        <Glyph px={px} a11y={{ ...named, focusable: "false" }} />
      </span>
    );
  }
  return (
    <span className={classes} {...named}>
      <Glyph px={px} a11y={{ "aria-hidden": true, focusable: "false" }} />
      {variant === "monogram" ? (
        <span className="ds-brand-name" aria-hidden="true">
          E<span className="ds-brand-accent">N</span>
        </span>
      ) : (
        <span className="ds-brand-name" aria-hidden="true">
          Eurogas <span className="ds-brand-accent">Nexus</span>
        </span>
      )}
    </span>
  );
}
