#!/usr/bin/env node
/**
 * 数据分区流转（多 Agent 并行协作的基础设施）
 * ------------------------------------------------------------------
 * 用物理目录隔离数据的「状态」：一个产品任一时刻只待在一个分区里，
 * 文件的位置就是它的状态，各 Agent 只写自己的分区，无需互相盯状态标签。
 *
 *   data/_draft/<品类>/<id>.json      草稿区   —— 采集方 A 的工作台（半成品随意改，只有 A 写）
 *   data/_intake/<品类>/<id>.json     待入库区 —— A 提交完成、等待 B 认领的交接队列
 *   data/_review/<品类>/<id>.json     修正区   —— 审核修正方 B 的工作台（核验/修正中，只有 B 写）
 *   data/<品类>/products.json         已入库区 —— 线上站点唯一数据源（只有 B 经 publish 写入）
 *
 * 每次流转都追加记录到 data/_flow/journal.jsonl（入库共享，append-only）。
 *
 * 用法（npm 同名脚本去掉前缀，如 `npm run flow:submit -- heater/ht_x`）：
 *   flow.mjs submit   <品类/id>...                    A：草稿区 → 待入库区（收录完成，提交待审）
 *   flow.mjs withdraw <品类/id>...                    A：待入库区 → 草稿区（提交后想继续改，撤回）
 *   flow.mjs claim    <品类/id>... [--force]          B：待入库区 → 修正区（认领，开始核验）
 *                     [--from <提交人>]               按提交人批量认领（不必手工拼 key 列表）
 *   flow.mjs recall   <品类/id>... --reason "…"       B：已入库区 → 修正区（召回复审，产品暂时下架）
 *   flow.mjs publish  <品类/id>... [--skip-legacy]    B：修正区 → 已入库区（修正完成，入库上线）
 *   flow.mjs return   <品类/id>... --reason "…"       B：待入库区 → 草稿区（不符收录标准，退回）
 *   flow.mjs drop     <品类/id>... --reason "…"       B：修正区删除（召回后判定不该收录；需用户确认）
 *   flow.mjs status   [--category 品类] [--zone draft|intake|review] [--by 提交人/认领人]
 *                     [--unclassified] [--n 条数]
 *   flow.mjs log      [-n 条数] [--batch <批次id>]
 *
 * 约定：分区文件入库（它们是各 Agent 的共享状态）；流转命令不做任何 git 操作，
 * 跑完当场提交。规则见仓库根目录 AGENTS.md。
 *
 * 批量语义（2026-10-03 起）：
 *   - 每次调用生成一个 batch id 并写进本批每条 journal，`flow:log --batch <id>` 可回查；
 *   - 命令结束打印「成功 / 已是目标态 / 失败」汇总，中途失败后**原样重跑**即可续上
 *     （已完成的项报告「已是目标态」而不是报错）。
 */
import crypto from 'node:crypto'
import { execFileSync } from 'node:child_process'
import fs from 'node:fs'
import path from 'node:path'
import process from 'node:process'
import { checkAuditFields, checkCategory, checkProduct, checkSchema } from './lib/product-check.mjs'
import { hashText, loadLibrary, saveLibrary } from './lib/library-io.mjs'

const ROOT = path.resolve(import.meta.dirname, '..')
// 测试时可设 FLOW_DATA_DIR 指向临时数据目录，避免污染真实 data/
const DATA = process.env.FLOW_DATA_DIR ? path.resolve(ROOT, process.env.FLOW_DATA_DIR) : path.join(ROOT, 'data')
const JOURNAL = path.join(DATA, '_flow', 'journal.jsonl')

const ZONES = {
  draft: { dir: '_draft', name: '草稿区' },
  intake: { dir: '_intake', name: '待入库区' },
  review: { dir: '_review', name: '修正区' },
  library: { dir: '', name: '已入库区' },
}
const FLOW_ORDER = ['draft', 'intake', 'review', 'library']

function ensureDir(d) {
  fs.mkdirSync(d, { recursive: true })
}

function readJson(file, fallback = null) {
  try {
    return JSON.parse(fs.readFileSync(file, 'utf8'))
  } catch {
    return fallback
  }
}

function writePretty(file, data) {
  ensureDir(path.dirname(file))
  fs.writeFileSync(file, JSON.stringify(data, null, 2) + '\n', 'utf8')
}

/** 跨分区移动一个产品文件（目标分区目录可能还不存在，先建再搬） */
function moveFile(src, dst) {
  ensureDir(path.dirname(dst))
  fs.copyFileSync(src, dst)
  fs.rmSync(src)
  // 源目录可能因此变空 —— 空目录会被 git 忽略，但会让 flow:status 的输出误导他人
  pruneEmptyDirs(path.dirname(src))
}

/** 删掉空的分区品类目录（只删到分区根为止，不越过分区边界） */
function pruneEmptyDirs(dir) {
  let cur = dir
  while (cur && fs.existsSync(cur)) {
    // 到了分区根（data/_intake 这一层）就停：分区目录本身要保留
    if (Object.values(ZONES).some((z) => z.dir && path.basename(cur) === z.dir)) return
    if (fs.readdirSync(cur).length > 0) return
    fs.rmdirSync(cur)
    cur = path.dirname(cur)
  }
}

