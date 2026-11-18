/**
 * The visible half of the loading rule (UX_REFERENCE rule 18): the named stages of work in
 * progress, the current one marked and moving, the done ones ticked, with a bar that never fills
 * before the answer arrives. It reserves the height the result will take (`reserve`), so nothing
 * jumps when the answer replaces it. Under reduced motion the bar and the dots stand still.
 */
export function WorkProgress({
  stages,
  current,
  label,
  reserve,
  className,
}: {
  /** Words for each stage, in order ("Reading prices", "Reading outages", "Writing"). */
  stages: readonly string[];
  current: number;
  /** What is being worked on, for assistive technology ("Drafting the morning brief"). */
  label: string;
  /** CSS min-height the result will need (a textarea, a table). */
  reserve?: string;
  className?: string;
}) {
  const done = Math.min(current, stages.length - 1);
  const percent = Math.round(((done + 0.5) / Math.max(1, stages.length)) * 90);
  return (
    <div
      className={["ds-work-progress", className].filter(Boolean).join(" ")}
      role="status"
      aria-live="polite"
      aria-busy="true"
      aria-label={label}
      style={reserve ? { minHeight: reserve } : undefined}
      data-work-stage={done}
    >
      <div className="ds-work-bar" aria-hidden="true">
        <span style={{ width: `${percent}%` }} />
      </div>
      <ol className="ds-work-stages">
        {stages.map((stage, index) => (
          <li key={stage} data-state={index < done ? "done" : index === done ? "current" : "next"} aria-current={index === done ? "step" : undefined}>
            <span className="ds-work-mark" aria-hidden="true" />
            {stage}
          </li>
        ))}
      </ol>
    </div>
  );
}
