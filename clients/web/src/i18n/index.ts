import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import en from "./en.json";
import zh from "./zh.json";
import { readStoredLanguage, storeLanguage } from "./language";

const resources = {
  en: {
    translation: {
      ...en,
      // Contract words live in en.json/zh.json only (the desk's language, owner 2026-11-19).
      "app.subtitle": "European gas intelligence and decision-support workspace",
      "nav.orders": "Market Positioning",
      "settings.chinese": "中文",
    },
  },
  "zh-CN": {
    translation: {
      ...zh,
      "app.subtitle": "欧洲天然气智能与决策支持工作台",
      "nav.orders": "市场定位",
      "settings.chinese": "中文",
    },
  },
};

function syncDocumentLanguage(language: string) {
  if (typeof document !== "undefined") {
    document.documentElement.lang = language;
  }
}

i18n.use(initReactI18next).init({
  resources,
  // The stored preference wins; English remains the shipped-complete fallback.
  // Before this, every reload reset the interface to English even after the user
  // picked Mandarin in settings.
  lng: readStoredLanguage(),
  fallbackLng: "en",
  interpolation: { escapeValue: false },
});

syncDocumentLanguage(i18n.language);
i18n.on("languageChanged", syncDocumentLanguage);

/**
 * The single way a surface switches language: persist the choice, then apply it.
 * Callers must not call `i18n.changeLanguage` directly, or the choice dies on the
 * next load.
 */
export async function changeAppLanguage(language: string): Promise<void> {
  const normalized = storeLanguage(language);
  if (i18n.language !== normalized) await i18n.changeLanguage(normalized);
}

export default i18n;
