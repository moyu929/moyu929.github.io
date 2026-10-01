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
      <div class="hero-bg" aria-hidden="true">
        <span class="orb orb-1"></span>
        <span class="orb orb-2"></span>
        <span class="orb orb-3"></span>
      </div>
      <div class="hero-content">
        <p class="hero-eyebrow">跨品牌家电参数横评</p>
        <h1>
          <span class="hero-title-line" style="animation-delay: 0.1s">按场景找</span>
          <span class="hero-title-line gradient" style="animation-delay: 0.25s">{{ total }} 个品类</span>
        </h1>
        <p class="subtitle" style="animation-delay: 0.4s">
          参数逐条标注来源 · 支持品牌与型号横向对比
        </p>
      </div>
    </header>

    <!-- 一级品类导航 + 该组品类 -->
    <main class="container browse">
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
              <span class="group-icon" aria-hidden="true">{{ g.icon }}</span>
              <span class="group-text">
                <span class="group-name">{{ g.name }}</span>
                <span class="group-count">{{ counts[g.id] }} 个品类</span>
              </span>
            </button>
          </li>
        </ul>
      </nav>

      <section v-if="activeGroup" class="panel" :aria-labelledby="`group-${activeGroup.id}`">
        <header class="panel-head">
          <span class="panel-icon" aria-hidden="true">{{ activeGroup.icon }}</span>
          <div>
            <h2>{{ activeGroup.name }}</h2>
            <p>{{ activeGroup.description }}</p>
          </div>
        </header>

        <div class="grid">
          <RouterLink
            v-for="c in activeGroup.categories"
            :key="c.id"
            class="card reveal"
            :to="`/${c.id}`"
          >
            <div class="card-icon">
              <span aria-hidden="true">{{ c.icon }}</span>
            </div>
            <div class="card-body">
              <h3>{{ c.name }}</h3>
              <p>{{ c.description }}</p>
            </div>
            <div class="card-arrow" aria-hidden="true">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                <path d="M9 18l6-6-6-6" />
              </svg>
            </div>
          </RouterLink>
        </div>
      </section>
    </main>
  </div>
</template>

<style scoped>
/* ============ Hero ============ */
.hero {
  position: relative;
  background: var(--header-gradient);
  background-size: 200% 200%;
  color: var(--header-text);
  padding: 72px 16px 64px;
  text-align: center;
  overflow: hidden;
  animation: gradientFlow 12s ease infinite;
}

.hero-bg {
  position: absolute;
  inset: 0;
  pointer-events: none;
}

.orb {
  position: absolute;
  border-radius: 50%;
  filter: blur(40px);
}

.orb-1 {
  width: 300px;
  height: 300px;
  background: var(--header-orb-1);
  top: -60px;
  left: -40px;
  animation: orbDrift1 16s ease-in-out infinite;
}

.orb-2 {
  width: 250px;
  height: 250px;
  background: var(--header-orb-2);
  bottom: -50px;
  right: -30px;
  animation: orbDrift2 20s ease-in-out infinite;
}

.orb-3 {
  width: 200px;
  height: 200px;
  background: var(--header-orb-3);
  top: 40%;
  left: 60%;
  animation: orbDrift3 24s ease-in-out infinite;
}

.hero-content {
  position: relative;
  z-index: 1;
  max-width: 720px;
  margin: 0 auto;
}

.hero-eyebrow {
  display: inline-block;
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.16em;
  text-transform: uppercase;
  color: var(--header-muted);
  margin-bottom: 14px;
  padding: 5px 14px;
  border: 1px solid var(--header-border);
  border-radius: var(--radius-full);
}

.hero h1 {
  font-size: clamp(30px, 6vw, 46px);
  font-weight: 800;
  line-height: 1.15;
  letter-spacing: -0.02em;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.hero-title-line {
  display: block;
  animation: titleIn 0.7s var(--ease-out) both;
}

.hero-title-line.gradient {
  background: var(--brand-gradient);
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
}

.subtitle {
  margin-top: 16px;
  font-size: 14px;
  color: var(--header-muted);
  animation: titleIn 0.7s var(--ease-out) both;
}

/* ============ 浏览区：左导航 + 右面板 ============ */
.browse {
  display: grid;
  grid-template-columns: 1fr;
  gap: 20px;
  padding-block: 32px 72px;
}

.groups-label {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.14em;
  color: var(--text-faint);
  text-transform: uppercase;
  padding: 0 4px;
  margin-bottom: 10px;
}

.group-list {
  display: flex;
  gap: 8px;
  overflow-x: auto;
  padding-bottom: 4px;
  scrollbar-width: none;
  list-style: none;
}

.group-list::-webkit-scrollbar {
  display: none;
}

.group-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 14px;
  min-width: max-content;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--surface);
  color: var(--text-muted);
  font: inherit;
  font-size: 13px;
  text-align: left;
  cursor: pointer;
  transition:
    border-color var(--dur-fast) var(--ease-smooth),
    background var(--dur-fast) var(--ease-smooth),
    color var(--dur-fast) var(--ease-smooth);
}

