import { fileURLToPath, URL } from 'node:url'
import { copyFileSync, existsSync, readdirSync, readFileSync } from 'node:fs'
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

/**
 * 构建期生成「品类 → 代表产品图」映射，虚拟模块 `virtual:category-thumbs`。
 *
 * 首页品类卡的缩略图用它：代表图取该品类 products.json **目录顺序里第一款有图
 * 且图片文件真实存在**的产品（products.json 的顺序是策展过的，小米系在前的品类
 * 通常第一款就是当家长焦）。映射在构建/dev 启动时算好，运行时零请求——
 * 首页默认视图依旧不加载任何产品 JSON。
 *
 * dev 期间新增图片不会热更新该模块（重启 dev server 即可）；构建永远是新鲜的。
 */
function categoryThumbs() {
  return {
    name: 'virtual-category-thumbs',
    resolveId(id: string) {
      if (id === 'virtual:category-thumbs') return '\0virtual:category-thumbs'
    },
    load(id: string) {
      if (id !== '\0virtual:category-thumbs') return
      const dataDir = fileURLToPath(new URL('./data', import.meta.url))
      const imgRoot = fileURLToPath(new URL('./public/images', import.meta.url))
      const thumbs: Record<string, string> = {}
      for (const cat of readdirSync(dataDir)) {
        if (cat.startsWith('_')) continue
        try {
          const products = JSON.parse(readFileSync(`${dataDir}/${cat}/products.json`, 'utf8'))
          if (!Array.isArray(products)) continue
          const hit = products.find(
            (p: { img?: unknown }) =>
              typeof p?.img === 'string' && existsSync(`${imgRoot}/${cat}/${p.img}`),
          )
          if (hit) thumbs[cat] = `${BASE}images/${cat}/${hit.img}`
        } catch {
          // 单个品类数据损坏不应阻断构建：该品类就没有缩略图，前端渲染占位
        }
      }
      return `export default ${JSON.stringify(thumbs)}`
    },
  }
}

export default defineConfig({
  base: BASE,
  plugins: [vue(), spaFallback(), categoryThumbs()],
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
