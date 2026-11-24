import { useCallback, useEffect, useState } from "react";

import { api, type AccessApiKeyDTO } from "@/api/client";
import { Button } from "@/components/ui/Button";

type Translate = (key: string, options?: Record<string, unknown>) => string;

/** A key's state in words, so it never rests on colour alone. */
function keyState(key: AccessApiKeyDTO, now: number): "revoked" | "expired" | "active" {
  if (key.revoked_at_utc) return "revoked";
  if (key.expires_at_utc && Date.parse(key.expires_at_utc) <= now) return "expired";
  return "active";
}

/**
 * The person's own API keys for the Python SDK and scripts. A key acts as its owner, within
 * the owner's data scopes, expires after 90 days, and is shown once. Administrators issue
 * keys for service principals only, so nobody can act as someone else.
 */
export function PersonalApiKeysPanel({ t }: { t: Translate }) {
  const [keys, setKeys] = useState<AccessApiKeyDTO[] | null>(null);
  const [name, setName] = useState("");
  const [issued, setIssued] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    api.myApiKeys().then((response) => setKeys(response.data)).catch(() => setKeys(null));
  }, []);
  useEffect(load, [load]);
  if (keys === null) return null; // a service identity, or the server has no database

  const create = async () => {
    setBusy(true);
    setMessage(null);
    try {
      const response = await api.createMyApiKey({ display_name: name.trim() || "personal" });
      setIssued(response.data.api_key);
      setName("");
      load();
    } catch (caught) {
      setMessage(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setBusy(false);
    }
  };
  const revoke = async (keyId: string) => {
    setMessage(null);
    try {
      await api.revokeMyApiKey(keyId);
      load();
    } catch (caught) {
      setMessage(caught instanceof Error ? caught.message : String(caught));
    }
  };
  const now = Date.now();

  return (
    <section className="personal-api-keys" aria-labelledby="personal-api-keys-title">
      <h3 id="personal-api-keys-title">{t("settings.api_keys.title")}</h3>
      <p className="panel-copy">{t("settings.api_keys.copy")}</p>
      {issued && (
        <div className="personal-api-key-issued" role="status">
          <p>{t("settings.api_keys.copy_now")}</p>
          <code className="personal-api-key-secret">{issued}</code>
          <Button onClick={() => setIssued(null)}>{t("settings.api_keys.done")}</Button>
        </div>
      )}
      <form
        className="personal-api-key-form"
        onSubmit={(event) => {
          event.preventDefault();
          void create();
        }}
      >
        <label>
          <span>{t("settings.api_keys.name")}</span>
          <input value={name} maxLength={128} onChange={(event) => setName(event.target.value)} placeholder="sdk-laptop" />
        </label>
        <Button type="submit" variant="primary" loading={busy}>
          {t("settings.api_keys.create")}
        </Button>
      </form>
      {message && <p className="panel-error" role="alert">{message}</p>}
      {keys.length === 0 ? (
        <p className="panel-copy">{t("settings.api_keys.none")}</p>
      ) : (
        <table className="data-table">
          <thead>
            <tr>
              <th scope="col">{t("settings.api_keys.name")}</th>
              <th scope="col">{t("settings.api_keys.prefix")}</th>
              <th scope="col">{t("settings.api_keys.expires")}</th>
              <th scope="col">{t("settings.api_keys.last_used")}</th>
              <th scope="col">{t("settings.api_keys.state")}</th>
              <th scope="col"><span className="visually-hidden">{t("settings.api_keys.revoke")}</span></th>
            </tr>
          </thead>
          <tbody>
            {keys.map((key) => {
              const state = keyState(key, now);
              return (
                <tr key={key.key_id}>
                  <td>{key.display_name}</td>
                  <td><code>{key.key_prefix}</code></td>
                  <td>{key.expires_at_utc ? key.expires_at_utc.slice(0, 10) : "-"}</td>
                  <td>{key.last_used_at_utc ? key.last_used_at_utc.slice(0, 16).replace("T", " ") + " UTC" : t("settings.api_keys.never")}</td>
                  <td>{t(`settings.api_keys.state_${state}`)}</td>
                  <td>
                    {state === "active" && (
                      <Button variant="danger" onClick={() => void revoke(key.key_id)} aria-label={`${t("settings.api_keys.revoke")}: ${key.display_name}`}>
                        {t("settings.api_keys.revoke")}
                      </Button>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </section>
  );
}
