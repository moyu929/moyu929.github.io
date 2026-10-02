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
 *   flow.mjs submit   <品类/id>...          A：草稿区 → 待入库区（收录完成，提交待审）
 *   flow.mjs withdraw <品类/id>             A：待入库区 → 草稿区（提交后想继续改，撤回）
 *   flow.mjs claim    <品类/id>...          B：待入库区 → 修正区（认领，开始核验）
 *   flow.mjs recall   <品类/id>... --reason B：已入库区 → 修正区（召回复审，产品暂时下架）
 *   flow.mjs publish  <品类/id>...          B：修正区 → 已入库区（修正完成，入库上线）
 *   flow.mjs return   <品类/id> --reason    B：待入库区 → 草稿区（不符收录标准，退回）
 *   flow.mjs drop     <品类/id> --reason    B：修正区删除（召回后判定不该收录；需用户确认）
 *   flow.mjs status   [--category 品类] [--zone draft|intake|review]
 *   flow.mjs log      [-n 条数]
 *
 * 约定：分区文件入库（它们是各 Agent 的共享状态）；流转命令不做任何 git 操作，
 * 跑完当场提交。规则见仓库根目录 AGENTS.md。
 */
import crypto from 'node:crypto'
import fs from 'node:fs'
import path from 'node:path'
import process from 'node:process'
import { checkAuditFields, checkProduct, checkSchema } from './lib/product-check.mjs'

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
}

