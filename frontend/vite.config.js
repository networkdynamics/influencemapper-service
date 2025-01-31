import { fileURLToPath, URL } from 'node:url'

import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import vueDevTools from 'vite-plugin-vue-devtools'

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    vue(),
    vueDevTools(),
  ],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url))
    },
  },
  server: {
    proxy: {
      '/upload': {
        target: 'http://localhost:8000', // FastAPI server URL
        changeOrigin: true
      },
      '/events': {
        target: 'http://localhost:8000', // FastAPI server URL
        changeOrigin: true
      },
      '/download' :{
        target: 'http://localhost:8000', // FastAPI server URL
        changeOrigin: true
      },
    },
  },
  build: {
    outDir: '../web/app/dist' // Replace 'custom-dist' with your desired directory
  }
})
