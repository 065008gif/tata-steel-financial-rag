import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    allowedHosts: ['.trycloudflare.com'],   // allow the temporary Cloudflare review tunnel
    proxy: {
      // The FastAPI backend (Docker) — every call in src/api.js uses a relative /api/... path.
      '/api': {
        target: process.env.VITE_API_TARGET || 'http://127.0.0.1:8000',   // teammate: set VITE_API_TARGET to the tunnel link
        changeOrigin: true,
        timeout: 300_000,
        proxyTimeout: 300_000,
      },
    },
  },
})
