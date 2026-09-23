import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    headers: {
      'X-Content-Type-Options': 'nosniff',
      'X-Frame-Options': 'DENY',
      'Referrer-Policy': 'no-referrer',
      // Dev-only baseline. The production SPA must set a strict
      // Content-Security-Policy (script-src 'self') at the reverse proxy - see
      // the README "Security notes". This value permits Vite/React-Refresh
      // inline scripts and HMR websockets so local development keeps working.
      'Content-Security-Policy':
        "default-src 'self'; script-src 'self' 'unsafe-inline'; " +
        "style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; " +
        "media-src 'self' blob:; connect-src 'self' ws: wss: http://localhost:8000",
    },
  },
})