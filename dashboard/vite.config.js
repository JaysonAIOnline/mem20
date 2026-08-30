import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In dev, proxy /api to the optional mem20 bridge (bridge/server.py, default :8000).
// In a static build, the dashboard calls VITE_API_BASE directly (default http://localhost:8000).
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": "http://localhost:8000",
    },
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
  },
});
