/**
 * Pure parts of the shell's data-problem surfaces (TopBarStatus, DataProblemNotice): how many
 * things are affected, the identity of a set of problems, and the one-line naming of them.
 */
import type { EndpointFailureSurface } from "./endpointFailures";

type Translate = (key: string, options?: Record<string, unknown>) => string;

/** How many things the panel lists as affected: the indicator's count. */
export function dataProblemCount({
  endpointFailures,
  staleFigures,
  sourceIssues,
}: {
  endpointFailures: number;
  staleFigures: number;
  sourceIssues: number;
}): number {
  return endpointFailures + staleFigures + sourceIssues;
}

/** The identity of a set of problems: its affected reads, sorted. */
export function problemSignature(failures: EndpointFailureSurface | null | undefined): string {
  return (failures?.entries ?? [])
    .map((entry) => entry.key)
    .concat(failures && failures.hiddenCount > 0 ? [`+${failures.hiddenCount}`] : [])
    .sort()
    .join("|");
}

/** The affected reads named in one line: three names, then "and N more". */
export function noticeNames(failures: EndpointFailureSurface, t: Translate): string {
  const labels = failures.entries.map((entry) => entry.label);
  const shown = labels.slice(0, 3).join(", ");
  const more = failures.total - Math.min(3, labels.length);
  return more > 0 ? t("status.notice_more", { names: shown, count: more }) : shown;
}

