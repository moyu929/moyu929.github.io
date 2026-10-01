<script setup lang="ts">
/**
 * 首页：一级品类分组导航。
 * 左侧竖排一级品类（环境与空气 / 厨房大家电 / …），右侧展示该组下的具体品类。
 * 分组比品类更稳定，新增品类只需改 categories.json，不必动这里的结构。
 */
import { computed, onMounted, onBeforeUnmount, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { categoryGroups } from '../data'
import { useScrollReveal } from '../useScrollReveal'

const { setup: setupReveal } = useScrollReveal()

/** 选中的一级品类 id；默认第一个，保证首屏右侧不是空白 */
const activeId = ref(categoryGroups[0]?.id ?? '')

const activeGroup = computed(
  () => categoryGroups.find((g) => g.id === activeId.value) ?? categoryGroups[0],
)

/** 每个一级品类下的产品总数，用于导航上的计数 */
const counts = computed(() =>
  Object.fromEntries(categoryGroups.map((g) => [g.id, g.categories.length])),
)

/** 分组序号补零到两位，像规格手册的目录编号 */
function pad2(n: number) {
  return String(n).padStart(2, '0')
}

/** 全部品类总数，hero 上展示 */
const total = computed(() => categoryGroups.reduce((n, g) => n + g.categories.length, 0))

/**
 * 键盘可达性：左右/上下方向键在分组间移动。
 * 用 roving tabindex 让整列只有一个可 Tab 项，方向键负责在其余项间移动。
 */
function onGroupKeydown(e: KeyboardEvent, index: number) {
  const delta = { ArrowDown: 1, ArrowRight: 1, ArrowUp: -1, ArrowLeft: -1 }[e.key]
  if (delta === undefined) return
  e.preventDefault()
  const next = Math.min(Math.max(index + delta, 0), categoryGroups.length - 1)
  selectGroup(categoryGroups[next].id)
  // 焦点跟着走，否则键盘用户按完方向键焦点还留在原处
  requestAnimationFrame(() => {
    document.querySelector<HTMLElement>(`#group-${categoryGroups[next].id}`)?.focus()
  })
}

function selectGroup(id: string) {
  activeId.value = id
  // 换组后右侧是新内容，重新挂一次滚动揭示
  requestAnimationFrame(() => setupReveal())
}

onMounted(() => {
  requestAnimationFrame(() => setupReveal())
})

onBeforeUnmount(() => {})
</script>

<template>
  <div class="home">
    <!-- Hero -->
    <header class="hero">
      <div class="hero-inner">
        <p class="hero-eyebrow">跨品牌家电参数横评</p>
        <h1>
          <span class="hero-line">按使用场景查</span>
          <span class="hero-line hero-accent">{{ total }} 个家电品类</span>
        </h1>
        <p class="hero-sub">
          参数逐条标注来源与核查时间，支持品牌与型号横向对比。
        </p>
      </div>
    </header>

    <!-- 一级品类导航 + 该组品类 -->
    <main id="main" class="container browse">
      <nav class="groups" aria-label="一级品类">
        <p class="groups-label">按使用场景</p>
        <ul class="group-list">
          <li v-for="(g, i) in categoryGroups" :key="g.id">
            <button
              :id="`group-${g.id}`"
              type="button"
              class="group-item"
              :class="{ active: g.id === activeId }"
              :aria-current="g.id === activeId ? 'true' : undefined"
              :tabindex="g.id === activeId ? 0 : -1"
              @click="selectGroup(g.id)"
              @keydown="onGroupKeydown($event, i)"
            >
              <span class="group-index" aria-hidden="true">{{ pad2(i + 1) }}</span>
              <span class="group-text">
                <span class="group-name">{{ g.name }}</span>
                <span class="group-count">{{ counts[g.id] }} 个品类</span>
              </span>
            </button>
          </li>
        </ul>
      </nav>

      <section
        v-if="activeGroup"
        class="panel"
        :aria-labelledby="`group-${activeGroup.id}`"
      >
        <header class="panel-head">
          <h2>{{ activeGroup.name }}</h2>
          <p>{{ activeGroup.description }}</p>
        </header>

        <div class="grid">
          <RouterLink
            v-for="c in activeGroup.categories"
            :key="c.id"
            class="card reveal"
            :to="`/${c.id}`"
          >
            <h3>{{ c.name }}</h3>
            <p>{{ c.description }}</p>
            <span class="card-arrow" aria-hidden="true">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M9 18l6-6-6-6" />
              </svg>
            </span>
          </RouterLink>
        </div>
      </section>
    </main>
  </div>
</template>

<style scoped>
/* ============================================================
   Hero —— 规格手册的题头，不是营销页的大图
   ============================================================ */
.hero {
  position: relative;
  background: var(--header-gradient);
  color: var(--header-text);
  padding: 64px 16px 52px;
  border-bottom: 1px solid var(--border);
  /* 顶部一道细的强调色横线，代替渐变色球 */
  overflow: hidden;
}

.hero::before {
  content: '';
  position: absolute;
  inset: 0 0 auto 0;
  height: 3px;
  background: var(--brand);
}

.hero-inner {
  position: relative;
  max-width: var(--page-max);
  margin: 0 auto;
}

.hero-eyebrow {
  font-size: 11.5px;
  font-weight: 600;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  color: var(--brand);
  margin-bottom: 12px;
}

.hero h1 {
  font-family: var(--font-display);
  font-size: clamp(30px, 5.6vw, 46px);
  font-weight: 700;
  line-height: 1.12;
  letter-spacing: -0.02em;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.hero-line {
  display: block;
  animation: titleIn 0.6s var(--ease-out) both;
}

.hero-line:nth-child(2) {
  animation-delay: 0.08s;
}

.hero-accent {
  color: var(--brand);
}

.hero-sub {
  margin-top: 14px;
  font-size: 13.5px;
  color: var(--header-muted);
  max-width: 56ch;
  animation: titleIn 0.6s var(--ease-out) both;
  animation-delay: 0.16s;
}

/* ============================================================
   浏览区：左分组导航 + 右品类面板
   ============================================================ */
.browse {
  display: grid;
  grid-template-columns: 1fr;
  gap: 22px;
  padding-block: 28px 72px;
}

.groups {
  min-width: 0;
}

.groups-label {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.16em;
  color: var(--text-faint);
  padding: 0 2px;
  margin-bottom: 10px;
}

.group-list {
  display: flex;
  gap: 6px;
  overflow-x: auto;
  padding-bottom: 4px;
  scrollbar-width: none;
  list-style: none;
}

.group-list::-webkit-scrollbar {
  display: none;
}

/* 分组项：编号 + 名称，像规格手册的目录 */
.group-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 9px 13px;
  min-width: max-content;
  border: 1px solid transparent;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--text-muted);
  font: inherit;
  font-size: 13px;
  text-align: left;
  cursor: pointer;
  transition:
    background var(--dur-fast) var(--ease-smooth),
    color var(--dur-fast) var(--ease-smooth),
    border-color var(--dur-fast) var(--ease-smooth);
}

