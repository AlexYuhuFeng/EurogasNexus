/**
 * Canonical Inspector panel (Architecture V2 Wave 9).
 *
 * Object detail belongs in one Inspector instead of a new top-level page per
 * object kind. The panel renders the *selection* the shell already holds: object
 * kind, reference, label and the page the selection came from. It performs no
 * fetch of its own, so it cannot become a second entitlement path - what the
 * caller may see was already authorised when the surface loaded it.
 *
 * Accessibility: a labelled complementary region with a close control, and the
 * current object announced politely when it changes.
 */

import type { InspectorSubject } from "@/app/experience/inspectorContract";

interface InspectorPanelProps {
  subject: InspectorSubject;
  canGoBack: boolean;
  t: (key: string, options?: Record<string, unknown>) => string;
  onClose: () => void;
  onBack: () => void;
}

export function InspectorPanel({ subject, canGoBack, t, onClose, onBack }: InspectorPanelProps) {
  return (
    <aside
      className="inspector-panel"
      data-shell-region="inspector"
      aria-label={t("experience.inspector.title")}
    >
      <header className="inspector-panel-header">
        <div>
          <span className="eyebrow">{t(`experience.inspect.${subject.kind}`)}</span>
          <h2>{subject.label}</h2>
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
      </dl>
      <p className="inspector-panel-note" aria-live="polite">
        {t("experience.inspector.note")}
      </p>
    </aside>
  );
}
