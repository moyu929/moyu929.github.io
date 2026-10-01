<script setup lang="ts">
import type { FacetDef, FieldDef } from '../types'
import type { SortDirection } from '../useProductFilter'
import GroupSelect from './GroupSelect.vue'

const props = defineProps<{
  /** 主分组选项（品牌） */
  groupOptions: string[]
  groupCounts: Record<string, number>
  /** 副分组维度：档位、类型等 */
  facets: FacetDef[]
  /** 各副分组维度的计数，key 为 facet.key */
  facetCounts: Record<string, Record<string, number>>
  /** 各副分组维度的当前选中项 */
  activeFacets: Record<string, string>
  totalCount: number
  activeGroup: string
  keyword: string
  sortKey: string | null
  sortDirection: SortDirection
  sortableFields: FieldDef[]
  viewMode: 'classic' | 'timeline'
  timelineOrder: 'asc' | 'desc'
}>()

const emit = defineEmits<{
  'update:activeGroup': [value: string]
  'update:activeFacet': [payload: { key: string; value: string }]
  'update:keyword': [value: string]
  'update:viewMode': [value: 'classic' | 'timeline']
  'update:timelineOrder': [value: 'asc' | 'desc']
  toggleSort: [key: string]
}>()

/** 时间轴方向：desc = 从晚到早（默认），asc = 从早到晚 */
function toggleTimelineOrder() {
  emit('update:timelineOrder', props.timelineOrder === 'desc' ? 'asc' : 'desc')
}

function onFacetChange(key: string, value: string) {
  emit('update:activeFacet', { key, value })
}

function sortIcon(key: string) {
  if (props.sortKey !== key || props.sortDirection === 'default') return '⇅'
  return props.sortDirection === 'asc' ? '↑' : '↓'
}
</script>

<template>
  <div ref="root" class="toolbar toolbar-surface glass">
    <div class="inner container">
      <!-- 品牌下拉 -->
      <GroupSelect
        label="品牌"
        :options="groupOptions"
        :counts="groupCounts"
        :model-value="activeGroup"
        @update:model-value="emit('update:activeGroup', $event)"
      />

      <!-- 副分组下拉（档位、类型…） -->
      <GroupSelect
        v-for="f in facets"
        :key="f.key"
        :label="f.label"
        :options="f.order"
        :counts="facetCounts[f.key] ?? {}"
        :model-value="activeFacets[f.key] ?? '全部'"
        @update:model-value="(v) => onFacetChange(f.key, v)"
      />

      <!-- 排序按钮（时间轴模式）：位于分组下拉与搜索框之间 -->
      <div v-show="viewMode === 'timeline'" class="sorts">
        <button
          class="sort-btn"
          :class="{ active: timelineOrder === 'desc' }"
          :title="timelineOrder === 'desc' ? '当前：从晚到早' : '当前：从早到晚'"
          @click="toggleTimelineOrder"
        >
          <span class="sort-icon" aria-hidden="true">{{ timelineOrder === 'desc' ? '↓' : '↑' }}</span>
          {{ timelineOrder === 'desc' ? '从晚到早' : '从早到晚' }}
        </button>
      </div>

      <!-- 排序按钮（经典模式） -->
      <div v-show="viewMode === 'classic'" class="sorts">
        <button
          v-for="f in sortableFields"
          :key="f.key"
          class="sort-btn"
          :class="{ active: sortKey === f.key && sortDirection !== 'default' }"
          @click="emit('toggleSort', f.key)"
        >
          <span class="sort-icon" aria-hidden="true">{{ sortIcon(f.key) }}</span>
          {{ f.label }}
        </button>
      </div>

      <!-- 搜索框 -->
      <div class="search">
        <label class="sr-only" for="search-input">搜索产品</label>
        <span class="search-icon" aria-hidden="true">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="11" cy="11" r="8" />
            <line x1="21" y1="21" x2="16.65" y2="16.65" />
          </svg>
        </span>
        <input
          id="search-input"
          :value="keyword"
          type="search"
          placeholder="搜索型号 / 关键词..."
          @input="emit('update:keyword', ($event.target as HTMLInputElement).value)"
        />
      </div>

      <!-- 视图切换 -->
      <div class="view-toggle" role="group" aria-label="视图模式">
        <button
          class="view-btn"
          :class="{ active: viewMode === 'classic' }"
          title="经典视图"
          aria-label="经典视图"
          @click="emit('update:viewMode', 'classic')"
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <rect x="3" y="3" width="7" height="7" rx="1.5" />
            <rect x="14" y="3" width="7" height="7" rx="1.5" />
            <rect x="3" y="14" width="7" height="7" rx="1.5" />
            <rect x="14" y="14" width="7" height="7" rx="1.5" />
          </svg>
        </button>
        <button
          class="view-btn"
          :class="{ active: viewMode === 'timeline' }"
          title="时间轴视图"
          aria-label="时间轴视图"
          @click="emit('update:viewMode', 'timeline')"
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <line x1="12" y1="3" x2="12" y2="21" />
            <circle cx="12" cy="7" r="2" fill="currentColor" stroke="none" />
            <circle cx="12" cy="14" r="2" fill="currentColor" stroke="none" />
            <line x1="15" y1="7" x2="19" y2="7" />
            <line x1="5" y1="14" x2="9" y2="14" />
          </svg>
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.toolbar {
  position: sticky;
  top: var(--header-h);
  z-index: 199;
  background: var(--surface-glass);
  backdrop-filter: blur(16px) saturate(180%);
  -webkit-backdrop-filter: blur(16px) saturate(180%);
  border-bottom: 1px solid var(--border);
  box-shadow: var(--shadow-sm);
}

