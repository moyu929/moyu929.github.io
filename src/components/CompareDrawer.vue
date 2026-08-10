<script setup lang="ts">
import { computed } from 'vue'
import type { CategorySchema, Product } from '../types'
import { allSame, formatValue } from '../format'
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
      const values = props.products.map((p) => formatValue(field, p))
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
  <Transition name="slide">
    <section v-if="open" class="drawer" role="dialog" aria-label="参数对比" aria-modal="true">
      <header class="head">
        <h2>参数对比 ({{ products.length }})</h2>
        <button class="close" aria-label="关闭对比" @click="emit('close')">✕</button>
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
                    📌
                  </button>
                  <button
                    class="del"
                    :aria-label="`移除 ${p.name}`"
                    @click="emit('remove', p.id)"
                  >
                    ✕
                  </button>
                  <img
                    v-if="imageUrl(schema, p)"
                    :src="imageUrl(schema, p)!"
                    :alt="p.name"
                    loading="lazy"
                  />
                  <div v-else class="ph" aria-hidden="true">📦</div>
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
</template>

<style scoped>
.drawer {
  position: fixed;
  inset: 0;
  z-index: 400;
  background: var(--surface);
  display: flex;
  flex-direction: column;
}

.head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 14px;
  background: linear-gradient(135deg, var(--header-from), var(--header-to));
  color: #fff;
  flex-shrink: 0;
}

.head h2 {
  font-size: 15px;
  font-weight: 700;
}

.close {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  border: none;
  background: rgb(255 255 255 / 15%);
  color: #fff;
  font-size: 13px;
}

.body {
  flex: 1;
  overflow: auto;
  -webkit-overflow-scrolling: touch;
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
  min-width: 88px;
  width: 88px;
}

.diff-toggle {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  padding: 8px 4px;
}

.diff-toggle .label {
  font-size: 8.5px;
  color: var(--text-faint);
  font-weight: 600;
}

.switch {
  position: relative;
  width: 34px;
  height: 18px;
  border-radius: 9px;
  background: #ccc;
  border: none;
  padding: 0;
  transition: background 0.2s;
}

.switch.on {
  background: var(--brand);
}

.switch::after {
  content: '';
  position: absolute;
  top: 2px;
  left: 2px;
  width: 14px;
  height: 14px;
  border-radius: 50%;
  background: #fff;
  transition: transform 0.2s;
  box-shadow: 0 1px 2px rgb(0 0 0 / 20%);
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
  min-width: 130px;
  max-width: 160px;
}

.model-head {
  position: relative;
  padding: 26px 6px 8px;
  text-align: center;
}

.pin,
.del {
  position: absolute;
  top: 4px;
  width: 22px;
  height: 22px;
  border-radius: 50%;
  border: none;
  background: var(--surface-alt);
  color: var(--text-faint);
  font-size: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.pin {
  left: 4px;
}

.del {
  right: 4px;
}

.pin.pinned {
  background: var(--brand);
  color: #fff;
}

.model-head img,
.ph {
  width: 76px;
  height: 64px;
  object-fit: cover;
  border-radius: 6px;
  margin: 2px auto;
  display: block;
}

.ph {
  background: var(--surface-alt);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 22px;
  opacity: 0.4;
}

.name {
  font-size: 10.5px;
  font-weight: 700;
  line-height: 1.3;
  padding: 3px 2px 0;
  white-space: normal;
}

.tier {
  font-size: 8.5px;
  padding: 1px 5px;
  border-radius: 3px;
  color: #fff;
  display: inline-block;
  margin-top: 3px;
}

.param {
  position: sticky;
  left: 0;
  z-index: 5;
  background: var(--surface);
  font-weight: 600;
  color: var(--text-muted);
  white-space: nowrap;
  padding: 8px 10px;
  text-align: left;
  border-right: 1px solid var(--border);
  border-bottom: 1px solid var(--border-soft);
  font-size: 10.5px;
}

.cmp td {
  padding: 8px 6px;
  border-bottom: 1px solid var(--border-soft);
  text-align: center;
  white-space: nowrap;
  font-size: 10.5px;
}

.cmp td.diff {
  color: var(--danger);
  font-weight: 700;
}

.cmp tbody tr:nth-child(even) td,
.cmp tbody tr:nth-child(even) .param {
  background: var(--surface-alt);
}

.empty {
  text-align: center;
  padding: 32px 16px;
  color: var(--text-faint);
  font-size: 12px;
}

.slide-enter-active,
.slide-leave-active {
  transition: transform 0.25s ease;
}

.slide-enter-from,
.slide-leave-to {
  transform: translateY(100%);
}

@media (min-width: 1024px) {
  .drawer {
    inset: 5% 8%;
    border-radius: 12px;
    overflow: hidden;
    box-shadow: var(--shadow-md);
  }

  .cmp td,
  .param {
    font-size: 12px;
  }

  .name {
    font-size: 12px;
  }
}
</style>
