import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    host: process.env.MYCELIUM_UI_HOST ?? '127.0.0.1',
    allowedHosts: (process.env.MYCELIUM_ALLOWED_HOSTS ?? 'localhost').split(',').map(host => host.trim()),
    proxy: {
      '/api': { target: 'http://127.0.0.1:8000', changeOrigin: false },
    },
  },
})
