import type { ReactNode } from "react";

/**
 * The one way a panel says it has nothing to show (#27): a short reason and, where there is one,
 * the next step. It replaces grids of "n/a" cards, empty bars and repeated "Unavailable" badges,
 * and it never draws a value: unknown is never shown as zero.
 */
export function EmptyState({
  reason,
  next,
  action,
  id,
}: {
  reason: ReactNode;
  next?: ReactNode;
  action?: ReactNode;
  /** `data-empty-state` marker, for acceptance checks that tell an empty panel from a broken one. */
  id?: string;
}) {
  return (
    <div className="empty-state" role="status" data-empty-state={id}>
      <p>
        <strong>{reason}</strong>
        {next ? <span> {next}</span> : null}
      </p>
      {action}
    </div>
  );
}