/** 已入库区的读写统一走 lib/library-io.mjs：规范化序列化 + 写前指纹校验 + 文件锁重试 */
function readLibrary(key) {
  return loadLibrary(libFile(key))
}

/** 键值稳定序列化 + 指纹：与 audit-lock.mjs 同款，流转日志可据此比对内容变化 */
function stable(value) {
  if (Array.isArray(value)) return `[${value.map(stable).join(',')}]`
  if (value && typeof value === 'object') {
    return `{${Object.keys(value)
      .sort()
      .map((k) => `${JSON.stringify(k)}:${stable(value[k])}`)
      .join(',')}}`
  }
  return JSON.stringify(value ?? null)
}

function hash(text) {
  return crypto.createHash('sha256').update(text).digest('hex').slice(0, 12)
}

/** 本批次的短标识：写进本批每条 journal，供 flow:log --batch 回查 */
function batchId(keys) {
  return crypto.createHash('sha1').update(`${keys.join(',')}@${Date.now()}`).digest('hex').slice(0, 8)
}

function parseArgs(argv) {
  const out = { _: [] }
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i]
    if (a.startsWith('--')) {
      const key = a.slice(2)
      const next = argv[i + 1]
      if (!next || next.startsWith('--')) out[key] = true
      else {
        out[key] = out[key] === undefined ? next : [].concat(out[key], next)
        i++
      }
    } else out._.push(a)
  }
  return out
}

// ---------------------------------------------------------------- 操作自证（P0-7）

