import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import en from "./en.json";
import zh from "./zh.json";

const resources = {
  en: {
    translation: {
      ...en,
      "nav.contracts": "Resource Terms",
      "nav.orders": "Market Positioning",
      "settings.chinese": "中文",
    },
  },
  "zh-CN": {
    translation: {
      ...zh,
      "nav.contracts": "资源条款",
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
  lng: "en",
  fallbackLng: "en",
  interpolation: { escapeValue: false },
});

syncDocumentLanguage(i18n.language);
i18n.on("languageChanged", syncDocumentLanguage);

export default i18n;
