<script setup lang="ts">
import { computed, ref, watch, onMounted, onBeforeUnmount, nextTick } from 'vue'
import type { CSSProperties } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import type { CategoryData } from '../types'
import { loadCategory } from '../data'
import { numberOf } from '../format'
import { useProductFilter } from '../useProductFilter'
import { useCompare } from '../useCompare'
import { useScrollReveal } from '../useScrollReveal'
import FilterBar from '../components/FilterBar.vue'
import ProductCard from '../components/ProductCard.vue'
import TimelineView from '../components/TimelineView.vue'
import CompareDrawer from '../components/CompareDrawer.vue'

const route = useRoute()
const categoryId = computed(() => String(route.params.categoryId))

const data = ref<CategoryData | null>(null)
const error = ref<string | null>(null)

/** 视图模式：经典网格 / 时间轴 */
const viewMode = ref<'classic' | 'timeline'>('classic')

/** 时间轴方向：desc = 从晚到早（默认），asc = 从早到晚 */
const timelineOrder = ref<'asc' | 'desc'>('desc')

const {
  count: compareCount,
  max: compareMax,
  pinnedId,
  diffOnly,
  isOpen: compareOpen,
  isSelected,
  toggle: toggleCompareId,
  remove: removeFromCompare,
  pin: pinProduct,
  resetCompare,
  resolveProducts,
} = useCompare()

const { setup: setupReveal } = useScrollReveal()

watch(
  categoryId,
  async (id) => {
    data.value = null
    error.value = null
    resetCompare()
    try {
      data.value = await loadCategory(id)
      // 数据加载后重新设置滚动监听
      requestAnimationFrame(() => setupReveal())
    } catch (e) {
      error.value = e instanceof Error ? e.message : '数据加载失败'
    }
  },
  { immediate: true },
)

// 切换视图模式后重新设置滚动监听，避免新渲染的 .reveal 元素丢失
watch(viewMode, () => {
  requestAnimationFrame(() => setupReveal())
})

const {
  activeGroup,
  keyword,
  sortKey,
  sortDirection,
  sortableFields,
  groupCounts,
  filtered,
  isGrouped,
  groupedList,
  toggleSort,
} = useProductFilter(data)

// 排序/分组状态变化导致分组容器被重建时也要重设监听
// 否则从平铺切回分组视图后，section.reveal 不会被观察、未滚动到的组保持 opacity:0
watch(isGrouped, () => {
  requestAnimationFrame(() => setupReveal())
})

const compareProducts = computed(() =>
  data.value ? resolveProducts(data.value.products) : [],
)

/** 顶部统计：总数、当前显示数，以及主指标的均值与区间 */
const stats = computed(() => {
  const current = data.value
  if (!current) return []

  const metric = current.schema.primaryMetric
  const field = current.schema.fields.find((f) => f.key === metric)
  const prefix = field?.prefix ?? ''
  const values = filtered.value
    .map((p) => numberOf(p, metric))
    .filter((v): v is number => v !== null)

  const items = [
    { label: '收录', value: `${current.products.length}`, unit: '款' },
    { label: '显示', value: `${filtered.value.length}`, unit: '款' },
  ]

  if (values.length) {
    const avg = Math.round(values.reduce((s, v) => s + v, 0) / values.length)
    items.push({ label: '均值', value: `${prefix}${avg}`, unit: '' })
    items.push({ label: '区间', value: `${prefix}${Math.min(...values)}~${prefix}${Math.max(...values)}`, unit: '' })
  }

  return items
})

const overLimitHint = ref(false)

function onToggleCompare(id: string) {
  if (!toggleCompareId(id)) {
    overLimitHint.value = true
    setTimeout(() => (overLimitHint.value = false), 2000)
  }
}

function openCompare() {
  compareOpen.value = true
}

// ============================================
// 动态同步 header 实际高度到 --header-h 变量
// 使 FilterBar 的 sticky top 能精确匹配 header 高度
// ============================================
const headerRef = ref<HTMLElement | null>(null)

