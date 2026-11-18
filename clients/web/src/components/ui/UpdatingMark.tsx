/**
 * "Updating": the panel shows its last answer while a newer one is read (app/data/readCache.ts).
 * Quiet, beside the title; nothing at all when nothing is being read.
 */
export function UpdatingMark({ active, label }: { active: boolean; label: string }) {
  if (!active) return null;
  return (
    <span className="ds-updating" role="status" aria-live="polite">
      <i aria-hidden="true" />
      {label}
    </span>
  );
}
