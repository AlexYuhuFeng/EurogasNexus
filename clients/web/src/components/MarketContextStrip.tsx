/**
 * Market context strip (Architecture V2 Wave 5, surface half).
 *
 * The projection gives the market surface one coherent reading: a single as-of
 * instant, one time basis, and per-slice freshness and entitlement. This strip
 * shows exactly that, so a trader can see which slices are usable before trusting
 * a number, instead of the surface reconciling several endpoint timestamps itself.
 *
 * It renders what the backend reported: a slice the backend could not serve reads
 * as unavailable rather than as an empty market, and a slice whose rows were
 * filtered reads as restricted rather than as a zero.
 */

import type { MarketContextProjectionDTO } from "@/api/client";
import {
  MARK_CONTEXT_SLICE_LABEL_KEYS,
  contextAsOf,
  contextTimeBasis,
  degradedSlices,
  sliceReadings,
} from "@/app/model/marketContextModel";
import { ProjectionContextStrip } from "@/components/ProjectionContextStrip";

type Translate = (key: string, options?: Record<string, unknown>) => string;

interface MarketContextStripProps {
  projection: MarketContextProjectionDTO | null;
  t: Translate;
}

export function MarketContextStrip({ projection, t }: MarketContextStripProps) {
  if (!projection) return null;

  return (
    <ProjectionContextStrip
      namespace="market_context"
      className="market-context-strip"
      readings={sliceReadings(projection)}
      degraded={degradedSlices(projection)}
      labelKeys={MARK_CONTEXT_SLICE_LABEL_KEYS}
      asOf={contextAsOf(projection)}
      basis={contextTimeBasis(projection)}
      t={t}
    />
  );
}
