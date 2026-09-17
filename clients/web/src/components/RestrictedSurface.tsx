/**
 * Restricted control-plane surface (Architecture V2 Wave 3).
 *
 * Architecture V2 section 8 of `06_IDENTITY_ACCESS_CONTROL_PLANE.md` makes
 * administration a distinct product surface and states that normal business
 * users should not navigate through those controls. The shell therefore hides
 * the administration primary for an identity without an administration
 * capability, and refuses a deep link into it.
 *
 * This component is *presentation only*: it explains the refusal and points at
 * what the identity can still do. It is not a security boundary - the backend
 * refuses the same requests independently - and it exposes no control that would
 * imply otherwise.
 */

interface RestrictedSurfaceProps {
  t: (key: string) => string;
}

export function RestrictedSurface({ t }: RestrictedSurfaceProps) {
  return (
    <section
      className="workspace-page restricted-surface"
      id="workspace-active-panel"
      role="alert"
      data-restricted-surface="true"
      aria-label={t("restricted.title")}
    >
      <header className="workspace-page-header">
        <div className="workspace-page-heading">
          <span className="eyebrow">{t("restricted.eyebrow")}</span>
          <h1>{t("restricted.title")}</h1>
        </div>
      </header>
      <p className="restricted-surface-body">{t("restricted.body")}</p>
      <p className="restricted-surface-note">{t("restricted.note")}</p>
    </section>
  );
}
