import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// In development the API is proxied, so the browser sees one origin and CORS never applies.
const BACKEND_URL = process.env.BACKEND_URL ?? "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      "/api": { target: BACKEND_URL, changeOrigin: true },
      "/health": { target: BACKEND_URL, changeOrigin: true },
    },
  },
});
