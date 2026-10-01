import type { FieldDef, Product } from './types'

/**
 * 判断字符串值是否自带单位。
 *
 * 竞品数据多来自第三方规格站，常把单位写进值里（「85英寸」「4000mAh」「16套」），
 * 而 schema 又声明了 unit。两者相加会渲染成「85英寸英寸」，所以先探测再决定是否追加。
 *
 * 只认「值里出现了单位写法」这个事实，不试图解析单位边界 —— 单位串本身
 * 没有统一分隔符，硬解析容易把「4L(4-5人)」这类值切错。
 */
function carriesUnit(value: string, unit: string | undefined): boolean {
  if (!unit) return false
  const tail = value.trimEnd()
  // 单位出现在结尾（85英寸 / 4000mAh / 16套），或以「数值+单位」形式出现（0.85Kwh/24h）
  const u = unit.trim()
  if (!u) return false
  if (tail.endsWith(u)) return true
  const idx = tail.lastIndexOf(u)
  // 单位前必须是数字结尾的一段（避免「4L(4-5人)」里 L 后面还有别的内容却被误判）
  if (idx < 0) return false
  return /^\d/.test(tail.slice(idx + u.length))
}

/** 按字段定义把原始值渲染成展示文本；空值统一显示为破折号 */
export function formatValue(field: FieldDef, product: Product): string {
  const raw = product[field.key]

  if (raw === null || raw === undefined || raw === '') return '—'

  if (Array.isArray(raw)) {
    return raw.length ? raw.join('、') : '—'
  }

  // 值里已经带了单位就不再追加，避免「85英寸英寸」
  if (typeof raw === 'string' && carriesUnit(raw, field.unit)) {
    return `${field.prefix ?? ''}${raw}`
  }

  return `${field.prefix ?? ''}${raw}${field.unit ?? ''}`
}

/** 取字段的标签数组，供 tags 类型字段渲染 */
export function tagsOf(field: FieldDef, product: Product): string[] {
  const raw = product[field.key]
  return Array.isArray(raw) ? (raw as string[]) : []
}

/** 取数值字段的数字值，非数值返回 null（如甲醛CADR 可能是「不适用」） */
export function numberOf(product: Product, key: string): number | null {
  const raw = product[key]
  if (typeof raw === 'number' && Number.isFinite(raw)) return raw
  if (typeof raw === 'string') {
    const parsed = Number.parseFloat(raw)
    if (Number.isFinite(parsed)) return parsed
  }
  return null
}

/**
 * 取用于排序/统计的价位：优先 official_price（品牌官方在售价），
 * 缺失时回退 ref_price（参考价）。
 *
 * 原因：非小米品牌往往没有可核验的官方商城在售价，只有权威第三方规格站给的参考价，
 * 而竞品在多数品类里占多数。若只认 official_price，这些产品会在默认排序里全部沉底、
 * 顶部均价与区间也只剩小米部分 —— 相当于把多品牌横评又变回小米单品牌榜。
 */
export function priceOf(product: Product): number | null {
  return numberOf(product, 'official_price') ?? numberOf(product, 'ref_price')
}

/** 对比表判断某行各产品的值是否全部相同 */
export function allSame(values: string[]): boolean {
  return values.every((v) => v === values[0])
}
