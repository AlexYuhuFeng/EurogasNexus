/**
 * Settings → Organisation → AI (administrators): the one switch for every AI feature, what the
 * model may be sent, and the model the installation is configured to call (small-desk plan 3.6).
 *
 * Shown plainly: whether AI is on, which provider and model, whether the model is on the firm's
 * own network, the time limits, and each data category with its own switch (all off until an
 * administrator allows them). Turning AI or a category on is a security-relevant change and
 * waits for a second administrator where four eyes are required; turning it off takes effect at
 * once. The endpoint itself is installation configuration (EUROGAS_NEXUS_LLM_*), named here.
 */
import { useCallback, useEffect, useState } from "react";

import { api, type AiSettingsDTO } from "@/api/client";

type Translate = (key: string, options?: Record<string, unknown>) => string;

export function AiSettingsPanel({ t }: { t: Translate }) {
  const [settings, setSettings] = useState<AiSettingsDTO | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const read = useCallback(async () => {
    try {
      const response = await api.aiSettings();
      setSettings(response.data);
      return response.data;
    } catch {
      setMessage(t("preferences.unavailable"));
      return null;
    }
  }, [t]);

  useEffect(() => {
    void read();
  }, [read]);

  const save = async (patch: { ai_enabled?: boolean; ai_data_sharing?: Record<string, boolean> }) => {
    setBusy(true);
    try {
      await api.saveAiSettings(patch);
      const now = await read();
      const applied =
        now !== null &&
        (patch.ai_enabled === undefined || now.enabled === patch.ai_enabled) &&
        Object.entries(patch.ai_data_sharing ?? {}).every(([key, value]) => now.sharing[key] === value);
      setMessage(t(applied ? "preferences.organisation_saved" : "ai.settings.pending"));
    } catch {
      setMessage(t("preferences.save_failed"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="workspace-panel settings-panel settings-ai-panel" aria-labelledby="settings-ai-title" data-ai-settings="">
      <h2 id="settings-ai-title">{t("ai.settings.title")}</h2>
      <p className="panel-copy">{t("ai.settings.help")}</p>
      {settings && (
        <>
          <label className="settings-checkbox">
            <input
              type="checkbox"
              checked={settings.enabled}
              disabled={busy}
              data-ai-master=""
              onChange={(event) => void save({ ai_enabled: event.target.checked })}
            />
            {t("ai.settings.master")}
          </label>
          <p className="settings-preference-hint" data-ai-state={settings.reason}>
            {t(`ai.state.${settings.reason}`)}
          </p>
          <dl className="settings-ai-facts">
            <dt>{t("ai.settings.provider")}</dt>
            <dd>
              {settings.provider
                ? `${settings.provider.name} · ${settings.provider.model}${settings.provider.self_hosted ? ` · ${t("ai.settings.self_hosted")}` : ""}`
                : t("ai.settings.no_provider")}
            </dd>
            <dt>{t("ai.settings.timeouts")}</dt>
            <dd>{t("ai.settings.timeouts_value", { interactive: settings.timeouts_seconds.interactive, draft: settings.timeouts_seconds.draft })}</dd>
          </dl>
          <p className="settings-preference-hint">{t("ai.settings.endpoint_help")}</p>
          <fieldset className="settings-language-set">
            <legend>{t("ai.settings.sharing")}</legend>
            {settings.sharing_categories.map((row) => (
              <label key={row.category} className="settings-checkbox">
                <input
                  type="checkbox"
                  checked={row.allowed}
                  disabled={busy}
                  data-ai-sharing={row.category}
                  onChange={(event) => void save({ ai_data_sharing: { [row.category]: event.target.checked } })}
                />
                {t(`ai.sharing.${row.category}`)}
              </label>
            ))}
            <p className="settings-preference-hint">{t("ai.settings.sharing_help")}</p>
          </fieldset>
        </>
      )}
      {message && <p className="settings-backend-message" role="status">{message}</p>}
    </section>
  );
}
