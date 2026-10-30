import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./i18n";
import { applyStoredPnlColors } from "@/app/preferences/remotePreferences";
import App from "./App";

applyStoredPnlColors();

createRoot(document.getElementById("root")!).render(
  <StrictMode><App /></StrictMode>
);
