import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import en from "./en.json";
import zh from "./zh.json";

const resources = {
  en: {
    translation: {
      ...en,
      "app.subtitle": "European gas intelligence and decision-support workspace",
      "nav.group.decision": "Decision Workspace",
      "nav.group.commercial": "Commercial Inputs",
      "nav.group.analytics": "Analytics",
      "nav.group.operations": "Operations",
      "nav.contracts": "Resource Terms",
      "nav.orders": "Market Positioning",
      "home.no_db_contracts": "No PostgreSQL resource terms loaded",
      "home.draft_contract_note": "Home waits for persisted resource terms. Use Resource Terms to capture EFET-style assumptions, then store them through the backend.",
      "home.blocker_contracts": "No persisted upstream resource terms are loaded.",
      "contracts.upload_contract": "Import Resource Terms",
      "contracts.upload_hint": "Import JSON or staged text to pre-fill EFET-style resource terms for decision support. Uploads do not create official contracts or ETRM records.",
      "contracts.title": "Resource Terms",
      "contracts.description": "Capture EFET-style resource terms and contract assumptions for portfolio/resource-pool decision support. This workspace is not contract lifecycle management, trade capture, settlement, or an ETRM master.",
      "contracts.agreement": "Resource Agreement Assumptions",
      "contracts.contract_id": "Resource term ID",
      "contracts.contract_name": "Resource term name",
      "contracts.contract_type": "Resource type",
      "contracts.library": "Resource Terms Library",
      "contracts.no_saved_contracts": "No saved resource terms yet.",
      "contracts.save_to_resource_pool": "Save Resource Terms to Pool",
      "contracts.save_hint": "Save terms through the backend to refresh resource-pool options. Human review remains required.",
      "contracts.new_draft": "New Resource-Term Draft",
      "contracts.new_draft_loaded": "New resource-term draft loaded.",
      "contracts.loaded_for_edit": "resource terms loaded for editing.",
      "manual.contracts": "EFET-style resource terms and contract assumptions feeding the portfolio resource pool.",
      "glossary.contract": "Resource term",
      "glossary.contracts": "Resource terms",
      "panel.contracts": "Resource terms",
      "settings.chinese": "中文",
    },
  },
  "zh-CN": {
    translation: {
      ...zh,
      "app.subtitle": "欧洲天然气智能与决策支持工作台",
      "nav.group.decision": "决策工作区",
      "nav.group.commercial": "商业输入",
      "nav.group.analytics": "分析工具",
      "nav.group.operations": "运行与设置",
      "nav.contracts": "资源条款",
      "nav.orders": "市场定位",
      "home.no_db_contracts": "PostgreSQL 暂无资源条款",
      "home.draft_contract_note": "首页等待已入库的资源条款。请在资源条款页录入 EFET 风格假设，并通过后端写入数据库。",
      "home.blocker_contracts": "尚未加载已入库的上游资源条款。",
      "contracts.upload_contract": "导入资源条款",
      "contracts.upload_hint": "导入 JSON 或暂存文本，用于预填 EFET 风格资源条款。上传不会形成正式合同或 ETRM 记录。",
      "contracts.title": "资源条款",
      "contracts.description": "录入用于组合资源池决策支持的 EFET 风格资源条款与合同假设。本工作区不作为合同生命周期管理、成交录入、结算或 ETRM 主数据。",
      "contracts.agreement": "资源协议假设",
      "contracts.contract_id": "资源条款 ID",
      "contracts.contract_name": "资源条款名称",
      "contracts.contract_type": "资源类型",
      "contracts.library": "资源条款库",
      "contracts.no_saved_contracts": "暂无已保存资源条款。",
      "contracts.save_to_resource_pool": "保存资源条款至资源池",
      "contracts.save_hint": "通过后端保存条款以刷新资源池方案，仍需人工复核。",
      "contracts.new_draft": "新建资源条款草稿",
      "contracts.new_draft_loaded": "已载入新的资源条款草稿。",
      "contracts.loaded_for_edit": "资源条款已载入编辑。",
      "manual.contracts": "EFET 风格资源条款和合同假设，并进入组合资源池。",
      "glossary.contract": "资源条款",
      "glossary.contracts": "资源条款",
      "panel.contracts": "资源条款",
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
