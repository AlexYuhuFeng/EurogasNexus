import { useState, type FormEvent } from "react";

import { api, type MfaEnrolmentDTO } from "@/api/client";
import { Button } from "@/components/ui/Button";
import { Field } from "@/components/ui/Field";
import { Panel } from "@/components/ui/Panel";

interface MfaEnrolmentProps {
  t: (key: string) => string;
  onDone: () => void;
  onSignOut: () => void;
}

/**
 * Setting up a second factor (security review H6). Shown when the installation's policy
 * requires one and this person has none yet: the server answers nothing else until they enrol.
 * Three steps: a secret for the authenticator app, a code to confirm it, then the recovery
 * codes, shown once.
 */
export function MfaEnrolment({ t, onDone, onSignOut }: MfaEnrolmentProps) {
  const [secret, setSecret] = useState<MfaEnrolmentDTO | null>(null);
  const [code, setCode] = useState("");
  const [recoveryCodes, setRecoveryCodes] = useState<string[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [errorKey, setErrorKey] = useState<string | null>(null);

  async function begin() {
    setBusy(true);
    setErrorKey(null);
    try {
      setSecret((await api.enrolMfa()).data);
    } catch {
      setErrorKey("auth.mfa_enrol_failed");
    } finally {
      setBusy(false);
    }
  }

  async function confirm(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy || !code.trim()) return;
    setBusy(true);
    setErrorKey(null);
    try {
      setRecoveryCodes((await api.confirmMfa(code.trim())).data.recovery_codes);
    } catch (error) {
      setErrorKey(String(error).includes("mfa_code_invalid") ? "auth.mfa_code_invalid" : "auth.mfa_enrol_failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="mfa-enrolment" aria-labelledby="mfa-enrolment-title">
      <Panel title={<span id="mfa-enrolment-title">{t("auth.mfa_enrol_title")}</span>}>
        {recoveryCodes ? (
          <>
            <p>{t("auth.mfa_recovery_codes_intro")}</p>
            <ul className="mfa-recovery-codes" aria-label={t("auth.mfa_recovery_codes_label")}>
              {recoveryCodes.map((item) => (
                <li key={item}><code>{item}</code></li>
              ))}
            </ul>
            <Button variant="primary" size="md" onClick={onDone}>{t("auth.mfa_enrol_done")}</Button>
          </>
        ) : secret ? (
          <form onSubmit={confirm} noValidate>
            <p>{t("auth.mfa_enrol_scan")}</p>
            <p><code className="mfa-secret">{secret.secret}</code></p>
            <p className="mfa-uri"><a href={secret.otpauth_uri}>{t("auth.mfa_enrol_open_app")}</a></p>
            <Field label={t("auth.mfa_code_label")} error={errorKey ? t(errorKey) : undefined}>
              <input
                name="one-time-code"
                type="text"
                inputMode="numeric"
                autoComplete="one-time-code"
                maxLength={8}
                value={code}
                onChange={(event) => setCode(event.target.value)}
              />
            </Field>
            <Button type="submit" variant="primary" size="md" loading={busy} disabled={!code.trim()}>
              {t("auth.mfa_enrol_confirm")}
            </Button>
          </form>
        ) : (
          <>
            <p>{t("auth.mfa_enrol_intro")}</p>
            {errorKey && <p role="alert">{t(errorKey)}</p>}
            <Button variant="primary" size="md" loading={busy} onClick={() => void begin()}>
              {t("auth.mfa_enrol_start")}
            </Button>
          </>
        )}
        <Button variant="quiet" size="md" onClick={onSignOut}>{t("auth.mfa_sign_out")}</Button>
      </Panel>
    </main>
  );
}
