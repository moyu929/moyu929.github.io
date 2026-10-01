<script setup lang="ts">
/**
 * 数据来源与免责声明。
 *
 * 两部分：
 *  - 页脚只留一行居中的定性文案，不再塞按钮（原来按钮和文案挤在一行，
 *    文案长时就换行错位）
 *  - 弹窗由外部触发（见 App.vue 右上角操作组），或首页首次访问自动弹出
 *
 * 关闭动画走 macOS 的「神奇效果」（genie effect）：窗口不是简单淡出缩小，
 * 而是被吸进底部按钮方向 —— 下边缘先收、上边缘后收，形成一个漏斗。
 * 纯 CSS 用两段 clip-path + 圆角形变近似，不需要逐帧 JS 驱动。
 */
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'

const NOTICE: Section[] = [
  {
    title: '数据来源',
    items: [
      '本站参数来自公开渠道：各品牌官方商城的在售商品页、官网规格页，公开的 MIoT 产品库（home.miot-spec.com），以及太平洋产品报价等第三方规格站。',
      '每款产品的「信息来源 / 来源链接 / 核查时间」字段标注了该条数据的具体出处，可按来源自行复核。',
      '每条产品都带「核查状态」：已核验（多源）表示至少两个独立来源相互印证；已核验（官方商城）表示名称、价格、图片取自品牌官方在售目录；已核验（第三方）表示参数来自权威第三方规格站、尚无第二来源印证；待核验表示仅早期录入、尚未找到可追溯来源。',
    ],
  },
  {
    title: '合法合规',
    items: [
      '本站只采集公开可得的产品参数与公开售价，不包含任何非公开资料、内部文档、个人隐私信息或商业秘密。',
      '采集时遵守目标站点的访问频率限制，不做高频请求、不绕过访问控制、不抓取登录后内容。',
      '若相关权利人认为本站内容不妥，请联系我们，会在核实后立即删除或更正。',
    ],
  },
  {
    title: '非官方声明',
    items: [
      '本站是个人爱好者整理的参数库，与收录涉及的各品牌厂商没有任何隶属、代理或合作关系，也不代表其立场。',
      '「小米」「米家」等商标、产品图片与相关素材的权利归各自权利人所有，本站仅作产品说明与对比之用。',
      '本站不销售任何商品，不提供购买、售后或维修服务。',
    ],
  },
  {
    title: '观点声明',
    items: [
      '产品优缺点、选购建议、排序与对比结论均为个人主观判断，仅代表个人观点，不构成任何购买建议、投资建议或专业意见。',
      '不同来源的测试条件与口径可能不同，数值横向对比仅供参考。',
      '购买决策请以厂商官方页面、实物与官方客服说明为准。',
    ],
  },
  {
    title: '数据准确性',
    items: [
      '产品参数、价格与在售状态随时间变化，本站数据可能滞后、遗漏或存在录入错误。',
      '数据中写「查不到」表示尚未找到可靠来源，不代表该参数不存在或该型号不存在。',
      '同一款产品若被不同品牌以相近名称出售，本站按各自品牌分列，不合并计数。',
      '第三方来源（如规格站）可能存在字段错标，本站对可疑数值采取「宁缺勿错」策略，未通过校验的值一律留空而不估算。',
    ],
  },
  {
    title: '价格与二手价',
    items: [
      '「官方价」为整理时的官方在售价格快照，可能已变动，具体以官方渠道实时页面为准。',
      '「二手价」仅为阶段性行情参考，波动很大，不构成报价或成交依据。',
    ],
  },
  {
    title: '纠错与联系',
    items: [
      '发现错误或希望补充型号，欢迎通过仓库 Issue 提出，会核实后更新，并在对应产品的「修改记录」字段中留下改动痕迹。',
      '所有改动都会记录核查时间与来源，方便回溯。',
    ],
  },
]

interface Section {
  title: string
  items: string[]
}

/**
 * 「今日不再弹出」的标记键（值是当天日期 YYYY-MM-DD）。
 * 只有点过这个按钮，当天内的首页访问才不再自动弹；否则每次访问首页都会弹。
 */
const DISMISS_KEY = 'app-notice-dismissed-on'