function syncHeaderHeight() {
  if (headerRef.value) {
    const h = headerRef.value.offsetHeight
    document.documentElement.style.setProperty('--header-h', `${h}px`)
  }
}

onMounted(() => {
  syncHeaderHeight()
  window.addEventListener('resize', syncHeaderHeight)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', syncHeaderHeight)
})

// 数据加载后 header 内容变化（统计行出现），需重新同步
watch(data, () => {
  nextTick(syncHeaderHeight)
})

// ============================================
// 全局对比浮标（FAB）：始终显示，默认左侧，可长按拖动到任意位置
// ============================================
const fabRef = ref<HTMLElement | null>(null)
const fabDragging = ref(false)
const fabPos = ref<{ x: number; y: number } | null>(null)
let fabOff = { x: 0, y: 0 }
let fabStart = { x: 0, y: 0 }
let fabPressed = false
const FAB_DRAG_THRESHOLD = 6

const FAB_POS_KEY = 'compareFabPos'
const FAB_SIZE = 56

// 读取持久化的位置
try {
  const raw = localStorage.getItem(FAB_POS_KEY)
  if (raw) {
    const p = JSON.parse(raw)
    if (typeof p?.x === 'number' && typeof p?.y === 'number') fabPos.value = p
  }
} catch {
  /* 忽略损坏的存储 */
}

const fabStyle = computed<CSSProperties>(() => ({
  position: 'fixed',
  right: 'auto',
  transform: 'none',
  ...(fabPos.value
    ? { left: `${fabPos.value.x}px`, top: `${fabPos.value.y}px`, bottom: 'auto' }
    : { left: '16px', bottom: '24px', top: 'auto' }),
}))

/**
 * 按下即准备：一旦指针移动超过阈值立即进入拖动态（无长按延迟，跟手）。
 * 若全程未达阈值则视为点击，打开对比抽屉。
 */
function onFabDown(e: PointerEvent) {
  if (e.pointerType === 'mouse' && e.button !== 0) return
  fabPressed = true
  fabStart = { x: e.clientX, y: e.clientY }
  fabDragging.value = false
  window.addEventListener('pointermove', onFabMove)
  window.addEventListener('pointerup', onFabUp, { once: true })
  window.addEventListener('pointercancel', onFabUp, { once: true })
}

function onFabMove(e: PointerEvent) {
  if (!fabPressed) return
  if (!fabDragging.value) {
    const dx = e.clientX - fabStart.x
    const dy = e.clientY - fabStart.y
    if (Math.hypot(dx, dy) < FAB_DRAG_THRESHOLD) return
    // 越过阈值，进入拖动态：以当前指针与浮标左上角的偏移为基准
    fabDragging.value = true
    const r = (fabRef.value as HTMLElement).getBoundingClientRect()
    fabOff = { x: e.clientX - r.left, y: e.clientY - r.top }
  }
  e.preventDefault()
  const x = Math.max(0, Math.min(e.clientX - fabOff.x, window.innerWidth - FAB_SIZE))
  const y = Math.max(0, Math.min(e.clientY - fabOff.y, window.innerHeight - FAB_SIZE))
  fabPos.value = { x, y }
}

function onFabUp() {
  window.removeEventListener('pointermove', onFabMove)
  if (!fabPressed) return
  fabPressed = false
  if (fabDragging.value) {
    fabDragging.value = false
    try {
      localStorage.setItem(FAB_POS_KEY, JSON.stringify(fabPos.value))
    } catch {
      /* 忽略写入失败 */
    }
  } else {
    openCompare()
  }
}
</script>

