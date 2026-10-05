<script setup lang="ts">
/**
 * 首页：一级品类分组导航（默认）与品牌导航两种浏览方式。
 * 左侧竖排导航（一级品类 / 品牌），右侧展示该组下的具体品类。
 * 分组比品类更稳定，新增品类只需改 categories.json，不必动这里的结构。
 * 品牌视图的「哪个品牌在哪些品类里有几款」按需异步统计（首次切换才加载全部产品）。
 */
import { computed, onMounted, onBeforeUnmount, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import { categoryGroups, loadCategory } from '../data'
import type { CategoryGroup } from '../types'
import thumbs from 'virtual:category-thumbs'
import { useScrollReveal } from '../useScrollReveal'

const { setup: setupReveal } = useScrollReveal()

type ViewMode = 'scene' | 'brand'
const VIEW_MODE_KEY = 'home.viewMode'

/** 浏览方式：使用场景（默认）/ 品牌。记住用户上次的选择 */
const viewMode = ref<ViewMode>(
  localStorage.getItem(VIEW_MODE_KEY) === 'brand' ? 'brand' : 'scene',
)
watch(viewMode, (m) => {
  localStorage.setItem(VIEW_MODE_KEY, m)
  if (m === 'brand') void ensureBrandIndex()
  requestAnimationFrame(() => setupReveal())
})

function switchMode(m: ViewMode) {
  viewMode.value = m
}

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

/**
 * 键盘可达性：左右/上下方向键在导航项间移动。
 * 用 roving tabindex 让整列只有一个可 Tab 项，方向键负责在其余项间移动。
 */
function onNavKeydown(e: KeyboardEvent, index: number, total: number, select: (i: number) => void) {
  const delta = { ArrowDown: 1, ArrowRight: 1, ArrowUp: -1, ArrowLeft: -1 }[e.key]
  if (delta === undefined) return
  e.preventDefault()
  const next = Math.min(Math.max(index + delta, 0), total - 1)
  select(next)
  // 焦点跟着走，否则键盘用户按完方向键焦点还留在原处
  requestAnimationFrame(() => {
    document
      .querySelector<HTMLElement>(`#nav-${viewMode.value === 'scene' ? categoryGroups[next].id : `b${next}`}`)
      ?.focus()
  })
}

function selectGroup(id: string) {
  activeId.value = id
  // 换组后右侧是新内容，重新挂一次滚动揭示
  requestAnimationFrame(() => setupReveal())
}

// ---------------------------------------------------------------- 品牌视图

interface BrandCatEntry {
  cat: CategoryGroup['categories'][number]
  count: number
}
interface BrandEntry {
  brand: string
  total: number
  cats: BrandCatEntry[]
}

/** 品牌 → 各品类产品数。首次切到品牌视图才统计（要读全部品类的产品），之后缓存 */
const brandEntries = ref<BrandEntry[] | null>(null)
const brandLoading = ref(false)
const activeBrand = ref('')

const activeBrandEntry = computed(
  () => brandEntries.value?.find((b) => b.brand === activeBrand.value) ?? null,
)

async function ensureBrandIndex() {
  if (brandEntries.value || brandLoading.value) return
  brandLoading.value = true
  try {
    const catIds = categoryGroups.flatMap((g) => g.categories.map((c) => c.id))
    const catById = new Map(categoryGroups.flatMap((g) => g.categories.map((c) => [c.id, c])))
    const datas = await Promise.all(catIds.map((id) => loadCategory(id).catch(() => null)))
    const byBrand = new Map<string, Map<string, number>>()
    catIds.forEach((id, i) => {
      const d = datas[i]
      if (!d) return
      for (const p of d.products) {
        const brand = String(p.brand ?? '').trim()
        if (!brand || brand === '查不到') continue
        let cats = byBrand.get(brand)
        if (!cats) byBrand.set(brand, (cats = new Map()))
        cats.set(id, (cats.get(id) ?? 0) + 1)
      }
    })
    const entries: BrandEntry[] = [...byBrand.entries()].map(([brand, cats]) => ({
      brand,
      total: [...cats.values()].reduce((a, b) => a + b, 0),
      cats: [...cats.entries()]
        .map(([id, count]) => ({ cat: catById.get(id)!, count }))
        .filter((e) => e.cat)
        // 品类按目录顺序排，和场景视图里的排布一致
        .sort(
          (a, b) =>
            catIds.indexOf(a.cat.id) - catIds.indexOf(b.cat.id),
        ),
    }))
    // 品牌按产品总数降序，同数按名称（品牌中立，不做小米优先）
    entries.sort(
      (a, b) => b.total - a.total || a.brand.localeCompare(b.brand, 'zh-Hans-CN'),
    )
    brandEntries.value = entries
    if (!entries.find((b) => b.brand === activeBrand.value)) {
      activeBrand.value = entries[0]?.brand ?? ''
    }
    // 品牌索引是异步的：此前面板一直是「加载中」占位，卡片此刻才首次渲染。
    // viewMode watcher 里的那次 setupReveal 跑在占位态，抓不到任何 .reveal 节点；
    // 不在数据到位后重挂观察器，40 张卡片就会永远停在 opacity:0（面板看似空白）。
    requestAnimationFrame(() => setupReveal())
  } finally {
    brandLoading.value = false
  }
}

function selectBrand(brand: string) {
  activeBrand.value = brand
  requestAnimationFrame(() => setupReveal())
}

onMounted(() => {
  requestAnimationFrame(() => setupReveal())
  if (viewMode.value === 'brand') void ensureBrandIndex()
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
          <span class="hero-line hero-accent">全品类参数对照</span>
        </h1>
        <p class="hero-sub">
          参数逐条标注来源与核查时间，支持品牌与型号横向对比。
        </p>
      </div>
    </header>

    <!-- 浏览方式切换：使用场景（默认）/ 品牌 -->
    <div class="container mode-row">
      <div class="mode-switch" role="group" aria-label="浏览方式">
        <button
          type="button"
          class="mode-btn"
          :class="{ active: viewMode === 'scene' }"
          :aria-pressed="viewMode === 'scene'"
          @click="switchMode('scene')"
        >
          按使用场景
        </button>
        <button
          type="button"
          class="mode-btn"
          :class="{ active: viewMode === 'brand' }"
          :aria-pressed="viewMode === 'brand'"
          @click="switchMode('brand')"
        >
          按品牌
        </button>
      </div>
    </div>

    <!-- 一级品类（或品牌）导航 + 该组品类 -->
    <main id="main" class="container browse">
      <!-- 场景视图 -->
      <nav v-if="viewMode === 'scene'" class="groups" aria-label="一级品类">
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
              @keydown="onNavKeydown($event, i, categoryGroups.length, (n) => selectGroup(categoryGroups[n].id))"
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

      <section v-if="viewMode === 'scene' && activeGroup" class="cat-panel" :aria-labelledby="`group-${activeGroup.id}`">
        <header class="cat-head">
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
            <span class="card-thumb" aria-hidden="true">
              <img
                v-if="thumbs[c.id]"
                :src="thumbs[c.id]"
                alt=""
                width="320"
                height="320"
                loading="lazy"
                decoding="async"
              />
              <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
                <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z" />
                <polyline points="3.27 6.96 12 12.01 20.73 6.96" />
                <line x1="12" y1="22.08" x2="12" y2="12" />
              </svg>
            </span>
            <span class="card-text">
              <h3>{{ c.name }}</h3>
              <p>{{ c.description }}</p>
            </span>
            <span class="card-arrow" aria-hidden="true">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M9 18l6-6-6-6" />
              </svg>
            </span>
          </RouterLink>
        </div>
      </section>

      <!-- 品牌视图 -->
      <nav v-if="viewMode === 'brand'" class="groups" aria-label="品牌">
        <p class="groups-label">按品牌</p>
        <ul class="group-list">
          <li v-for="(b, i) in brandEntries ?? []" :key="b.brand">
            <button
              :id="`nav-b${i}`"
              type="button"
              class="group-item"
              :class="{ active: b.brand === activeBrand }"
              :aria-current="b.brand === activeBrand ? 'true' : undefined"
              :tabindex="b.brand === activeBrand ? 0 : -1"
              @click="selectBrand(b.brand)"
              @keydown="onNavKeydown($event, i, brandEntries?.length ?? 0, (n) => selectBrand(brandEntries![n].brand))"
            >
              <span class="group-index" aria-hidden="true">{{ pad2(i + 1) }}</span>
              <span class="group-text">
                <span class="group-name">{{ b.brand }}</span>
                <span class="group-count">{{ b.total }} 款</span>
              </span>
            </button>
          </li>
        </ul>
      </nav>

      <section v-if="viewMode === 'brand'" class="cat-panel" :aria-label="`品牌：${activeBrand}`">
        <p v-if="brandLoading || !activeBrandEntry" class="panel-loading">正在统计各品牌的产品…</p>
        <template v-else>
          <header class="cat-head">
            <h2>{{ activeBrandEntry.brand }}</h2>
            <p>{{ activeBrandEntry.cats.length }} 个品类 · {{ activeBrandEntry.total }} 款产品</p>
          </header>

          <div class="grid">
            <RouterLink
              v-for="e in activeBrandEntry.cats"
              :key="e.cat.id"
              class="card reveal"
              :to="{ path: `/${e.cat.id}`, query: { brand: activeBrandEntry.brand } }"
            >
              <span class="card-thumb" aria-hidden="true">
                <img
                  v-if="thumbs[e.cat.id]"
                  :src="thumbs[e.cat.id]"
                  alt=""
                  width="320"
                  height="320"
                  loading="lazy"
                  decoding="async"
                />
                <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
                  <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z" />
                  <polyline points="3.27 6.96 12 12.01 20.73 6.96" />
                  <line x1="12" y1="22.08" x2="12" y2="12" />
                </svg>
              </span>
              <span class="card-text">
                <h3>{{ e.cat.name }}</h3>
                <p>{{ e.cat.description }}</p>
              </span>
              <span class="card-count">{{ e.count }} 款</span>
              <span class="card-arrow" aria-hidden="true">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
                  <path d="M9 18l6-6-6-6" />
                </svg>
              </span>
            </RouterLink>
          </div>
        </template>
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
  text-align: center;
}

.hero-eyebrow {
  display: inline-block;
  font-size: 11.5px;
  font-weight: 600;
  letter-spacing: 0.18em;
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
  align-items: center;
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
  margin-inline: auto;
  animation: titleIn 0.6s var(--ease-out) both;
  animation-delay: 0.16s;
}

/* ============================================================
   浏览方式切换：分段控件
   ============================================================ */
.mode-row {
  display: flex;
  justify-content: center;
  padding-block: 22px 0;
}

.mode-switch {
  display: inline-flex;
  gap: 2px;
  padding: 3px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--surface);
}

.mode-btn {
  padding: 6px 16px;
  border: 1px solid transparent;
  border-radius: var(--radius-xs);
  background: transparent;
  color: var(--text-muted);
  font: inherit;
  font-size: 13px;
  font-weight: 550;
  cursor: pointer;
  transition:
    background var(--dur-fast) var(--ease-smooth),
    color var(--dur-fast) var(--ease-smooth),
    border-color var(--dur-fast) var(--ease-smooth);
}

.mode-btn:hover {
  color: var(--text);
}

.mode-btn.active {
  background: var(--brand-surface);
  border-color: var(--border-brand);
  color: var(--brand);
}

.mode-btn:focus-visible {
  outline: 2px solid var(--brand);
  outline-offset: 2px;
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
.cat-panel {
  min-width: 0;
}

.cat-head {
  display: flex;
  align-items: baseline;
  gap: 10px;
  padding-bottom: 12px;
  margin-bottom: 14px;
  border-bottom: 1px solid var(--border);
}

.cat-head h2 {
  font-family: var(--font-display);
  font-size: 19px;
  font-weight: 700;
  letter-spacing: -0.01em;
}

.cat-head p {
  font-size: 12.5px;
  color: var(--text-faint);
}

.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(228px, 1fr));
  gap: 8px;
}

