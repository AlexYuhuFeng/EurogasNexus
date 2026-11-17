/**
 * An instant on screen: a `<time>` in the reader's zone with the zone named ("00:57 CET"), the full
 * instant as its tooltip and the UTC instant as `dateTime` (app/time/timeFormat.ts).
 */
import { useInstantFormatter } from "@/app/time/useInstant";

export function Instant({
  value,
  seconds,
  date,
  fallback = "–",
  prefix,
  className,
}: {
  value: string | number | Date | null | undefined;
  seconds?: boolean;
  date?: "auto" | "always" | "never";
  fallback?: string;
  /** Words before the time inside the same element ("as of"). */
  prefix?: string;
  className?: string;
}) {
  const format = useInstantFormatter();
  const shown = format(value, { seconds, date });
  if (!shown) return <span className={className}>{fallback}</span>;
  return (
    <time className={className} dateTime={shown.iso} title={shown.title}>
      {prefix ? `${prefix} ` : ""}
      {shown.text}
    </time>
  );
}
