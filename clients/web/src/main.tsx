// The design system loads first: it declares the cascade-layer order every stylesheet uses.
import "./styles/design-system.css";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./i18n";
import { applyStoredPnlColors } from "@/app/preferences/remotePreferences";
import App from "./App";

applyStoredPnlColors();

createRoot(document.getElementById("root")!).render(
  <StrictMode><App /></StrictMode>
);
