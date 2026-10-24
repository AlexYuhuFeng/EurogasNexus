export interface StrategyChartPoint {
  label: string;
  value: number | null | undefined;
}

export function isChartValue(value: StrategyChartPoint["value"]): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

// Keep the original positions: removing missing observations would join across gaps.
export function chartLinePath(
  points: StrategyChartPoint[],
  xFor: (index: number) => number,
  yFor: (value: number) => number,
): string {
  let connected = false;
  return points.map((point, index) => {
    if (!isChartValue(point.value)) {
      connected = false;
      return "";
    }
    const command = connected ? "L" : "M";
    connected = true;
    return `${command}${xFor(index).toFixed(1)},${yFor(point.value).toFixed(1)}`;
  }).filter(Boolean).join(" ");
}

// Filled PnL/drawdown area measures distance from the actual zero line.
export function chartAreaPath(
  points: StrategyChartPoint[],
  xFor: (index: number) => number,
  yFor: (value: number) => number,
): string {
  if (points.length < 2 || points.some((point) => !isChartValue(point.value))) return "";
  const baseline = yFor(0).toFixed(1);
  return `${chartLinePath(points, xFor, yFor)} L${xFor(points.length - 1).toFixed(1)},${baseline} L${xFor(0).toFixed(1)},${baseline} Z`;
}
