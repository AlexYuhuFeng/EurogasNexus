import type { ReactNode } from "react";

interface PanelHeaderProps {
  title: ReactNode;
  meta?: ReactNode;
  /** Controls on the title row (see Panel). */
  actions?: ReactNode;
  className?: string;
  /** Lets a section be labelled by its heading (`aria-labelledby`). */
  headingId?: string;
}

export function PanelHeader({ title, meta, actions, className, headingId }: PanelHeaderProps) {
  const classes = ["panel-title-row", className].filter(Boolean).join(" ");
  return (
    <div className={classes}>
      <h2 id={headingId}>{title}</h2>
      {meta !== undefined && meta !== null ? <span>{meta}</span> : null}
      {actions ? <div className="ds-panel-actions">{actions}</div> : null}
    </div>
  );
}