.group-item:hover {
  background: var(--surface-hover);
  color: var(--text);
}

.group-item.active {
  background: var(--brand-surface);
  border-color: var(--border-brand);
  color: var(--brand);
}

/* 选中项左侧一道实心竖条，替代填充色块 */
.group-item.active .group-index {
  background: var(--brand);
  border-color: var(--brand);
  color: #fff;
}

.group-item:focus-visible {
  outline: 2px solid var(--brand);
  outline-offset: 2px;
}

/* 序号用等宽数字，像目录编号 */
.group-index {
  display: grid;
  place-items: center;
  width: 22px;
  height: 22px;
  flex-shrink: 0;
  border: 1px solid var(--border);
  border-radius: var(--radius-xs);
  background: var(--surface);
  font-family: var(--font-mono);
  font-size: 10.5px;
  font-weight: 600;
  color: var(--text-faint);
  font-variant-numeric: tabular-nums;
  transition:
    background var(--dur-fast) var(--ease-smooth),
    color var(--dur-fast) var(--ease-smooth),
    border-color var(--dur-fast) var(--ease-smooth);
}

.group-text {
  display: flex;
  flex-direction: column;
  gap: 0;
  line-height: 1.35;
}

.group-name {
  font-weight: 550;
  white-space: nowrap;
}

.group-count {
  font-size: 11px;
  color: var(--text-faint);
  white-space: nowrap;
}

/* ---- 右侧面板 ---- */
.panel {
  min-width: 0;
}

.panel-head {
  display: flex;
  align-items: baseline;
  gap: 10px;
  padding-bottom: 12px;
  margin-bottom: 14px;
  border-bottom: 1px solid var(--border);
}

.panel-head h2 {
  font-family: var(--font-display);
  font-size: 19px;
  font-weight: 700;
  letter-spacing: -0.01em;
}

.panel-head p {
  font-size: 12.5px;
  color: var(--text-faint);
}

.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(228px, 1fr));
  gap: 8px;
}

/* 品类卡：靠底色与内边距分层，不靠边框+阴影堆叠。
   卡片数量多（一屏十几个），阴影一多就全是噪音。 */
.card {
  position: relative;
  display: block;
  padding: 13px 34px 13px 14px;
  border: 1px solid var(--border-soft);
  border-radius: var(--radius-sm);
  background: var(--surface);
  color: inherit;
  text-decoration: none;
  transition:
    background var(--dur-fast) var(--ease-smooth),
    border-color var(--dur-fast) var(--ease-smooth),
    transform var(--dur-fast) var(--ease-out);
}

.card:hover {
  background: var(--brand-surface);
  border-color: var(--border-brand);
  transform: translateY(-1px);
}

.card:active {
  transform: translateY(0);
}

.card h3 {
  font-size: 14px;
  font-weight: 600;
  letter-spacing: -0.005em;
}

.card p {
  font-size: 11.5px;
  color: var(--text-faint);
  margin-top: 3px;
  overflow: hidden;
  text-overflow: ellipsis;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  -webkit-box-orient: vertical;
}

.card-arrow {
  position: absolute;
  right: 13px;
  top: 14px;
  width: 14px;
  height: 14px;
  color: var(--text-faint);
  transition:
    transform var(--dur-normal) var(--ease-out),
    color var(--dur-fast) var(--ease-smooth);
}

.card:hover .card-arrow {
  transform: translateX(3px);
  color: var(--brand);
}

.card-arrow svg {
  width: 100%;
  height: 100%;
}

@keyframes titleIn {
  from {
    opacity: 0;
    transform: translateY(10px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

/* ---- 宽屏：左导航固定竖排 ---- */
@media (min-width: 900px) {
  .browse {
    grid-template-columns: 218px minmax(0, 1fr);
    gap: 36px;
    align-items: start;
  }

  .groups {
    position: sticky;
    top: calc(var(--header-h) + 20px);
  }

  .group-list {
    flex-direction: column;
    overflow: visible;
    gap: 2px;
  }

  .group-item {
    width: 100%;
    min-width: 0;
    border-radius: var(--radius-xs);
  }
}

@media (min-width: 1200px) {
  .browse {
    grid-template-columns: 240px minmax(0, 1fr);
    gap: 44px;
  }
}

@media (max-width: 899px) {
  .hero {
    padding: 44px 16px 36px;
  }
}
</style>
