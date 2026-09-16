import { useState, type FormEvent } from "react";
import { devLoginOffered, type AuthStatusSnapshot } from "@/stores/authGate";
import type { AuthState } from "@/stores/workspaceLoading";
import "./SignInScreen.css";

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

  return (
    <div className="sign-in-screen">
      <section className="sign-in-card" aria-labelledby="sign-in-title">
        <div className="sign-in-masthead">
          <span className="eyebrow">{t("auth.eyebrow")}</span>
          <select
            aria-label={t("settings.language")}
            value={language}
            onChange={(event) => onLanguageChange(event.target.value)}
          >
            <option value="en">EN</option>
            <option value="zh-CN">{t("settings.chinese")}</option>
          </select>
        </div>

        <h1 id="sign-in-title">{t("auth.title")}</h1>
        <p className="sign-in-body">{t("auth.body")}</p>

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
            {authStatus.oidcConfigured ? (
              <div className="sign-in-block">
                <span className="sign-in-block-title">{t("auth.sso_title")}</span>
                <button
                  type="button"
                  className="sign-in-primary"
                  onClick={onOidcSignIn}
                  disabled={authBusy}
                >
                  {t("auth.sso_button")}
                </button>
              </div>
            ) : (
              <p className="sign-in-status" role="status">
                {t(devLoginAvailable ? "auth.sso_unavailable" : "auth.no_methods")}
              </p>
            )}

            <div className="sign-in-retry-row">
              <button type="button" className="sign-in-retry" onClick={onRetryIdentity} disabled={authBusy}>
                {t("auth.retry_identity")}
              </button>
            </div>

            {devLoginAvailable && (
              <form className="sign-in-block sign-in-dev-form" onSubmit={handleDevLoginSubmit}>
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

          </>
        )}

      </section>
    </div>
  );
}
