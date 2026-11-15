import type { ReactNode } from "react";

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
  compact = false,
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
}) {
  return (
    <div className={compact ? "empty-state empty-state-compact" : "empty-state"} role="status" data-empty-state={id}>
      <p>
        <strong>{reason}</strong>
        {next ? <span> {next}</span> : null}
      </p>
      {action}
    </div>
  );
}
