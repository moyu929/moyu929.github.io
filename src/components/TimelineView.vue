<script setup lang="ts">
import { computed, ref, onMounted, onBeforeUnmount } from 'vue'
import type { CategorySchema, Product, FieldDef } from '../types'
import { formatValue, tagsOf, numberOf } from '../format'
import { imageUrl } from '../data'
import { useScrollReveal } from '../useScrollReveal'

const props = defineProps<{
  products: Product[]
  schema: CategorySchema
  selected: (id: string) => boolean
  orderDir: 'asc' | 'desc'
}>()

const emit = defineEmits<{ toggleCompare: [id: string] }>()

useScrollReveal()

/** 卡片上展示的字段（与 ProductCard 的 grid slot 一致） */
const gridFields = computed(() => props.schema.fields.filter((f) => f.card === 'grid'))
const chipFields = computed(() => props.schema.fields.filter((f) => f.card === 'chip'))
const tagFields = computed(() => props.schema.fields.filter((f) => f.card === 'tag'))

/** 按年份分组，依据 orderDir 决定升序 / 降序；同一年内部按月份排序，无月份沉底 */
const yearGroups = computed(() => {
  const yearKey = 'year'
  const buckets = new Map<number, Product[]>()

  for (const p of props.products) {
    const yr = numberOf(p, yearKey)
    const key = yr ?? 0
    const bucket = buckets.get(key)
    if (bucket) bucket.push(p)
    else buckets.set(key, [p])
  }

  const factor = props.orderDir === 'desc' ? -1 : 1
  return Array.from(buckets.entries())
    .sort((a, b) => factor * (b[0] - a[0]))
    .map(([year, items]) => ({ year, products: sortByMonth(items, factor) }))
})

/**
 * 同一年内按上市月份排序。
 * - 有月份：数值升/降序（随时间轴整体方向）
 * - 无月份（null/非数字）：始终排在该年最后面
 */
function sortByMonth(items: Product[], factor: number): Product[] {
  const monthOf = (p: Product) => {
    const m = numberOf(p, 'month')
    return m === null ? Infinity : m
  }
  // 保留原始顺序用于稳定排序
  return items
    .map((p, i) => ({ p, i, m: monthOf(p) }))
    .sort((a, b) => {
      if (a.m === Infinity && b.m === Infinity) return a.i - b.i
      if (a.m === Infinity) return 1 // 无月份沉底
      if (b.m === Infinity) return -1
      const cmp = factor * (a.m - b.m)
      return cmp !== 0 ? cmp : a.i - b.i
    })
    .map((x) => x.p)
}

/** 每个产品在时间轴上的侧边：left / right 交替 */
function sideOf(yearIndex: number, productIndex: number): 'left' | 'right' {
  return (yearIndex + productIndex) % 2 === 0 ? 'left' : 'right'
}

// ============================================
// 悬停详情弹窗 —— position:fixed 动态定位
// ============================================
const hoveredProduct = ref<Product | null>(null)
const popStyle = ref<Record<string, string>>({})
let hideTimer: ReturnType<typeof setTimeout> | null = null

function onCardEnter(p: Product, event: MouseEvent) {
  if (hideTimer) {
    clearTimeout(hideTimer)
    hideTimer = null
  }
  // currentTarget 在事件传播结束后会被置 null，必须在此处捕获
  const card = event.currentTarget as HTMLElement
  updatePopPosition(card)
  hoveredProduct.value = p
}

function onCardLeave() {
  hideTimer = setTimeout(() => {
    hoveredProduct.value = null
  }, 200)
}

function onPopupEnter() {
  if (hideTimer) {
    clearTimeout(hideTimer)
    hideTimer = null
  }
}

function onPopupLeave() {
  hideTimer = setTimeout(() => {
    hoveredProduct.value = null
  }, 200)
}

