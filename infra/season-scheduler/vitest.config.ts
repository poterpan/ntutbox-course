import { defineConfig } from "vitest/config";

// 邏輯只依賴 fetch，測試全部 mock fetch，用 node 環境跑即可（不需要 workers pool）。
export default defineConfig({
  test: {
    environment: "node",
  },
});
