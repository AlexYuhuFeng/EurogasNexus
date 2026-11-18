import { useEffect, useState } from "react";

import { api, type OrganisationSettingsDTO, type PreferenceKey, type PreferencesDTO } from "@/api/client";
import { LOCALES } from "@/i18n/locales";
import { applyEffectivePreferences } from "@/app/preferences/remotePreferences";
import { FOCUS_HUB_CHOICES, MAX_FOCUS_HUBS, STRIP_BUILT_IN, STRIP_CHOICES } from "@/app/preferences/stripPreferences";
import { PanelHelp } from "@/components/ui/PanelHelp";
import { useTranslation } from "react-i18next";
import { formatInstant, TIME_ZONE_PREFERENCES } from "@/app/time/timeFormat";
import { ENERGY_UNITS, REPORTING_CURRENCIES } from "@/app/time/valueFormat";

type Translate = (key: string, options?: Record<string, unknown>) => string;

/** Keys chosen from a closed list (the focus hubs and the hide list are edited differently). */
type ChoiceKey = Exclude<PreferenceKey, "strip_focus_hubs" | "strip_hidden">;

const stripChoices = (key: keyof typeof STRIP_CHOICES, labelKey: string) =>
  STRIP_CHOICES[key].map((value) => ({ value, labelKey, labelValue: value }));

const CHOICES: Record<ChoiceKey, { value: string; labelKey?: string; label?: string; labelValue?: string }[]> = {
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
  pnl_colors: [
    { value: "green_up", labelKey: "preferences.pnl_green_up" },
    { value: "red_up", labelKey: "preferences.pnl_red_up" },
  ],
  time_zone: [
    { value: "device", labelKey: "preferences.time_zone.device" },
    { value: "utc", labelKey: "preferences.time_zone.utc" },
    { value: "market", labelKey: "preferences.time_zone.market" },
  ],
  reporting_currency: REPORTING_CURRENCIES.map((code) => ({ value: code, label: code })),
  // Unit symbols are written the same in every language; only the therm is a word.
  energy_unit: ENERGY_UNITS.map((unit) => (unit === "th" ? { value: unit, labelKey: "preferences.energy_unit.th" } : { value: unit, label: unit })),
  strip_outage_gwh_d: stripChoices("strip_outage_gwh_d", "strip.pref.gwh_value"),
  strip_outage_share_pct: stripChoices("strip_outage_share_pct", "strip.pref.pct_value"),
  strip_price_move_pct: stripChoices("strip_price_move_pct", "strip.pref.pct_value"),
  strip_quiet_line: [
    { value: "on", labelKey: "strip.pref.quiet_on" },
    { value: "off", labelKey: "strip.pref.quiet_off" },
  ],
};

const LABEL_KEYS: Record<ChoiceKey, string> = {
  language: "settings.language",
  theme: "settings.appearance",
  market_view: "settings.market_default_view",
  market_board_layout: "preferences.board_layout",
  pnl_colors: "preferences.pnl_colors",
  time_zone: "preferences.time_zone",
  reporting_currency: "preferences.reporting_currency",
  energy_unit: "preferences.energy_unit",
  strip_outage_gwh_d: "strip.pref.outage_gwh_d",
  strip_outage_share_pct: "strip.pref.outage_share_pct",
  strip_price_move_pct: "strip.pref.price_move_pct",
  strip_quiet_line: "strip.pref.quiet_line",
};

const GENERAL_KEYS: ChoiceKey[] = ["language", "theme", "time_zone", "market_view", "market_board_layout", "pnl_colors"];
/** Currency and units (design basis G2): the secondary value beside native figures, never the price itself. */
const DISPLAY_KEYS: ChoiceKey[] = ["reporting_currency", "energy_unit"];
/** The situational strip's thresholds (role-first redesign §5.2), grouped under their own heading. */
const STRIP_KEYS: ChoiceKey[] = ["strip_outage_gwh_d", "strip_outage_share_pct", "strip_price_move_pct", "strip_quiet_line"];
const KEYS: ChoiceKey[] = [...GENERAL_KEYS, ...DISPLAY_KEYS, ...STRIP_KEYS];

/** Mirrors BUILT_IN_DEFAULTS in domain/settings/preferences.py. */
const BUILT_IN: Record<ChoiceKey, string> = {
  language: "en",
  theme: "system",
  market_view: "curves",
  market_board_layout: "board",
  pnl_colors: "green_up",
  time_zone: "device",
  reporting_currency: "EUR",
  energy_unit: "MWh",
  strip_outage_gwh_d: STRIP_BUILT_IN.strip_outage_gwh_d,
  strip_outage_share_pct: STRIP_BUILT_IN.strip_outage_share_pct,
  strip_price_move_pct: STRIP_BUILT_IN.strip_price_move_pct,
  strip_quiet_line: STRIP_BUILT_IN.strip_quiet_line,
};

