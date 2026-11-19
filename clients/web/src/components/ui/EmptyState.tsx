import type { ReactNode } from "react";

import { SeeExample } from "./ExampleView";

/**
 * The one way a panel says it has nothing to show (#27, UX-02): one line with the cause and,
 * where there is one, the next step and one action. It replaces grids of "n/a" cards, empty bars
 * and repeated "Unavailable" badges, and it never draws a value: unknown is never shown as zero.
 *
 * `compact` is the one-line form for a rail or a table footer (no padding of its own).
 */
export function EmptyState({
  reason,
  next,
  action,
  id,
  need,
  compact = false,
  onSeeExample,
}: {
  /** Why there is nothing: "No outages on the network now." */
  reason: ReactNode;
  /** What would fill it: "Appears after the GIE AGSI source is ingested." */
  next?: ReactNode;
  /** One action (a Button), or nothing. */
  action?: ReactNode;
  /** `data-empty-state` marker, for acceptance checks that tell an empty panel from a broken one. */
  id?: string;
  compact?: boolean;
  /**
   * What is missing, when it is not data (design basis H.1, I5): a permission names who grants
   * it (`empty.permission`); a licence says the administrator connects it (`empty.licence`),
   * never a prompt to buy.
   */
  need?: "data" | "permission" | "licence";
  /** A page empty for a new installation offers its example ("See an example", design H.1). */
  onSeeExample?: () => void;
}) {
  return (
    <div className={compact ? "empty-state empty-state-compact" : "empty-state"} role="status" data-empty-state={id} data-empty-need={need}>
      <p>
        <strong>{reason}</strong>
        {next ? <span> {next}</span> : null}
      </p>
      {action}
      {onSeeExample ? <SeeExample onShow={onSeeExample} /> : null}
    </div>
  );
}
