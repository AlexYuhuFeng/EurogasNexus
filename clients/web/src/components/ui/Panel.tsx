import { useId, type ReactNode } from "react";

/**
 * A panel (UX-02): a title row with an actions slot, and a body. The title names the panel for
 * assistive technology (the section is labelled by it), and the actions sit on the title's row
 * so a panel never spends a second row on its own controls.
 *
 * It renders the same `workspace-panel` / `panel-title-row` structure the stylesheet and the
 * acceptance sweep already know.
 */
export interface PanelProps {
  title: ReactNode;
  /** Controls for the whole panel: Refresh, export, a view switch. */
  actions?: ReactNode;
  /** Secondary text on the title row: a unit, an as-of time. */
  meta?: ReactNode;
  children: ReactNode;
  className?: string;
  /** Heading level; panels sit under the page title. */
  level?: 2 | 3;
  /** A tooltip on the title: what the panel answers. */
  titleHint?: string;
  id?: string;
}

export function Panel({ title, actions, meta, children, className, level = 2, titleHint, id }: PanelProps) {
  const headingId = useId();
  const Heading = level === 2 ? "h2" : "h3";
  return (
    <section id={id} className={["workspace-panel", "ds-panel", className].filter(Boolean).join(" ")} aria-labelledby={headingId}>
      <div className="panel-title-row ds-panel-head">
        <Heading id={headingId} title={titleHint}>{title}</Heading>
        {meta !== undefined && meta !== null ? <span className="ds-panel-meta">{meta}</span> : null}
        {actions ? <div className="ds-panel-actions">{actions}</div> : null}
      </div>
      <div className="ds-panel-body">{children}</div>
    </section>
  );
}
