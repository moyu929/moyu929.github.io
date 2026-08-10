import { computed, ref } from 'vue'
import type { Product } from './types'

const MAX_COMPARE = 6

/** 对比队列存产品 id，模块级状态，切换品类时由 resetCompare 清空 */
const queue = ref<string[]>([])
const pinnedId = ref<string | null>(null)
const diffOnly = ref(false)
const isOpen = ref(false)

const count = computed(() => queue.value.length)

function isSelected(id: string) {
  return queue.value.includes(id)
}

/** 返回 false 表示因超出上限而未加入 */
function toggle(id: string): boolean {
  const idx = queue.value.indexOf(id)
  if (idx >= 0) {
    queue.value.splice(idx, 1)
    if (pinnedId.value === id) pinnedId.value = null
    if (queue.value.length === 0) isOpen.value = false
    return true
  }
  if (queue.value.length >= MAX_COMPARE) return false
  queue.value.push(id)
  return true
}

function remove(id: string) {
  queue.value = queue.value.filter((n) => n !== id)
  if (pinnedId.value === id) pinnedId.value = null
  if (queue.value.length === 0) isOpen.value = false
}

/** 置顶：把该产品移到队首作为对比基准 */
function pin(id: string) {
  if (pinnedId.value === id) {
    pinnedId.value = null
    return
  }
  pinnedId.value = id
  queue.value = [id, ...queue.value.filter((n) => n !== id)]
}

/** 切换品类时调用，避免混入其他品类的产品 */
function resetCompare() {
  queue.value = []
  pinnedId.value = null
  isOpen.value = false
}

/** 按队列顺序取出产品对象 */
function resolveProducts(products: Product[]): Product[] {
  const byId = new Map(products.map((p) => [p.id, p]))
  return queue.value.map((id) => byId.get(id)).filter((p): p is Product => Boolean(p))
}

export function useCompare() {
  return {
    queue,
    count,
    max: MAX_COMPARE,
    pinnedId,
    diffOnly,
    isOpen,
    isSelected,
    toggle,
    remove,
    pin,
    resetCompare,
    resolveProducts,
  }
}
