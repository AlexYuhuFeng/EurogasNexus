/**
 * The analyst's path through Research, one line per page (owner, 2026-11-19): the physical
 * picture (Fundamentals) → what the price structure says (Spreads) → what it means for a cargo
 * or a flow (Cargo & netback) → the write-up (Reports). Each step is a link with its context
 * ("EU storage 12 pts below the 5-yr mean → see the Win–Sum spread"); the study travels in the
 * address (`app/model/spreadsBoard.ts`), so the next page opens on the same object.
 */
import type { ReactNode } from "react";

import "@/styles/research.css";

export interface NextStep {
  id: string;
  /** What the link does, in desk words. */
  label: string;
  /** The address to open (`?workspace=research&task=…`). */
  href: string;
  /** The context in front of the link ("EU storage 12 pts below the 5-yr mean"). */
  lead?: ReactNode;
}

/** Open a Research address in place: the shell follows the history entry. */
export function followLink(href: string) {
  window.history.pushState({ workspace: "research" }, "", href);
  window.dispatchEvent(new PopStateEvent("popstate"));
}

export function NextSteps({ steps, label }: { steps: readonly NextStep[]; label: string }) {
  if (steps.length === 0) return null;
  return (
    <nav className="research-next" aria-label={label} data-next-steps="true">
      <span className="research-next-label">{label}</span>
      {steps.map((step) => (
        <span key={step.id} className="research-next-step" data-next-step={step.id}>
          {step.lead && <span className="research-next-lead">{step.lead}</span>}
          <a
            className="ds-inline-link"
            href={step.href}
            onClick={(event) => {
              if (event.metaKey || event.ctrlKey || event.shiftKey || event.button !== 0) return;
              event.preventDefault();
              followLink(step.href);
            }}
          >
            {step.label}
          </a>
        </span>
      ))}
    </nav>
  );
}
