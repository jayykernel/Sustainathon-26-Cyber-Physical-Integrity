import { defineConfig } from "vitest/config";

export default defineConfig({
  base: "./",
  server: {
    port: 4173,
    strictPort: true,
  },
  build: {
    target: "es2020",
    outDir: "dist",
    assetsDir: "assets",
  },
  test: {
    environment: "node",
    include: ["tests/**/*.test.ts"],
  },
});