function today(): string {
  const d = new Date()
  const p = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`
}

const open = ref(false)
const closing = ref(false)

function readStore(key: string): string | null {
  try {
    return localStorage.getItem(key)
  } catch {
    return null
  }
}

function writeStore(key: string, value: string) {
  try {
    localStorage.setItem(key, value)
  } catch {
    /* 隐私模式下写入会失败，降级为「本次会话不自动弹」即可 */
  }
}

function close() {
  if (closing.value) return
  closing.value = true
  // 等收起动画播完再卸载，避免动画中途元素消失变成生硬淡出
  setTimeout(() => {
    open.value = false
    closing.value = false
  }, 420)
}

/** 「今日不再弹出」：今天内首页不再自动弹，但仍可从右上角按钮打开 */
function dismissForToday() {
  writeStore(DISMISS_KEY, today())
  close()
}

/** 打开声明（右上角按钮） */
function show() {
  open.value = true
}

function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape' && open.value) close()
}

/** 首页自动弹窗：今天点过「今日不再弹出」就不再弹 */
function maybeAutoShow() {
  if (readStore(DISMISS_KEY) === today()) return
  open.value = true
}

const route = useRoute()

onMounted(() => {
  document.addEventListener('keydown', onKeydown)
})

// 自动弹出只发生在首页。组件挂在 App 上不会随路由切换重新 mount，
// 所以每次路由变化都要重新判断：进首页且当天没点过「今日不再弹出」就弹。
watch(
  () => route.path,
  (path) => {
    if (path === '/' || path === '') maybeAutoShow()
    // 离开首页时若弹窗还开着（用户没点就点了品类卡），立即关掉
    else if (open.value) close()
  },
  { immediate: true },
)

onBeforeUnmount(() => {
  document.removeEventListener('keydown', onKeydown)
})

defineExpose({ show })
</script>

<template>
  <footer class="notice-bar">
    <p class="bar-text">
      本站为个人整理的多品牌家电参数库，非任何厂商官方 · 数据来自公开渠道并逐条标注来源 · 评价与建议仅代表个人观点
    </p>
  </footer>

  <Teleport to="body">
    <Transition name="modal">
      <div v-if="open" class="overlay" :class="{ closing }" @click.self="close">
        <div
          class="panel"
          role="dialog"
          aria-modal="true"
          aria-labelledby="notice-title"
          @click.stop
        >
          <header class="panel-head">
            <div>
              <h2 id="notice-title">数据来源与免责声明</h2>
              <p class="panel-sub">叠甲须知 · 请在使用本站数据前阅读</p>
            </div>
            <button class="close" type="button" aria-label="关闭" @click="close">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round">
                <path d="M18 6 6 18M6 6l12 12" />
              </svg>
            </button>
          </header>

          <div class="panel-body">
            <section v-for="s in NOTICE" :key="s.title" class="block">
              <h3>{{ s.title }}</h3>
              <ul>
                <li v-for="(t, i) in s.items" :key="i">{{ t }}</li>
              </ul>
            </section>
            <p class="stamp">以上须知随站点数据同步更新 · 最近更新 2026-10-01</p>
          </div>

          <!-- 按钮区固定在面板底部：与滚动主体分离，滚多长都在原位 -->
          <footer class="panel-foot">
            <button class="foot-btn ghost" type="button" @click="dismissForToday">
              今日不再弹出
            </button>
            <button class="foot-btn solid" type="button" @click="close">
              关闭声明
            </button>
          </footer>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
/* ============ 页脚文案（只留一行，居中） ============ */
.notice-bar {
  border-top: 1px solid var(--border-soft);
  background: var(--surface-alt);
  padding: 18px 16px 22px;
  text-align: center;
}

.bar-text {
  font-size: 12px;
  color: var(--text-faint);
  line-height: 1.7;
  max-width: 68ch;
  margin: 0 auto;
}

/* ============ 弹窗 ============ */
.overlay {
  position: fixed;
  inset: 0;
  z-index: 500;
  background: rgba(20, 18, 14, 0.5);
  backdrop-filter: blur(6px);
  -webkit-backdrop-filter: blur(6px);
  display: flex;
  align-items: flex-end;
  justify-content: center;
  padding: 0;
}

.panel {
  width: 100%;
  max-width: 680px;
  max-height: 86vh;
  display: flex;
  flex-direction: column;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg) var(--radius-lg) 0 0;
  box-shadow: var(--shadow-lg);
  overflow: hidden;
  /* genie 动画要作用在 transform/clip-path 上，这里给个变换原点 */
  transform-origin: 50% 100%;
}

.panel-head {
  flex-shrink: 0;
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  padding: 18px 18px 14px;
  border-bottom: 1px solid var(--border-soft);
}

.panel-head h2 {
  font-family: var(--font-display);
  font-size: 17px;
  font-weight: 700;
}

.panel-sub {
  margin-top: 4px;
  font-size: 12px;
  color: var(--text-faint);
}

.close {
  flex-shrink: 0;
  width: 30px;
  height: 30px;
  display: grid;
  place-items: center;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--surface);
  color: var(--text-muted);
  transition:
    background var(--dur-fast) var(--ease-smooth),
    color var(--dur-fast) var(--ease-smooth);
}

.close:hover {
  background: var(--surface-hover);
  color: var(--text);
}

.close svg {
  width: 15px;
  height: 15px;
}

/* 主体独立滚动，按钮区因此永远在底部 */
.panel-body {
  flex: 1;
  min-height: 0;
  padding: 6px 18px 20px;
  overflow-y: auto;
  -webkit-overflow-scrolling: touch;
}

/* ============ 底部按钮区 ============ */
.panel-foot {
  flex-shrink: 0;
  display: flex;
  gap: 10px;
  justify-content: flex-end;
  padding: 12px 18px;
  border-top: 1px solid var(--border-soft);
  background: var(--surface-alt);
}

.foot-btn {
  font: inherit;
  font-size: 13px;
  font-weight: 600;
  padding: 8px 18px;
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition:
    background var(--dur-fast) var(--ease-smooth),
    border-color var(--dur-fast) var(--ease-smooth),
    color var(--dur-fast) var(--ease-smooth),
    transform var(--dur-fast) var(--ease-out);
}

.foot-btn:active {
  transform: scale(0.98);
}

.foot-btn.ghost {
  background: transparent;
  border: 1px solid var(--border);
  color: var(--text-muted);
}

.foot-btn.ghost:hover {
  background: var(--surface);
  border-color: var(--border-strong);
  color: var(--text);
}

.foot-btn.solid {
  background: var(--brand);
  border: 1px solid var(--brand);
  color: #fff;
}

.foot-btn.solid:hover {
  background: var(--brand-dark);
  border-color: var(--brand-dark);
}

/* ============ 条款正文 ============ */
.block {
  padding: 14px 0;
  border-bottom: 1px dashed var(--border-soft);
}

.block:last-of-type {
  border-bottom: 0;
}

.block h3 {
  font-size: 13px;
  font-weight: 700;
  color: var(--brand);
  margin-bottom: 8px;
  display: flex;
  align-items: center;
  gap: 6px;
}

.block h3::before {
  content: '';
  width: 3px;
  height: 13px;
  border-radius: 2px;
  background: var(--brand);
}

.block ul {
  display: grid;
  gap: 6px;
}

.block li {
  position: relative;
  font-size: 12.5px;
  line-height: 1.75;
  color: var(--text-muted);
  padding-left: 14px;
}

.block li::before {
  content: '';
  position: absolute;
  left: 2px;
  top: 8px;
  width: 4px;
  height: 4px;
  border-radius: 50%;
  background: var(--text-faint);
}

.stamp {
  margin-top: 14px;
  text-align: center;
  font-size: 11px;
  color: var(--text-faint);
}

/* ============ 进出动画 ============ */

/* 进入：底部升起，模仿窗口从 Dock 展开 */
.modal-enter-active .panel {
  animation: panelRise 0.34s var(--ease-out) both;
}

.modal-enter-active .overlay {
  animation: fadeIn 0.24s var(--ease-smooth) both;
}

@keyframes panelRise {
  from {
    opacity: 0;
    transform: translateY(24px) scaleY(0.86);
  }
  to {
    opacity: 1;
    transform: translateY(0) scaleY(1);
  }
}

@keyframes fadeIn {
  from {
    opacity: 0;
  }
  to {
    opacity: 1;
  }
}

/* 退出：macOS 神奇效果。
   真 genie 是窗口被吸向 Dock 按钮，形状沿路径拉伸 —— 这里用
   「下边缘不动、上边缘向下收窄 + 整体缩放」近似出漏斗形。 */
.closing .panel {
  animation: genieClose 0.4s cubic-bezier(0.5, 0, 0.75, 0) both;
}

@keyframes genieClose {
  0% {
    transform: translateY(0) scaleY(1);
    transform-origin: 50% 100%;
  }
  55% {
    transform: translateY(10px) scaleY(0.28) scaleX(0.72);
    transform-origin: 50% 100%;
  }
  100% {
    transform: translateY(18px) scaleY(0.02) scaleX(0.12);
    transform-origin: 50% 100%;
  }
}

.closing {
  animation: fadeOut 0.4s var(--ease-smooth) both;
}

@keyframes fadeOut {
  from {
    opacity: 1;
  }
  to {
    opacity: 0;
  }
}

@media (prefers-reduced-motion: reduce) {
  .modal-enter-active .panel,
  .closing .panel,
  .modal-enter-active .overlay,
  .closing {
    animation: none;
  }
}

@media (min-width: 768px) {
  .overlay {
    align-items: center;
    padding: 24px;
  }

  .panel {
    border-radius: var(--radius-lg);
    max-height: 80vh;
  }

  .panel-head {
    padding: 22px 26px 16px;
  }

  .panel-body {
    padding: 8px 26px 26px;
  }

  .block li {
    font-size: 13px;
  }
}
</style>