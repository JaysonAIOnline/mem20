import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  base: "./",
  build: {
    outDir: "../built/react_editor",
    emptyOutDir: true,
    target: "es2020",
  },
  server: {
    proxy: {
      "/api": {
        target: "http://127.0.0.1:48022",
        changeOrigin: true,
      },
    },
  },
});