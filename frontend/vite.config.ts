import react from "@vitejs/plugin-react";
import { loadEnv } from "vite";
import { defineConfig } from "vitest/config";

export default defineConfig(({ mode }) => {
  const fileEnv = loadEnv(mode, "..", "");
  const value = (name: string, fallback: string) =>
    process.env[name] ?? fileEnv[name] ?? fallback;
  const backendHost = value("BACKEND_HOST", "127.0.0.1");
  const proxyHost = backendHost === "0.0.0.0" ? "127.0.0.1" : backendHost;

  return {
    plugins: [react()],
    server: {
      host: value("FRONTEND_HOST", "0.0.0.0"),
      port: Number(value("FRONTEND_PORT", "5173")),
      strictPort: true,
      proxy: {
        "/api": `http://${proxyHost}:${value("BACKEND_PORT", "8000")}`,
      },
    },
    test: {
      environment: "jsdom",
      setupFiles: "./src/test/setup.ts",
      css: true,
    },
  };
});
