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
const DATA = path.join(ROOT, 'data')
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

  // ③ 型号未出现在产品名里（提示，不阻断）
  //    只查非小米品牌：小米/米家的 name 是营销名（如「巨省电Pro」），零售型号本来就不在名字里，
  //    查了只会产生大量噪音；竞品的 name 通常直接含型号，这一查能发现「抄错行」。
  for (const p of products) {
    if (p.brand === '小米') continue
    const code = p.model_code
    if (BLANK.has(code)) continue
    const name = String(p.name ?? '')
    const normalized = name.replace(/[\s\-_/]/g, '').toUpperCase()
    const c = String(code).replace(/[\s\-_/]/g, '').toUpperCase()
    if (c && !normalized.includes(c)) {
      warnings.push(`${cid}/${p.id}：model_code「${code}」未出现在产品名「${name}」中，请人工确认是否为同一机型`)
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