/** 根据卡片位置计算弹窗的最佳位置（始终在视口内） */
function updatePopPosition(card: HTMLElement) {
  const rect = card.getBoundingClientRect()
  const vw = window.innerWidth
  const vh = window.innerHeight
  const gap = 10
  const margin = 14
  const popW = vw >= 768 ? 340 : Math.min(290, vw - margin * 2)

  // 水平：以卡片中心为基准居中，然后 clamp 到视口内
  let left = rect.left + rect.width / 2 - popW / 2
  left = Math.max(margin, Math.min(left, vw - popW - margin))

  // 垂直：优先在卡片下方
  const top = rect.bottom + gap
  const maxH = Math.max(180, vh - top - margin)

  popStyle.value = {
    position: 'fixed',
    top: `${top}px`,
    left: `${left}px`,
    width: `${popW}px`,
    maxWidth: `${vw - margin * 2}px`,
    maxHeight: `${maxH}px`,
    zIndex: '1000',
  }
}

// 滚动 / 缩放时隐藏弹窗
function onHide() {
  hoveredProduct.value = null
}

onMounted(() => {
  window.addEventListener('scroll', onHide, { passive: true })
  window.addEventListener('resize', onHide, { passive: true })
})

onBeforeUnmount(() => {
  window.removeEventListener('scroll', onHide)
  window.removeEventListener('resize', onHide)
  if (hideTimer) clearTimeout(hideTimer)
})

function groupOf(p: Product) {
  return String(p[props.schema.groupBy.key] ?? '')
}

function groupColor(p: Product) {
  return props.schema.groupBy.colors[groupOf(p)] ?? '#999'
}

/** 年份产品计数 */
function yearCount(g: { products: Product[] }) {
  return g.products.length
}

/** 产品上市月份标签，无月份返回空串（不展示） */
function monthLabel(p: Product): string {
  const m = numberOf(p, 'month')
  return m === null ? '' : `${m} 月`
}

/** 参数值：year 字段若有月份则附加「N月」 */
function valueWithMonth(field: FieldDef, p: Product): string {
  const base = formatValue(field, p)
  if (field.key !== 'year') return base
  const m = numberOf(p, 'month')
  return m === null ? base : `${base}${m}月`
}
</script>

