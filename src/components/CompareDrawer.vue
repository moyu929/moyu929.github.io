<script setup lang="ts">
import { computed } from 'vue'
import type { CategorySchema, Product } from '../types'
import { allSame, formatValue, numberOf } from '../format'
import { imageUrl } from '../data'

const props = defineProps<{
  open: boolean
  products: Product[]
  schema: CategorySchema
  pinnedId: string | null
  diffOnly: boolean
}>()

const emit = defineEmits<{
  close: []
  remove: [id: string]
  pin: [id: string]
  'update:diffOnly': [value: boolean]
}>()

const compareFields = computed(() => props.schema.fields.filter((f) => f.compare))

/** 预先算出每行的值和是否存在差异，模板里直接用 */
const rows = computed(() =>
  compareFields.value
    .map((field) => {
      const values =
        field.key === 'year'
          ? props.products.map((p) => {
              const base = formatValue(field, p)
              const m = numberOf(p, 'month')
              return m === null ? base : `${base}${m}月`
            })
          : props.products.map((p) => formatValue(field, p))
      const differs = props.products.length > 1 && !allSame(values)
      return { field, values, differs }
    })
    .filter((row) => !props.diffOnly || props.products.length <= 1 || row.differs),
)

function groupOf(p: Product) {
  return String(p[props.schema.groupBy.key] ?? '')
}

function colorOf(p: Product) {
  return props.schema.groupBy.colors[groupOf(p)] ?? '#999'
}
</script>

<template>
  <Teleport to="body">
    <Transition name="backdrop">
      <div v-if="open" class="backdrop" @click="emit('close')"></div>
    </Transition>

    <Transition name="slide">
      <section v-if="open" class="drawer drawer-surface" role="dialog" aria-label="参数对比" aria-modal="true">
        <header class="head header-gradient">
          <div class="head-bg" aria-hidden="true">
            <span class="orb"></span>
          </div>
          <h2>
            <svg class="head-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M3 6h18M3 12h18M3 18h18" />
            </svg>
            参数对比 ({{ products.length }})
          </h2>
          <button class="close" aria-label="关闭对比" @click="emit('close')">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </header>

        <div class="body">
          <table class="cmp">
            <thead>
              <tr>
                <th class="corner">
                  <div class="diff-toggle">
                    <button
                      class="switch"
                      :class="{ on: diffOnly }"
                      role="switch"
                      :aria-checked="diffOnly"
                      aria-label="只看不同项"
                      @click="emit('update:diffOnly', !diffOnly)"
                    ></button>
                    <span class="label">只看不同</span>
                  </div>
                </th>
                <th v-for="p in products" :key="p.id" class="model">
                  <div class="model-head">
                    <button
                      class="pin"
                      :class="{ pinned: pinnedId === p.id }"
                      :aria-pressed="pinnedId === p.id"
                      :aria-label="`将 ${p.name} 设为对比基准`"
                      @click="emit('pin', p.id)"
                    >
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <path d="M12 2v6M12 22V12M5 9l7-7 7 7M5 9h14l-7 13z" />
                      </svg>
                    </button>
                    <button
                      class="del"
                      :aria-label="`移除 ${p.name}`"
                      @click="emit('remove', p.id)"
                    >
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                        <line x1="18" y1="6" x2="6" y2="18" />
                        <line x1="6" y1="6" x2="18" y2="18" />
                      </svg>
                    </button>
                    <img
                      v-if="imageUrl(schema, p)"
                      :src="imageUrl(schema, p)!"
                      :alt="p.name"
                      loading="lazy"
                    />
                    <div v-else class="ph" aria-hidden="true">
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
                        <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z" />
                      </svg>
                    </div>
                    <div class="name">{{ p.name }}</div>
                    <span class="tier" :style="{ background: colorOf(p) }">{{ groupOf(p) }}</span>
                  </div>
                </th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in rows" :key="row.field.key">
                <th class="param">{{ row.field.label }}</th>
                <td v-for="(v, i) in row.values" :key="i" :class="{ diff: row.differs }">
                  {{ v }}
                </td>
              </tr>
            </tbody>
          </table>

          <p v-if="!rows.length" class="empty">所选型号的参数完全相同</p>
        </div>
      </section>
    </Transition>
  </Teleport>
