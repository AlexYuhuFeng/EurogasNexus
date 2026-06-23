/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_EUROGAS_API_BASE_URL?: string;
}

interface Window {
  readonly __TAURI_INTERNALS__?: unknown;
}
