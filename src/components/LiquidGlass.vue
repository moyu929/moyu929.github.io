<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import type { CSSProperties } from 'vue'

const props = withDefaults(
  defineProps<{
    /** 浮标直径（px），决定玻璃圆的大小 */
    size?: number
    /** 默认停靠位置（未拖动/无持久化时） */
    defaultPos?: 'left' | 'right'
    /** 徽标数字，>0 时显示 */
    badge?: number
  }>(),
  { size: 56, defaultPos: 'left', badge: 0 },
)

const emit = defineEmits<{
  (e: 'activate'): void
}>()

const SIZE = computed(() => props.size)
const FAB_DRAG_THRESHOLD = 6
const FAB_POS_KEY = 'compareFabPos'

const rootRef = ref<HTMLElement | null>(null)
/** 定位容器（.lg-wrap）：position 由它承载，拖动时直接改它的 style */
const wrapRef = ref<HTMLElement | null>(null)
const dragging = ref(false)
const pos = ref<{ x: number; y: number } | null>(null)
let off = { x: 0, y: 0 }
let start = { x: 0, y: 0 }
let pressed = false

// 拖动性能：pointermove 事件频率高于帧率，直接改 ref 会每帧触发 Vue 重渲染 +
// backdrop-filter 重算折射（重排成本极高）。这里改为 rAF 节流 + 拖动期直接写
// DOM style 绕过响应式，松手才同步回 ref。
let rafId = 0
let pendingX = 0
let pendingY = 0

// 读取持久化位置
try {
  const raw = localStorage.getItem(FAB_POS_KEY)
  if (raw) {
    const p = JSON.parse(raw)
    if (typeof p?.x === 'number' && typeof p?.y === 'number') pos.value = p
  }
} catch {
  /* 忽略损坏的存储 */
}

const style = computed<CSSProperties>(() => ({
  position: 'fixed',
  width: `${SIZE.value}px`,
  height: `${SIZE.value}px`,
  '--lg-size': `${SIZE.value}px`,
  right: 'auto',
  transform: 'none',
  ...(pos.value
    ? { left: `${pos.value.x}px`, top: `${pos.value.y}px`, bottom: 'auto' }
    : props.defaultPos === 'left'
      ? { left: '16px', bottom: '24px', top: 'auto' }
      : { right: '16px', bottom: '24px', left: 'auto', top: 'auto' }),
}))

function clamp(v: number, max: number) {
  return Math.max(0, Math.min(v, max))
}

function endDrag(emitActivate: boolean) {
  window.removeEventListener('pointermove', onMove)
  window.removeEventListener('pointerup', onUp)
  window.removeEventListener('pointercancel', onUp)
  window.removeEventListener('blur', cancelDrag)
  if (rafId) {
    cancelAnimationFrame(rafId)
    rafId = 0
  }
  if (!pressed) return
  pressed = false
  if (dragging.value) {
    // 拖动期间位置只写在 DOM 上，这里补写一次响应式状态，
    // 让 Vue 重新接管后续渲染（否则松手后 hover 态等会失效）
    pos.value = { x: pendingX, y: pendingY }
    dragging.value = false
    try {
      localStorage.setItem(FAB_POS_KEY, JSON.stringify(pos.value))
    } catch {
      /* 忽略写入失败 */
    }
  } else if (emitActivate) {
    emit('activate')
  }
}

function onDown(e: PointerEvent) {
  if (e.pointerType === 'mouse' && e.button !== 0) return
  // 防御：先清理可能残留的监听
  endDrag(false)
  pressed = true
  start = { x: e.clientX, y: e.clientY }
  dragging.value = false
  window.addEventListener('pointermove', onMove)
  window.addEventListener('pointerup', onUp)
  window.addEventListener('pointercancel', onUp)
  // 窗口失焦（如最小化/切走）时强制结束拖拽，避免监听残留把窗口拽回
  window.addEventListener('blur', cancelDrag)
}

function applyDrag() {
  rafId = 0
  const el = wrapRef.value
  if (!el) return
  // 拖动中直接改定位样式，不走 Vue 响应式（避免每帧重渲 + 重排）。
  // 用 transform 走合成层，比改 left/top 更跟手。
  el.style.left = `${pendingX}px`
  el.style.top = `${pendingY}px`
  el.style.bottom = 'auto'
  el.style.right = 'auto'
}