</template>

<style scoped>
/* ============ 背景遮罩 ============ */
.backdrop {
  position: fixed;
  inset: 0;
  z-index: 399;
  background: rgba(0, 0, 0, 0.5);
  backdrop-filter: blur(4px);
  -webkit-backdrop-filter: blur(4px);
}

/* ============ 抽屉 ============ */
.drawer {
  position: fixed;
  inset: 0;
  z-index: 400;
  background: var(--surface);
  display: flex;
  flex-direction: column;
}

/* ============ 头部 ============ */
.head {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 16px;
  background: var(--header-gradient);
  color: var(--header-text);
  flex-shrink: 0;
  overflow: hidden;
}

.head-bg {
  position: absolute;
  inset: 0;
  pointer-events: none;
}

.orb {
  position: absolute;
  width: 180px;
  height: 180px;
  border-radius: 50%;
  background: var(--header-orb-1);
  filter: blur(40px);
  top: -40px;
  right: 10%;
  animation: orbDrift1 14s ease-in-out infinite;
}

.head h2 {
  position: relative;
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 16px;
  font-weight: 700;
}

.head-icon {
  width: 18px;
  height: 18px;
}

.close {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border-radius: var(--radius-full);
  background: var(--header-surface);
  backdrop-filter: blur(8px);
  color: var(--header-text);
  transition: background var(--dur-fast) var(--ease-smooth),
              transform var(--dur-fast) var(--ease-spring);
}

.close svg {
  width: 16px;
  height: 16px;
}

.close:hover {
  filter: brightness(1.3);
  transform: rotate(90deg);
}

.close:active {
  transform: rotate(90deg) scale(0.92);
}

/* ============ 表格 ============ */
.body {
  flex: 1;
  overflow: auto;
  -webkit-overflow-scrolling: touch;
  /* 细滚动条（抽屉内独立滚动容器） */
  scrollbar-width: thin;
  scrollbar-color: rgba(120, 120, 130, 0.4) transparent;
}

.body::-webkit-scrollbar {
  width: 6px;
  height: 6px;
}

.body::-webkit-scrollbar-track {
  background: transparent;
}

.body::-webkit-scrollbar-thumb {
  background: rgba(120, 120, 130, 0.4);
  border-radius: 3px;
}

.body::-webkit-scrollbar-thumb:hover {
  background: var(--brand);
}

.cmp {
  border-collapse: collapse;
  width: max-content;
  min-width: 100%;
}

.corner {
  position: sticky;
  left: 0;
  top: 0;
  z-index: 12;
  background: var(--surface);
  border-right: 1px solid var(--border);
  border-bottom: 1px solid var(--border);
  min-width: 100px;
  width: 100px;
}

.diff-toggle {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 5px;
  padding: 10px 4px;
}

.diff-toggle .label {
  font-size: 9px;
  color: var(--text-faint);
  font-weight: 600;
}

.switch {
  position: relative;
  width: 36px;
  height: 20px;
  border-radius: var(--radius-full);
  background: var(--border);
  border: none;
  padding: 0;
  transition: background var(--dur-normal) var(--ease-smooth);
}

.switch.on {
  background: var(--brand-gradient);
}

.switch::after {
  content: '';
  position: absolute;
  top: 2px;
  left: 2px;
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: #fff;
  transition: transform var(--dur-normal) var(--ease-spring);
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.2);
}

.switch.on::after {
  transform: translateX(16px);
}

.model {
  position: sticky;
  top: 0;
  z-index: 10;
  background: var(--surface);
  border-bottom: 1px solid var(--border);
  min-width: 140px;
  max-width: 170px;
}

