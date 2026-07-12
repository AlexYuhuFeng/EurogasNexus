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
      "/api": "http://127.0.0.1:8000",
    },
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks(moduleId) {
          if (!moduleId.includes("node_modules")) return undefined;
          if (moduleId.includes("maplibre-gl")) return "vendor-map";
          if (moduleId.includes("react-i18next") || moduleId.includes("i18next")) {
            return "vendor-i18n";
          }
          if (moduleId.includes("zustand")) return "vendor-state";
          if (moduleId.includes("react-dom") || moduleId.includes("react")) {
            return "vendor-react";
          }
          return undefined;
        },
      },
    },
    chunkSizeWarningLimit: 1200,
  },
});
