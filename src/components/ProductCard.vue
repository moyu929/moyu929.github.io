<script setup lang="ts">
import { computed } from 'vue'
import type { CategorySchema, Product } from '../types'
import { formatValue, tagsOf, numberOf } from '../format'
import { imageUrl } from '../data'

const props = defineProps<{
  product: Product
  schema: CategorySchema
  /** 平铺展示时需要在卡片上显示分组徽章 */
  showGroupBadge: boolean
  selected: boolean
  /** 在列表中的索引，用于入场动画交错延迟 */
  index?: number
}>()

const emit = defineEmits<{ toggleCompare: [id: string] }>()

const fieldsBySlot = computed(() => {
  const slots = { title: [], chip: [], grid: [], tag: [] } as Record<
    'title' | 'chip' | 'grid' | 'tag',
    typeof props.schema.fields
  >
  for (const f of props.schema.fields) {
    if (f.card) slots[f.card].push(f)
  }
  return slots
})

/** 网格参数值：year 字段若有月份则附加「N月」 */
function valueWithMonth(field: typeof props.schema.fields[number], p: Product): string {
  const base = formatValue(field, p)
  if (field.key !== 'year') return base
  const m = numberOf(p, 'month')
  return m === null ? base : `${base}${m}月`
}

const groupName = computed(() => String(props.product[props.schema.groupBy.key] ?? ''))
const groupColor = computed(() => props.schema.groupBy.colors[groupName.value] ?? '#999')
const img = computed(() => imageUrl(props.schema, props.product))

const cardStyle = computed(() => ({
  animationDelay: props.index !== undefined ? `${Math.min(props.index * 0.05, 0.4)}s` : '0s',
}))
</script>

<template>
  <article class="card card-surface" :style="cardStyle">
    <button
      class="cmp-btn"
      :class="{ active: selected }"
      :aria-pressed="selected"
      @click="emit('toggleCompare', product.id)"
    >
      <svg v-if="selected" class="cmp-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round">
        <polyline points="20 6 9 17 4 12" />
      </svg>
      <svg v-else class="cmp-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M3 6h18M3 12h18M3 18h18" />
      </svg>
      {{ selected ? '已加入' : '对比' }}
    </button>

    <div class="top">
      <div class="thumb">
        <img v-if="img" :src="img" :alt="product.name" loading="lazy" decoding="async" />
        <span v-else class="no-img" aria-hidden="true">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
            <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z" />
            <polyline points="3.27 6.96 12 12.01 20.73 6.96" />
            <line x1="12" y1="22.08" x2="12" y2="12" />
          </svg>
        </span>
      </div>

      <div class="main">
        <div class="head">
          <h3>{{ product.name }}</h3>
          <span
            v-if="showGroupBadge"
            class="badge"
            :style="{ background: groupColor }"
          >{{ groupName }}</span>
        </div>

        <div class="chips">
          <span v-for="f in fieldsBySlot.chip" :key="f.key" class="chip">
            {{ f.label }} <b>{{ formatValue(f, product) }}</b>
          </span>
        </div>

        <dl class="params">
          <template v-for="f in fieldsBySlot.grid" :key="f.key">
            <dt>{{ f.label }}</dt>
            <dd>{{ valueWithMonth(f, product) }}</dd>
          </template>
        </dl>
      </div>
    </div>

    <div class="bottom">
      <div v-if="fieldsBySlot.tag.length" class="tags">
        <template v-for="f in fieldsBySlot.tag" :key="f.key">
          <span
            v-for="t in tagsOf(f, product)"
            :key="t"
            class="tag"
            :class="`tag-${f.tagVariant ?? 'blue'}`"
          >{{ f.tagPrefix ?? '' }}{{ t }}</span>
        </template>
      </div>
    </div>
  </article>
</template>

<style scoped>
.card {
  position: relative;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  overflow: hidden;
  box-shadow: var(--shadow-sm);
  display: flex;
  flex-direction: column;
  opacity: 0;
  animation: fadeInUp 0.5s var(--ease-out) forwards;
  transition: transform var(--dur-normal) var(--ease-out),
              box-shadow var(--dur-normal) var(--ease-smooth),
              border-color var(--dur-normal) var(--ease-smooth);
}

.card:hover {
  transform: translateY(-3px);
  box-shadow: var(--shadow-md);
  border-color: var(--border-brand);
}