<template>
  <div class="page">
    <!-- 动画头部 -->
    <header ref="headerRef" class="head header-gradient">
      <div class="head-bg" aria-hidden="true">
        <span class="orb orb-a"></span>
        <span class="orb orb-b"></span>
      </div>

      <div class="container head-inner">
        <RouterLink to="/" class="back" aria-label="返回首页">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
            <path d="M15 18l-6-6 6-6" />
          </svg>
        </RouterLink>
        <div class="titles">
          <h1>{{ data?.schema.name ?? '加载中' }}</h1>
          <p v-if="data">{{ data.schema.subtitle }}</p>
        </div>
      </div>

      <div v-if="data" class="container stats">
        <div
          v-for="(s, i) in stats"
          :key="s.label"
          class="stat"
          :style="{ animationDelay: `${0.15 + i * 0.08}s` }"
        >
          <span class="stat-label">{{ s.label }}</span>
          <span class="stat-value">{{ s.value }}<small v-if="s.unit">{{ s.unit }}</small></span>
        </div>
      </div>
    </header>

    <FilterBar
      v-if="data"
      v-model:active-group="activeGroup"
      v-model:keyword="keyword"
      v-model:view-mode="viewMode"
      :group-by="data.schema.groupBy"
      :group-counts="groupCounts"
      :total-count="data.products.length"
      :sort-key="sortKey"
      :sort-direction="sortDirection"
      :sortable-fields="sortableFields"
      :timeline-order="timelineOrder"
      @toggle-sort="toggleSort"
      @update:timeline-order="timelineOrder = $event"
    />

    <main class="container body">
      <p v-if="error" class="notice">{{ error }}</p>
      <div v-else-if="!data" class="loading">
        <span class="spinner"></span>
        <p>正在加载数据...</p>
      </div>

      <template v-else>
        <!-- 时间轴模式 -->
        <TimelineView
          v-if="viewMode === 'timeline'"
          :products="filtered"
          :schema="data.schema"
          :selected="isSelected"
          :order-dir="timelineOrder"
          @toggle-compare="onToggleCompare"
        />

        <!-- 经典模式 -->
        <template v-else-if="isGrouped">
          <section v-for="g in groupedList" :key="g.group" class="reveal">
            <h2 class="group-title">
              <span
                class="dot"
                :style="{ background: data.schema.groupBy.colors[g.group] ?? '#999' }"
                aria-hidden="true"
              ></span>
              {{ g.group }}
              <span class="group-count">{{ g.products.length }} 款</span>
            </h2>
            <div class="grid">
              <ProductCard
                v-for="(p, idx) in g.products"
                :key="p.id"
                :product="p"
                :schema="data.schema"
                :show-group-badge="false"
                :selected="isSelected(p.id)"
                :index="idx"
                @toggle-compare="onToggleCompare"
              />
            </div>
          </section>
        </template>

        <div v-else-if="filtered.length" class="grid">
          <ProductCard
            v-for="(p, idx) in filtered"
            :key="p.id"
            :product="p"
            :schema="data.schema"
            :show-group-badge="true"
            :selected="isSelected(p.id)"
            :index="idx"
            @toggle-compare="onToggleCompare"
          />
        </div>

        <p v-else class="notice">没有匹配的产品</p>

        <section v-if="data.schema.guide" class="guide guide-surface reveal">
          <div class="guide-head">
            <svg class="guide-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <circle cx="12" cy="12" r="10" />
              <path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3" />
              <line x1="12" y1="17" x2="12.01" y2="17" />
            </svg>
            <h2>{{ data.schema.guide.title }}</h2>
          </div>
          <ul>
            <li v-for="item in data.schema.guide.items" :key="item.scene">
              <b>{{ item.scene }}</b>{{ item.advice }}
            </li>
          </ul>
        </section>
      </template>
    </main>

    <!-- FAB -->
    <Transition name="fab">
      <button
        ref="fabRef"
        class="fab"
        :class="{ dragging: fabDragging }"
        :style="fabStyle"
        @pointerdown="onFabDown"
      >
        <span class="fab-icon" aria-hidden="true">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M3 6h18M3 12h18M3 18h18" />
          </svg>
        </span>
        <span class="fab-text">对比</span>
        <span v-if="compareCount > 0" class="fab-badge">{{ compareCount }}</span>
      </button>
    </Transition>

    <!-- Toast -->
    <Transition name="toast">
      <p v-if="overLimitHint" class="toast" role="status">
        最多可同时对比 {{ compareMax }} 款
      </p>
    </Transition>

    <CompareDrawer
      v-if="data"
      v-model:diff-only="diffOnly"
      :open="compareOpen"
      :products="compareProducts"
      :schema="data.schema"
      :pinned-id="pinnedId"
      @close="compareOpen = false"
      @remove="removeFromCompare"
      @pin="pinProduct"
    />
  </div>
