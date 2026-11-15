import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import { viteSingleFile } from "vite-plugin-singlefile";

// `npm run build:single` genera un único index.html (modo mock) para publicarlo como Artifact.
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const single = mode === "single";
  return {
    plugins: [react(), ...(single ? [viteSingleFile()] : [])],
    base: "./",
    define: single ? { "import.meta.env.VITE_USE_MOCK": JSON.stringify("true") } : {},
    build: {
      outDir: single ? "dist-single" : "dist",
      assetsInlineLimit: single ? 100_000_000 : 4096,
      chunkSizeWarningLimit: 2000,
    },
    server: {
      // El backend no declara CORS: en desarrollo se usa el mismo origen y Vite reenvía /api.
      proxy: { "/api": { target: env.VITE_API_PROXY ?? "http://127.0.0.1:8000", changeOrigin: true } },
    },
  };
});