function gitOut(argv) {
  try {
    return execFileSync('git', argv, { cwd: ROOT, encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'] }).trim() || null
  } catch {
    return null
  }
}

/**
 * 每个命令开头打印「在哪操作、谁在操作」。
 * 作用：隔离是软的（Agent 可能在工作目录之外读写），挡不住误操作，但可以让它**当场可见**。
 */
function attest(args) {
  const by = typeof args.by === 'string' ? args.by : 'unknown'
  const branch = gitOut(['rev-parse', '--abbrev-ref', 'HEAD'])
  const rel = path.relative(ROOT, DATA) || '.'
  console.log(`操作自证：数据 ${rel}/；分支 ${branch ?? '（非 git 仓库）'}；actor ${by}`)
  const toplevel = gitOut(['rev-parse', '--show-toplevel'])
  if (toplevel && path.resolve(toplevel) !== ROOT) {
    console.log(`  ⚠ 当前 shell 所在工作树是 ${toplevel}，与本脚本所在仓库不同`)
    console.log(`    脚本按自身位置解析，本命令操作的仍是 ${ROOT} 的数据`)
  }
  console.log('')
  return { by, branch }
}

// ---------------------------------------------------------------- 分区文件定位

function zoneFile(zone, key) {
  const [cat, id] = key.split('/')
  return path.join(DATA, ZONES[zone].dir, cat, `${id}.json`)
}

function libFile(key) {
  return path.join(DATA, key.split('/')[0], 'products.json')
}

function libraryIndex(key) {
  return readLibrary(key).products.findIndex((p) => p.id === key.split('/')[1])
}

function registeredCategories() {
  const groups = readJson(path.join(DATA, 'categories.json'), [])
  return new Set((Array.isArray(groups) ? groups : []).flatMap((g) => (g?.categories ?? []).map((c) => c.id)))
}

/**
 * 解析「品类/id」，允许只写 id（在指定分区里全局找，唯一才通过）。
 * 返回解析结果数组 [{ key, error? }]，与入参顺序一致。
 */
function resolveKeys(rawKeys, zone) {
  const all = listZoneKeys(zone)
  return rawKeys.map((raw) => {
    if (raw.includes('/')) return { key: raw }
    const hits = all.filter((k) => k.split('/')[1] === raw)
    if (hits.length === 1) return { key: hits[0] }
    if (hits.length === 0) return { key: raw, error: `在${ZONES[zone].name}里找不到产品「${raw}」` }
    return { key: raw, error: `「${raw}」在多个品类下都存在，请写成 品类/id` }
  })
}

/** 扫描某个分区，返回其中的产品键清单（如 heater/ht_kick2） */
function listZoneKeys(zone) {
  const base = path.join(DATA, ZONES[zone].dir)
  if (!fs.existsSync(base)) return []
  const keys = []
  for (const cat of fs.readdirSync(base, { withFileTypes: true })) {
    if (!cat.isDirectory()) continue
    for (const f of fs.readdirSync(path.join(base, cat.name))) {
      if (f.endsWith('.json')) keys.push(`${cat.name}/${f.slice(0, -5)}`)
    }
  }
  return keys.sort()
}

/** 按品类分组计数，只返回有内容的品类（空目录不该出现在输出里） */
function countByCategory(keys) {
  const m = new Map()
  for (const k of keys) {
    const cat = k.split('/')[0]
    m.set(cat, (m.get(cat) ?? 0) + 1)
  }
  return [...m.entries()].map(([cat, n]) => `${cat} ${n}`).join(' / ')
}

// ---------------------------------------------------------------- 日志

function journal(entry) {
  ensureDir(path.dirname(JOURNAL))
  fs.appendFileSync(JOURNAL, JSON.stringify({ ts: new Date().toISOString(), ...entry }) + '\n', 'utf8')
}

function readJournal() {
  if (!fs.existsSync(JOURNAL)) return []
  return fs
    .readFileSync(JOURNAL, 'utf8')
    .split('\n')
    .filter((l) => l.trim())
    .map((l) => {
      try {
        return JSON.parse(l)
      } catch {
        return { ts: '?', action: '（无法解析的行）', raw: l }
      }
    })
}

/**
 * 一次性把 journal 读进来建索引：某 key 最后被谁提交 / 谁认领。
 * 归属信息取自 journal（共享事实），不需要往分区文件里塞额外字段。
 */
function journalIndex() {
  const entries = readJournal()
  const lastSubmit = new Map()
  const lastClaim = new Map()
  const lastRecall = new Map()
  const byBatch = new Map()
  for (const e of entries) {
    if (!e.key) continue
    if (e.action === 'submit') lastSubmit.set(e.key, e)
    if (e.action === 'claim') lastClaim.set(e.key, e)
    if (e.action === 'recall') lastRecall.set(e.key, e)
  }
  for (const e of entries) {
    if (e.batch) byBatch.set(e.batch, (byBatch.get(e.batch) ?? 0) + 1)
  }
  return { entries, lastSubmit, lastClaim, lastRecall, byBatch }
}

function fmtTs(ts) {
  if (!ts || ts === '?') return '?'
  return String(ts).replace('T', ' ').slice(0, 16)
}

/** 描述一个 key 的来源：谁提交的、什么时候 */
function describeSubmit(idx, key) {
  const e = idx.lastSubmit.get(key)
  return e ? `${e.actor ?? '?'} @ ${fmtTs(e.ts)}` : '（journal 里查不到提交记录）'
}

function describeClaim(idx, key) {
  const e = idx.lastClaim.get(key)
  return e ? `${e.actor ?? '?'} @ ${fmtTs(e.ts)}` : '（journal 里查不到认领记录）'
}

// ---------------------------------------------------------------- 批量结果汇总（P0-4）

function collector() {
  const results = []
  return {
    results,
    ok(key, msg) {
      results.push({ key, status: 'ok', msg })
      console.log(`✓ ${msg}`)
    },
    skip(key, msg) {
      results.push({ key, status: 'skip', msg })
      console.log(`= ${key}：${msg}`)
    },
    fail(key, msg) {
      results.push({ key, status: 'fail', msg })
      console.error(`✗ ${key}：${msg}`)
    },
    summary(action, batch, extra = []) {
      const ok = results.filter((r) => r.status === 'ok').length
      const skip = results.filter((r) => r.status === 'skip').length
      const bad = results.filter((r) => r.status === 'fail')
      console.log('')
      console.log(`批次 ${batch}（${action}）：共 ${results.length} 项 —— 成功 ${ok} / 已是目标态 ${skip} / 失败 ${bad.length}`)
      if (skip) console.log(`  （「已是目标态」= 本批已处理过，重跑时自动跳过，无需人工比对）`)
      for (const line of extra) console.log(line)
      return bad.length
    },
  }
}

// ---------------------------------------------------------------- 关口校验

/**
 * 流转关口校验：分区数据必须对照当前 schema 合法、审核标注字段齐全。
 * 返回 error 清单（空 = 通过）。
 */
function gateCheck(zone, key, { withAuditFields = true } = {}) {
  const [catId] = key.split('/')
  const product = readJson(zoneFile(zone, key))
  const errors = []
  if (!product) {
    errors.push('JSON 解析失败或文件为空')
    return { product, errors }
  }
  const id = key.split('/')[1]
  if (product.id !== id) {
    errors.push(`产品 id「${product.id}」与文件名「${id}.json」不一致`)
  }
  const schema = readJson(path.join(DATA, catId, 'schema.json'))
  if (!schema) {
    errors.push(`data/${catId}/schema.json 不存在（新品类请先建 schema 再提交）`)
    return { product, errors }
  }
  errors.push(...checkSchema(catId, schema))
  const { errors: productErrors } = checkProduct(catId, schema, product)
  errors.push(...productErrors)
  if (withAuditFields) errors.push(...checkAuditFields(product))
  return { product, errors }
}

// ---------------------------------------------------------------- 命令：A 侧

function cmdSubmit(args, at) {
  const col = collector()
  const resolved = resolveKeys(args._, 'draft')
  for (const r of resolved.filter((x) => x.error)) col.fail(r.key, r.error)
  const keys = resolved.filter((r) => !r.error).map((r) => r.key)
  const batch = batchId(keys)

  for (const key of keys) {
    const src = zoneFile('draft', key)
    const dst = zoneFile('intake', key)
    if (!fs.existsSync(src)) {
      if (fs.existsSync(dst)) {
        col.skip(key, '已在待入库区（本批已提交过）；要改先 flow:withdraw 撤回')
        continue
      }
      col.fail(key, `草稿区没有这个文件（${path.relative(ROOT, src)}）`)
      continue
    }
    const { errors } = gateCheck('draft', key)
    if (errors.length) {
      col.fail(key, `提交校验未通过，请先在草稿区修好：\n    - ${errors.join('\n    - ')}`)
      continue
    }
    if (fs.existsSync(dst)) {
      col.fail(key, '待入库区已有同名文件（可能已提交过；要重提请先 flow:withdraw 撤回）')
      continue
    }
    const inLib = libraryIndex(key) >= 0
    if (!registeredCategories().has(key.split('/')[0])) {
      console.log(`⚠ ${key.split('/')[0]}：尚未登记进 data/categories.json，首次入库（publish）前需要登记，否则站点没有入口`)
    }
    moveFile(src, dst)
    journal({ actor: at.by, branch: at.branch, action: 'submit', key, from: 'draft', to: 'intake', batch, ...(inLib ? { supersedes: true } : {}) })
    col.ok(key, `${key}：草稿区 → 待入库区，等待审核方认领${inLib ? '（订正稿）' : ''}`)
  }

  const bad = col.summary('submit', batch)
  if (bad === 0 && keys.length) {
    console.log(`\n建议立刻提交（注意带 flow 标记，便于提交闸门识别）：`)
    console.log(`  git add data/_intake data/_flow && git commit -m "data: flow:submit ${keys.join(' ')}（来源与核验方式见 change_log）"`)
    console.log(`  （草稿区不入 git，无需 add；见 .gitignore 与 AGENTS.md 3.1）`)
  }
  if (bad) process.exit(1)
}

function cmdWithdraw(args, at) {
  const col = collector()
  const resolved = resolveKeys(args._, 'intake')
  const keys = resolved.filter((r) => !r.error).map((r) => r.key)
  const batch = batchId(keys)
  for (const r of resolved.filter((x) => x.error)) col.fail(r.key, r.error)

  for (const key of keys) {
    const src = zoneFile('intake', key)
    const dst = zoneFile('draft', key)
    if (!fs.existsSync(src)) {
      if (fs.existsSync(dst)) {
        col.skip(key, '已在草稿区（本批已撤回）')
        continue
      }
      col.fail(key, '待入库区没有这个文件（可能已被认领，用 flow:status 确认）')
      continue
    }
    if (fs.existsSync(dst)) {
      col.fail(key, '草稿区已有同名文件，先处理它再撤回')
      continue
    }
    moveFile(src, dst)
    journal({ actor: at.by, branch: at.branch, action: 'withdraw', key, from: 'intake', to: 'draft', batch })
    col.ok(key, `${key}：待入库区 → 草稿区，可继续编辑`)
  }
  if (col.summary('withdraw', batch)) process.exit(1)
}

// ---------------------------------------------------------------- 命令：B 侧

/**
 * 认领。
 * 归属不靠硬拦（`--by` 是自述字段，硬拦既拦不住也会误伤正常交接），而是**可见化**：
 * 打印每个键的提交人、按提交人分组汇总，自己提交自己认领时给出警告（方案 P0-6）。
 */
function cmdClaim(args, at) {
  const col = collector()
  const idx = journalIndex()

  let keys = []
  if (typeof args.from === 'string') {
    keys = listZoneKeys('intake').filter((k) => (idx.lastSubmit.get(k)?.actor ?? null) === args.from)
    if (!keys.length) {
      console.error(`✗ 待入库区没有「${args.from}」提交的产品（用 flow:status 看现状）`)
      process.exit(1)
    }
    console.log(`按提交人认领：${args.from} → ${keys.length} 款\n`)
  } else {
    const resolved = resolveKeys(args._, 'intake')
    for (const r of resolved.filter((x) => x.error)) col.fail(r.key, r.error)
    keys = resolved.filter((r) => !r.error).map((r) => r.key)
  }
  const batch = batchId(keys)

  // 来源可见化：先按提交人分组打印，避免"越量无感代人认领"
  const bySubmitter = new Map()
  for (const k of keys) {
    const who = idx.lastSubmit.get(k)?.actor ?? '（查不到提交记录）'
    bySubmitter.set(who, [...(bySubmitter.get(who) ?? []), k])
  }
  if (bySubmitter.size > 1 || !args.from) {
    console.log('本批待认领数据的提交人分布：')
    for (const [who, ks] of [...bySubmitter.entries()].sort((a, b) => b[1].length - a[1].length)) {
      console.log(`  · ${who}（${ks.length} 款）：${ks.slice(0, 4).join('、')}${ks.length > 4 ? ' …' : ''}`)
    }
    console.log('')
  }

  let selfReview = 0
  for (const key of keys) {
    const src = zoneFile('intake', key)
    const dst = zoneFile('review', key)
    const submitActor = idx.lastSubmit.get(key)?.actor ?? null
    if (!fs.existsSync(src)) {
      if (fs.existsSync(dst)) {
        col.skip(key, '已在修正区（本批已认领）')
        continue
      }
      col.fail(key, '待入库区没有这个文件（可能已被撤回或他人认领，git pull 后用 flow:status 确认）')
      continue
    }
    const { errors } = gateCheck('intake', key)
    if (errors.length && !args.force) {
      col.fail(key, `认领校验未通过（可能提交后 schema 又改过）。可在修正区就地修正后正常入库；坚持现在认领用 --force：\n    - ${errors.join('\n    - ')}`)
      continue
    }
    if (fs.existsSync(dst)) {
      col.fail(key, '修正区已有该产品的文件（正在复审中）；先 publish 或 drop 那份，再认领这份')
      continue
    }
    const inLib = libraryIndex(key) >= 0
    const isSelf = submitActor && submitActor === at.by
    if (isSelf) selfReview++
    moveFile(src, dst)
    journal({
      actor: at.by,
      branch: at.branch,
      action: 'claim',
      key,
      from: 'intake',
      to: 'review',
      batch,
      submitActor,
      ...(isSelf ? { selfReview: true } : {}),
      ...(inLib ? { supersedes: true } : {}),
      ...(args.force ? { forced: true } : {}),
    })
    col.ok(key, `${key}：待入库区 → 修正区（提交人 ${submitActor ?? '?'}）${inLib ? '（订正稿，入库时替换库内同 id 条目）' : ''}`)
  }

  const extra = []
  if (selfReview) {
    extra.push(`⚠ 其中 ${selfReview} 款是你自己提交的（journal 已记 selfReview: true）——请确认这次是**独立复核**，而不是自采自审。`)
  }
  const bad = col.summary('claim', batch, extra)
  if (bad) process.exit(1)
}

function cmdRecall(args, at) {
  const col = collector()
  const reason = typeof args.reason === 'string' ? args.reason : null
  if (!reason) {
    console.error('用法：flow.mjs recall <品类/id>... --reason "为什么召回"')
    process.exit(1)
  }
  const keys = args._
  const batch = batchId(keys)
  const legacy = []

  for (const key of keys) {
    if (!key.includes('/')) {
      col.fail(key, '召回已入库产品请写完整的 品类/id')
      continue
    }
    const lib = readLibrary(key)
    const i = lib.products.findIndex((p) => p.id === key.split('/')[1])
    if (i < 0) {
      if (fs.existsSync(zoneFile('review', key))) {
        col.skip(key, '已在修正区（本批已召回）')
        continue
      }
      col.fail(key, '已入库区没有这个产品')
      continue
    }
    const dst = zoneFile('review', key)
    if (fs.existsSync(dst)) {
      col.fail(key, '修正区已有该产品的文件（正在复审中），不能重复召回')
      continue
    }
    const product = lib.products[i]
    writePretty(dst, product)
    const rest = lib.products.filter((_, j) => j !== i)
    saveLibrary(libFile(key), rest, { expectHash: lib.hash })
    journal({ actor: at.by, branch: at.branch, action: 'recall', key, from: 'library', to: 'review', batch, reason, index: i, fingerprint: hash(stable(product)) })
    col.ok(key, `${key}：已入库区 → 修正区（召回复审：${reason}）`)
    if (fs.existsSync(zoneFile('intake', key))) legacy.push(`  ⚠ ${key}：待入库区还有该产品的订正稿；先处理修正区这份（publish/drop），才能 claim 那份`)
  }

  console.log('\n  ⚠ 召回会让产品从线上消失，重新 publish 前站点不再展示它；大批量审核请按「召回一批→修正→入库一批」滚动推进')
  const bad = col.summary('recall', batch, legacy)
  if (bad) process.exit(1)
}

/**
 * 入库。
 * 回滚范围只限**本批写坏的东西**（方案 P0-5）：品类内历史遗留的问题照样报出来，
 * 但明确指出「不是你造成的」，用 --skip-legacy 可消除该提示。
 */
function cmdPublish(args, at) {
  const col = collector()
  const idx = journalIndex()
  const resolved = resolveKeys(args._, 'review')
  for (const r of resolved.filter((x) => x.error)) col.fail(r.key, r.error)
  const keys = resolved.filter((r) => !r.error).map((r) => r.key)
  const batch = batchId(keys)
  const touched = new Set()
  const legacyReports = []

  for (const key of keys) {
    const src = zoneFile('review', key)
    const [catId, id] = key.split('/')
    if (!fs.existsSync(src)) {
      if (libraryIndex(key) >= 0) {
        col.skip(key, '修正区无文件、库内已有同 id —— 视为本批已入库（若你没预期这样，用 flow:status 复核）')
        continue
      }
      col.fail(key, '修正区没有这个文件（flow:status 看看它现在在哪）')
      continue
    }
    const { errors } = gateCheck('review', key)
    if (errors.length) {
      col.fail(key, `入库校验未通过，修正后再 publish：\n    - ${errors.join('\n    - ')}`)
      continue
    }
    if (!registeredCategories().has(catId)) {
      col.fail(key, '尚未登记进 data/categories.json，站点没有入口；请先登记再 publish')
      continue
    }
    const product = readJson(src)
    const lib = readLibrary(key)
    const i = lib.products.findIndex((p) => p.id === id)
    if (i >= 0 && stable(lib.products[i]) === stable(product)) {
      col.skip(key, '库内内容与修正区已完全一致，无需入库')
      continue
    }
    const prev = lib.exists ? lib.products.slice() : null
    // 召回后重新入库：尽量放回原位，而不是追加到数组末尾。
    // 为什么在意：库文件是一行一款，两个分支各自 recall→publish 同一品类的
    // 不同产品时，若都往尾部追加就会在数组末尾撞成同一个冲突；放回原位则互不干扰。
    const recalled = idx.lastRecall.get(key)
    const restoreAt = i < 0 && recalled && Number.isInteger(recalled.index) ? Math.min(recalled.index, lib.products.length) : null
    if (i >= 0) lib.products[i] = product
    else if (restoreAt !== null) lib.products.splice(restoreAt, 0, product)
    else lib.products.push(product)

    let writtenHash
    try {
      const written = saveLibrary(libFile(key), lib.products, { expectHash: lib.hash })
      writtenHash = hashText(written)
    } catch (e) {
      col.fail(key, e.code === 'ELIBRARYCONFLICT' ? e.message : `写库失败：${e.message}`)
      continue
    }
    fs.rmSync(src)
    pruneEmptyDirs(path.dirname(src))
    touched.add(catId)

    // 入库后复检本批产品所属品类：只对本批写坏的东西回滚
    const schema = readJson(path.join(DATA, catId, 'schema.json'))
    const now = readLibrary(key).products
    const checked = checkCategory(catId, schema, now)
    const mine = []
    const others = []
    // 错误串里产品标签形如 `catId/id：…`；用 label 前缀精确匹配，
    // 避免 "rv_6" 命中 "rv_6pro" 这类子串误判
    const myLabels = keys.filter((k) => k.startsWith(`${catId}/`)).map((k) => `${catId}/${k.split('/')[1]}`)
    for (const err of checked.errors) {
      const isMine =
        myLabels.some((lbl) => err.startsWith(`${lbl}：`)) ||
        myLabels.some((lbl) => err.includes(`产品 id 重复 —— ${lbl.split('/')[1]}`))
      if (isMine) mine.push(err)
      else others.push(err)
    }
    if (mine.length) {
      if (prev === null) fs.rmSync(libFile(key))
      else saveLibrary(libFile(key), prev, { expectHash: writtenHash })
      writePretty(src, product)
      col.fail(key, `入库后本批数据未通过 ${catId} 品类校验，已自动回滚到修正区：\n    - ${mine.join('\n    - ')}`)
      continue
    }
    if (others.length) {
      legacyReports.push({ catId, id, errors: others })
    }
    journal({ actor: at.by, branch: at.branch, action: 'publish', key, from: 'review', to: 'library', batch, ...(i >= 0 ? { supersedes: true } : {}) })
    col.ok(key, `${key}：修正区 → 已入库区${i >= 0 ? '（已替换库内同 id 条目）' : '（新增）'}`)
  }

  if (legacyReports.length) {
    console.log('')
    console.log('⚠ 品类内存在**历史遗留**问题（不是你本批造成的，本次入库已成功且未回滚）：')
    for (const r of legacyReports.slice(0, 5)) {
      console.log(`  · ${r.catId}/${r.id}：${r.errors.length} 条`)
      for (const e of r.errors.slice(0, 3)) console.log(`      - ${e}`)
    }
    if (legacyReports.length > 5) console.log(`  …另有 ${legacyReports.length - 5} 款同类问题`)
    console.log('  处理建议：另立 issue 修历史数据；要忽略该提示可加 --skip-legacy')
  }

  const bad = col.summary('publish', batch)
  if (touched.size) console.log(`\n推送前记得 npm run check；入库数据对访客生效以 push 后的部署为准。`)
  if (bad) process.exit(1)
  if (legacyReports.length && !args['skip-legacy']) {
    console.log('\n（退出码非零：仅因品类内存在历史遗留问题；本次入库本身已成功。加 --skip-legacy 可消除）')
    process.exit(1)
  }
}

function cmdReturn(args, at) {
  const col = collector()
  const reason = typeof args.reason === 'string' ? args.reason : null
  if (!reason) {
    console.error('用法：flow.mjs return <品类/id> --reason "为什么退回"')
    process.exit(1)
  }
  const resolved = resolveKeys(args._, 'intake')
  const keys = resolved.filter((r) => !r.error).map((r) => r.key)
  const batch = batchId(keys)
  for (const r of resolved.filter((x) => x.error)) col.fail(r.key, r.error)

  for (const key of keys) {
    const src = zoneFile('intake', key)
    const dst = zoneFile('draft', key)
    if (!fs.existsSync(src)) {
      if (fs.existsSync(dst)) {
        col.skip(key, '已在草稿区（本批已退回）')
        continue
      }
      col.fail(key, '待入库区没有这个文件')
      continue
    }
    if (fs.existsSync(dst)) {
      col.fail(key, '草稿区已有同名文件，请采集方先处理再退回')
      continue
    }
    moveFile(src, dst)
    journal({ actor: at.by, branch: at.branch, action: 'return', key, from: 'intake', to: 'draft', batch, reason })
    col.ok(key, `${key}：待入库区 → 草稿区（退回：${reason}）`)
  }
  console.log('\n  采集方可通过 flow:status / flow:log 看到退回原因')
  if (col.summary('return', batch)) process.exit(1)
}

function cmdDrop(args, at) {
  const col = collector()
  const reason = typeof args.reason === 'string' ? args.reason : null
  if (!reason) {
    console.error('用法：flow.mjs drop <品类/id> --reason "为什么剔除"')
    process.exit(1)
  }
  const resolved = resolveKeys(args._, 'review')
  const keys = resolved.filter((r) => !r.error).map((r) => r.key)
  const batch = batchId(keys)
  for (const r of resolved.filter((x) => x.error)) col.fail(r.key, r.error)

  for (const key of keys) {
    const src = zoneFile('review', key)
    if (!fs.existsSync(src)) {
      col.skip(key, '修正区没有这个文件（可能已剔除，或还没被召回）')
      continue
    }
    const product = readJson(src)
    fs.rmSync(src)
    pruneEmptyDirs(path.dirname(src))
    journal({ actor: at.by, branch: at.branch, action: 'drop', key, from: 'review', to: null, batch, reason, fingerprint: product ? hash(stable(product)) : null })
    col.ok(key, `${key}：已从修正区剔除，不再入库（${reason}）`)
  }
  console.log('  内容指纹已记入流转日志，git 历史可找回；剔除已入库产品属于收录范围变更，应由用户确认')
  if (col.summary('drop', batch)) process.exit(1)
}

// ---------------------------------------------------------------- 查询

/** 列出库里 facet 值为「未归类」的产品（供立 issue 认领，方案 P0-6⑤） */
function cmdUnclassified() {
  const cats = [...registeredCategories()]
  let total = 0
  let mi = 0
  console.log('未归类产品（schema.facets[0] 取值为「未归类」）：')
  console.log('口径：主清单只列**竞品**（与 classify-facets.py 的处理范围一致），小米自有的另计。')
  for (const catId of cats) {
    const schema = readJson(path.join(DATA, catId, 'schema.json'))
    const facetKey = schema?.facets?.[0]?.key
    if (!facetKey) continue
    const products = readJson(path.join(DATA, catId, 'products.json'), []) ?? []
    const unclassified = products.filter((p) => p[facetKey] === '未归类')
    mi += unclassified.filter((p) => p.brand === '小米').length
    const hit = unclassified.filter((p) => p.brand !== '小米')
    if (!hit.length) continue
    total += hit.length
    console.log(`  ${catId}（${facetKey}）：${hit.length} 款`)
    for (const p of hit) console.log(`      · ${catId}/${p.id}  ${p.name ?? ''}（${p.brand ?? '?'}）`)
  }
  console.log(`\n合计 ${total} 款竞品未归类${mi ? `（另有 ${mi} 款小米自有产品同为「未归类」）` : ''}。`)
  console.log('建议按品类分批立 issue（标签：数据缺陷 + 品类名）供采集方认领。')
}

function cmdStatus(args) {
  const catFilter = typeof args.category === 'string' ? args.category : null
  const zoneFilter = typeof args.zone === 'string' ? args.zone : null
  const byFilter = typeof args.by === 'string' ? args.by : null
  const registered = registeredCategories()
  const idx = journalIndex()

  if (args.unclassified) {
    cmdUnclassified()
    return
  }

  const lines = []
  for (const zone of FLOW_ORDER) {
    if (zoneFilter && zone !== zoneFilter) continue
    if (zone === 'library') {
      const cats = catFilter ? [catFilter] : [...registered]
      let count = 0
      for (const c of cats) count += (readJson(path.join(DATA, c, 'products.json'), []) ?? []).length
      lines.push(`${ZONES[zone].name.padEnd(5)} products.json   ${String(count).padStart(5)} 款（${cats.length} 个品类）`)
      continue
    }
    let keys = listZoneKeys(zone)
    if (catFilter) keys = keys.filter((k) => k.startsWith(`${catFilter}/`))
    if (byFilter) {
      keys = keys.filter((k) =>
        zone === 'intake' ? (idx.lastSubmit.get(k)?.actor ?? null) === byFilter : (idx.lastClaim.get(k)?.actor ?? null) === byFilter,
      )
    }
    const scope = zone === 'intake' ? '提交人' : zone === 'review' ? '认领人' : '归属'
    lines.push(
      `${ZONES[zone].name.padEnd(5)} ${`_${zone}`.padEnd(9)} ${String(keys.length).padStart(5)} 款` +
        (keys.length ? `（${countByCategory(keys)}）` : '') +
        (byFilter ? `  [按${scope}过滤：${byFilter}]` : ''),
    )
    for (const k of keys) {
      const extra =
        zone === 'intake'
          ? `（提交人 ${idx.lastSubmit.get(k)?.actor ?? '?'} @ ${fmtTs(idx.lastSubmit.get(k)?.ts)}）`
          : zone === 'review'
            ? `（认领人 ${idx.lastClaim.get(k)?.actor ?? '?'}${libraryIndex(k) >= 0 ? '；订正稿：库内有同 id' : ''}）`
            : ''
      lines.push(`    · ${k}${extra}`)
    }
  }
  console.log('数据分区现状（草稿区 → 待入库区 → 修正区 → 已入库区）：')
  console.log(lines.join('\n'))
  console.log('')
  if (byFilter) console.log(`（已按 ${byFilter} 过滤；去掉 --by 看全部）\n`)

  const entries = idx.entries
  const recent = entries.slice(-((typeof args.n === 'string' && Number(args.n)) || 10)).reverse()
  console.log(`最近流转（data/_flow/journal.jsonl，共 ${entries.length} 条）：`)
  if (!recent.length) console.log('  （还没有流转记录）')
  for (const e of recent) {
    const tail = [e.reason, e.batch ? `批次 ${e.batch}` : null, e.submitActor ? `提交人 ${e.submitActor}` : null, e.selfReview ? 'selfReview' : null, e.supersedes ? '订正稿' : null, e.forced ? 'force' : null]
      .filter(Boolean)
      .join('；')
    console.log(`  · ${fmtTs(e.ts)}  ${String(e.actor ?? '?').padEnd(10)} ${String(e.action ?? '?').padEnd(9)} ${e.key ?? ''}${tail ? `（${tail}）` : ''}`)
  }
}

function cmdLog(args) {
  const n = (typeof args.n === 'string' && Number(args.n)) || 30
  let entries = readJournal()
  if (typeof args.batch === 'string') {
    entries = entries.filter((e) => e.batch === args.batch)
    console.log(`批次 ${args.batch}：共 ${entries.length} 条\n`)
  } else {
    entries = entries.slice(-n)
  }
  if (!entries.length) {
    console.log('（无匹配记录）')
    return
  }
  for (const e of entries.slice().reverse()) {
    const tail = [e.reason, e.batch ? `批次 ${e.batch}` : null, e.submitActor ? `提交人 ${e.submitActor}` : null, e.selfReview ? 'selfReview' : null, e.supersedes ? '订正稿' : null]
      .filter(Boolean)
      .join('；')
    console.log(`${fmtTs(e.ts)}  ${String(e.actor ?? '?').padEnd(10)} ${String(e.action ?? '?').padEnd(9)} ${e.key ?? ''}${tail ? `（${tail}）` : ''}`)
  }
}

// ---------------------------------------------------------------- 入口

const args = parseArgs(process.argv.slice(2))
const cmd = args._.shift()
args._ = args._.filter(Boolean)

/** 每个命令都先打印操作自证（在哪操作、谁在操作），再执行 */
function run(fn) {
  fn(args, attest(args))
}

try {
  switch (cmd) {
    case 'submit':
      run(cmdSubmit)
      break
    case 'withdraw':
      run(cmdWithdraw)
      break
    case 'claim':
      run(cmdClaim)
      break
    case 'recall':
      run(cmdRecall)
      break
    case 'publish':
      run(cmdPublish)
      break
    case 'return':
      run(cmdReturn)
      break
    case 'drop':
      run(cmdDrop)
      break
    case 'status':
      attest(args)
      cmdStatus(args)
      break
    case 'log':
      attest(args)
      cmdLog(args)
      break
    default:
      console.log(
        [
          '数据分区流转 —— 多 Agent 并行协作用（规则见 AGENTS.md）',
          '',
          '  草稿区 _draft（A 的工作台） → 待入库区 _intake（交接队列） → 修正区 _review（B 的工作台） → 已入库区 products.json',
          '',
          '  submit   <品类/id>...                    A：草稿区 → 待入库区',
          '  withdraw <品类/id>...                    A：待入库区 → 草稿区（撤回继续改）',
          '  claim    <品类/id>... [--force]          B：待入库区 → 修正区',
          '           --from <提交人>                 按提交人批量认领',
          '  recall   <品类/id>... --reason           B：已入库区 → 修正区（召回复审）',
          '  publish  <品类/id>... [--skip-legacy]    B：修正区 → 已入库区',
          '  return   <品类/id>... --reason           B：待入库区 → 草稿区（退回）',
          '  drop     <品类/id>... --reason           B：修正区剔除（需用户确认）',
          '  status   [--category 品类] [--zone draft|intake|review] [--by 提交人/认领人] [--unclassified] [--n 条数]',
          '  log      [-n 条数] [--batch <批次id>]',
          '',
          '  所有命令都支持 --by <名字> 标注操作者。批量命令会生成 batch id；中途失败原样重跑即可续上。',
          '  测试可用 FLOW_DATA_DIR=<目录> 把流转指向临时数据副本。',
        ].join('\n'),
      )
  }
} catch (e) {
  console.error(`失败：${e.message}`)
  process.exit(1)
}
