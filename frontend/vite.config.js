import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        // Must stay above the backend provider timeout, otherwise the proxy
        // cuts a long-running generation before the backend gives up.
        timeout: 1800000,
        proxyTimeout: 1800000,
      },
    },
  },
})