.group-item:hover {
  border-color: var(--border-brand);
  background: var(--surface-hover);
}

.group-item.active {
  background: var(--brand-surface);
  border-color: var(--brand);
  color: var(--brand-dark);
  font-weight: 700;
}

.group-item:focus-visible {
  outline: 2px solid var(--brand);
  outline-offset: 2px;
}

.group-icon {
  font-size: 17px;
  line-height: 1;
}

.group-text {
  display: flex;
  flex-direction: column;
  gap: 1px;
}

.group-name {
  white-space: nowrap;
}

.group-count {
  font-size: 11px;
  font-weight: 400;
  color: var(--text-faint);
  white-space: nowrap;
}

/* ---- 右侧面板 ---- */
.panel {
  min-width: 0;
}

.panel-head {
  display: flex;
  align-items: center;
  gap: 12px;
  padding-bottom: 14px;
  margin-bottom: 16px;
  border-bottom: 1px solid var(--border-soft);
}

.panel-icon {
  display: grid;
  place-items: center;
  width: 40px;
  height: 40px;
  font-size: 20px;
  border-radius: var(--radius);
  background: var(--brand-surface);
  flex-shrink: 0;
}

.panel-head h2 {
  font-size: 18px;
  font-weight: 700;
  letter-spacing: -0.01em;
}

.panel-head p {
  font-size: 12.5px;
  color: var(--text-faint);
  margin-top: 2px;
}

.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(230px, 1fr));
  gap: 12px;
}

.card {
  position: relative;
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px 40px 14px 14px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--surface);
  text-decoration: none;
  color: inherit;
  transition:
    transform var(--dur-normal) var(--ease-out),
    border-color var(--dur-normal) var(--ease-smooth),
    box-shadow var(--dur-normal) var(--ease-smooth);
}

.card:hover {
  transform: translateY(-2px);
  border-color: var(--border-brand);
  box-shadow: var(--shadow-md);
}

.card-icon {
  display: grid;
  place-items: center;
  width: 38px;
  height: 38px;
  font-size: 19px;
  border-radius: var(--radius-sm);
  background: var(--surface-alt);
  flex-shrink: 0;
}

.card-body {
  min-width: 0;
}

.card-body h3 {
  font-size: 14px;
  font-weight: 650;
  letter-spacing: -0.01em;
}

.card-body p {
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
  right: 14px;
  top: 50%;
  transform: translateY(-50%);
  width: 16px;
  height: 16px;
  color: var(--text-faint);
  transition: transform var(--dur-normal) var(--ease-spring);
}

.card:hover .card-arrow {
  transform: translateY(-50%) translateX(3px);
  color: var(--brand);
}

.card-arrow svg {
  width: 100%;
  height: 100%;
}

@keyframes titleIn {
  from {
    opacity: 0;
    transform: translateY(14px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

@keyframes gradientFlow {
  0%,
  100% {
    background-position: 0% 50%;
  }
  50% {
    background-position: 100% 50%;
  }
}

@keyframes orbDrift1 {
  0%,
  100% {
    transform: translate(0, 0) scale(1);
  }
  50% {
    transform: translate(40px, 30px) scale(1.1);
  }
}

@keyframes orbDrift2 {
  0%,
  100% {
    transform: translate(0, 0) scale(1);
  }
  50% {
    transform: translate(-35px, -25px) scale(1.15);
  }
}

@keyframes orbDrift3 {
  0%,
  100% {
    transform: translate(0, 0) scale(1);
  }
  50% {
    transform: translate(25px, -35px) scale(0.95);
  }
}

/* ---- 宽屏：左导航固定竖排，右面板占满 ---- */
@media (min-width: 900px) {
  .browse {
    grid-template-columns: 216px minmax(0, 1fr);
    gap: 32px;
    align-items: start;
  }

  .groups {
    position: sticky;
    top: calc(var(--header-h) + 20px);
  }

  .group-list {
    flex-direction: column;
    overflow: visible;
    gap: 4px;
  }

  .group-item {
    width: 100%;
    min-width: 0;
  }
}

@media (min-width: 1200px) {
  .browse {
    grid-template-columns: 236px minmax(0, 1fr);
    gap: 40px;
  }
}

@media (max-width: 899px) {
  .hero {
    padding: 52px 16px 44px;
  }
}
</style>