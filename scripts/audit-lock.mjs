#!/usr/bin/env node
/**
 * 审核快照锁（多 Agent 并行协作的基础设施）
 * ------------------------------------------------------------------
 * 解决的问题：两个 Agent 并行干活时，A 一边在加新品类/新型号，B 一边在按用户指令审核
 * 某一批产品。如果 A 在审核期间改动了被审的产品，B 的审核结论就基于过期数据。
 *
 * 做法：B 在开始审核前对「审核范围」拍快照，记录每款产品的内容指纹；
 * 冻结期内任何人（主要是 A）都不该改这些产品；事后用 check 检测是否有人越界。
 *
 * 用法：
 *   node scripts/audit-lock.mjs snapshot --label "空气净化器验收" --by agent-b --category air-purifier
 *   node scripts/audit-lock.mjs snapshot --label "全站抽查" --by agent-b            # 不给范围=全站冻结
 *   node scripts/audit-lock.mjs check [--strict] [--json]                          # 检测越界改动
 *   node scripts/audit-lock.mjs status <品类[/产品id] ...>                          # 查某范围是否被冻结
 *   node scripts/audit-lock.mjs diff <快照id>                                       # 看具体改了哪些字段
 *   node scripts/audit-lock.mjs release <快照id> [--note "审核完成"]                 # 解除冻结
 *   node scripts/audit-lock.mjs list                                               # 列出所有快照
 *
 * 约定：快照文件入库（data/_locks/*.json），因为它是两个 Agent 之间的共享状态。
 * 字段级指纹默认在范围 ≤150 款时记录，超出只记整条指纹（文件不至于过大）。
 */
import crypto from 'node:crypto'
import fs from 'node:fs'
import path from 'node:path'
import process from 'node:process'

const ROOT = path.resolve(import.meta.dirname, '..')
const DATA = path.join(ROOT, 'data')
const LOCKS = path.join(DATA, '_locks')
const MAX_FIELD_HASH_PRODUCTS = 150

const AUDIT_FIELDS = ['verify_status', 'verify_date', 'verify_source', 'verify_url', 'change_log', 'updated_at']

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

function categoryIds() {
  const cats = readJson(path.join(DATA, 'categories.json'), [])
  return (Array.isArray(cats) ? cats : []).map((c) => c.id).filter(Boolean)
}

function loadProducts(catId) {
  return readJson(path.join(DATA, catId, 'products.json'), []) ?? []
}

/** 键值稳定序列化：字段顺序不同不影响指纹 */
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