</template>

<style scoped>
.page {
  padding-bottom: 100px;
}

/* ============ 头部 ============ */
.head {
  position: relative;
  background: var(--header-gradient);
  background-size: 200% 200%;
  color: var(--header-text);
  position: sticky;
  top: 0;
  z-index: 200;
  box-shadow: 0 4px 24px rgba(0, 0, 0, 0.15);
  padding-block: 12px 10px;
  overflow: hidden;
  animation: gradientFlow 12s ease infinite;
}

.head-bg {
  position: absolute;
  inset: 0;
  pointer-events: none;
}

.orb {
  position: absolute;
  border-radius: 50%;
  filter: blur(30px);
}

.orb-a {
  width: 200px;
  height: 200px;
  background: var(--header-orb-1);
  top: -40px;
  right: -20px;
  animation: orbDrift1 14s ease-in-out infinite;
}

.orb-b {
  width: 150px;
  height: 150px;
  background: var(--header-orb-2);
  bottom: -30px;
  left: 30%;
  animation: orbDrift2 18s ease-in-out infinite;
}

.head-inner {
  position: relative;
  display: grid;
  grid-template-columns: 36px 1fr 36px;
  align-items: center;
}

.back {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border-radius: var(--radius-sm);
  background: var(--header-surface);
  backdrop-filter: blur(8px);
  border: 1px solid var(--header-surface-border);
  flex-shrink: 0;
  justify-self: start;
  transition: background var(--dur-fast) var(--ease-smooth),
              transform var(--dur-fast) var(--ease-spring);
}

.titles {
  grid-column: 2;
  text-align: center;
}

.back svg {
  width: 18px;
  height: 18px;
}

.back:hover {
  background: var(--header-surface);
  filter: brightness(1.3);
  transform: translateX(-3px);
}

.back:active {
  transform: translateX(-3px) scale(0.95);
}

.titles h1 {
  font-size: 18px;
  font-weight: 700;
  line-height: 1.3;
  animation: fadeInUp 0.5s var(--ease-out) both;
}

.titles p {
  font-size: 11px;
  color: var(--header-text-muted);
  animation: fadeInUp 0.5s var(--ease-out) 0.1s both;
}

/* ============ 统计 ============ */
.stats {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  justify-content: center;
  margin-top: 8px;
  position: relative;
}

.stat {
  display: flex;
  flex-direction: column;
  gap: 1px;
  background: var(--header-surface);
  backdrop-filter: blur(8px);
  border: 1px solid var(--header-surface-border);
  border-radius: var(--radius-sm);
  padding: 6px 12px;
  animation: fadeInUp 0.5s var(--ease-out) both;
  transition: background var(--dur-fast) var(--ease-smooth);
}

.stat:hover {
  filter: brightness(1.25);
}

.stat-label {
  font-size: 9px;
  color: var(--header-text-muted);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.stat-value {
  font-size: 14px;
  font-weight: 700;
}

.stat-value small {
  font-size: 10px;
  font-weight: 500;
  color: var(--header-text-muted);
  margin-left: 1px;
}

/* ============ 主体 ============ */
.body {
  padding-top: 12px;
}

.loading {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 16px;
  padding: 60px 16px;
  color: var(--text-faint);
}

.spinner {
  width: 32px;
  height: 32px;
  border: 3px solid var(--border);
  border-top-color: var(--brand);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

.group-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  font-weight: 700;
  color: var(--text-muted);
  padding: 14px 4px 8px;
}

.dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
  box-shadow: 0 0 0 3px var(--surface);
}

.group-count {
  font-size: 11px;
  color: var(--text-faint);
  font-weight: 500;
  margin-left: 2px;
}

.grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: 10px;
}

