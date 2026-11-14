import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [react()],
  server: {
    // All interfaces — Tailscale / LAN / phone
    host: true,
    port: 5173,
    strictPort: true,
    // Allow MagicDNS (pinokio-….ts.net) and any other remote Host header
    allowedHosts: true,
    proxy: {
      '/api': 'http://127.0.0.1:8787',
      '/media': 'http://127.0.0.1:8787',
    },
  },
  preview: {
    host: true,
    port: 5173,
    allowedHosts: true,
  },
})
