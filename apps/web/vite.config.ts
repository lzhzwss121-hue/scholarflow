import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@scholarflow/schemas": new URL("../../packages/schemas/src/index.ts", import.meta.url).pathname,
    },
  },
});
