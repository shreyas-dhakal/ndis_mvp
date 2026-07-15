import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Dev-time proxy: the browser calls /api/... and Vite forwards it to FastAPI.
// This avoids CORS entirely during local development. In production, point
// VITE_API_URL at your deployed backend instead (see lib/api.js).
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },
});
