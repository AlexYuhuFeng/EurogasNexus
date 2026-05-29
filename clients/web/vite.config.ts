import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { "@": path.resolve(__dirname, "./src") },
  },
  server: {
    port: 3000,
    proxy: {
      "/api": "http://localhost:8000",
    },
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          "vendor-react": ["react", "react-dom"],
          "vendor-map": ["maplibre-gl"],
          "vendor-i18n": ["i18next", "react-i18next"],
          "vendor-state": ["zustand"],
        },
      },
    },
    chunkSizeWarningLimit: 1200,
  },
});
