import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";

// Tauri 期望前端开发服务器运行在固定端口（默认 5173），与 tauri.conf.json 的 devUrl 对应。
const host = process.env.TAURI_DEV_HOST;

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "src"),
    },
  },

  // 为 Tauri 优化的开发服务器配置
  clearScreen: false,
  server: {
    port: 5173,
    strictPort: true,
    host: host || false,
    hmr: host
      ? {
          protocol: "ws",
          host,
          port: 5174,
        }
      : undefined,
    watch: {
      // 忽略 Rust 外壳目录，避免无意义的热更新触发
      ignored: ["**/src-tauri/**"],
    },
  },

  build: {
    // 产物输出目录，对应 tauri.conf.json 的 build.frontendDist
    outDir: "dist",
    target: "es2021",
    sourcemap: false,
  },
});
