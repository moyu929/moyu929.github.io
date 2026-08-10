<script setup lang="ts">
import { computed } from 'vue'
import type { CategorySchema, Product } from '../types'
import { formatValue, tagsOf } from '../format'
import { imageUrl } from '../data'

const props = defineProps<{
  product: Product
  schema: CategorySchema
  /** 平铺展示时需要在卡片上显示分组徽章 */
  showGroupBadge: boolean
  selected: boolean
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

const groupName = computed(() => String(props.product[props.schema.groupBy.key] ?? ''))
const groupColor = computed(() => props.schema.groupBy.colors[groupName.value] ?? '#999')
const img = computed(() => imageUrl(props.schema, props.product))
</script>

<template>
  <article class="card">
    <div class="top">
      <div class="thumb">
        <img v-if="img" :src="img" :alt="product.name" loading="lazy" decoding="async" />
        <span v-else class="no-img" aria-hidden="true">📦</span>
      </div>

      <div class="main">
        <div class="head">
          <h3>{{ product.name }}</h3>
          <span
            v-if="showGroupBadge"
            class="badge"
            :style="{ background: groupColor }"
          >{{ groupName }}</span>
          <button
            class="cmp-btn"
            :class="{ active: selected }"
            :aria-pressed="selected"
            @click="emit('toggleCompare', product.id)"
          >
            {{ selected ? '✓ 对比' : '对比' }}
          </button>
        </div>

        <div class="chips">
          <span v-for="f in fieldsBySlot.chip" :key="f.key" class="chip">
            {{ f.label }} <b>{{ formatValue(f, product) }}</b>
          </span>
        </div>

        <dl class="params">
          <template v-for="f in fieldsBySlot.grid" :key="f.key">
            <dt>{{ f.label }}</dt>
            <dd>{{ formatValue(f, product) }}</dd>
          </template>
        </dl>
      </div>
    </div>

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
  </article>
</template>

<style scoped>
.card {
  background: var(--surface);
  border-radius: var(--radius);
  overflow: hidden;
  box-shadow: var(--shadow-sm);
  display: flex;
  flex-direction: column;
}

.top {
  display: flex;
  padding: 8px;
  gap: 8px;
}

.thumb {
  width: 64px;
  height: 78px;
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
}

.no-img {
  font-size: 24px;
  opacity: 0.35;
}

.main {
  flex: 1;
  min-width: 0;
}

.head {
  display: flex;
  align-items: center;
  gap: 4px;
  flex-wrap: wrap;
  margin-bottom: 3px;
}

.head h3 {
  font-size: 12.5px;
  font-weight: 700;
  line-height: 1.25;
  flex: 1;
  min-width: 0;
}

.badge {
  font-size: 8.5px;
  padding: 1px 5px;
  border-radius: 3px;
  color: #fff;
  white-space: nowrap;
  flex-shrink: 0;
}

.cmp-btn {
  font-size: 9.5px;
  padding: 2px 7px;
  border-radius: 4px;
  border: 1px solid var(--brand);
  background: var(--brand-surface);
  color: var(--brand);
  font-weight: 600;
  white-space: nowrap;
  flex-shrink: 0;
  transition: background 0.15s, color 0.15s;
}

.cmp-btn.active {
  background: var(--brand);
  color: #fff;
}

.chips {
  display: flex;
  gap: 3px;
  flex-wrap: wrap;
  margin-bottom: 3px;
}

.chip {
  background: var(--surface-alt);
  border-radius: 3px;
  padding: 1px 5px;
  font-size: 9px;
  white-space: nowrap;
  color: var(--text-muted);
}

.chip b {
  color: var(--danger);
  font-weight: 700;
}

.params {
  display: grid;
  grid-template-columns: auto 1fr;
  font-size: 9.5px;
  line-height: 1.55;
  margin-top: 2px;
}

.params dt {
  color: var(--text-faint);
  white-space: nowrap;
  padding-right: 6px;
}

.params dd {
  color: var(--text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.tags {
  display: flex;
  gap: 2px;
  flex-wrap: wrap;
  padding: 0 8px 8px;
  margin-top: auto;
}

.tag {
  font-size: 8.5px;
  padding: 0 4px;
  border-radius: 3px;
  line-height: 1.6;
  background: var(--tag-blue-bg);
  color: var(--tag-blue-fg);
}

.tag-red {
  background: var(--tag-red-bg);
  color: var(--tag-red-fg);
}

.tag-green {
  background: var(--tag-green-bg);
  color: var(--tag-green-fg);
}

/* 桌面端卡片更宽松 */
@media (min-width: 768px) {
  .top {
    padding: 12px;
    gap: 12px;
  }

  .thumb {
    width: 84px;
    height: 100px;
  }

  .head h3 {
    font-size: 14px;
  }

  .params {
    font-size: 10.5px;
  }

  .chip {
    font-size: 10px;
  }

  .tags {
    padding: 0 12px 12px;
  }
}
</style>
