import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// In development the API is proxied, so the browser talks to one origin.
// In production set VITE_API_URL to the backend's public URL (e.g. https://cmrs-api.onrender.com).
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { '/api': { target: process.env.VITE_PROXY_TARGET ?? 'http://localhost:8000', changeOrigin: true } },
  },
})
