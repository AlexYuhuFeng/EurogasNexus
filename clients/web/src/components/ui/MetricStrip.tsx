import type { ReactNode } from "react";

export interface MetricStripItem {
  label: string;
  value: ReactNode;
  detail?: ReactNode;
}

interface MetricStripProps {
  className?: string;
  items: readonly MetricStripItem[];
}

export function MetricStrip({ className, items }: MetricStripProps) {
  return (
    <div className={className ?? "metric-grid"}>
      {items.map((item, index) => (
        <div key={`${item.label}-${index}`}>
          <span>{item.label}</span>
          <strong>{item.value}</strong>
          {item.detail !== undefined && item.detail !== null ? <small>{item.detail}</small> : null}
        </div>
      ))}
    </div>
  );
}