function optionLabel(t: Translate, choice: { value: string; labelKey?: string; label?: string; labelValue?: string }): string {
  if (choice.label) return choice.label;
  return t(choice.labelKey ?? choice.value, choice.labelValue !== undefined ? { value: choice.labelValue } : undefined);
}

function choiceLabel(t: Translate, key: ChoiceKey, value: string | undefined): string {
  const choice = CHOICES[key].find((item) => item.value === value);
  if (!choice) return t("preferences.built_in");
  return optionLabel(t, choice);
}

/** The same instant in the three zones, so the choice is concrete ("00:57 CET / 23:57 UTC"). */
function TimeZonePreview({ t }: { t: Translate }) {
  const { i18n } = useTranslation();
  const now = Date.now();
  const shown = TIME_ZONE_PREFERENCES.map((preference) => ({
    preference,
    text: formatInstant(now, { language: i18n.language, preference, nowMs: now })?.text ?? "",
  }));
  return (
    <p className="settings-preference-hint" data-time-zone-preview="">
      {t("preferences.time_zone.preview")}{" "}
      {shown.map((item, index) => (
        <span key={item.preference}>
          {index > 0 ? " · " : ""}
          <strong>{item.text}</strong>
        </span>
      ))}
    </p>
  );
}

/** The person's focus hubs: a set of toggles; none chosen means "the hubs of my book". */
function FocusHubsField({
  t,
  value,
  fallback,
  onChange,
}: {
  t: Translate;
  value: string | undefined;
  fallback: string;
  onChange: (next: string | null) => void;
}) {
  const chosen = (value ?? "").split(",").filter(Boolean);
  const toggle = (hub: string) => {
    const next = chosen.includes(hub) ? chosen.filter((item) => item !== hub) : [...chosen, hub];
    onChange(next.length ? next.join(",") : null);
  };
  return (
    <fieldset className="settings-focus-hubs" data-preference="strip_focus_hubs">
      <legend>{t("strip.pref.focus_hubs")}</legend>
      <div className="settings-focus-hub-set">
        {FOCUS_HUB_CHOICES.map((hub) => {
          const on = chosen.includes(hub);
          return (
            <button
              key={hub}
              type="button"
              className={on ? "settings-hub-toggle is-on" : "settings-hub-toggle"}
              aria-pressed={on}
              disabled={!on && chosen.length >= MAX_FOCUS_HUBS}
              onClick={() => toggle(hub)}
            >
              {hub}
            </button>
          );
        })}
      </div>
      <small className="muted">
        {chosen.length
          ? t("strip.pref.focus_hubs_chosen")
          : t("strip.pref.focus_hubs_auto", { value: fallback || t("strip.pref.focus_hubs_book") })}
      </small>
    </fieldset>
  );
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
      <PanelHelp text={t("preferences.personal_help")} label={t("panel.how_to_read")} />
      {error && <p className="settings-backend-message" role="alert">{error}</p>}
      {state &&
        KEYS.map((key) => {
          const personal = state.personal[key];
          const options = key === "language"
            ? CHOICES.language.filter((item) => state.effective.enabled_languages.includes(item.value))
            : CHOICES[key];
          return (
            <div key={key} className="settings-preference-group">
              {key === DISPLAY_KEYS[0] && (
                <h3 className="settings-subheading" id="settings-display-title">{t("preferences.display_title")}</h3>
              )}
              {key === DISPLAY_KEYS[0] && <p className="panel-copy">{t("preferences.display_hint")}</p>}
              {key === STRIP_KEYS[0] && (
                <h3 className="settings-subheading" id="settings-strip-title">{t("strip.pref.title")}</h3>
              )}
              {key === STRIP_KEYS[0] && <p className="panel-copy">{t("strip.pref.help")}</p>}
              <label className="settings-preference-row" data-preference={key}>
                <span>{t(LABEL_KEYS[key])}</span>
                <select
                  value={personal ?? ""}
                  onChange={(event) => void save(key, event.target.value === "" ? null : event.target.value)}
                >
                  <option value="">
                    {t("preferences.use_default", {
                      value: choiceLabel(t, key, state.organisation_defaults[key] ?? state.effective[key] ?? BUILT_IN[key]),
                    })}
                  </option>
                  {options.map((choice) => (
                    <option key={choice.value} value={choice.value}>
                      {optionLabel(t, choice)}
                    </option>
                  ))}
                </select>
              </label>
              {key === "time_zone" && <TimeZonePreview t={t} />}
            </div>
          );
        })}
      {state && (
        <FocusHubsField
          t={t}
          value={state.personal.strip_focus_hubs}
          fallback={state.organisation_defaults.strip_focus_hubs ?? ""}
          onChange={(next) => void save("strip_focus_hubs", next)}
        />
      )}
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
                      {optionLabel(t, choice)}
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
