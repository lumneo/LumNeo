import path from 'path'
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath, URL } from 'node:url'
import { createSvgIconsPlugin } from 'vite-plugin-svg-icons'
// import monacoEditorPlugin from 'vite-plugin-monaco-editor-esm'

export default defineConfig(({ mode }) => ({
  base: mode === 'production' ? '/app/' : '/',
  build: {
    cssCodeSplit: true,
    rollupOptions: {
      output: {
        // 手动分包策略 —— 针对大型依赖单独拆分
        manualChunks(id) {
          if (id.includes('node_modules')) {
            // naive-ui 全家桶单独打包（体积大）
            if (id.includes('naive-ui') || id.includes('vueuc') || id.includes('css-render')) {
              return 'vendor-naive-ui';
            }
            // mermaid 图表库单独打包（体积巨大）
            if (id.includes('mermaid') || id.includes('d3') || id.includes('khroma')) {
              return 'vendor-mermaid';
            }
            // Markdown 相关全家桶
            if (id.includes('marked') || id.includes('highlight.js') || id.includes('katex')) {
              return 'vendor-markdown';
            }
            // 虚拟滚动库
            if (id.includes('@tanstack/vue-virtual')) {
              return 'vendor-virtual';
            }
            // Vue 核心生态
            if (id.includes('vue') || id.includes('pinia') || id.includes('vue-router')) {
              return 'vendor-vue-core';
            }
            // 其他第三方库归为一个 vendor
            return 'vendor-common';
          }
        },
        chunkFileNames: 'assets/js/[name]-[hash].js',
        entryFileNames: 'assets/js/[name]-[hash].js',
        assetFileNames: (assetInfo: any) => {
          const ext = assetInfo.name.split('.').pop();
          if (/png|jpe?g|gif|svg|webp/i.test(ext)) {
            return 'assets/images/[name]-[hash].[ext]';
          }
          if (/css/i.test(ext)) {
            return 'assets/css/[name]-[hash].[ext]';
          }
          if (/woff2?|eot|ttf|otf/i.test(ext)) {
            return 'assets/fonts/[name]-[hash].[ext]';
          }
          return 'assets/[ext]/[name]-[hash].[ext]';
        },
      },
    },
    // 小于 4KB 的资源内联为 base64（减少请求数）
    assetsInlineLimit: 4096,
  },
  plugins: [
    vue(),
    createSvgIconsPlugin({
      iconDirs: [path.resolve(process.cwd(), 'src/assets/icons')],
      symbolId: '[name]',
    }),
    // monacoEditorPlugin({
    //   languageWorkers: ['editorWorkerService', 'typescript', 'css', 'html', 'json']
    // })
  ],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
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
      },
    },
  },
}))