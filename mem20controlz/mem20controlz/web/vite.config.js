import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Production build: the backend serves ./dist and the app calls same-origin /api/*.
// No proxy is required (or wanted) for `npm run build`.
//
// `npm run dev` only, and only if you opt in:
//   MEM20_CONTROL_API_TARGET=http://127.0.0.1:8000 npm run dev
const devApiTarget = process.env.MEM20_CONTROL_API_TARGET;

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    ...(devApiTarget ? { proxy: { "/api": devApiTarget } } : {}),
  },
  build: {
    // Emitted into the package's static/ dir, which the FastAPI app serves, so
    // there is exactly one build output and no copy step.
    outDir: "../static",
    emptyOutDir: true,
    sourcemap: false,
  },
});
