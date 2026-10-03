#!/usr/bin/env node
/**
 * 数据一致性检查（`npm run data:lint`）
 * ------------------------------------------------------------------
 * `validate`（scripts/validate-data.mjs）管的是「数据合不合法」——schema 一致性、
 * 必填的审核标注字段、图片是否存在。它管不了「数据对不对」。
 * 本脚本补的是后者，都是**跑得起来但数据错**的那一类：

 *   ① 同品类内 model_code 重复 —— 两个 Agent 各自补型号时最容易撞出的问题，
 *      合并到 main 之后才暴露（乙评 §6.2 明确提过，他当时是手工查出来的）
 *   ② 同品类内产品名完全相同 —— 大概率是重复收录
 *   ③ 型号与产品名一致性（warning）—— model_code 未出现在 name 里，值得人看一眼
 *   ④ 审核标注字段覆盖率（warning）—— 库内历史数据按设计不强制（见 product-check.mjs），
 *      这里只报数，不阻断
 *
 * 退出码：有 error 时非零（供 CI 与 npm run check 使用）。
 */
import fs from 'node:fs'
import path from 'node:path'
import process from 'node:process'

const ROOT = path.resolve(import.meta.dirname, '..')
// 与 flow.mjs / validate-data.mjs 一致：可用 FLOW_DATA_DIR 指向数据副本做演练
const DATA = process.env.FLOW_DATA_DIR ? path.resolve(ROOT, process.env.FLOW_DATA_DIR) : path.join(ROOT, 'data')
const BLANK = new Set(['查不到', '—', '', null, undefined])
const AUDIT_FIELDS = ['verify_status', 'verify_date', 'verify_source', 'verify_url', 'change_log', 'updated_at']

const readJson = (p, fallback = null) => {
  try {
    return JSON.parse(fs.readFileSync(p, 'utf8'))
  } catch {
    return fallback
  }
}

const groups = readJson(path.join(DATA, 'categories.json'), []) ?? []
const cats = groups.flatMap((g) => g?.categories ?? [])
/** 已登记的「同机型不同 SKU」共用型号例外（见 data/_sources/shared-model-codes.json） */
const sharedAllowed = readJson(path.join(DATA, '_sources', 'shared-model-codes.json'), {}) ?? {}

const errors = []
const warnings = []
let total = 0

for (const cat of cats) {
  const cid = cat.id
  const products = readJson(path.join(DATA, cid, 'products.json'), []) ?? []
  total += products.length

  // ① model_code 重复（同品类内，忽略空值）
  const byCode = new Map()
  for (const p of products) {
    const code = p.model_code
    if (BLANK.has(code)) continue
    const key = String(code).trim()
    if (!byCode.has(key)) byCode.set(key, [])
    byCode.get(key).push(p.id)
  }
  for (const [code, ids] of byCode) {
    if (ids.length > 1) {
      const reason = sharedAllowed[`${cid}/${code}`]
      if (reason) {
        warnings.push(`${cid}：model_code「${code}」由 ${ids.length} 款共用（已登记例外：同机型不同 SKU）—— ${ids.join('、')}`)
      } else {
        errors.push(`${cid}：model_code「${code}」被 ${ids.length} 款产品共用 —— ${ids.join('、')}`)
      }
    }
  }

  // ② 产品名完全相同
  const byName = new Map()
  for (const p of products) {
    const name = String(p.name ?? '').trim()
    if (!name) continue
    if (!byName.has(name)) byName.set(name, [])
    byName.get(name).push(p.id)
  }
  for (const [name, ids] of byName) {
    if (ids.length > 1) {
      errors.push(`${cid}：产品名「${name}」重复 —— ${ids.join('、')}`)
    }
  }

  // ③「型号未出现在产品名里」（warning，**仅对竞品生效**）
  //
  //    原先整条规则被撤，理由是「以误报为主」。复核后那个统计口径有问题：
  //    「产品名应含 model_code」在真实数据上命中 79 例，但**拆开看是 79 例小米系 + 0 例竞品**——
  //    合并统计成「60+ 例误报」掩盖了两者性质完全不同：
  //
  //      · 小米系：产品名是营销名（"米家空调 巨省电Pro 大1匹"），国标型号
  //        （KFR-26GW-NA20/V1A1）本就不出现在名称里，对小米系检查**必然全误报**；
  //      · 竞品：529 款回填的型号全部来自产品名（fill-model-codes.py 的逻辑），
  //        实测 **0 例误报**。
  //
  //    所以规则不是「无效」，而是「作用域错了」。限定 brand !== '小米' 后：
  //    - 噪音归零（79 例全部是小米系）
  //    - 保留对竞品的检查能力：若将来有型号不是从名称提取的（手工填错、
  //      从别处导入），这条能报警
  //
  //    「同族但不同」（前缀相同、长度相近）那条启发式仍然不做——复核 13 对命中，
  //    全是合法后缀变体（P / Pro / S / ET 是厂家区分型号的方式），噪音大于价值。
  //    型号抄错仍主要靠**参数逐项比对**发现（见 HANDOFF §0.3 用官方 API 核对
  //    制冷量/风量/噪音的做法）。
  for (const p of products) {
    if (p.brand === '小米') continue
    const code = String(p.model_code ?? '').trim()
    const name = String(p.name ?? '')
    if (!code || code === '查不到' || code === '—') continue
    if (!name.toLowerCase().includes(code.toLowerCase())) {
      warnings.push(
        `${cid}/${p.id}：model_code「${code}」未出现在产品名「${name}」里 —— 若型号来自官方/说明书而非产品名属正常；` +
          `若是从别处抄来，值得核对是否与本款对应`,
      )
    }
  }

  // ④ 审核标注字段覆盖率（报数，不阻断）
  const missing = products.filter((p) => AUDIT_FIELDS.some((f) => !(f in p))).length
  if (missing) {
    warnings.push(`${cid}：${missing}/${products.length} 款缺少部分审核标注字段（库内历史数据按设计不强制，流转中的数据由关口强制）`)
  }
}

console.log(`数据一致性检查：${cats.length} 个品类 / ${total} 款产品`)
if (warnings.length) {
  console.log(`\n提示 ${warnings.length} 条（不阻断）：`)
  for (const w of warnings.slice(0, 20)) console.log(`  · ${w}`)
  if (warnings.length > 20) console.log(`  …另有 ${warnings.length - 20} 条`)
}
if (errors.length) {
  console.error(`\n错误 ${errors.length} 条：`)
  for (const e of errors) console.error(`  ✗ ${e}`)
  console.error('\n重复型号 / 重复名称会让「按型号去重」失效，也会让对比页出现两条同款，请先修掉。')
  process.exit(1)
}
console.log('\n一致性检查通过（无重复型号、无重复产品名）')
