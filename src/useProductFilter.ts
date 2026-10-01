import { computed, ref, type Ref } from 'vue'
import type { CategoryData, Product } from './types'
import { numberOf, priceOf } from './format'

export type SortDirection = 'default' | 'asc' | 'desc'

/**
 * 品类列表页的筛选 / 排序 / 搜索状态。
 * 排序字段来自 schema 中标记了 sortable 的字段，因此新品类无需改代码。
 */
export function useProductFilter(data: Ref<CategoryData | null>) {
  const activeGroup = ref('全部')
  const keyword = ref('')
  const sortKey = ref<string | null>(null)
  const sortDirection = ref<SortDirection>('default')
  /** 副分组选中项，key 为 facet 的字段名 */
  const activeFacets = ref<Record<string, string>>({})

  const sortableFields = computed(() =>
    (data.value?.schema.fields ?? []).filter((f) => f.sortable),
  )

  /** 各分组的产品数量，用于下拉里的计数 */
  const groupCounts = computed(() => {
    const counts: Record<string, number> = {}
    const groupKey = data.value?.schema.groupBy.key
    if (!groupKey) return counts
    for (const p of data.value?.products ?? []) {
      const group = String(p[groupKey] ?? '')
      counts[group] = (counts[group] ?? 0) + 1
    }
    return counts
  })

  /** 每个副分组维度下的产品计数；维度未选中时按主分组收窄后再统计 */
  const facetCounts = computed(() => {
    const current = data.value
    if (!current) return {} as Record<string, Record<string, number>>

    const { schema, products } = current
    const base =
      activeGroup.value === '全部'
        ? products
        : products.filter((p) => String(p[schema.groupBy.key] ?? '') === activeGroup.value)

    const out: Record<string, Record<string, number>> = {}
    for (const facet of schema.facets ?? []) {
      const counts: Record<string, number> = {}
      for (const p of base) {
        const v = String(p[facet.key] ?? '')
        counts[v] = (counts[v] ?? 0) + 1
      }
      out[facet.key] = counts
    }
    return out
  })

  function setFacet(key: string, value: string) {
    if (value === '全部') {
      const next = { ...activeFacets.value }
      delete next[key]
      activeFacets.value = next
      return
    }
    activeFacets.value = { ...activeFacets.value, [key]: value }
  }

  const filtered = computed<Product[]>(() => {
    const current = data.value
    if (!current) return []

    const { schema, products } = current
    const groupKey = schema.groupBy.key
    let list = products.slice()

    if (activeGroup.value !== '全部') {
      list = list.filter((p) => String(p[groupKey] ?? '') === activeGroup.value)
    }

    for (const [key, value] of Object.entries(activeFacets.value)) {
      if (value === '全部') continue
      list = list.filter((p) => String(p[key] ?? '') === value)
    }

    const q = keyword.value.trim().toLowerCase()
    if (q) {
      list = list.filter((p) =>
        schema.searchFields.some((key) => {
          const raw = p[key]
          if (Array.isArray(raw)) {
            return raw.some((t) => String(t).toLowerCase().includes(q))
          }
          return String(raw ?? '').toLowerCase().includes(q)
        }),
      )
    }

    const key = sortKey.value
    if (key && sortDirection.value !== 'default') {
      const sign = sortDirection.value === 'asc' ? 1 : -1
      list.sort((a, b) => {
        // 主排序键：year 等数值字段；价格键回退到 ref_price
        const metricOf = (p: Product) =>
          key === 'official_price' ? priceOf(p) : numberOf(p, key)
        const av = metricOf(a)
        const bv = metricOf(b)
        // 无法比较的值沉底，不参与排序竞争
        if (av === null && bv === null) return 0
        if (av === null) return 1
        if (bv === null) return -1
        const cmp = (av - bv) * sign
        if (cmp !== 0) return cmp
        // 同一年时按月份进一步排序（month 缺失沉底），仅对上市时间等含月份字段生效
        if (key === 'year') {
          const am = numberOf(a, 'month')
          const bm = numberOf(b, 'month')
          if (am === null && bm === null) return 0
          if (am === null) return 1
          if (bm === null) return -1
          return (am - bm) * sign
        }
        return 0
      })
    } else {
      // 默认排序：按分组顺序，组内按主指标降序
      const rank: Record<string, number> = {}
      schema.groupBy.order.forEach((g, i) => (rank[g] = i))
      const metricOf = (p: Product) =>
        schema.primaryMetric === 'official_price' ? priceOf(p) : numberOf(p, schema.primaryMetric)
      list.sort((a, b) => {
        const ga = rank[String(a[groupKey] ?? '')] ?? 99
        const gb = rank[String(b[groupKey] ?? '')] ?? 99
        if (ga !== gb) return ga - gb
        return (metricOf(b) ?? 0) - (metricOf(a) ?? 0)
      })
    }

    return list
  })

  /** 仅在「全部 + 无副分组筛选 + 默认排序 + 无搜索」时按分组展示，否则平铺 */
  const isGrouped = computed(
    () =>
      activeGroup.value === '全部' &&
      Object.keys(activeFacets.value).length === 0 &&
      sortDirection.value === 'default' &&
      !keyword.value.trim(),
  )

  const groupedList = computed(() => {
    const current = data.value
    if (!current || !isGrouped.value) return []

    const groupKey = current.schema.groupBy.key
    const buckets = new Map<string, Product[]>()
    for (const p of filtered.value) {
      const group = String(p[groupKey] ?? '')
      const bucket = buckets.get(group)
      if (bucket) bucket.push(p)
      else buckets.set(group, [p])
    }

    return current.schema.groupBy.order
      .filter((g) => buckets.get(g)?.length)
      .map((g) => ({ group: g, products: buckets.get(g)! }))
  })

  /** 点击同一字段循环切换 升序 → 降序 → 默认 */
  function toggleSort(key: string) {
    if (sortKey.value !== key) {
      sortKey.value = key
      sortDirection.value = 'asc'
      return
    }
    sortDirection.value =
      sortDirection.value === 'asc' ? 'desc' : sortDirection.value === 'desc' ? 'default' : 'asc'
    if (sortDirection.value === 'default') sortKey.value = null
  }

  return {
    activeGroup,
    activeFacets,
    keyword,
    sortKey,
    sortDirection,
    sortableFields,
    groupCounts,
    facetCounts,
    setFacet,
    filtered,
    isGrouped,
    groupedList,
    toggleSort,
  }
}