.inner {
  display: flex;
  gap: 8px;
  align-items: center;
  padding-block: 8px;
  flex-wrap: wrap;
}

/* ============ 排序按钮 ============ */
.sorts {
  display: flex;
  gap: 6px;
  flex: 0 1 auto;
  min-width: 0;
  overflow-x: auto;
  scrollbar-width: none;
  /* 排序项可以横向滚，不把搜索框挤扁 */
  scroll-snap-type: x proximity;
}

.sorts::-webkit-scrollbar {
  display: none;
}

.sorts::-webkit-scrollbar {
  display: none;
}

.sort-btn {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  padding: 6px 11px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--border);
  background: var(--surface);
  color: var(--text-muted);
  font-size: 12px;
  white-space: nowrap;
  font-weight: 500;
  transition: all var(--dur-fast) var(--ease-spring);
}

.sort-btn:hover {
  border-color: var(--border-brand);
  color: var(--brand);
  transform: translateY(-1px);
}

.sort-btn.active {
  background: var(--brand-gradient);
  color: #fff;
  border-color: transparent;
  box-shadow: var(--shadow-brand);
}

.sort-icon {
  font-size: 11px;
}

/* ============ 搜索框 ============ */
.search {
  /* 排序项多的时候（除湿机有 6 个）搜索框容易被挤到只剩 140px。
     给一个更宽松的基准宽度，并允许它换到下一行独占整行 */
  flex: 1 1 260px;
  min-width: 220px;
  position: relative;
}

.search-icon {
  position: absolute;
  left: 10px;
  top: 50%;
  transform: translateY(-50%);
  color: var(--text-faint);
  pointer-events: none;
  transition: color var(--dur-fast) var(--ease-smooth);
}

.search-icon svg {
  width: 15px;
  height: 15px;
}

.search input {
  width: 100%;
  padding: 7px 12px 7px 34px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  font-size: 12.5px;
  outline: none;
  background: var(--surface);
  color: var(--text);
  transition: border-color var(--dur-fast) var(--ease-smooth),
              box-shadow var(--dur-fast) var(--ease-smooth);
}

.search input::placeholder {
  color: var(--text-faint);
}

.search input:focus {
  border-color: var(--brand);
  box-shadow: 0 0 0 3px var(--brand-soft);
}

.search input:focus + .search-icon,
.search:focus-within .search-icon {
  color: var(--brand);
}

/* ============ 视图切换 ============ */
.view-toggle {
  display: flex;
  gap: 0;
  flex: 0 0 auto;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  padding: 2px;
  transition: border-color var(--dur-fast) var(--ease-smooth);
}

.view-toggle:hover {
  border-color: var(--border-brand);
}

.view-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 30px;
  height: 28px;
  border-radius: calc(var(--radius-sm) - 2px);
  background: transparent;
  color: var(--text-faint);
  transition: all var(--dur-fast) var(--ease-spring);
}

.view-btn svg {
  width: 15px;
  height: 15px;
}

.view-btn:hover {
  color: var(--brand);
  background: var(--brand-surface);
}

.view-btn.active {
  background: var(--brand-gradient);
  color: #fff;
  box-shadow: var(--shadow-brand);
}

</style>