/** 已入库区是压缩单行格式（与历史文件一致），重写时保持同款避免无意义 diff */
function writeLibrary(file, products) {
  ensureDir(path.dirname(file))
  fs.writeFileSync(file, JSON.stringify(products) + '\n', 'utf8')
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

// ---------------------------------------------------------------- 分区文件定位

function zoneFile(zone, key) {
  const [cat, id] = key.split('/')
  return path.join(DATA, ZONES[zone].dir, cat, `${id}.json`)
}

function libFile(key) {
  return path.join(DATA, key.split('/')[0], 'products.json')
}

function loadLibrary(key) {
  return readJson(libFile(key), []) ?? []
}

function libraryIndex(key) {
  return loadLibrary(key).findIndex((p) => p.id === key.split('/')[1])
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

function fail(keys, results, action) {
  const ok = keys.filter((_, i) => !results[i])
  for (const line of results) {
    if (line) console.error(`✗ ${line}`)
  }
  if (ok.length) console.error(`（其余 ${ok.length} 项已${action}，记得一并提交）`)
  process.exit(1)
}

// ---------------------------------------------------------------- 命令：A 侧

function cmdSubmit(args) {
  const by = args.by ?? 'unknown'
  const resolved = resolveKeys(args._, 'draft')
  const problems = resolved.filter((r) => r.error)
  const keys = resolved.filter((r) => !r.error).map((r) => r.key)
  for (const p of problems) console.error(`✗ ${p.error}`)

  let moved = 0
  for (const key of keys) {
    const src = zoneFile('draft', key)
    const dst = zoneFile('intake', key)
    if (!fs.existsSync(src)) {
      console.error(`✗ ${key}：草稿区没有这个文件（${path.relative(ROOT, src)}）`)
      continue
    }
    const { errors } = gateCheck('draft', key)
    if (errors.length) {
      console.error(`✗ ${key}：提交校验未通过，请先在草稿区修好：`)
      for (const e of errors) console.error(`    - ${e}`)
      continue
    }
    if (fs.existsSync(dst)) {
      console.error(`✗ ${key}：待入库区已有同名文件（可能已提交过；要重提请先 flow:withdraw 撤回）`)
      continue
    }
    const inLib = libraryIndex(key) >= 0
    if (inLib) console.error(`⚠ ${key}：库内已有同 id 产品，这份提交将作为订正稿处理（认领后入库时整条替换）`)
    if (!registeredCategories().has(key.split('/')[0])) {
      console.error(`⚠ ${key.split('/')[0]}：尚未登记进 data/categories.json，首次入库（publish）前需要登记，否则站点没有入口`)
    }
    moveFile(src, dst)
    journal({ actor: by, action: 'submit', key, from: 'draft', to: 'intake', ...(inLib ? { supersedes: true } : {}) })
    console.log(`✓ ${key}：草稿区 → 待入库区，等待审核方认领`)
    moved++
  }
  if (!moved && !problems.length) process.exit(1)
  if (moved) {
    console.log(`\n建议立刻提交：`)
    console.log(`  git add data/_draft data/_intake data/_flow && git commit -m "data: 提交待审 ${keys.join(' ')}（来源与核验方式见 change_log）"`)
  }
  if (problems.length || moved < keys.length) process.exit(1)
}

function cmdWithdraw(args) {
  const by = args.by ?? 'unknown'
  const resolved = resolveKeys(args._, 'intake')
  let failed = 0
  for (const { key, error } of resolved) {
    if (error) {
      console.error(`✗ ${error}`)
      failed++
      continue
    }
    const src = zoneFile('intake', key)
    const dst = zoneFile('draft', key)
    if (!fs.existsSync(src)) {
      console.error(`✗ ${key}：待入库区没有这个文件（可能已被认领，用 flow:status 确认）`)
      failed++
      continue
    }
    if (fs.existsSync(dst)) {
      console.error(`✗ ${key}：草稿区已有同名文件，先处理它再撤回`)
      failed++
      continue
    }
    moveFile(src, dst)
    journal({ actor: by, action: 'withdraw', key, from: 'intake', to: 'draft' })
    console.log(`✓ ${key}：待入库区 → 草稿区，可继续编辑`)
  }
  if (failed) process.exit(1)
}

// ---------------------------------------------------------------- 命令：B 侧

function cmdClaim(args) {
  const by = args.by ?? 'unknown'
  const resolved = resolveKeys(args._, 'intake')
  const problems = resolved.filter((r) => r.error)
  const keys = resolved.filter((r) => !r.error).map((r) => r.key)
  for (const p of problems) console.error(`✗ ${p.error}`)

  let moved = 0
  for (const key of keys) {
    const src = zoneFile('intake', key)
    const dst = zoneFile('review', key)
    if (!fs.existsSync(src)) {
      console.error(`✗ ${key}：待入库区没有这个文件（可能已被撤回或他人认领，git pull 后用 flow:status 确认）`)
      continue
    }
    const { errors } = gateCheck('intake', key)
    if (errors.length && !args.force) {
      console.error(`✗ ${key}：认领校验未通过（可能提交后 schema 又改过）。可在修正区就地修正后正常入库；坚持现在认领用 --force：`)
      for (const e of errors) console.error(`    - ${e}`)
      continue
    }
    if (fs.existsSync(dst)) {
      console.error(`✗ ${key}：修正区已有该产品的文件（正在复审中）；先 publish 或 drop 那份，再认领这份`)
      continue
    }
    const inLib = libraryIndex(key) >= 0
    moveFile(src, dst)
    journal({ actor: by, action: 'claim', key, from: 'intake', to: 'review', ...(inLib ? { supersedes: true } : {}), ...(args.force ? { forced: true } : {}) })
    console.log(`✓ ${key}：待入库区 → 修正区${inLib ? '（订正稿，入库时替换库内同 id 条目）' : ''}`)
    moved++
  }
  if (problems.length || moved < keys.length) process.exit(1)
}

function cmdRecall(args) {
  const by = args.by ?? 'unknown'
  const reason = typeof args.reason === 'string' ? args.reason : null
  if (!reason) {
    console.error('用法：flow.mjs recall <品类/id>... --reason "为什么召回"')
    process.exit(1)
  }
  let failed = 0
  for (const key of args._) {
    if (!key.includes('/')) {
      console.error(`✗ ${key}：召回已入库产品请写完整的 品类/id`)
      failed++
      continue
    }
    const lib = loadLibrary(key)
    const idx = lib.findIndex((p) => p.id === key.split('/')[1])
    if (idx < 0) {
      console.error(`✗ ${key}：已入库区没有这个产品`)
      failed++
      continue
    }
    const dst = zoneFile('review', key)
    if (fs.existsSync(dst)) {
      console.error(`✗ ${key}：修正区已有该产品的文件（正在复审中），不能重复召回`)
      failed++
      continue
    }
    const product = lib[idx]
    const pendingIntake = fs.existsSync(zoneFile('intake', key))
    writePretty(dst, product)
    lib.splice(idx, 1)
    writeLibrary(libFile(key), lib)
    journal({
      actor: by,
      action: 'recall',
      key,
      from: 'library',
      to: 'review',
      reason,
      fingerprint: hash(stable(product)),
    })
    console.log(`✓ ${key}：已入库区 → 修正区（召回复审：${reason}）`)
    console.log(`  ⚠ 该产品已从线上移除，重新 publish 前站点不再展示它；大批量审核请按「召回一批→修正→入库一批」滚动推进`)
    if (pendingIntake) console.log(`  ⚠ 待入库区还有该产品的订正稿；先处理修正区这份（publish/drop），才能 claim 那份`)
  }
  if (failed) process.exit(1)
}

function cmdPublish(args) {
  const by = args.by ?? 'unknown'
  const resolved = resolveKeys(args._, 'review')
  const problems = resolved.filter((r) => r.error)
  const keys = resolved.filter((r) => !r.error).map((r) => r.key)
  for (const p of problems) console.error(`✗ ${p.error}`)

  let moved = 0
  for (const key of keys) {
    const src = zoneFile('review', key)
    const [catId, id] = key.split('/')
    if (!fs.existsSync(src)) {
      console.error(`✗ ${key}：修正区没有这个文件（flow:status 看看它现在在哪）`)
      continue
    }
    const { errors } = gateCheck('review', key)
    if (errors.length) {
      console.error(`✗ ${key}：入库校验未通过，修正后再 publish：`)
      for (const e of errors) console.error(`    - ${e}`)
      continue
    }
    if (!registeredCategories().has(catId)) {
      console.error(`✗ ${catId}：尚未登记进 data/categories.json，站点没有入口；请先登记再 publish`)
      continue
    }
    const product = readJson(src)
    const libFile_ = libFile(key)
    const lib = loadLibrary(key)
    const idx = lib.findIndex((p) => p.id === id)
    const supersedes = idx >= 0
    const backup = fs.existsSync(libFile_) ? fs.readFileSync(libFile_, 'utf8') : null
    if (supersedes) lib[idx] = product
    else lib.push(product)
    writeLibrary(libFile_, lib)
    fs.rmSync(src)

    // 入库后对整个品类跑一次同口径校验，不过关就整体回滚（库文件还原 + 产品退回修正区）
    const libErrors = validateCategory(catId)
    if (libErrors.length) {
      if (backup !== null) fs.writeFileSync(libFile_, backup, 'utf8')
      else fs.rmSync(libFile_)
      writePretty(src, product)
      console.error(`✗ ${key}：入库后 ${catId} 品类校验未通过，已自动回滚到修正区：`)
      for (const e of libErrors.slice(0, 10)) console.error(`    - ${e}`)
      continue
    }
    journal({ actor: by, action: 'publish', key, from: 'review', to: 'library', ...(supersedes ? { supersedes: true } : {}) })
    console.log(`✓ ${key}：修正区 → 已入库区${supersedes ? '（已替换库内同 id 条目）' : '（新增）'}`)
    moved++
  }
  if (moved) console.log(`\n推送前记得 npm run check；入库数据对访客生效以 push 后的部署为准。`)
  if (problems.length || moved < keys.length) process.exit(1)
}

function cmdReturn(args) {
  const by = args.by ?? 'unknown'
  const reason = typeof args.reason === 'string' ? args.reason : null
  if (!reason) {
    console.error('用法：flow.mjs return <品类/id> --reason "为什么退回"')
    process.exit(1)
  }
  const resolved = resolveKeys(args._, 'intake')
  let failed = 0
  for (const { key, error } of resolved) {
    if (error) {
      console.error(`✗ ${error}`)
      failed++
      continue
    }
    const src = zoneFile('intake', key)
    const dst = zoneFile('draft', key)
    if (!fs.existsSync(src)) {
      console.error(`✗ ${key}：待入库区没有这个文件`)
      failed++
      continue
    }
    if (fs.existsSync(dst)) {
      console.error(`✗ ${key}：草稿区已有同名文件，请采集方先处理再退回`)
      failed++
      continue
    }
    moveFile(src, dst)
    journal({ actor: by, action: 'return', key, from: 'intake', to: 'draft', reason })
    console.log(`✓ ${key}：待入库区 → 草稿区（退回：${reason}）`)
    console.log(`  采集方可通过 flow:status / flow:log 看到退回原因`)
  }
  if (failed) process.exit(1)
}

function cmdDrop(args) {
  const by = args.by ?? 'unknown'
  const reason = typeof args.reason === 'string' ? args.reason : null
  if (!reason) {
    console.error('用法：flow.mjs drop <品类/id> --reason "为什么剔除"')
    process.exit(1)
  }
  const resolved = resolveKeys(args._, 'review')
  let failed = 0
  for (const { key, error } of resolved) {
    if (error) {
      console.error(`✗ ${error}`)
      failed++
      continue
    }
    const src = zoneFile('review', key)
    if (!fs.existsSync(src)) {
      console.error(`✗ ${key}：修正区没有这个文件`)
      failed++
      continue
    }
    const product = readJson(src)
    fs.rmSync(src)
    journal({ actor: by, action: 'drop', key, from: 'review', to: null, reason, fingerprint: product ? hash(stable(product)) : null })
    console.log(`✓ ${key}：已从修正区剔除，不再入库（${reason}）`)
    console.log(`  内容指纹已记入流转日志，git 历史可找回；剔除已入库产品属于收录范围变更，应由用户确认`)
  }
  if (failed) process.exit(1)
}

// ---------------------------------------------------------------- 查询

function validateCategory(catId) {
  const schema = readJson(path.join(DATA, catId, 'schema.json'))
  if (!schema) return [`data/${catId}/schema.json 不存在`]
  const errors = checkSchema(catId, schema)
  const products = readJson(path.join(DATA, catId, 'products.json'), []) ?? []
  const seen = new Set()
  for (const p of products) {
    if (p?.id) {
      if (seen.has(p.id)) errors.push(`${catId}：产品 id 重复 —— ${p.id}`)
      seen.add(p.id)
    }
    const { errors: e } = checkProduct(catId, schema, p)
    errors.push(...e)
  }
  return errors
}

function cmdStatus(args) {
  const catFilter = typeof args.category === 'string' ? args.category : null
  const zoneFilter = typeof args.zone === 'string' ? args.zone : null
  const registered = registeredCategories()

  const lines = []
  for (const zone of FLOW_ORDER) {
    if (zoneFilter && zone !== zoneFilter) continue
    let keys = listZoneKeys(zone)
    if (catFilter) keys = keys.filter((k) => k.startsWith(`${catFilter}/`))
    if (zone === 'library') {
      // 已入库区按 products.json 统计
      const cats = catFilter ? [catFilter] : [...registered]
      let count = 0
      for (const c of cats) count += (readJson(path.join(DATA, c, 'products.json'), []) ?? []).length
      lines.push(`${ZONES[zone].name.padEnd(5)} products.json   ${String(count).padStart(5)} 款（${cats.length} 个品类）`)
      continue
    }
    const marks = keys.map((k) => {
      const extra =
        zone === 'review' && libraryIndex(k) >= 0
          ? '（订正稿：库内有同 id，入库时整条替换）'
          : zone === 'intake' && libraryIndex(k) >= 0
            ? '（订正稿）'
            : ''
      return `    · ${k}${extra}`
    })
    lines.push(`${ZONES[zone].name.padEnd(5)} _${zone.padEnd(8)} ${String(keys.length).padStart(5)} 款`)
    lines.push(...(keys.length ? marks : ['    （空）']))
  }
  console.log('数据分区现状（草稿区 → 待入库区 → 修正区 → 已入库区）：')
  console.log(lines.join('\n'))
  console.log('')

  const entries = readJournal()
  const recent = entries.slice(-((typeof args.n === 'string' && Number(args.n)) || 10)).reverse()
  console.log(`最近流转（data/_flow/journal.jsonl，共 ${entries.length} 条）：`)
  if (!recent.length) console.log('  （还没有流转记录）')
  for (const e of recent) {
    const tail = [e.reason, e.supersedes ? '订正稿' : null, e.forced ? 'force' : null].filter(Boolean).join('；')
    console.log(`  · ${e.ts}  ${String(e.actor ?? '?').padEnd(10)} ${String(e.action ?? '?').padEnd(9)} ${e.key ?? ''}${tail ? `（${tail}）` : ''}`)
  }
}

function cmdLog(args) {
  const n = (typeof args.n === 'string' && Number(args.n)) || 30
  const entries = readJournal().slice(-n).reverse()
  if (!entries.length) {
    console.log('流转日志为空。')
    return
  }
  for (const e of entries) {
    const tail = [e.reason, e.supersedes ? '订正稿' : null, e.forced ? 'force' : null].filter(Boolean).join('；')
    console.log(`${e.ts}  ${String(e.actor ?? '?').padEnd(10)} ${String(e.action ?? '?').padEnd(9)} ${e.key ?? ''}${tail ? `（${tail}）` : ''}`)
  }
}

// ---------------------------------------------------------------- 入口

const args = parseArgs(process.argv.slice(2))
const cmd = args._.shift()
args._ = args._.filter(Boolean)
try {
  switch (cmd) {
    case 'submit':
      cmdSubmit(args)
      break
    case 'withdraw':
      cmdWithdraw(args)
      break
    case 'claim':
      cmdClaim(args)
      break
    case 'recall':
      cmdRecall(args)
      break
    case 'publish':
      cmdPublish(args)
      break
    case 'return':
      cmdReturn(args)
      break
    case 'drop':
      cmdDrop(args)
      break
    case 'status':
      cmdStatus(args)
      break
    case 'log':
      cmdLog(args)
      break
    default:
      console.log(
        [
          '数据分区流转 —— 多 Agent 并行协作用（规则见 AGENTS.md）',
          '',
          '  草稿区 _draft（A 的工作台） → 待入库区 _intake（交接队列） → 修正区 _review（B 的工作台） → 已入库区 products.json',
          '',
          '  submit   <品类/id>...            A：草稿区 → 待入库区',
          '  withdraw <品类/id>...            A：待入库区 → 草稿区（撤回继续改）',
          '  claim    <品类/id>... [--force]  B：待入库区 → 修正区',
          '  recall   <品类/id>... --reason   B：已入库区 → 修正区（召回复审）',
          '  publish  <品类/id>...            B：修正区 → 已入库区',
          '  return   <品类/id>... --reason   B：待入库区 → 草稿区（退回）',
          '  drop     <品类/id>... --reason   B：修正区剔除（需用户确认）',
          '  status   [--category 品类] [--zone draft|intake|review] [--n 条数]',
          '  log      [-n 条数]',
          '',
          '  测试可用 FLOW_DATA_DIR=<目录> 把流转指向临时数据副本。',
        ].join('\n'),
      )
  }
} catch (e) {
  console.error(`失败：${e.message}`)
  process.exit(1)
}
