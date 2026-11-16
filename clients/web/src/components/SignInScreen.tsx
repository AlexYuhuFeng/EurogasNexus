import { useState, type FormEvent } from "react";
import { BRAND_HEX_LOWER, BRAND_HEX_UPPER, BRAND_STROKE, BRAND_WAVE, BrandMark } from "@/components/ui/BrandMark";
import { CLIENT_APPLICATION_VERSION } from "@/app/releaseMetadata";
import { LOCALES } from "@/i18n/locales";
import { devLoginOffered, type AuthStatusSnapshot } from "@/stores/authGate";
import type { AuthState } from "@/stores/workspaceLoading";
import "./SignInScreen.css";

/** Failures of the company SSO path, where checking the identity again can help. */
const SSO_FAILURE_KEYS = new Set([
  "auth.error_sso_failed",
  "auth.sso_unavailable",
  "auth.error_identity_unreachable",
  "auth.error_server_not_configured",
]);

interface SignInScreenProps {
  t: (key: string) => string;
  authState: AuthState;
  authStatus: AuthStatusSnapshot;
  /** i18n key of the last authentication failure; the store localises, the screen renders. */
  authErrorKey: string | null;
  authNoticeKey: string | null;
  authBusy: boolean;
  language: string;
  onLanguageChange: (language: string) => void;
  onOidcSignIn: () => void;
  onDevLogin: (username: string, password: string) => void;
  onRetryIdentity: () => void;
}

export function SignInScreen({
  t,
  authState,
  authStatus,
  authErrorKey,
  authNoticeKey,
  authBusy,
  language,
  onLanguageChange,
  onOidcSignIn,
  onDevLogin,
  onRetryIdentity,
}: SignInScreenProps) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const resolvingIdentity = authState === "unknown";
  // Server-advertised capability only: the form cannot be enabled from the client.
  const devLoginAvailable = devLoginOffered(authStatus);

  function handleDevLoginSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (authBusy) return;
    onDevLogin(username, password);
  }

  // Retrying the identity check helps only when company SSO is configured and has failed; with
  // no sign-in method at all it is the one thing left to try. Otherwise the screen says nothing
  // about SSO.
  const ssoFailing = authStatus.oidcConfigured && authErrorKey !== null && SSO_FAILURE_KEYS.has(authErrorKey);
  const noMethods = !authStatus.oidcConfigured && !devLoginAvailable;
  const retry = (
    <div className="sign-in-retry-row">
      <button type="button" className="sign-in-retry" onClick={onRetryIdentity} disabled={authBusy}>
        {t("auth.retry_identity")}
      </button>
    </div>
  );

  return (
    <div className="sign-in-screen">
      <div className="sign-in-shell">
      <aside className="sign-in-brand" aria-hidden="true">
        <BrandMark variant="wordmark" tone="reverse" size="xl" decorative className="sign-in-brand-lockup" />
        <p className="sign-in-brand-tagline">{t("auth.brand_tagline")}</p>
        {/* The one decoration: the mark itself, very large and faint, cropped by the panel. */}
        <svg
          className="sign-in-brand-watermark"
          viewBox="0 0 32 32"
          fill="none"
          stroke="currentColor"
          strokeWidth={BRAND_STROKE}
          strokeLinejoin="round"
          focusable="false"
        >
          <path d={BRAND_HEX_UPPER} />
          <path d={BRAND_HEX_LOWER} />
          <path d={BRAND_WAVE} />
        </svg>
      </aside>
      <section className="sign-in-card" aria-labelledby="sign-in-title">
        {/* Below 760 px the brand panel folds away; the card carries the lock-up instead. */}
        <BrandMark variant="wordmark" tone="auto" size="lg" className="sign-in-card-lockup" />
        <div className="sign-in-masthead">
          <h1 id="sign-in-title">{t("auth.title")}</h1>
          <select
            aria-label={t("settings.language")}
            value={language}
            onChange={(event) => onLanguageChange(event.target.value)}
          >
            {LOCALES.map((locale) => (
              <option key={locale.code} value={locale.code}>{locale.shortLabel}</option>
            ))}
          </select>
        </div>

        {authNoticeKey && (
          <p className="sign-in-notice" role="status" aria-live="polite">{t(authNoticeKey)}</p>
        )}
        {authErrorKey && (
          <p className="sign-in-error" role="alert">{t(authErrorKey)}</p>
        )}

        {resolvingIdentity ? (
          <div className="sign-in-resolving" role="status" aria-live="polite">
            <strong>{t("auth.resolving_title")}</strong>
            <span>{t("auth.resolving_body")}</span>
          </div>
        ) : (
          <>
            {authStatus.oidcConfigured && (
              <div className="sign-in-sso">
                <button
                  type="button"
                  className="sign-in-primary"
                  onClick={onOidcSignIn}
                  disabled={authBusy}
                >
                  {t("auth.sso_button")}
                </button>
                {ssoFailing && retry}
              </div>
            )}

            {authStatus.oidcConfigured && devLoginAvailable && (
              <div className="sign-in-or" role="separator" aria-label={t("auth.or")}>
                <span aria-hidden="true">{t("auth.or")}</span>
              </div>
            )}

            {devLoginAvailable && (
              <form className="sign-in-dev-form" onSubmit={handleDevLoginSubmit}>
                <span className="sign-in-block-title">{t("auth.dev_title")}</span>
                <label htmlFor="sign-in-username">{t("auth.dev_username")}</label>
                <input
                  id="sign-in-username"
                  name="username"
                  type="text"
                  autoComplete="username"
                  value={username}
                  onChange={(event) => setUsername(event.target.value)}
                  required
                />
                <label htmlFor="sign-in-password">{t("auth.dev_password")}</label>
                <input
                  id="sign-in-password"
                  name="password"
                  type="password"
                  autoComplete="current-password"
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  required
                />
                <button
                  type="submit"
                  className={authStatus.oidcConfigured ? "sign-in-secondary" : "sign-in-primary"}
                  disabled={authBusy}
                >
                  {authBusy ? t("auth.dev_submitting") : t("auth.dev_submit")}
                </button>
              </form>
            )}

            {noMethods && (
              <>
                <p className="sign-in-status" role="status">{t("auth.no_methods")}</p>
                {retry}
              </>
            )}
          </>
        )}

        {/* The client's own version: known without a request, useful when reporting a problem. */}
        <p className="sign-in-version">{t("release.client_version")} {CLIENT_APPLICATION_VERSION}</p>
      </section>
      </div>
    </div>
  );
}
