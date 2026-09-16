import type { ReactNode } from "react";
import "./EvidenceBlock.css";

export interface EvidenceBlockItem {
  label: ReactNode;
  value: ReactNode;
  detail?: ReactNode;
  wide?: boolean;
}

interface EvidenceBlockProps {
  items: readonly EvidenceBlockItem[];
  className?: string;
  ariaLabel?: string;
}

export function EvidenceBlock({
  items,
  className,
  ariaLabel,
}: EvidenceBlockProps) {
  const classes = ["evidence-block", className].filter(Boolean).join(" ");
  return (
    <dl className={classes} aria-label={ariaLabel}>
      {items.map((item, index) => (
        <div
          key={index}
          className={item.wide ? "evidence-block-item wide" : "evidence-block-item"}
        >
          <dt>{item.label}</dt>
          <dd>
            <strong>{item.value}</strong>
            {item.detail !== undefined && <small>{item.detail}</small>}
          </dd>
        </div>
      ))}
    </dl>
  );
}
