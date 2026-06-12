import path from 'path'
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath, URL } from 'node:url'
import { createSvgIconsPlugin } from 'vite-plugin-svg-icons'
import viteCompression from 'vite-plugin-compression'


const CHUNK_GROUPS: Record<string, string[]> = {
  'vendor-base': ['vue', 'vue-router', 'pinia', '@vue', '@vicons', 
    '@tanstack/virtual-core', 'naive-ui', 'vueuc', 'css-render', 'seemly', 'treemate', 
    'marked', 'markdown-it', 'markstream-vue', 'katex'],
  'vendor-virtual': ['@tanstack/vue-virtual'],
  'vendor-monaco': ['monaco-editor', 'stream-monaco'],
  'vendor-mermaid-infographic': ['mermaid', 'infographic'],
  'vendor-d2': ['d2'],
}

const getChunkName = (id: string): string | undefined => {
  for (const [chunkName, deps] of Object.entries(CHUNK_GROUPS)) {
    if (deps.some(dep => id.includes(dep))) return chunkName
  }
  return undefined
}

export default defineConfig(({ mode }) => {
  const isProd = mode === 'production'
  return {
  base: isProd ? '/app/' : '/',
  build: {
    target: 'es2020', 
    cssCodeSplit: false,
    chunkSizeWarningLimit: 500,
    emptyOutDir: true,
    sourcemap: false,
    rollupOptions: {
      output: {
        // 智能分包
        manualChunks(id:any) {
          if (!id.includes('node_modules')) return
          return getChunkName(id) ?? 'vendor-common'
        },

        // hash 截断为 8 位
        chunkFileNames: 'assets/js/[name]-[hash:8].js',
        entryFileNames: 'assets/js/[name]-[hash:8].js',

        assetFileNames: (assetInfo:any) => {
          const name = assetInfo.name ?? ''
          const ext = name.split('.').pop() ?? ''

          if (/png|jpe?g|gif|svg|webp|ico/i.test(ext))
            return 'assets/images/[name]-[hash:8][extname]'
          if (/css/i.test(ext))
            return 'assets/css/[name]-[hash:8][extname]'
          if (/woff2?|eot|ttf|otf/i.test(ext))
            return 'assets/fonts/[name]-[hash:8][extname]'
          if (/js/i.test(ext))
            return 'assets/js/[name]-[hash:8][extname]'
          return 'assets/[ext]/[name]-[hash:8][extname]'
        },
      },
    },
    // 小于 16KB 的资源内联为 base64（减少请求数）
    assetsInlineLimit: 16384,
  },

  // 依赖预构建（加快冷启动）
  optimizeDeps: {
    include: [
      'vue', 'vue-router', 'pinia', 'naive-ui',
      'katex', '@tanstack/vue-virtual', 'mermaid',
    ],
    exclude: [
      'monaco-editor',
    ],
  },
  plugins: [
    vue(),
    createSvgIconsPlugin({
      iconDirs: [path.resolve(process.cwd(), 'src/assets/icons')],
      symbolId: '[name]',
    }),
    isProd && viteCompression({
      verbose: true,                // 是否在控制台输出压缩结果
      disable: false,                // 是否禁用压缩
      threshold: 10240,             // 对大于10KB的文件进行压缩，单位是字节 (b)
      algorithm: 'brotliCompress',  // 压缩算法
      ext: '.br',                   // 生成的压缩包后缀
      deleteOriginFile: true        // 压缩后删除源文件
    }),
  ].filter(Boolean),
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    host: '0.0.0.0',
    proxy: {
      '/api': { target: 'http://127.0.0.1:8080', changeOrigin: true },
      '/files/uploads': { target: 'http://127.0.0.1:8080', changeOrigin: true },
      '/files/generate/': { target: 'http://127.0.0.1:80', changeOrigin: true },
    },
  },
}})