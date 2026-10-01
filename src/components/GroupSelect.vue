<script setup lang="ts">
/**
 * 分组下拉（主分组=品牌 / 副分组=档位、类型…共用）。
 * 品牌与副分组的交互完全一致，只是选项来源和计数口径不同，所以抽成一个组件，
 * 避免在 FilterBar 里堆两套几乎一样的下拉 DOM 与关闭逻辑。
 */
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

const props = defineProps<{
  /** 分组维度名，显示在触发按钮左侧，如「品牌」「档位」 */
  label: string
  /** 可选项，'全部' 由本组件自动插在最前 */
  options: string[]
  /** 各选项的产品数 */
  counts: Record<string, number>
  /** 当前选中项；未选中时传 '全部' */
  modelValue: string
}>()

const emit = defineEmits<{ 'update:modelValue': [value: string] }>()

const open = ref(false)
const root = ref<HTMLElement | null>(null)

const allOptions = computed(() => ['全部', ...props.options])

const triggerLabel = computed(() =>
  props.modelValue === '全部' ? '全部' : props.modelValue,
)

const triggerCount = computed(() =>
  props.modelValue === '全部' ? '' : String(props.counts[props.modelValue] ?? 0),
)

function countOf(option: string) {
  return props.counts[option] ?? 0
}

function select(option: string) {
  emit('update:modelValue', option)
  open.value = false
}

function onDocumentClick(e: MouseEvent) {
  if (!root.value?.contains(e.target as Node)) open.value = false
}

function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape' && open.value) open.value = false
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
  <div ref="root" class="select">
    <button
      class="trigger"
      :class="{ open }"
      :aria-expanded="open"
      aria-haspopup="listbox"
      @click="open = !open"
    >
      <span class="trigger-icon" aria-hidden="true">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <line x1="3" y1="6" x2="21" y2="6" />
          <line x1="6" y1="12" x2="18" y2="12" />
          <line x1="9" y1="18" x2="15" y2="18" />
        </svg>
      </span>
      <span class="trigger-text">{{ label }} · {{ triggerLabel }}</span>
      <span v-if="triggerCount" class="trigger-count">{{ triggerCount }}</span>
      <span class="arrow" aria-hidden="true">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
          <polyline points="6 9 12 15 18 9" />
        </svg>
      </span>
    </button>

    <Transition name="dropdown">
      <ul v-show="open" class="dropdown" role="listbox">
        <li
          v-for="(o, i) in allOptions"
          :key="o"
          class="option"
          :class="{ active: o === modelValue }"
          role="option"
          :aria-selected="o === modelValue"
          :style="{ animationDelay: `${i * 0.04}s` }"
          @click="select(o)"
        >
          <span>{{ o }}</span>
          <span class="count">{{ countOf(o) }}</span>
        </li>
      </ul>
    </Transition>
  </div>
</template>

<style scoped>
/* 下拉样式原先在 FilterBar 的 scoped CSS 里，随下拉组件抽出一起搬过来 */
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
  border-radius: var(--radius-xs);
}

.option.active .count {
  color: var(--brand);
  background: var(--brand-surface);
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
