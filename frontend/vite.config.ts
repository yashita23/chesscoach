import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Chuyển /api sang FastAPI để cookie phiên đăng nhập cùng origin với trang.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': 'http://127.0.0.1:8000',
    },
  },
})
