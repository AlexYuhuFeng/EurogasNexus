import { Spinner } from "./Spinner";

/**
 * "Updating": the panel shows its last answer while a newer one is read (app/data/readCache.ts).
 * Quiet, beside the title: the small busy ring, with the word for assistive technology and as the
 * tooltip; nothing at all when nothing is being read.
 */
export function UpdatingMark({ active, label }: { active: boolean; label: string }) {
  if (!active) return null;
  return (
    <span className="ds-updating" role="status" aria-live="polite" title={label}>
      <Spinner size="xs" />
      <span className="ds-visually-hidden">{label}</span>
    </span>
  );
}
