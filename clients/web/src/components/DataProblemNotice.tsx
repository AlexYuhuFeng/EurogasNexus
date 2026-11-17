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
import { noticeNames, problemSignature } from "@/app/model/dataProblems";

export { noticeNames, problemSignature };

type Translate = (key: string, options?: Record<string, unknown>) => string;

export const DISMISSED_PROBLEMS_STORAGE_KEY = "eurogas.data_problems.dismissed";

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
