/**
 * A panel's standing explanation, folded under "How to read this" (#69).
 *
 * The explanation is read once; on every later visit it would take the space the panel's
 * reading needs. State messages (unavailable, stale, a one-time secret) are not help and stay
 * visible: use this only for text that is true every time the panel renders.
 */
export function PanelHelp({ text, label }: { text: string; label: string }) {
  return (
    <details className="panel-help">
      <summary>{label}</summary>
      <p className="panel-copy">{text}</p>
    </details>
  );
}
