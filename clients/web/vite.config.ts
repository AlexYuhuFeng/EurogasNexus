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
    watch: {
      // Atomic editors briefly lock their hidden staging directory on Windows.
      // Watch the final source file, without opening those transient artifacts.
      ignored: [/[\\/]\.[^\\/]+\.tmpdir(?:[\\/]|$)/],
    },
    proxy: {
      "/api": "http://127.0.0.1:8000",
    },
  },
  // Name the runtime dependencies so the dev server pre-bundles them in its first pass. A
  // dependency it discovers later costs a second optimisation and a full page reload; on a
  // cold two-core CI runner that reload pushed the first paint past the acceptance sweep's
  // sign-in wait when the chart library was added.
  optimizeDeps: {
    include: [
      "react",
      "react-dom",
      "react-dom/client",
      "react-i18next",
      "i18next",
      "zustand",
      "maplibre-gl",
      "uplot",
    ],
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks(moduleId) {
          if (!moduleId.includes("node_modules")) return undefined;
          if (moduleId.includes("maplibre-gl")) return "vendor-map";
          if (moduleId.includes("uplot")) return "vendor-chart";
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
