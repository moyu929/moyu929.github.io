import type { FieldDef, Product } from './types'

/** 按字段定义把原始值渲染成展示文本；空值统一显示为破折号 */
export function formatValue(field: FieldDef, product: Product): string {
  const raw = product[field.key]

  if (raw === null || raw === undefined || raw === '') return '—'

  if (Array.isArray(raw)) {
    return raw.length ? raw.join('、') : '—'
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

/** 对比表判断某行各产品的值是否全部相同 */
export function allSame(values: string[]): boolean {
  return values.every((v) => v === values[0])
}