/** 采集当前全站产品：{ "品类/产品id": { product, catId } } */
function collectAll() {
  const all = new Map()
  for (const catId of categoryIds()) {
    for (const p of loadProducts(catId)) {
      if (p?.id) all.set(`${catId}/${p.id}`, { product: p, catId })
    }
  }
  return all
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

function asList(v) {
  if (v === undefined) return []
  return [].concat(v)
}

function loadLocks() {
  if (!fs.existsSync(LOCKS)) return []
  return fs
    .readdirSync(LOCKS)
    .filter((f) => f.endsWith('.json'))
    .map((f) => ({ file: path.join(LOCKS, f), data: readJson(path.join(LOCKS, f)) }))
    .filter((x) => x.data)
}

function activeLocks() {
  return loadLocks().filter((x) => x.data.status === 'frozen')
}

/** 该产品是否被某冻结快照覆盖 */
function frozenBy(key) {
  const hits = []
  for (const { data } of activeLocks()) {
    if (data.scope?.keys?.includes(key)) hits.push(data)
  }
  return hits
}

// ---------------------------------------------------------------- 命令

function cmdSnapshot(args) {
  const all = collectAll()
  const label = typeof args.label === 'string' ? args.label : '未命名审核'
  const by = typeof args.by === 'string' ? args.by : 'unknown'
  const cats = asList(args.category)
  const prods = asList(args.product)

  let keys
  if (!cats.length && !prods.length) {
    keys = [...all.keys()]
  } else {
    keys = [...all.keys()].filter((k) => cats.includes(k.split('/')[0]) || prods.includes(k))
  }
  if (!keys.length) {
    console.error('范围为空：检查 --category / --product 是否拼错')
    process.exit(1)
  }

  // 与已有冻结快照求交集提示：同一个产品被两份快照冻结会造成混乱
  const overlap = keys.filter((k) => frozenBy(k).length)
  if (overlap.length) {
    console.error(`以下 ${overlap.length} 款产品已被其它快照冻结，请先 release 或调整范围：`)
    for (const k of overlap.slice(0, 10)) console.error(`  - ${k}`)
    process.exit(1)
  }

  const withFields = keys.length <= MAX_FIELD_HASH_PRODUCTS
  const hashes = {}
  for (const k of keys) {
    const p = all.get(k).product
    const rec = { _: hash(stable(p)) }
    if (withFields) {
      rec.fields = {}
      for (const f of Object.keys(p).sort()) rec.fields[f] = hash(stable(p[f]))
    }
    hashes[k] = rec
  }

  const stamp = new Date()
  const id = `${stamp.toISOString().slice(0, 10)}-${String(stamp.getTime()).slice(-5)}-${label
    .replace(/[^\w\u4e00-\u9fa5-]+/g, '')
    .slice(0, 12)}`
  const record = {
    id,
    label,
    createdBy: by,
    createdAt: stamp.toISOString(),
    status: 'frozen',
    releasedAt: null,
    releaseNote: null,
    fieldLevel: withFields,
    scope: {
      categories: [...new Set(keys.map((k) => k.split('/')[0]))].sort(),
      keys,
    },
    hashes,
    _说明:
      '审核快照锁。冻结期内任何 Agent 不得修改 scope.keys 内产品的字段。' +
      '审核完成后用 npm run audit:release -- <id> 解除。检测越界用 npm run audit:check。',
  }
  ensureDir(LOCKS)
  const file = path.join(LOCKS, `${id}.json`)
  fs.writeFileSync(file, JSON.stringify(record, null, 1) + '\n', 'utf8')
  console.log(`已创建审核快照：${id}`)
  console.log(`  范围：${record.scope.categories.length} 个品类 / ${keys.length} 款产品${withFields ? '（含字段级指纹）' : '（仅整条指纹）'}`)
  console.log(`  文件：${path.relative(ROOT, file)}`)
  console.log('  下一步：审核结束后 npm run audit:release -- ' + id)
}

function checkOne(lock) {
  const all = collectAll()
  const violations = []
  let missing = 0
  for (const k of lock.scope.keys) {
    const cur = all.get(k)
    if (!cur) {
      violations.push({ key: k, type: 'removed', fields: [] })
      missing++
      continue
    }
    const nowHash = hash(stable(cur.product))
    const was = lock.hashes[k]
    if (!was || was._ === nowHash) continue
    let fields = []
    if (was.fields) {
      fields = Object.keys(was.fields).filter((f) => hash(stable(cur.product[f])) !== was.fields[f])
      // 新增字段
      for (const f of Object.keys(cur.product)) if (!(f in was.fields)) fields.push(`${f}(新增)`)
    }
    violations.push({ key: k, type: 'modified', fields })
  }
  // 范围内新增的产品
  const added = []
  const scopeCats = new Set(lock.scope.keys.map((k) => k.split('/')[0]))
  for (const [k, v] of all) {
    if (!scopeCats.has(v.catId)) continue
    if (!lock.scope.keys.includes(k) && lock.label.includes(v.catId)) added.push(k)
  }
  return { violations, added }
}

function cmdCheck(args) {
  const locks = activeLocks()
  const result = { total: 0, frozenProducts: 0, violations: [], locks: [] }
  for (const { data } of locks) {
    const { violations, added } = checkOne(data)
    result.total += violations.length
    result.frozenProducts += data.scope.keys.length
    result.locks.push({ id: data.id, label: data.label, by: data.createdBy, createdAt: data.createdAt, count: data.scope.keys.length })
    for (const v of violations) result.violations.push({ lock: data.id, label: data.label, ...v, added })
  }

  if (args.json) {
    console.log(JSON.stringify(result, null, 2))
  } else if (!locks.length) {
    console.log('没有正在生效的审核快照锁，可以自由改动。')
  } else {
    console.log(`生效中的审核快照：${locks.length} 份，共冻结 ${result.frozenProducts} 款产品`)
    for (const l of result.locks) console.log(`  · ${l.id}  「${l.label}」 by ${l.by}（${l.count} 款）`)
    console.log('')
    if (!result.violations.length) {
      console.log('✓ 冻结范围内数据与快照一致，没有越界改动。')
    } else {
      console.log(`✗ 发现 ${result.violations.length} 处越界改动：`)
      for (const v of result.violations) {
        const what = v.type === 'removed' ? '被删除' : `被修改：${v.fields.join(', ') || '（整条，字段级指纹未记录）'}`
        console.log(`  · [${v.lock}] ${v.key} ${what}`)
      }
    }
  }
  if (args.strict && result.total) process.exit(1)
}

function cmdStatus(args) {
  const targets = args._.length ? args._ : ['']
  const all = collectAll()
  const keys = targets[0] === '' ? [...all.keys()] : [...all.keys()].filter((k) => targets.some((t) => k.startsWith(t)))
  const locks = activeLocks()
  if (!locks.length) {
    console.log('当前没有冻结中的审核快照，全部产品可改。')
    return
  }
  const frozen = keys.filter((k) => frozenBy(k).length)
  console.log(`查询范围：${targets[0] === '' ? '全站' : targets.join(', ')}（${keys.length} 款）`)
  console.log(`冻结中：${frozen.length} 款`)
  for (const k of frozen.slice(0, 20)) {
    console.log(`  · ${k}  ← ${frozenBy(k).map((d) => d.id).join(', ')}`)
  }
  if (frozen.length > 20) console.log(`  …… 其余 ${frozen.length - 20} 款省略`)
  if (!frozen.length) console.log('该范围内没有产品被冻结，可安全改动。')
}

function cmdDiff(args) {
  const id = args._[0]
  const lock = loadLocks().find((x) => x.data.id === id || path.basename(x.file) === `${id}.json`)
  if (!lock) {
    console.error(`找不到快照：${id}`)
    process.exit(1)
  }
  const { violations } = checkOne(lock.data)
  if (!violations.length) {
    console.log(`快照 ${id} 范围内无改动。`)
    return
  }
  console.log(`快照 ${id}「${lock.data.label}」共 ${violations.length} 处改动：`)
  for (const v of violations) {
    console.log(`\n  ${v.key}  ${v.type === 'removed' ? '（已删除）' : ''}`)
    if (v.fields?.length) console.log(`    变更字段：${v.fields.join(', ')}`)
  }
}

function cmdRelease(args) {
  const id = args._[0]
  if (!id) {
    console.error('用法：audit-lock.mjs release <快照id> [--note "说明"]')
    process.exit(1)
  }
  const lock = loadLocks().find((x) => x.data.id === id || path.basename(x.file) === `${id}.json`)
  if (!lock) {
    console.error(`找不到快照：${id}`)
    process.exit(1)
  }
  const { violations } = checkOne(lock.data)
  if (violations.length) {
    console.log(`⚠ 解除前发现冻结期内有 ${violations.length} 处改动，请确认是否知情：`)
    for (const v of violations.slice(0, 10)) console.log(`  · ${v.key} ${v.fields?.join(', ') ?? ''}`)
  }
  lock.data.status = 'released'
  lock.data.releasedAt = new Date().toISOString()
  lock.data.releaseNote = typeof args.note === 'string' ? args.note : null
  lock.data.violationsAtRelease = violations.length
  fs.writeFileSync(lock.file, JSON.stringify(lock.data, null, 1) + '\n', 'utf8')
  console.log(`已解除冻结：${id}${violations.length ? `（遗留 ${violations.length} 处改动已记录在快照里）` : ''}`)
}

function cmdList() {
  const locks = loadLocks()
  if (!locks.length) {
    console.log('还没有任何审核快照。')
    return
  }
  console.log(`${'快照 id'.padEnd(34)} ${'状态'.padEnd(9)} 产品数  标签`)
  for (const { data } of locks) {
    console.log(`${String(data.id).padEnd(34)} ${String(data.status).padEnd(9)} ${String(data.scope.keys.length).padStart(5)}   ${data.label}`)
  }
}

const args = parseArgs(process.argv.slice(2))
const cmd = args._.shift()
try {
  switch (cmd) {
    case 'snapshot':
      cmdSnapshot(args)
      break
    case 'check':
      cmdCheck(args)
      break
    case 'status':
      cmdStatus(args)
      break
    case 'diff':
      cmdDiff(args)
      break
    case 'release':
      cmdRelease(args)
      break
    case 'list':
      cmdList()
      break
    default:
      console.log(
        [
          '审核快照锁 —— 多 Agent 并行协作用',
          '',
          '  snapshot --label "..." [--by agent-b] [--category 品类...] [--product 品类/产品id...]',
          '  check [--strict] [--json]',
          '  status [品类[/产品id]...]',
          '  diff <快照id>',
          '  release <快照id> [--note "说明"]',
          '  list',
          '',
          '规则见仓库根目录 AGENTS.md。',
        ].join('\n'),
      )
  }
} catch (e) {
  console.error(`失败：${e.message}`)
  process.exit(1)
}
