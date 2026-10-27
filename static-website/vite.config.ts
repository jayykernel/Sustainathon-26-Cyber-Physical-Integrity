import { defineConfig } from "vitest/config";

export default defineConfig({
  base: "./",
  server: {
    port: 4173,
    strictPort: true,
    proxy: {
      "/api": { target: "http://127.0.0.1:8000", ws: true },
    },
  },
  build: {
    target: "es2020",
    outDir: "dist",
    assetsDir: "assets",
    rolldownOptions: {
      output: {
        codeSplitting: {
          groups: [{ name: "vendor", test: /node_modules[\\/]/, maxSize: 450_000 }],
        },
      },
    },
  },
  test: {
    environment: "node",
    include: ["tests/**/*.test.ts"],
  },
});
