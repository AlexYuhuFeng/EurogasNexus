import type { ReactNode } from "react";

interface PanelHeaderProps {
  title: ReactNode;
  meta?: ReactNode;
  className?: string;
}

export function PanelHeader({ title, meta, className }: PanelHeaderProps) {
  const classes = ["panel-title-row", className].filter(Boolean).join(" ");
  return (
    <div className={classes}>
      <h2>{title}</h2>
      {meta !== undefined && meta !== null ? <span>{meta}</span> : null}
    </div>
  );
}
