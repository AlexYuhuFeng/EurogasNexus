/**
 * Portfolio context strip (Architecture V2 Wave 5, surface half).
 *
 * `/portfolio/live-summary`, `/portfolio/screen-orders` and
 * `/portfolio/pnl-snapshots` used to be three reads with three timestamps. The
 * projection is one read on one as-of, and this strip shows that reading: which
 * slices are fresh, which are stale or missing, and how many rows an entitlement
 * withheld - so a portfolio total is qualified before it is trusted.
 */

import type { PortfolioSnapshotProjectionDTO } from "@/api/client";
import {
  PORTFOLIO_SNAPSHOT_SLICE_LABEL_KEYS,
  degradedPortfolioSlices,
  portfolioReadings,
  snapshotAsOf,
  snapshotTimeBasis,
} from "@/app/model/portfolioSnapshotModel";
import { ProjectionContextStrip } from "@/components/ProjectionContextStrip";

type Translate = (key: string, options?: Record<string, unknown>) => string;

interface PortfolioContextStripProps {
  projection: PortfolioSnapshotProjectionDTO | null;
  t: Translate;
}

export function PortfolioContextStrip({ projection, t }: PortfolioContextStripProps) {
  if (!projection) return null;

  return (
    <ProjectionContextStrip
      namespace="portfolio_context"
      className="portfolio-context-strip"
      readings={portfolioReadings(projection)}
      degraded={degradedPortfolioSlices(projection)}
      labelKeys={PORTFOLIO_SNAPSHOT_SLICE_LABEL_KEYS}
      asOf={snapshotAsOf(projection)}
      basis={snapshotTimeBasis(projection)}
      t={t}
    />
  );
}
