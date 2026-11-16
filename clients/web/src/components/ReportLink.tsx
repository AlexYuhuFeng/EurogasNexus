/**
 * "Report" beside "Why" on an alert or an outage: opens Research → Reports with a situation
 * report about it prepared (nothing is generated until the user presses Generate).
 */
import { reportSubjectSearch, type ReportSubject } from "@/app/model/reportsModel";

type Translate = (key: string, options?: Record<string, unknown>) => string;

export function ReportLink({ subject, label, t }: { subject: ReportSubject; label: string; t: Translate }) {
  const href = `?${reportSubjectSearch(typeof window === "undefined" ? "" : window.location.search, subject)}`;
  const name = t("reports.link_label", { subject: label });
  return (
    <a
      className="report-link ds-inline-link"
      href={href}
      aria-label={name}
      title={name}
      onClick={(event) => {
        if (event.metaKey || event.ctrlKey || event.shiftKey) return;
        event.preventDefault();
        window.history.pushState({ workspace: "research" }, "", href);
        window.dispatchEvent(new PopStateEvent("popstate"));
      }}
    >
      {t("reports.link")}
    </a>
  );
}