<template>
  <div class="timeline">
    <!-- 无数据 -->
    <p v-if="!yearGroups.length" class="empty">没有匹配的产品</p>

    <!-- 时间轴主体 -->
    <div v-else class="track">
      <!-- 顶部渐隐 -->
      <div class="track-fade top" aria-hidden="true"></div>

      <section
        v-for="(g, yi) in yearGroups"
        :key="g.year"
        class="year-group reveal"
        :style="{ transitionDelay: `${yi * 0.08}s` }"
      >
        <!-- 年份标记 -->
        <div class="year-marker">
          <span class="year-dot" aria-hidden="true"></span>
          <span class="year-label">
            {{ g.year > 0 ? g.year : '未知' }}
            <small>{{ yearCount(g) }} 款</small>
          </span>
        </div>

        <!-- 该年份的产品 -->
        <div class="products">
          <div
            v-for="(p, pi) in g.products"
            :key="p.id"
            class="product-slot"
            :class="sideOf(yi, pi)"
          >
            <!-- 连接线 -->
            <span class="connector" aria-hidden="true"></span>

            <!-- 产品卡片（仅图片 + 名称） -->
            <div
              class="product-card"
              :class="{ selected: selected(p.id) }"
              @mouseenter="onCardEnter(p, $event)"
              @mouseleave="onCardLeave"
            >
              <div class="thumb">
                <img
                  v-if="imageUrl(schema, p)"
                  :src="imageUrl(schema, p)!"
                  :alt="p.name"
                  loading="lazy"
                  decoding="async"
                />
                <div v-else class="ph" aria-hidden="true">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z" />
                    <polyline points="3.27 6.96 12 12.01 20.73 6.96" />
                    <line x1="12" y1="22.08" x2="12" y2="12" />
                  </svg>
                </div>
                <span
                  class="tier-dot"
                  :style="{ background: groupColor(p) }"
                  :title="groupOf(p)"
                ></span>
              </div>
              <span class="name">{{ p.name }}</span>
              <span v-if="monthLabel(p)" class="month">{{ monthLabel(p) }}</span>
            </div>
          </div>
        </div>
      </section>

      <!-- 底部渐隐 -->
      <div class="track-fade bottom" aria-hidden="true"></div>
    </div>

    <!-- 悬停详情弹窗（固定定位，动态计算位置） -->
    <Transition name="pop">
      <div
        v-if="hoveredProduct"
        class="detail-pop"
        :style="popStyle"
        @mouseenter="onPopupEnter"
        @mouseleave="onPopupLeave"
      >
        <!-- 桥接间隙（防止鼠标从卡片移到弹窗时丢失悬停） -->
        <span class="pop-bridge" aria-hidden="true"></span>

        <div class="detail-inner">
          <!-- 标题行：产品名称、对比按钮、品质徽章 同行 -->
          <div class="detail-head">
            <h4>{{ hoveredProduct.name }}</h4>
            <button
              class="detail-cmp"
              :class="{ active: selected(hoveredProduct.id) }"
              @click.stop="emit('toggleCompare', hoveredProduct.id)"
            >
              <svg v-if="selected(hoveredProduct.id)" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round">
                <polyline points="20 6 9 17 4 12" />
              </svg>
              <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M3 6h18M3 12h18M3 18h18" />
              </svg>
              {{ selected(hoveredProduct.id) ? '已加入' : '对比' }}
            </button>
            <span
              class="detail-tier"
              :style="{ background: groupColor(hoveredProduct) }"
            >{{ groupOf(hoveredProduct) }}</span>
          </div>

          <!-- 价格胶囊 -->
          <div v-if="chipFields.length" class="detail-chips">
            <span v-for="f in chipFields" :key="f.key" class="d-chip">
              {{ f.label }} <b>{{ formatValue(f, hoveredProduct) }}</b>
            </span>
          </div>

          <!-- 参数网格 -->
          <dl v-if="gridFields.length" class="detail-params">
            <template v-for="f in gridFields" :key="f.key">
              <dt>{{ f.label }}</dt>
              <dd>{{ valueWithMonth(f, hoveredProduct) }}</dd>
            </template>
          </dl>

          <!-- 标签 -->
          <div v-if="tagFields.length" class="detail-tags">
            <template v-for="f in tagFields" :key="f.key">
              <span
                v-for="t in tagsOf(f, hoveredProduct)"
                :key="t"
                class="d-tag"
                :class="`tag-${f.tagVariant ?? 'blue'}`"
              >{{ f.tagPrefix ?? '' }}{{ t }}</span>
            </template>
          </div>
        </div>
      </div>
    </Transition>
  </div>
</template>

<style scoped>
.timeline {
  padding: 8px 0 32px;
}

.empty {
  text-align: center;
  padding: 48px 16px;
  color: var(--text-faint);
  font-size: 13px;
}

/* ============ 时间轴轨道 ============ */
.track {
  position: relative;
  max-width: 900px;
  margin: 0 auto;
  padding: 0 16px;
}

/* 中线 */
.track::before {
  content: '';
  position: absolute;
  left: 50%;
  top: 0;
  bottom: 0;
  width: 3px;
  margin-left: -1.5px;
  background: linear-gradient(
    to bottom,
    transparent 0%,
    var(--brand) 8%,
    var(--brand-light) 50%,
    var(--brand) 92%,
    transparent 100%
  );
  border-radius: 2px;
  opacity: 0.4;
}

/* 顶部/底部渐隐 */
.track-fade {
  position: absolute;
  left: 50%;
  transform: translateX(-50%);
  width: 3px;
  height: 40px;
  z-index: 2;
}

.track-fade.top {
  top: 0;
  background: linear-gradient(to bottom, var(--bg), transparent);
}

.track-fade.bottom {
  bottom: 0;
  background: linear-gradient(to top, var(--bg), transparent);
}

/* ============ 年份组 ============ */
.year-group {
  position: relative;
  margin-bottom: 16px;
}

.year-marker {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-bottom: 16px;
  z-index: 3;
}

