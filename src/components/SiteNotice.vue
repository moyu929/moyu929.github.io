<script setup lang="ts">
/**
 * 站点须知（叠甲）——数据来源、合规、非官方与观点声明。
 * 全站页脚常驻一行摘要，点击展开完整条款；条款文案集中在本文件的 NOTICE 常量里，改文案只改这里。
 */
import { onBeforeUnmount, ref, watch } from 'vue'

const open = ref(false)

interface Section {
  title: string
  items: string[]
}

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

function close() {
  open.value = false
}

function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape' && open.value) close()
}

watch(open, (v) => {
  document.documentElement.style.overflow = v ? 'hidden' : ''
  if (v) document.addEventListener('keydown', onKeydown)
  else document.removeEventListener('keydown', onKeydown)
})

onBeforeUnmount(() => {
  document.removeEventListener('keydown', onKeydown)
  document.documentElement.style.overflow = ''
})
</script>

<template>
  <footer class="notice-bar">
    <div class="bar-inner">
      <p class="bar-text">
        本站为个人整理的多品牌家电参数库，非任何厂商官方 · 数据来自公开渠道并逐条标注来源 · 评价与建议仅代表个人观点
      </p>
      <button class="bar-btn" type="button" @click="open = true">
        数据来源与免责声明
      </button>
    </div>
  </footer>

  <Teleport to="body">
    <Transition name="fade">
      <div v-if="open" class="overlay" @click.self="close">
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
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.notice-bar {
  border-top: 1px solid var(--border-soft);
  background: var(--surface-alt);
  padding: 20px 16px 28px;
}

.bar-inner {
  max-width: var(--page-max);
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
  text-align: center;
}

.bar-text {
  font-size: 12px;
  line-height: 1.7;
  color: var(--text-faint);
}

.bar-btn {
  font: inherit;
  font-size: 12px;
  font-weight: 600;
  color: var(--brand);
  background: var(--brand-surface);
  border: 1px solid var(--border-brand);
  border-radius: var(--radius-full);
  padding: 6px 16px;
  cursor: pointer;
  transition: background var(--dur-fast) var(--ease-smooth),
              transform var(--dur-fast) var(--ease-out);
}

.bar-btn:hover {
  background: var(--brand-soft);
  transform: translateY(-1px);
}

.bar-btn:active {
  transform: translateY(0);
}

.overlay {
  position: fixed;
  inset: 0;
  z-index: 500;
  background: rgba(20, 18, 40, 0.45);
  backdrop-filter: blur(6px);
  display: flex;
  align-items: flex-end;
  justify-content: center;
  padding: 0;
}

.panel {
  width: 100%;
  max-width: 720px;
  max-height: 86vh;
  display: flex;
  flex-direction: column;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg) var(--radius-lg) 0 0;
  box-shadow: var(--shadow-lg);
  overflow: hidden;
}

.panel-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  padding: 20px 20px 14px;
  border-bottom: 1px solid var(--border-soft);
}

.panel-head h2 {
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
  width: 32px;
  height: 32px;
  display: grid;
  place-items: center;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--surface);
  color: var(--text-muted);
  cursor: pointer;
  transition: background var(--dur-fast) var(--ease-smooth);
}

.close:hover {
  background: var(--surface-hover);
}

.close svg {
  width: 16px;
  height: 16px;
}

.panel-body {
  padding: 8px 20px 24px;
  overflow-y: auto;
  -webkit-overflow-scrolling: touch;
}

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
  color: var(--brand-dark);
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
  background: var(--brand-gradient);
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
  background: var(--brand-light);
}

.stamp {
  margin-top: 14px;
  text-align: center;
  font-size: 11px;
  color: var(--text-faint);
}

.fade-enter-active,
.fade-leave-active {
  transition: opacity var(--dur-normal) var(--ease-smooth);
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}

@media (min-width: 768px) {
  .bar-inner {
    flex-direction: row;
    justify-content: space-between;
    text-align: left;
  }

  .overlay {
    align-items: center;
    padding: 24px;
  }

  .panel {
    border-radius: var(--radius-lg);
    max-height: 80vh;
  }

  .panel-head {
    padding: 24px 28px 16px;
  }

  .panel-body {
    padding: 8px 28px 28px;
  }

  .block li {
    font-size: 13px;
  }
}
</style>
