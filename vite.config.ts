import { fileURLToPath, URL } from 'node:url'
import { copyFileSync } from 'node:fs'
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// GitHub Pages 用户站点（moyu929.github.io）部署在根路径
const BASE = '/'

/**
 * GitHub Pages 没有 SPA 回退，直接访问 /air-purifier 这类子路由会 404。
 * 把 index.html 复制一份为 404.html，Pages 会用它兜底，前端路由再接管。
 */
function spaFallback() {
  return {
    name: 'spa-fallback-404',
    closeBundle() {
      copyFileSync('dist/index.html', 'dist/404.html')
    },
  }
}

export default defineConfig({
  base: BASE,
  plugins: [vue(), spaFallback()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
      '@data': fileURLToPath(new URL('./data', import.meta.url)),
    },
  },
  build: {
    // 产品图按原样输出，不内联成 base64
    assetsInlineLimit: 0,
  },
})
