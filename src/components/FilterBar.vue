<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import type { FieldDef, GroupByDef } from '../types'
import type { SortDirection } from '../useProductFilter'

const props = defineProps<{
  groupBy: GroupByDef
  groupCounts: Record<string, number>
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
  'update:keyword': [value: string]
  'update:viewMode': [value: 'classic' | 'timeline']
  'update:timelineOrder': [value: 'asc' | 'desc']
  toggleSort: [key: string]
}>()

/** 时间轴方向：desc = 从晚到早（默认），asc = 从早到晚 */
function toggleTimelineOrder() {
  emit('update:timelineOrder', props.timelineOrder === 'desc' ? 'asc' : 'desc')
}

const dropdownOpen = ref(false)
const root = ref<HTMLElement | null>(null)

const options = computed(() => ['全部', ...props.groupBy.order])

const triggerLabel = computed(() =>
  props.activeGroup === '全部' ? `全部 (${props.totalCount})` : props.activeGroup,
)

function countOf(option: string) {
  return option === '全部' ? props.totalCount : (props.groupCounts[option] ?? 0)
}

function select(option: string) {
  emit('update:activeGroup', option)
  dropdownOpen.value = false
}

function sortIcon(key: string) {
  if (props.sortKey !== key || props.sortDirection === 'default') return '⇅'
  return props.sortDirection === 'asc' ? '↑' : '↓'
}

function onDocumentClick(e: MouseEvent) {
  if (root.value && !root.value.contains(e.target as Node)) dropdownOpen.value = false
}

function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape') dropdownOpen.value = false
}

onMounted(() => {
  document.addEventListener('click', onDocumentClick)
  document.addEventListener('keydown', onKeydown)
})

onBeforeUnmount(() => {
  document.removeEventListener('click', onDocumentClick)
  document.removeEventListener('keydown', onKeydown)
})
</script>

<template>
  <div ref="root" class="toolbar toolbar-surface glass">
    <div class="inner container">
      <!-- 分组下拉 -->
      <div class="select">
        <button
          class="trigger"
          :class="{ open: dropdownOpen }"
          :aria-expanded="dropdownOpen"
          aria-haspopup="listbox"
          @click="dropdownOpen = !dropdownOpen"
        >
          <span class="trigger-icon" aria-hidden="true">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <line x1="3" y1="6" x2="21" y2="6" />
              <line x1="6" y1="12" x2="18" y2="12" />
              <line x1="9" y1="18" x2="15" y2="18" />
            </svg>
          </span>
          <span class="trigger-text">{{ triggerLabel }}</span>
          <span class="arrow" aria-hidden="true">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
              <polyline points="6 9 12 15 18 9" />
            </svg>
          </span>
        </button>

        <Transition name="dropdown">
          <ul v-show="dropdownOpen" class="dropdown" role="listbox">
            <li
              v-for="(o, i) in options"
              :key="o"
              class="option"
              :class="{ active: o === activeGroup }"
              role="option"
              :aria-selected="o === activeGroup"
              :style="{ animationDelay: `${i * 0.04}s` }"
              @click="select(o)"
            >
              <span>{{ o }}</span>
              <span class="count">{{ countOf(o) }}</span>
            </li>
          </ul>
        </Transition>
      </div>

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

/* ============ 分组下拉 ============ */
.select {
  position: relative;
  flex: 0 0 auto;
}

.trigger {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 7px 12px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--border);
  background: var(--surface);
  color: var(--text);
  font-size: 12.5px;
  font-weight: 600;
  white-space: nowrap;
  transition: border-color var(--dur-fast) var(--ease-smooth),
              box-shadow var(--dur-fast) var(--ease-smooth);
}

.trigger:hover {
  border-color: var(--border-brand);
}

.trigger.open {
  border-color: var(--brand);
  box-shadow: 0 0 0 3px var(--brand-soft);
}

.trigger-icon svg {
  width: 14px;
  height: 14px;
  color: var(--brand);
}

.trigger-text {
  flex: 1;
}

.arrow {
  display: flex;
  align-items: center;
  transition: transform var(--dur-normal) var(--ease-spring);
}

.arrow svg {
  width: 12px;
  height: 12px;
  color: var(--text-faint);
}

.trigger.open .arrow {
  transform: rotate(180deg);
}

.dropdown {
  position: absolute;
  top: calc(100% + 6px);
  left: 0;
  min-width: 150px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  box-shadow: var(--shadow-lg);
  overflow: hidden;
  z-index: 300;
  list-style: none;
}

.option {
  padding: 8px 12px;
  font-size: 12.5px;
  cursor: pointer;
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: center;
  border-bottom: 1px solid var(--border-soft);
  transition: background var(--dur-fast) var(--ease-smooth),
              color var(--dur-fast) var(--ease-smooth);
  animation: fadeInLeft 0.3s var(--ease-out) both;
}

.option:last-child {
  border-bottom: none;
}

.option:hover {
  background: var(--brand-surface);
}

.option.active {
  background: var(--brand-soft);
  color: var(--brand);
  font-weight: 600;
}

.count {
  font-size: 10px;
  color: var(--text-faint);
  font-weight: 400;
  background: var(--surface-alt);
  padding: 1px 6px;
  border-radius: var(--radius-full);
}

.option.active .count {
  color: var(--brand);
  background: var(--brand-surface);
}

/* ============ 排序按钮 ============ */
.sorts {
  display: flex;
  gap: 6px;
  flex: 0 0 auto;
  overflow-x: auto;
  scrollbar-width: none;
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
  flex: 1;
  min-width: 140px;
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

/* ============ 下拉过渡 ============ */
.dropdown-enter-active {
  transition: opacity var(--dur-normal) var(--ease-out),
              transform var(--dur-normal) var(--ease-spring);
}

.dropdown-leave-active {
  transition: opacity var(--dur-fast) var(--ease-smooth),
              transform var(--dur-fast) var(--ease-smooth);
}

.dropdown-enter-from {
  opacity: 0;
  transform: translateY(-8px) scale(0.96);
}

.dropdown-leave-to {
  opacity: 0;
  transform: translateY(-4px) scale(0.96);
}
</style>
