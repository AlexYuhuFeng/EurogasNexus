/**
 * Canonical Inspector panel (Architecture V2 Wave 9).
 *
 * Object detail belongs in one Inspector instead of a new top-level page per
 * object kind. The panel renders the *selection* the shell already holds - object
 * kind, reference, label, the page the selection came from - together with the
 * detail Wave 9 resolves from data the surface already received. It performs no
 * fetch of its own, so it cannot become a second entitlement path: what the caller
 * may see was already authorised when the surface loaded it.
 *
 * It is a view of facts, not an authority: every value is shown as the backend
 * reported it, a field the record does not carry is absent rather than zero, and a
 * kind this build cannot resolve says so instead of rendering an empty panel.
 *
 * Accessibility: a labelled complementary region with a close control, and the
 * current object announced politely when it changes.
 */

import type { InspectorSubject } from "@/app/experience/inspectorContract";
import type { InspectorDetail } from "@/app/model/inspectorDetail";

interface InspectorPanelProps {
  subject: InspectorSubject;
  detail: InspectorDetail;
  canGoBack: boolean;
  t: (key: string, options?: Record<string, unknown>) => string;
  onClose: () => void;
  onBack: () => void;
}

export function InspectorPanel({
  subject,
  detail,
  canGoBack,
  t,
  onClose,
  onBack,
}: InspectorPanelProps) {
  return (
    <aside
      className="inspector-panel"
      data-shell-region="inspector"
      aria-label={t("experience.inspector.title")}
    >
      <header className="inspector-panel-header">
        <div>
          <span className="eyebrow">{t(`experience.inspect.${subject.kind}`)}</span>
          <h2>{detail.label ?? subject.label}</h2>
        </div>
        <div className="inspector-panel-actions">
          {canGoBack && (
            <button type="button" onClick={onBack}>
              {t("experience.inspector.back")}
            </button>
          )}
          <button type="button" aria-label={t("experience.inspector.close")} onClick={onClose}>
            ×
          </button>
        </div>
      </header>
      <dl className="inspector-panel-facts">
        <div>
          <dt>{t("experience.inspector.ref")}</dt>
          <dd>
            <code>{subject.ref}</code>
          </dd>
        </div>
        <div>
          <dt>{t("experience.inspector.origin")}</dt>
          <dd>{t(`nav.${subject.originPage}`)}</dd>
        </div>
        {detail.facts.map((fact) => (
          <div key={fact.labelKey}>
            <dt>{t(fact.labelKey)}</dt>
            <dd>{fact.value}</dd>
          </div>
        ))}
      </dl>
      {detail.evidenceRefs.length > 0 && (
        <section className="inspector-panel-evidence" aria-label={t("experience.inspector.evidence")}>
          <h3>{t("experience.inspector.evidence")}</h3>
          <ul>
            {detail.evidenceRefs.map((ref) => (
              <li key={ref}>
                <code>{ref}</code>
              </li>
            ))}
          </ul>
        </section>
      )}
      <p className="inspector-panel-note" aria-live="polite">
        {detail.resolved
          ? t("experience.inspector.note")
          : t("experience.inspector.unresolved")}
      </p>
    </aside>
  );
}
