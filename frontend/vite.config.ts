import path from 'path'
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath, URL } from 'node:url'
import { createSvgIconsPlugin } from 'vite-plugin-svg-icons'

export default defineConfig(({mode}) => ({
  base: mode === 'production' ? '/app/' : '/',
  build: {
      // 文件分类打包
      cssCodeSplit: true,
      rollupOptions: {
          output: {
              manualChunks: undefined,
              chunkFileNames: 'assets/js/[name]-[hash].js',
              entryFileNames: 'assets/js/[name]-[hash].js',
              assetFileNames: 'assets/[ext]/[name]-[hash].[ext]'
          }
      }
  },
  plugins: [
    vue(),
    createSvgIconsPlugin({
        iconDirs: [path.resolve(process.cwd(), 'src/assets/icons')],
        symbolId: '[name]'
    }),
  ],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url))
    }
  },
  server: {
    host: '0.0.0.0',
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8080',
        changeOrigin: true,
      },
      '/files/uploads': {
        target: 'http://127.0.0.1:8080',
        changeOrigin: true,
      },
      '/files/generate/': {
        target: 'http://127.0.0.1:80',
        changeOrigin: true,
      }
    }
  }
}))