/**
 * The line under the top bar when data does not load (docs/product/UX_REFERENCE.md, "Problems
 * are listed, not pinned").
 *
 * - Reads that did not load: shown once per set of problems in a session, in one line that names
 *   them, with Retry, Details (the status panel) and Dismiss. Dismissing is remembered for the
 *   session until the set changes (a new read failing, or one recovering, is a new set).
 * - The data store not answering is critical: it stays, cannot be dismissed, and says what it
 *   means for the figures. Losing the sign-in returns to the sign-in screen (the auth gate).
 *
 * The status indicator on the bar keeps the count and the full list either way.
 */
import { useEffect, useState } from "react";
import { Button, IconButton } from "@/components/ui";
import type { EndpointFailureSurface, EndpointRetrySurface } from "@/app/model/endpointFailures";
import { OPEN_DATA_STATUS_EVENT } from "./TopBarStatus";

type Translate = (key: string, options?: Record<string, unknown>) => string;

export const DISMISSED_PROBLEMS_STORAGE_KEY = "eurogas.data_problems.dismissed";

/** The identity of a set of problems: its affected reads, sorted. */
export function problemSignature(failures: EndpointFailureSurface | null | undefined): string {
  return (failures?.entries ?? [])
    .map((entry) => entry.key)
    .concat(failures && failures.hiddenCount > 0 ? [`+${failures.hiddenCount}`] : [])
    .sort()
    .join("|");
}

function readDismissed(): string | null {
  try {
    return window.sessionStorage.getItem(DISMISSED_PROBLEMS_STORAGE_KEY);
  } catch {
    return null;
  }
}

function writeDismissed(signature: string): void {
  try {
    window.sessionStorage.setItem(DISMISSED_PROBLEMS_STORAGE_KEY, signature);
  } catch {
    // Private window: the dismissal holds until the page reloads.
  }
}

/** The affected reads named in one line: three names, then "and N more". */
export function noticeNames(failures: EndpointFailureSurface, t: Translate): string {
  const labels = failures.entries.map((entry) => entry.label);
  const shown = labels.slice(0, 3).join(", ");
  const more = failures.total - Math.min(3, labels.length);
  return more > 0 ? t("status.notice_more", { names: shown, count: more }) : shown;
}

export function DataProblemNotice({
  t,
  failures,
  retry,
  onRetry,
  storeDown,
}: {
  t: Translate;
  failures: EndpointFailureSurface;
  retry: EndpointRetrySurface;
  onRetry: () => void;
  /** The runtime store does not answer: blocking, not dismissible. */
  storeDown: boolean;
}) {
  const signature = problemSignature(failures);
  const [dismissed, setDismissed] = useState<string | null>(readDismissed);
  useEffect(() => {
    // A set that clears and comes back is new again.
    if (!signature && dismissed) setDismissed(null);
  }, [signature, dismissed]);

  if (storeDown) {
    return (
      <div className="data-problem-notice is-critical" role="alert" data-problem-notice="store">
        <p>{t("status.store_down")}</p>
        <Button size="sm" variant="secondary" loading={retry.busy} onClick={onRetry}>
          {retry.busy ? t("workspace.retry_in_progress") : t("workspace.retry_failed")}
        </Button>
      </div>
    );
  }
  if (!signature || dismissed === signature) return null;
  return (
    <div className="data-problem-notice" role="status" aria-live="polite" data-problem-notice="reads">
      <p>{t("status.notice_reads", { names: noticeNames(failures, t) })}</p>
      <div className="data-problem-notice-actions">
        <Button size="sm" variant="secondary" loading={retry.busy} onClick={onRetry}>
          {retry.busy ? t("workspace.retry_in_progress") : t("workspace.retry_failed")}
        </Button>
        <Button size="sm" variant="quiet" onClick={() => window.dispatchEvent(new Event(OPEN_DATA_STATUS_EVENT))}>
          {t("status.notice_details")}
        </Button>
        <IconButton
          label={t("status.notice_dismiss")}
          icon="×"
          size="sm"
          variant="quiet"
          onClick={() => {
            writeDismissed(signature);
            setDismissed(signature);
          }}
        />
      </div>
    </div>
  );
}
