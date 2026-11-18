import type { ReactNode } from "react";

import { missingReadiness, type ReadinessItem } from "./readinessModel";

export type { ReadinessItem } from "./readinessModel";

/**
 * "What it needs" (design basis H.1, B.7): shown only when something the page needs is missing,
 * as at most three items, each with its state and the one control that fixes it. When everything
 * is present the checklist is absent, not a row of green ticks.
 */
export function ReadinessChecklist({
  title,
  items,
  id,
}: {
  /** "Before this page can answer:" */
  title: ReactNode;
  items: readonly ReadinessItem[];
  id?: string;
}) {
  const missing = missingReadiness(items);
  if (missing.length === 0) return null;
  return (
    <section className="readiness-checklist" data-readiness={id ?? ""} aria-label={typeof title === "string" ? title : undefined}>
      <p className="readiness-checklist-title">{title}</p>
      <ul>
        {missing.map((item) => (
          <li key={item.id} data-readiness-item={item.id}>
            <span className="readiness-checklist-label">{item.label}</span>
            {item.state ? <span className="readiness-checklist-state">{item.state}</span> : null}
            {item.fix ? <span className="readiness-checklist-fix">{item.fix}</span> : null}
          </li>
        ))}
      </ul>
    </section>
  );
}
