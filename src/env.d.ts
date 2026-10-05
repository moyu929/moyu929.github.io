/// <reference types="vite/client" />

declare module 'virtual:category-thumbs' {
  /** 品类 id → 代表产品图 URL（构建期由 vite.config.ts 的 categoryThumbs 插件生成） */
  const thumbs: Record<string, string>
  export default thumbs
}

declare module 'virtual:brand-logos' {
  /** 品牌名 → logo 图 URL（public/images/brands/<品牌名>.<ext>，构建期扫描） */
  const logos: Record<string, string>
  export default logos
}