.model-head {
  position: relative;
  padding: 30px 8px 10px;
  text-align: center;
}

.pin,
.del {
  position: absolute;
  top: 6px;
  width: 24px;
  height: 24px;
  border-radius: var(--radius-full);
  background: var(--surface-alt);
  color: var(--text-faint);
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all var(--dur-fast) var(--ease-spring);
}

.pin svg,
.del svg {
  width: 12px;
  height: 12px;
}

.pin {
  left: 6px;
}

.del {
  right: 6px;
}

.pin:hover {
  background: var(--brand-soft);
  color: var(--brand);
  transform: scale(1.1);
}

.pin.pinned {
  background: var(--brand-gradient);
  color: #fff;
  box-shadow: var(--shadow-brand);
}

.del:hover {
  background: var(--tag-red-bg);
  color: var(--tag-red-fg);
  transform: scale(1.1) rotate(90deg);
}

.del:active {
  transform: scale(0.92) rotate(90deg);
}

.model-head img,
.ph {
  width: 80px;
  height: 68px;
  object-fit: cover;
  border-radius: var(--radius-sm);
  margin: 2px auto;
  display: block;
  box-shadow: var(--shadow-sm);
}

.ph {
  background: var(--surface-alt);
  display: flex;
  align-items: center;
  justify-content: center;
  opacity: 0.3;
}

.ph svg {
  width: 28px;
  height: 28px;
}

.name {
  font-size: 11.5px;
  font-weight: 700;
  line-height: 1.3;
  padding: 4px 2px 0;
  white-space: normal;
}

.tier {
  font-size: 9px;
  padding: 2px 7px;
  border-radius: var(--radius-xs);
  color: #fff;
  display: inline-block;
  margin-top: 4px;
  font-weight: 600;
}

.param {
  position: sticky;
  left: 0;
  z-index: 5;
  background: var(--surface);
  font-weight: 600;
  color: var(--text-muted);
  white-space: nowrap;
  padding: 10px 12px;
  text-align: left;
  border-right: 1px solid var(--border);
  border-bottom: 1px solid var(--border-soft);
  font-size: 11.5px;
}

.cmp td {
  padding: 10px 8px;
  border-bottom: 1px solid var(--border-soft);
  text-align: center;
  white-space: nowrap;
  font-size: 11.5px;
  transition: background var(--dur-fast) var(--ease-smooth);
}

.cmp td.diff {
  color: var(--danger);
  font-weight: 700;
  background: var(--tag-red-bg);
}

.cmp tbody tr:nth-child(even) td,
.cmp tbody tr:nth-child(even) .param {
  background: var(--surface-alt);
}

.cmp tbody tr:nth-child(even) td.diff {
  background: var(--tag-red-bg);
}

.cmp tbody tr:hover td {
  background: var(--brand-surface);
}

.cmp tbody tr:hover td.diff {
  background: var(--tag-red-bg);
}

.empty {
  text-align: center;
  padding: 40px 16px;
  color: var(--text-faint);
  font-size: 13px;
}

/* ============ 过渡动画 ============ */
.backdrop-enter-active,
.backdrop-leave-active {
  transition: opacity var(--dur-normal) var(--ease-smooth);
}

.backdrop-enter-from,
.backdrop-leave-to {
  opacity: 0;
}

.slide-enter-active {
  transition: transform var(--dur-slow) var(--ease-out);
}

.slide-leave-active {
  transition: transform var(--dur-normal) var(--ease-smooth);
}

.slide-enter-from,
.slide-leave-to {
  transform: translateY(100%);
}

/* ============ 响应式 ============ */
@media (min-width: 1024px) {
  .drawer {
    inset: 4% 6%;
    border-radius: var(--radius-lg);
    overflow: hidden;
    box-shadow: var(--shadow-lg);
  }

  .cmp td,
  .param {
    font-size: 13px;
  }

  .name {
    font-size: 13px;
  }

  .model-head img,
  .ph {
    width: 90px;
    height: 76px;
  }
}
</style>