/* 品类卡：靠底色与内边距分层，不靠边框+阴影堆叠。
   卡片数量多（一屏十几个），阴影一多就全是噪音。
   左侧缩略图 + 右侧文字两列，用户不读字也能靠图找到品类。 */
.card {
  position: relative;
  display: flex;
  align-items: center;
  gap: 11px;
  padding: 11px 34px 11px 11px;
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

/* 品类缩略图：与产品卡（ProductCard .thumb）同款视觉，等比缩小 */
.card-thumb {
  width: 45px;
  height: 54px;
  flex-shrink: 0;
  border-radius: var(--radius-sm);
  overflow: hidden;
  background: var(--surface-alt);
  display: flex;
  align-items: center;
  justify-content: center;
}

.card-thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.card-thumb svg {
  width: 20px;
  height: 20px;
  color: var(--text-faint);
  opacity: 0.4;
}

/* 文本列：h3 + 描述，压缩到缩略图右侧；
   右侧让开 20px 给「N 款」角标，避免长描述与角标贴字 */
.card-text {
  min-width: 0;
  padding-right: 20px;
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

/* 品牌视图卡片右下的品类内产品数 */
.card-count {
  position: absolute;
  right: 13px;
  bottom: 11px;
  font-family: var(--font-mono);
  font-size: 10.5px;
  color: var(--text-faint);
  font-variant-numeric: tabular-nums;
}

.panel-loading {
  padding: 28px 2px;
  font-size: 13px;
  color: var(--text-faint);
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
