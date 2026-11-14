import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [react()],
  server: {
    // Listen on all interfaces so Tailscale / LAN / phone access works
    host: true,
    port: 5173,
    strictPort: true,
    // Vite blocks unknown Host headers by default — allow MagicDNS (.ts.net) etc.
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
