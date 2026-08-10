<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import type { CategoryData } from '../types'
import { loadCategory } from '../data'
import { numberOf } from '../format'
import { useProductFilter } from '../useProductFilter'
import { useCompare } from '../useCompare'
import FilterBar from '../components/FilterBar.vue'
import ProductCard from '../components/ProductCard.vue'
import CompareDrawer from '../components/CompareDrawer.vue'

const route = useRoute()
const categoryId = computed(() => String(route.params.categoryId))

const data = ref<CategoryData | null>(null)
const error = ref<string | null>(null)

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

watch(
  categoryId,
  async (id) => {
    data.value = null
    error.value = null
    resetCompare()
    try {
      data.value = await loadCategory(id)
    } catch (e) {
      error.value = e instanceof Error ? e.message : '数据加载失败'
    }
  },
  { immediate: true },
)

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
    `收录 ${current.products.length} 款`,
    `显示 ${filtered.value.length} 款`,
  ]

  if (values.length) {
    const avg = Math.round(values.reduce((s, v) => s + v, 0) / values.length)
    items.push(`均值 ${prefix}${avg}`)
    items.push(`${prefix}${Math.min(...values)} ~ ${prefix}${Math.max(...values)}`)
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
  if (compareCount.value === 0) return
  compareOpen.value = true
}
</script>

<template>
  <div class="page">
    <header class="head">
      <div class="container head-inner">
        <RouterLink to="/" class="back" aria-label="返回首页">‹</RouterLink>
        <div class="titles">
          <h1>{{ data?.schema.name ?? '加载中' }}</h1>
          <p v-if="data">{{ data.schema.subtitle }}</p>
        </div>
      </div>
      <div v-if="data" class="container stats">
        <span v-for="s in stats" :key="s" class="stat">{{ s }}</span>
      </div>
    </header>

    <FilterBar
      v-if="data"
      v-model:active-group="activeGroup"
      v-model:keyword="keyword"
      :group-by="data.schema.groupBy"
      :group-counts="groupCounts"
      :total-count="data.products.length"
      :sort-key="sortKey"
      :sort-direction="sortDirection"
      :sortable-fields="sortableFields"
      @toggle-sort="toggleSort"
    />

    <main class="container body">
      <p v-if="error" class="notice">{{ error }}</p>
      <p v-else-if="!data" class="notice">正在加载数据...</p>

      <template v-else-if="isGrouped">
        <section v-for="g in groupedList" :key="g.group">
          <h2 class="group-title">
            <span
              class="dot"
              :style="{ background: data.schema.groupBy.colors[g.group] ?? '#999' }"
              aria-hidden="true"
            ></span>
            {{ g.group }} ({{ g.products.length }}款)
          </h2>
          <div class="grid">
            <ProductCard
              v-for="p in g.products"
              :key="p.id"
              :product="p"
              :schema="data.schema"
              :show-group-badge="false"
              :selected="isSelected(p.id)"
              @toggle-compare="onToggleCompare"
            />
          </div>
        </section>
      </template>

      <div v-else-if="filtered.length" class="grid">
        <ProductCard
          v-for="p in filtered"
          :key="p.id"
          :product="p"
          :schema="data.schema"
          :show-group-badge="true"
          :selected="isSelected(p.id)"
          @toggle-compare="onToggleCompare"
        />
      </div>

      <p v-else class="notice">没有匹配的产品</p>

      <section v-if="data?.schema.guide" class="guide">
        <h2>{{ data.schema.guide.title }}</h2>
        <ul>
          <li v-for="item in data.schema.guide.items" :key="item.scene">
            <b>{{ item.scene }}：</b>{{ item.advice }}
          </li>
        </ul>
      </section>
    </main>

    <Transition name="fade">
      <button v-if="compareCount > 0" class="fab" @click="openCompare">
        <span aria-hidden="true">⚖</span>
        <span class="fab-text">对比</span>
        <span class="fab-badge">{{ compareCount }}</span>
      </button>
    </Transition>

    <Transition name="fade">
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
  padding-bottom: 80px;
}

.head {
  background: linear-gradient(135deg, var(--header-from), var(--header-to));
  color: #fff;
  position: sticky;
  top: 0;
  z-index: 200;
  box-shadow: 0 2px 8px rgb(0 0 0 / 25%);
  padding-block: 8px 6px;
}

.head-inner {
  display: flex;
  align-items: center;
  gap: 8px;
}

.back {
  font-size: 24px;
  line-height: 1;
  width: 26px;
  height: 26px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 6px;
  background: rgb(255 255 255 / 12%);
  flex-shrink: 0;
}

.titles h1 {
  font-size: 15px;
  font-weight: 700;
  line-height: 1.3;
}

.titles p {
  font-size: 10px;
  opacity: 0.6;
}

.stats {
  display: flex;
  gap: 5px;
  flex-wrap: wrap;
  margin-top: 5px;
}

.stat {
  background: rgb(255 255 255 / 12%);
  border-radius: 6px;
  padding: 2px 7px;
  font-size: 10px;
}

.body {
  padding-top: 8px;
}

.group-title {
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: 12px;
  font-weight: 700;
  color: var(--text-muted);
  padding: 10px 2px 6px;
}

.dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  flex-shrink: 0;
}

.grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: 6px;
}

.notice {
  text-align: center;
  padding: 40px 16px;
  color: var(--text-faint);
  font-size: 12px;
}

.guide {
  background: var(--surface);
  border-radius: var(--radius);
  padding: 12px 14px;
  margin-top: 14px;
  box-shadow: var(--shadow-sm);
}

.guide h2 {
  font-size: 12.5px;
  font-weight: 700;
  margin-bottom: 8px;
}

.guide ul {
  list-style: none;
  display: grid;
  gap: 6px;
}

.guide li {
  font-size: 11px;
  line-height: 1.6;
  color: var(--text-muted);
  padding-left: 10px;
  position: relative;
}

.guide li::before {
  content: '•';
  position: absolute;
  left: 0;
  color: var(--brand);
}

.guide b {
  color: var(--text);
}

.fab {
  position: fixed;
  right: 16px;
  bottom: 20px;
  z-index: 300;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 1px;
  width: 52px;
  height: 52px;
  border-radius: 50%;
  border: none;
  background: var(--brand);
  color: #fff;
  font-size: 16px;
  box-shadow: 0 4px 14px rgb(108 92 231 / 45%);
}

.fab-text {
  font-size: 9px;
  font-weight: 600;
}

.fab-badge {
  position: absolute;
  top: -3px;
  right: -3px;
  min-width: 18px;
  height: 18px;
  border-radius: 9px;
  background: var(--danger);
  color: #fff;
  font-size: 10px;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0 4px;
}

.toast {
  position: fixed;
  left: 50%;
  bottom: 86px;
  transform: translateX(-50%);
  z-index: 350;
  background: rgb(0 0 0 / 82%);
  color: #fff;
  font-size: 11.5px;
  padding: 7px 14px;
  border-radius: 16px;
  white-space: nowrap;
}

.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.2s;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}

/* 桌面端多列网格 */
@media (min-width: 640px) {
  .grid {
    grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
    gap: 10px;
  }

  .titles h1 {
    font-size: 18px;
  }

  .titles p {
    font-size: 11px;
  }
}

@media (min-width: 1024px) {
  .grid {
    grid-template-columns: repeat(auto-fill, minmax(360px, 1fr));
  }

  .guide li {
    font-size: 12px;
  }
}
</style>