.card:hover .thumb img {
  transform: scale(1.08);
}

.top {
  display: flex;
  padding: 12px;
  gap: 12px;
}

/* ============ 缩略图 ============ */
.thumb {
  position: relative;
  width: 80px;
  height: 96px;
  flex-shrink: 0;
  border-radius: var(--radius-sm);
  overflow: hidden;
  background: var(--surface-alt);
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

.no-img {
  color: var(--text-faint);
  opacity: 0.3;
}

.no-img svg {
  width: 32px;
  height: 32px;
}

/* ============ 主体内容 ============ */
.main {
  flex: 1;
  min-width: 0;
}

.head {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  margin-bottom: 5px;
  /* 给右上角的对比按钮留出空间，避免标题/徽章被遮挡 */
  padding-right: 64px;
}

.head h3 {
  font-size: 13.5px;
  font-weight: 700;
  line-height: 1.3;
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.badge {
  font-size: 9px;
  padding: 2px 6px;
  border-radius: var(--radius-xs);
  color: #fff;
  white-space: nowrap;
  flex-shrink: 0;
  font-weight: 600;
}

.chips {
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
  margin-bottom: 5px;
}

.chip {
  background: var(--surface-alt);
  border-radius: var(--radius-xs);
  padding: 2px 7px;
  font-size: 10px;
  white-space: nowrap;
  color: var(--text-muted);
  transition: background var(--dur-fast) var(--ease-smooth);
}

.card:hover .chip {
  background: var(--brand-surface);
}

.chip b {
  color: var(--danger);
  font-weight: 700;
}

.params {
  display: grid;
  grid-template-columns: auto 1fr;
  font-size: 10.5px;
  line-height: 1.7;
  margin-top: 2px;
}

.params dt {
  color: var(--text-faint);
  white-space: nowrap;
  padding-right: 8px;
}

.params dd {
  color: var(--text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* ============ 底部 ============ */
.bottom {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 0 12px 12px;
  margin-top: auto;
}

.tags {
  display: flex;
  gap: 3px;
  flex-wrap: wrap;
  flex: 1;
  min-width: 0;
}

.tag {
  font-size: 9px;
  padding: 1px 6px;
  border-radius: var(--radius-xs);
  line-height: 1.6;
  background: var(--tag-blue-bg);
  color: var(--tag-blue-fg);
  font-weight: 500;
  transition: transform var(--dur-fast) var(--ease-spring);
}

.tag:hover {
  transform: scale(1.05);
}

.tag-red {
  background: var(--tag-red-bg);
  color: var(--tag-red-fg);
}

.tag-green {
  background: var(--tag-green-bg);
  color: var(--tag-green-fg);
}

/* ============ 对比按钮（右上角浮层） ============ */
.cmp-btn {
  position: absolute;
  top: 10px;
  right: 10px;
  z-index: 2;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 10.5px;
  padding: 4px 10px;
  border-radius: var(--radius-full);
  border: 1.5px solid var(--brand);
  background: var(--brand-surface);
  color: var(--brand);
  font-weight: 600;
  white-space: nowrap;
  flex-shrink: 0;
  transition: all var(--dur-fast) var(--ease-spring);
}

.cmp-icon {
  width: 12px;
  height: 12px;
}

.cmp-btn:hover {
  background: var(--brand-soft);
  transform: scale(1.05);
}

.cmp-btn:active {
  transform: scale(0.95);
}

.cmp-btn.active {
  background: var(--brand-gradient);
  color: #fff;
  border-color: transparent;
  box-shadow: var(--shadow-brand);
}

.cmp-btn.active:hover {
  transform: scale(1.05);
}

/* ============ 响应式 ============ */
@media (min-width: 768px) {
  .top {
    padding: 16px;
    gap: 16px;
  }

  .thumb {
    width: 96px;
    height: 112px;
  }

  .head h3 {
    font-size: 15px;
  }

  .params {
    font-size: 11.5px;
  }

  .chip {
    font-size: 11px;
  }

  .tag {
    font-size: 10px;
  }

  .bottom {
    padding: 0 16px 16px;
  }

  .cmp-btn {
    font-size: 11.5px;
    padding: 5px 12px;
  }

  .cmp-icon {
    width: 14px;
    height: 14px;
  }
}
</style>