function onMove(e: PointerEvent) {
  if (!pressed) return
  if (!dragging.value) {
    const dx = e.clientX - start.x
    const dy = e.clientY - start.y
    if (Math.hypot(dx, dy) < FAB_DRAG_THRESHOLD) return
    dragging.value = true
    const r = (rootRef.value as HTMLElement).getBoundingClientRect()
    off = { x: e.clientX - r.left, y: e.clientY - r.top }
    // 拖动期禁用 backdrop-filter 折射——它是拖动卡顿的最大来源，
    // 每帧重算整个背景的位移贴图。松手后自动恢复。
    rootRef.value?.classList.add('is-dragging')
  }
  e.preventDefault()
  pendingX = clamp(e.clientX - off.x, window.innerWidth - SIZE.value)
  pendingY = clamp(e.clientY - off.y, window.innerHeight - SIZE.value)
  // 一帧只处理一次，避免事件频率高于刷新率时排队
  if (!rafId) rafId = requestAnimationFrame(applyDrag)
}

function onUp() {
  endDrag(true)
}

function cancelDrag() {
  endDrag(false)
}

// ============================================================
// 液态玻璃折射：严格复刻 shuding/liquid-glass
//  - 只有一个 backdrop-filter: url(#id) 作用在玻璃容器上
//  - 离屏 canvas 生成 displacement map（圆角矩形 SDF + smoothStep）
//  - 无任何元素使用 filter: url(#...)（那是错位/重影的根源）
// ============================================================
const uid = `lg-${Math.random().toString(36).slice(2, 8)}`
const canvasRef = ref<HTMLCanvasElement | null>(null)

// backdrop-filter：严格匹配原版参数
const glassStyle = computed<CSSProperties>(() => {
  const filter = `url(#${uid}) blur(0.25px) contrast(1.2) brightness(1.05) saturate(1.1)`
  return {
    backdropFilter: filter,
    WebkitBackdropFilter: filter,
  }
})
const mapHref = ref('')

function smoothStep(a: number, b: number, x: number) {
  const t = Math.max(0, Math.min(1, (x - a) / (b - a)))
  return t * t * (3 - 2 * t)
}

// 圆角矩形有符号距离场（UV 空间，-0.5..0.5）
function roundedRectSDF(x: number, y: number, halfW: number, halfH: number, r: number) {
  const qx = Math.abs(x) - (halfW - r)
  const qy = Math.abs(y) - (halfH - r)
  const ax = Math.max(qx, 0)
  const ay = Math.max(qy, 0)
  const outside = Math.hypot(ax, ay)
  const inside = Math.min(Math.max(qx, qy), 0)
  return outside + inside - r
}

// 原版 fragment：roundedRectSDF(ix, iy, 0.3, 0.2, 0.6)
//   displacement = smoothStep(0.8, 0, distanceToEdge - 0.15)
//   scaled = smoothStep(0, 1, displacement)
//   return texture(ix * scaled + 0.5, iy * scaled + 0.5)
// 使用原版 SDF 参数 (0.3, 0.3, 0.6)（对称化以适配正圆），
// 这些参数产生的折射梯度是液态玻璃质感的核心。
function fragment(uvx: number, uvy: number) {
  const ix = uvx - 0.5
  const iy = uvy - 0.5
  const distanceToEdge = roundedRectSDF(ix, iy, 0.3, 0.3, 0.6)
  const displacement = smoothStep(0.8, 0, distanceToEdge - 0.15)
  const scaled = smoothStep(0, 1, displacement)
  return { x: ix * scaled + 0.5, y: iy * scaled + 0.5 }
}

function buildDisplacementMap() {
  const cv = canvasRef.value
  if (!cv) return
  const dpr = Math.min(window.devicePixelRatio || 1, 2)
  const px = Math.max(2, Math.round(SIZE.value * dpr))
  cv.width = px
  cv.height = px
  const ctx = cv.getContext('2d')
  if (!ctx) return
  const img = ctx.createImageData(px, px)
  const d = img.data

  // 原版逐像素循环：uv = (x/px, y/px)
  let maxScale = 0
  const dxArr = new Float32Array(px * px)
  const dyArr = new Float32Array(px * px)
  for (let y = 0; y < px; y++) {
    for (let x = 0; x < px; x++) {
      const uvx = x / px
      const uvy = y / px
      const pos = fragment(uvx, uvy)
      const dx = pos.x * px - x
      const dy = pos.y * px - y
      const idx = y * px + x
      dxArr[idx] = dx
      dyArr[idx] = dy
      maxScale = Math.max(maxScale, Math.abs(dx), Math.abs(dy))
    }
  }
  maxScale *= 0.5

  for (let i = 0; i < px * px; i++) {
    const dx = dxArr[i]
    const dy = dyArr[i]
    const o = i * 4
    d[o] = clamp255((dx / maxScale + 0.5) * 255)
    d[o + 1] = clamp255((dy / maxScale + 0.5) * 255)
    d[o + 2] = 0
    d[o + 3] = 255
  }
  ctx.putImageData(img, 0, 0)
  mapHref.value = cv.toDataURL()

  // 原版：feDisplacementMap scale = maxScale / canvasDPI
  displacementScale.value = maxScale / dpr
}

