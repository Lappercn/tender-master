import { defineConfig } from "vite"
import vue from "@vitejs/plugin-vue"

export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    proxy: {
      "/admin": "http://127.0.0.1:8788",
      "/api": "http://127.0.0.1:8788",
      "/docs": "http://127.0.0.1:8788",
      "/redoc": "http://127.0.0.1:8788",
      "/openapi.json": "http://127.0.0.1:8788",
    },
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
  },
})
