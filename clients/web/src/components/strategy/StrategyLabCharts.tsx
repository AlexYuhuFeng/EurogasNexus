import { useId } from "react";

export interface StrategyChartPoint {
  label: string;
  value: number;
}

interface StrategyLineChartProps {
  points: StrategyChartPoint[];
  title: string;
  unit: string;
  height?: number;
  valueFormatter?: (value: number) => string;
}

function defaultFormatter(value: number): string {
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toLocaleString(undefined, { maximumFractionDigits: 2 })}`;
}

export function StrategyLineChart({
  points,
  title,
  unit,
  height = 180,
  valueFormatter = defaultFormatter,
}: StrategyLineChartProps) {
  const gradientId = useId();
  if (points.length === 0) {
    return (
      <div className="strategy-chart strategy-chart-empty" role="img" aria-label={`${title}: no series`}>
        <span>No persisted series</span>
      </div>
    );
  }
  const width = 920;
  const padding = { top: 12, right: 16, bottom: 22, left: 58 };
  const values = points.map((point) => point.value);
  const minValue = Math.min(0, ...values);
  const maxValue = Math.max(0, ...values);
  const range = Math.max(1, maxValue - minValue);
  const xFor = (index: number) =>
    padding.left +
    (points.length === 1 ? 0 : index * ((width - padding.left - padding.right) / (points.length - 1)));
  const yFor = (value: number) =>
    padding.top + (maxValue - value) * ((height - padding.top - padding.bottom) / range);
  const path = points
    .map((point, index) => `${index === 0 ? "M" : "L"}${xFor(index).toFixed(1)},${yFor(point.value).toFixed(1)}`)
    .join(" ");
  const area = points.length > 1
    ? `${path} L${xFor(points.length - 1).toFixed(1)},${height - padding.bottom} L${padding.left},${height - padding.bottom} Z`
    : "";
  const summary = `${title}. ${points.length} points. Last ${valueFormatter(points[points.length - 1].value)} ${unit}.`;
  return (
    <figure className="strategy-chart" aria-label={summary}>
      <figcaption>{title}</figcaption>
      <svg
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-label={summary}
        preserveAspectRatio="none"
      >
        <defs>
          <linearGradient id={gradientId} x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" stopColor="currentColor" stopOpacity="0.18" />
            <stop offset="100%" stopColor="currentColor" stopOpacity="0.02" />
          </linearGradient>
        </defs>
        <line x1={padding.left} x2={width - padding.right} y1={yFor(0)} y2={yFor(0)} className="strategy-chart-zero" />
        {area && <path d={area} fill={`url(#${gradientId})`} className="strategy-chart-area" />}
        <path d={path} className="strategy-chart-line" />
        {points.map((point, index) => (
          <circle
            key={`${point.label}-${index}`}
            cx={xFor(index)}
            cy={yFor(point.value)}
            r={points.length > 60 ? 1.2 : 2.2}
            className="strategy-chart-point"
          >
            <title>{`${point.label}: ${valueFormatter(point.value)} ${unit}`}</title>
          </circle>
        ))}
        <text x={padding.left} y={height - 6} className="strategy-chart-axis">
          {points[0].label}
        </text>
        <text x={width - padding.right} y={height - 6} textAnchor="end" className="strategy-chart-axis">
          {points[points.length - 1].label}
        </text>
        <text x={padding.left - 8} y={padding.top + 4} textAnchor="end" className="strategy-chart-axis">
          {valueFormatter(maxValue)}
        </text>
        <text x={padding.left - 8} y={height - padding.bottom + 4} textAnchor="end" className="strategy-chart-axis">
          {valueFormatter(minValue)}
        </text>
      </svg>
    </figure>
  );
}