function clamp255(v: number) {
  return Math.max(0, Math.min(255, Math.round(v)))
}

const displacementScale = ref(0)

onMounted(() => {
  buildDisplacementMap()
  window.addEventListener('resize', buildDisplacementMap)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', buildDisplacementMap)
  endDrag(false)
})
</script>

<template>
  <div ref="wrapRef" class="lg-wrap" :style="style">
    <!-- 液态玻璃 SVG 滤镜定义（唯一滤镜，仅作用于 backdrop-filter） -->
    <svg class="lg-svg" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
      <defs>
        <filter :id="uid" filterUnits="userSpaceOnUse" color-interpolation-filters="sRGB"
          x="0" y="0" :width="SIZE" :height="SIZE">
          <feImage :href="mapHref" :width="SIZE" :height="SIZE" :result="`${uid}_map`" />
          <feDisplacementMap
            in="SourceGraphic"
            :in2="`${uid}_map`"
            x-channel-selector="R"
            y-channel-selector="G"
            :scale="displacementScale"
          />
        </filter>
      </defs>
    </svg>

    <button
      ref="rootRef"
      class="liquid-glass"
      :class="{ dragging }"
      :style="glassStyle"
      @pointerdown="onDown"
    >
      <span class="glass-content">
        <svg class="glass-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M3 6h18M3 12h18M3 18h18" />
        </svg>
        <span class="glass-text">对比</span>
        <span v-if="badge > 0" class="glass-badge">{{ badge }}</span>
      </span>
    </button>

    <!-- 离屏位移图 -->
    <canvas ref="canvasRef" class="lg-canvas" aria-hidden="true"></canvas>
  </div>
</template>

<style scoped>
/* 层级与旧 FAB 一致：高于工具条（199/300），低于对比抽屉（399/400） */
.lg-wrap {
  z-index: 350;
}

.lg-svg {
  position: fixed;
  width: 0;
  height: 0;
  pointer-events: none;
}

.lg-canvas {
  position: absolute;
  width: 1px;
  height: 1px;
  opacity: 0;
  pointer-events: none;
}

/* 玻璃容器：backdrop-filter 唯一作用点（复刻原版 container） */
.liquid-glass {
  position: relative;
  width: 100%;
  height: 100%;
  border: none;
  border-radius: calc(var(--lg-size, 56px) / 2);
  padding: 0;
  cursor: grab;
  user-select: none;
  touch-action: none;
  background: var(--brand-glass-tint, rgba(108, 92, 231, 0.08));
  overflow: hidden;
  box-shadow:
    0 4px 8px rgba(0, 0, 0, 0.25),
    0 -10px 25px inset rgba(0, 0, 0, 0.15),
    inset 0 0 0 1px rgba(108, 92, 231, 0.2);
  transition: transform var(--dur-fast, 0.15s) var(--ease-spring, ease),
              box-shadow var(--dur-normal, 0.3s) var(--ease-smooth, ease);
}

.liquid-glass:hover {
  box-shadow:
    0 6px 16px rgba(108, 92, 231, 0.3),
    0 -10px 25px inset rgba(0, 0, 0, 0.15),
    inset 0 0 0 1px rgba(108, 92, 231, 0.35);
}

.liquid-glass:active {
  cursor: grabbing;
}

/* 拖动期：摘掉 backdrop-filter 折射（每帧重算背景位移贴图，是卡顿主因），
   换成半透明底色保持视觉连贯；松手立即恢复液态玻璃。 */
.liquid-glass.dragging {
  transition: none;
  cursor: grabbing;
  backdrop-filter: none !important;
  -webkit-backdrop-filter: none !important;
  background: rgba(108, 92, 231, 0.22);
  will-change: transform;
}

.glass-content {
  position: relative;
  z-index: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 1px;
  width: 100%;
  height: 100%;
  color: #fff;
  text-shadow: 0 1px 3px rgba(108, 92, 231, 0.5);
  font-weight: 700;
}

.glass-icon {
  width: 16px;
  height: 16px;
  filter: drop-shadow(0 0 4px rgba(162, 155, 254, 0.4));
}

.glass-text {
  font-size: 9.5px;
  line-height: 1;
  letter-spacing: 0.5px;
}

.glass-badge {
  position: absolute;
  top: -2px;
  right: -2px;
  min-width: 16px;
  height: 16px;
  padding: 0 4px;
  border-radius: 9999px;
  background: var(--brand, #6c5ce7);
  color: #fff;
  font-size: 10px;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.3);
  border: 1px solid rgba(255, 255, 255, 0.6);
}
</style>
