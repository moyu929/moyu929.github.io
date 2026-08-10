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
}>()

const emit = defineEmits<{
  'update:activeGroup': [value: string]
  'update:keyword': [value: string]
  toggleSort: [key: string]
}>()

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
  <div ref="root" class="toolbar">
    <div class="inner container">
      <div class="select">
        <button
          class="trigger"
          :class="{ open: dropdownOpen }"
          :aria-expanded="dropdownOpen"
          aria-haspopup="listbox"
          @click="dropdownOpen = !dropdownOpen"
        >
          <span>{{ triggerLabel }}</span>
          <span class="arrow" aria-hidden="true">▼</span>
        </button>

        <ul v-show="dropdownOpen" class="dropdown" role="listbox">
          <li
            v-for="o in options"
            :key="o"
            class="option"
            :class="{ active: o === activeGroup }"
            role="option"
            :aria-selected="o === activeGroup"
            @click="select(o)"
          >
            <span>{{ o }}</span>
            <span class="count">{{ countOf(o) }}</span>
          </li>
        </ul>
      </div>

      <div class="sorts">
        <button
          v-for="f in sortableFields"
          :key="f.key"
          class="sort-btn"
          :class="{ active: sortKey === f.key && sortDirection !== 'default' }"
          @click="emit('toggleSort', f.key)"
        >
          <span aria-hidden="true">{{ sortIcon(f.key) }}</span> {{ f.label }}
        </button>
      </div>

      <div class="search">
        <label class="sr-only" for="search-input">搜索产品</label>
        <input
          id="search-input"
          :value="keyword"
          type="search"
          placeholder="搜索型号 / 关键词..."
          @input="emit('update:keyword', ($event.target as HTMLInputElement).value)"
        />
      </div>
    </div>
  </div>
</template>

<style scoped>
.toolbar {
  position: sticky;
  top: var(--header-h);
  z-index: 199;
  background: var(--surface);
  border-bottom: 1px solid var(--border);
  box-shadow: var(--shadow-sm);
}

.inner {
  display: flex;
  gap: 6px;
  align-items: center;
  padding-block: 6px;
  flex-wrap: wrap;
}

.select {
  position: relative;
  flex: 0 0 auto;
}

.trigger {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 5px 9px;
  border-radius: 7px;
  border: 1px solid var(--border);
  background: var(--surface);
  color: var(--text);
  font-size: 12px;
  font-weight: 600;
  white-space: nowrap;
  min-width: 88px;
  justify-content: space-between;
}

.arrow {
  font-size: 9px;
  color: var(--text-faint);
  transition: transform 0.2s;
}

.trigger.open .arrow {
  transform: rotate(180deg);
}

.dropdown {
  position: absolute;
  top: calc(100% + 4px);
  left: 0;
  min-width: 130px;
  background: var(--surface);
  border-radius: var(--radius);
  box-shadow: var(--shadow-md);
  overflow: hidden;
  z-index: 300;
  list-style: none;
}

.option {
  padding: 7px 10px;
  font-size: 12px;
  cursor: pointer;
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: center;
  border-bottom: 1px solid var(--border-soft);
  transition: background 0.15s;
}

.option:last-child {
  border-bottom: none;
}

.option:hover,
.option.active {
  background: var(--brand-soft);
  color: var(--brand);
  font-weight: 600;
}

.count {
  font-size: 10px;
  color: var(--text-faint);
  font-weight: 400;
}

.option.active .count {
  color: var(--brand);
}

.sorts {
  display: flex;
  gap: 5px;
  flex: 0 0 auto;
  overflow-x: auto;
  scrollbar-width: none;
}

.sorts::-webkit-scrollbar {
  display: none;
}

.sort-btn {
  padding: 5px 9px;
  border-radius: 7px;
  border: 1px solid var(--brand);
  background: var(--brand-surface);
  color: var(--brand);
  font-size: 11.5px;
  white-space: nowrap;
  font-weight: 600;
  transition: background 0.2s, color 0.2s;
}

.sort-btn.active {
  background: var(--brand);
  color: #fff;
}

.search {
  flex: 1;
  min-width: 140px;
}

.search input {
  width: 100%;
  padding: 6px 10px;
  border: 1px solid var(--border);
  border-radius: 7px;
  font-size: 12px;
  outline: none;
  background: var(--surface);
  color: var(--text);
}

.search input:focus {
  border-color: var(--brand);
}
</style>