.year-dot {
  width: 14px;
  height: 14px;
  border-radius: 50%;
  background: var(--brand-gradient);
  border: 3px solid var(--surface);
  box-shadow: 0 0 0 3px var(--brand-soft), var(--shadow-sm);
  flex-shrink: 0;
  position: relative;
  z-index: 2;
  animation: fadeInScale 0.4s var(--ease-spring) both;
}

.year-label {
  position: absolute;
  left: calc(50% + 16px);
  white-space: nowrap;
  font-size: 18px;
  font-weight: 800;
  color: var(--brand);
  letter-spacing: -0.02em;
  animation: fadeInLeft 0.4s var(--ease-out) 0.1s both;
}

.year-label small {
  font-size: 11px;
  font-weight: 500;
  color: var(--text-faint);
  margin-left: 6px;
}

/* ============ 产品槽位 ============ */
.products {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.product-slot {
  position: relative;
  display: flex;
  width: 50%;
}

.product-slot.left {
  justify-content: flex-end;
  padding-right: 28px;
}

.product-slot.right {
  justify-content: flex-start;
  padding-left: 28px;
  margin-left: 50%;
}

/* 连接线 */
.connector {
  position: absolute;
  top: 28px;
  width: 24px;
  height: 2px;
  background: var(--brand);
  opacity: 0.3;
}

.product-slot.left .connector {
  right: 4px;
}

.product-slot.right .connector {
  left: 4px;
}

/* ============ 产品卡片（精简：仅图片+名称） ============ */
.product-card {
  position: relative;
  display: flex;
  align-items: center;
  gap: 10px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 8px 12px;
  box-shadow: var(--shadow-sm);
  cursor: pointer;
  max-width: 280px;
  transition: transform var(--dur-normal) var(--ease-out),
              box-shadow var(--dur-normal) var(--ease-smooth),
              border-color var(--dur-normal) var(--ease-smooth);
  animation: fadeInUp 0.4s var(--ease-out) both;
}

.product-card:hover {
  transform: translateY(-2px);
  box-shadow: var(--shadow-md);
  border-color: var(--border-brand);
  z-index: 10;
}

.product-card.selected {
  border-color: var(--brand);
  box-shadow: 0 0 0 2px var(--brand-soft);
}

.thumb {
  position: relative;
  width: 48px;
  height: 56px;
  border-radius: var(--radius-xs);
  overflow: hidden;
  background: var(--surface-alt);
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
}

.thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  transition: transform var(--dur-slow) var(--ease-out);
}

.product-card:hover .thumb img {
  transform: scale(1.1);
}

.ph {
  color: var(--text-faint);
  opacity: 0.3;
}

.ph svg {
  width: 22px;
  height: 22px;
}

.tier-dot {
  position: absolute;
  bottom: 2px;
  right: 2px;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  border: 1.5px solid var(--surface);
}

