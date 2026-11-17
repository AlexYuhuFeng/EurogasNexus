import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";
import { readFileSync } from "fs";

/**
 * The bundled fonts' licence texts travel with the build (dist/licenses/), beside the font files
 * Vite emits into dist/assets: the web build, the desktop bundle and the demo image all ship
 * dist/. The manifest is src/assets/fonts/fonts.json (recorded in THIRD_PARTY_NOTICES.md).
 */
function bundledFontLicences() {
  const fontsDir = path.resolve(__dirname, "src/assets/fonts");
  return {
    name: "eurogas-bundled-font-licences",
    generateBundle(this: { emitFile: (file: { type: "asset"; fileName: string; source: string }) => void }) {
      const manifest = JSON.parse(readFileSync(path.join(fontsDir, "fonts.json"), "utf8")) as {
        fonts: { name: string; license: string; license_file: string }[];
      };
      for (const font of manifest.fonts) {
        this.emitFile({
          type: "asset",
          fileName: `licenses/${font.name}-${font.license}.txt`,
          source: readFileSync(path.join(fontsDir, font.license_file), "utf8"),
        });
      }
    },
  };
}

export default defineConfig({
  plugins: [react(), bundledFontLicences()],
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
      // EUROGAS_API_PROXY_TARGET lets a second local stack run beside the default one.
      ...(process.env.EUROGAS_API_PROXY_TARGET ? { "/api": process.env.EUROGAS_API_PROXY_TARGET } : {}),
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