.notice {
  text-align: center;
  padding: 48px 16px;
  color: var(--text-faint);
  font-size: 13px;
}

/* ============ 选购指南 ============ */
.guide {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 20px;
  margin-top: 20px;
  box-shadow: var(--shadow-sm);
}

.guide-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}

.guide-icon {
  width: 18px;
  height: 18px;
  color: var(--brand);
}

.guide h2 {
  font-size: 14px;
  font-weight: 700;
}

.guide ul {
  list-style: none;
  display: grid;
  gap: 8px;
}

.guide li {
  font-size: 12px;
  line-height: 1.6;
  color: var(--text-muted);
  padding-left: 14px;
  position: relative;
}

.guide li::before {
  content: '';
  position: absolute;
  left: 0;
  top: 7px;
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: var(--brand);
}

.guide b {
  color: var(--text);
  font-weight: 600;
}

/* ============ FAB ============ */
.fab {
  position: fixed;
  z-index: 300;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 1px;
  width: 56px;
  height: 56px;
  border-radius: var(--radius-full);
  background: var(--brand-gradient);
  color: #fff;
  font-size: 16px;
  box-shadow: var(--shadow-brand-lg);
  animation: fabPulse 2.5s ease-in-out infinite;
  transition: transform var(--dur-fast) var(--ease-spring);
  touch-action: none; /* 长按拖动时禁止页面滚动 */
  cursor: grab;
  user-select: none;
}

.fab.dragging {
  animation: none;
  transition: none;
  cursor: grabbing;
  box-shadow: 0 12px 30px rgba(99, 102, 241, 0.5);
}

.fab:hover {
  filter: brightness(1.08);
}

.fab:active {
  filter: brightness(0.95);
}

.fab-icon svg {
  width: 20px;
  height: 20px;
}

.fab-text {
  font-size: 9px;
  font-weight: 600;
}

.fab-badge {
  position: absolute;
  top: -4px;
  right: -4px;
  min-width: 20px;
  height: 20px;
  border-radius: var(--radius-full);
  background: var(--danger);
  color: #fff;
  font-size: 11px;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0 5px;
  border: 2px solid var(--bg);
  animation: bounce 1s ease infinite;
}

/* ============ Toast ============ */
.toast {
  position: fixed;
  left: 50%;
  bottom: 92px;
  transform: translateX(-50%);
  z-index: 350;
  background: rgba(0, 0, 0, 0.85);
  backdrop-filter: blur(12px);
  color: #fff;
  font-size: 12px;
  padding: 8px 16px;
  border-radius: var(--radius-full);
  white-space: nowrap;
  box-shadow: var(--shadow-lg);
}

/* ============ 过渡动画 ============ */
.fab-enter-active {
  transition: transform var(--dur-normal) var(--ease-spring),
              opacity var(--dur-normal) var(--ease-smooth);
}

.fab-leave-active {
  transition: transform var(--dur-fast) var(--ease-smooth),
              opacity var(--dur-fast) var(--ease-smooth);
}

.fab-enter-from {
  transform: scale(0) translateY(20px);
  opacity: 0;
}

.fab-leave-to {
  transform: scale(0) translateY(20px);
  opacity: 0;
}

.toast-enter-active,
.toast-leave-active {
  transition: opacity var(--dur-normal) var(--ease-smooth),
              transform var(--dur-normal) var(--ease-spring);
}

.toast-enter-from {
  opacity: 0;
  transform: translateX(-50%) translateY(10px);
}

.toast-leave-to {
  opacity: 0;
  transform: translateX(-50%) translateY(-10px);
}

/* ============ 响应式 ============ */
@media (min-width: 640px) {
  .grid {
    grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
    gap: 12px;
  }

  .titles h1 {
    font-size: 22px;
  }

  .titles p {
    font-size: 12px;
  }

  .guide li {
    font-size: 13px;
  }
}

@media (min-width: 1024px) {
  .grid {
    grid-template-columns: repeat(auto-fill, minmax(380px, 1fr));
  }
}
</style>