.name {
  font-size: 12px;
  font-weight: 600;
  line-height: 1.3;
  color: var(--text);
  flex: 1;
  min-width: 0;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.month {
  margin-top: 3px;
  font-size: 10px;
  font-weight: 500;
  line-height: 1;
  color: var(--text-faint);
  flex-shrink: 0;
}

/* ============ 悬停详情弹窗（position:fixed 动态定位） ============ */
.detail-pop {
  overflow-y: auto;
  overflow-x: hidden;
  overscroll-behavior: contain;
  scrollbar-width: thin;
  scrollbar-color: var(--text-faint) transparent;
}

/* Vue Transition 动画类 */
.pop-enter-active {
  transition: opacity 0.15s var(--ease-out), transform 0.15s var(--ease-spring);
}
.pop-leave-active {
  transition: opacity 0.1s var(--ease-out);
}
.pop-enter-from {
  opacity: 0;
  transform: scale(0.92) translateY(-6px);
}
.pop-leave-to {
  opacity: 0;
}

.detail-pop::-webkit-scrollbar {
  width: 5px;
}

.detail-pop::-webkit-scrollbar-track {
  background: transparent;
}

.detail-pop::-webkit-scrollbar-thumb {
  background: var(--text-faint);
  border-radius: 3px;
  opacity: 0.3;
}

/* 桥接间隙：防止鼠标从卡片移到弹窗时丢失悬停 */
.pop-bridge {
  position: absolute;
  top: -12px;
  left: 0;
  right: 0;
  height: 12px;
  z-index: 1;
}

.detail-inner {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 14px;
  box-shadow: var(--shadow-lg);
  position: relative;
}

/* 上方小箭头 */
.detail-inner::before {
  content: '';
  position: absolute;
  top: -6px;
  left: 50%;
  transform: translateX(-50%) rotate(45deg);
  width: 12px;
  height: 12px;
  background: var(--surface);
  border-left: 1px solid var(--border);
  border-top: 1px solid var(--border);
}

/* 详情内部 */
.detail-head {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 8px;
}

.detail-head h4 {
  font-size: 13px;
  font-weight: 700;
  line-height: 1.3;
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.detail-tier {
  font-size: 9px;
  padding: 2px 6px;
  border-radius: var(--radius-xs);
  color: #fff;
  white-space: nowrap;
  flex-shrink: 0;
  font-weight: 600;
}

.detail-chips {
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
  margin-bottom: 8px;
}

.d-chip {
  background: var(--surface-alt);
  border-radius: var(--radius-xs);
  padding: 2px 7px;
  font-size: 10px;
  white-space: nowrap;
  color: var(--text-muted);
}

.d-chip b {
  color: var(--danger);
  font-weight: 700;
}

.detail-params {
  display: grid;
  grid-template-columns: auto 1fr;
  font-size: 10.5px;
  line-height: 1.7;
  margin-bottom: 8px;
}

.detail-params dt {
  color: var(--text-faint);
  white-space: nowrap;
  padding-right: 8px;
}

.detail-params dd {
  color: var(--text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.detail-tags {
  display: flex;
  gap: 3px;
  flex-wrap: wrap;
  margin-bottom: 10px;
}

.d-tag {
  font-size: 9px;
  padding: 1px 6px;
  border-radius: var(--radius-xs);
  line-height: 1.6;
  background: var(--tag-blue-bg);
  color: var(--tag-blue-fg);
  font-weight: 500;
}

.d-tag.tag-red {
  background: var(--tag-red-bg);
  color: var(--tag-red-fg);
}

.d-tag.tag-green {
  background: var(--tag-green-bg);
  color: var(--tag-green-fg);
}

.detail-cmp {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  flex-shrink: 0;
  font-size: 10.5px;
  padding: 4px 9px;
  border-radius: var(--radius-sm);
  border: 1.5px solid var(--brand);
  background: var(--brand-surface);
  color: var(--brand);
  font-weight: 600;
  white-space: nowrap;
  transition: all var(--dur-fast) var(--ease-spring);
}

.detail-cmp svg {
  width: 14px;
  height: 14px;
}

.detail-cmp:hover {
  background: var(--brand-soft);
}

.detail-cmp.active {
  background: var(--brand-gradient);
  color: #fff;
  border-color: transparent;
  box-shadow: var(--shadow-brand);
}

/* ============ 响应式 ============ */
@media (min-width: 768px) {
  .track {
    padding: 0 32px;
  }

  .product-card {
    max-width: 320px;
    padding: 10px 14px;
  }

  .thumb {
    width: 56px;
    height: 64px;
  }

  .name {
    font-size: 13px;
  }

  .detail-inner {
    padding: 16px;
  }

  .detail-head h4 {
    font-size: 14px;
  }

  .detail-params {
    font-size: 11.5px;
  }
}

/* 小屏：时间轴偏左，产品全在右侧 */
@media (max-width: 639px) {
  .track::before {
    left: 24px;
  }

  .year-marker {
    justify-content: flex-start;
    padding-left: 24px;
  }

  .year-label {
    position: static;
    transform: none;
  }

  .product-slot.left,
  .product-slot.right {
    width: 100%;
    margin-left: 0;
    padding-left: 52px;
    padding-right: 0;
    justify-content: flex-start;
  }

  .product-slot.left .connector,
  .product-slot.right .connector {
    left: 24px;
    right: auto;
  }

  .track-fade {
    left: 24px;
    transform: none;
  }
}
</style>
