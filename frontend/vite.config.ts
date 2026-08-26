import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Override to run a second instance alongside a already-running dev server:
//   VITE_API_TARGET=http://127.0.0.1:8011 npm run dev -- --port 5174
const apiTarget = process.env.VITE_API_TARGET ?? "http://127.0.0.1:8010";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      // Keeps the SPA and the API same-origin in development, so the
      // SameSite=Strict refresh cookie behaves exactly as in production.
      "/api": { target: apiTarget, changeOrigin: false },
    },
  },
  build: { outDir: "dist", sourcemap: false },
});
