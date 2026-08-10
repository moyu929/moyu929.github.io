import type { CategoryData, CategoryMeta, Product, CategorySchema } from './types'
import categoriesJson from '@data/categories.json'

/**
 * 品类数据通过 glob 懒加载：新增一个品类只需在 data/ 下建目录并放两个 JSON，
 * 再往 categories.json 里加一行，无需改动任何代码。
 */
const schemaModules = import.meta.glob<{ default: CategorySchema }>('../data/*/schema.json')
const productModules = import.meta.glob<{ default: Product[] }>('../data/*/products.json')

export const categories = categoriesJson as CategoryMeta[]

const cache = new Map<string, CategoryData>()

export async function loadCategory(id: string): Promise<CategoryData> {
  const cached = cache.get(id)
  if (cached) return cached

  const schemaLoader = schemaModules[`../data/${id}/schema.json`]
  const productsLoader = productModules[`../data/${id}/products.json`]
  if (!schemaLoader || !productsLoader) {
    throw new Error(`品类「${id}」的数据文件不存在`)
  }

  const [schemaMod, productsMod] = await Promise.all([schemaLoader(), productsLoader()])
  const data: CategoryData = { schema: schemaMod.default, products: productsMod.default }
  cache.set(id, data)
  return data
}

/** 拼接产品图的完整 URL；无图返回 null */
export function imageUrl(schema: CategorySchema, product: Product): string | null {
  if (!product.img) return null
  return `${import.meta.env.BASE_URL}${schema.imageBase}/${product.img}`
}
