import { useEffect, useState } from "react";

import { api, type OrganisationSettingsDTO, type PreferenceKey, type PreferencesDTO } from "@/api/client";
import { LOCALES } from "@/i18n/locales";
import { applyEffectivePreferences } from "@/app/preferences/remotePreferences";

type Translate = (key: string, options?: Record<string, unknown>) => string;

const CHOICES: Record<PreferenceKey, { value: string; labelKey?: string; label?: string }[]> = {
  language: LOCALES.map((locale) => ({ value: locale.code, label: locale.nativeName })),
  theme: [
    { value: "system", labelKey: "theme.system" },
    { value: "light", labelKey: "theme.light" },
    { value: "dark", labelKey: "theme.dark" },
  ],
  market_view: [
    { value: "curves", labelKey: "market.view.numeric" },
    { value: "network", labelKey: "market.view.map" },
  ],
  market_board_layout: [
    { value: "board", labelKey: "preferences.layout_board" },
    { value: "ladder", labelKey: "preferences.layout_ladder" },
  ],
};

const LABEL_KEYS: Record<PreferenceKey, string> = {
  language: "settings.language",
  theme: "settings.appearance",
  market_view: "settings.market_default_view",
  market_board_layout: "preferences.board_layout",
};

const KEYS = Object.keys(LABEL_KEYS) as PreferenceKey[];

/** Mirrors BUILT_IN_DEFAULTS in domain/settings/preferences.py. */
const BUILT_IN: Record<PreferenceKey, string> = {
  language: "en",
  theme: "system",
  market_view: "curves",
  market_board_layout: "board",
};

function choiceLabel(t: Translate, key: PreferenceKey, value: string | undefined): string {
  const choice = CHOICES[key].find((item) => item.value === value);
  if (!choice) return t("preferences.built_in");
  return choice.label ?? t(choice.labelKey ?? value ?? "");
}

interface PersonalPreferencesPanelProps {
  t: Translate;
  principalId: string | null;
}

/**
 * The user's own choices, stored on the server per person. Each row shows what the
 * organisation default is, so "Use organisation default" is an informed choice.
 */
export function PersonalPreferencesPanel({ t, principalId }: PersonalPreferencesPanelProps) {
  const [state, setState] = useState<PreferencesDTO | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    api
      .myPreferences()
      .then((response) => live && setState(response.data))
      .catch(() => live && setError(t("preferences.unavailable")));
    return () => {
      live = false;
    };
  }, [t]);

  const save = async (key: PreferenceKey, value: string | null) => {
    try {
      const response = await api.saveMyPreferences({ [key]: value });
      setState(response.data);
      setError(null);
      await applyEffectivePreferences(response.data.effective, principalId);
    } catch {
      setError(t("preferences.save_failed"));
    }
  };

  return (
    <section className="workspace-panel settings-panel settings-personal-panel" aria-labelledby="settings-personal-title">
      <h2 id="settings-personal-title">{t("preferences.personal_title")}</h2>
      <p className="panel-copy">{t("preferences.personal_help")}</p>
      {error && <p className="settings-backend-message" role="alert">{error}</p>}
      {state &&
        KEYS.map((key) => {
          const personal = state.personal[key];
          const options = key === "language"
            ? CHOICES.language.filter((item) => state.effective.enabled_languages.includes(item.value))
            : CHOICES[key];
          return (
            <label key={key} className="settings-preference-row">
              <span>{t(LABEL_KEYS[key])}</span>
              <select
                value={personal ?? ""}
                onChange={(event) => void save(key, event.target.value === "" ? null : event.target.value)}
              >
                <option value="">
                  {t("preferences.use_default", {
                    value: choiceLabel(t, key, state.organisation_defaults[key] ?? state.effective[key]),
                  })}
                </option>
                {options.map((choice) => (
                  <option key={choice.value} value={choice.value}>
                    {choice.label ?? t(choice.labelKey ?? choice.value)}
                  </option>
                ))}
              </select>
            </label>
          );
        })}
      <small className="muted">{t("preferences.follows_you")}</small>
    </section>
  );
}

interface OrganisationDefaultsPanelProps {
  t: Translate;
  canManage: boolean;
}

/** Organisation-wide defaults: editable by platform administrators, visible to everyone. */
export function OrganisationDefaultsPanel({ t, canManage }: OrganisationDefaultsPanelProps) {
  const [settings, setSettings] = useState<OrganisationSettingsDTO | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    api
      .organisationSettings()
      .then((response) => live && setSettings(response.data))
      .catch(() => live && setMessage(t("preferences.unavailable")));
    return () => {
      live = false;
    };
  }, [t]);

  const save = async (patch: OrganisationSettingsDTO) => {
    try {
      const response = await api.saveOrganisationSettings(patch);
      setSettings(response.data);
      setMessage(t("preferences.organisation_saved"));
    } catch {
      setMessage(t("preferences.save_failed"));
    }
  };

  const enabled = settings?.enabled_languages ?? LOCALES.map((locale) => locale.code);

  return (
    <section className="workspace-panel settings-panel settings-organisation-panel" aria-labelledby="settings-organisation-title">
      <h2 id="settings-organisation-title">{t("preferences.organisation_title")}</h2>
      <p className="panel-copy">
        {t(canManage ? "preferences.organisation_help_admin" : "preferences.organisation_help_readonly")}
      </p>
      {settings &&
        KEYS.map((key) => (
          <label key={key} className="settings-preference-row">
            <span>{t(LABEL_KEYS[key])}</span>
            {canManage ? (
              <select value={settings[key] ?? ""} onChange={(event) => void save({ [key]: event.target.value })}>
                {!settings[key] && (
                  <option value="">
                    {choiceLabel(t, key, BUILT_IN[key])} · {t("preferences.built_in")}
                  </option>
                )}
                {CHOICES[key]
                  .filter((choice) => key !== "language" || enabled.includes(choice.value))
                  .map((choice) => (
                    <option key={choice.value} value={choice.value}>
                      {choice.label ?? t(choice.labelKey ?? choice.value)}
                    </option>
                  ))}
              </select>
            ) : (
              <strong>
                {choiceLabel(t, key, settings[key] ?? BUILT_IN[key])}
                {!settings[key] && <small className="muted"> · {t("preferences.built_in")}</small>}
              </strong>
            )}
          </label>
        ))}
      {settings && canManage && (
        <fieldset className="settings-language-set">
          <legend>{t("preferences.enabled_languages")}</legend>
          {LOCALES.map((locale) => (
            <label key={locale.code} className="settings-checkbox">
              <input
                type="checkbox"
                checked={enabled.includes(locale.code)}
                disabled={enabled.length === 1 && enabled.includes(locale.code)}
                onChange={(event) => {
                  const next = event.target.checked
                    ? [...enabled, locale.code]
                    : enabled.filter((code) => code !== locale.code);
                  const language = settings.language && next.includes(settings.language) ? settings.language : next[0];
                  void save({ enabled_languages: next, language });
                }}
              />
              {locale.nativeName}
            </label>
          ))}
        </fieldset>
      )}
      {message && <p className="settings-backend-message" role="status">{message}</p>}
    </section>
  );
}
