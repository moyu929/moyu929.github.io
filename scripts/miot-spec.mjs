#!/usr/bin/env node
/**
 * home.miot-spec.com（小米/米家产品库，第三方）查询工具
 * ------------------------------------------------------------------
 * 用途（对应 SKILL.md 的「仅作交叉印证」层级）：
 *   - 核对某型号**是否存在**、拿到 **miot 协议型号代码**、判断是否海外版/生态链非小米品牌
 *   - 读取官方中文名与**官方产品图**（attrs.icon_real，小米 CDN）
 *   - 读取固件能力项（传感器/滤芯/电机等，来自 MIoT 协议）
 *
 * ⚠️ 该站 attrs.verified_time 是固件协议**认证时间**，不等于上市时间；
 *    站点存在大量固件改版重复条目且收录不完整，不能以其缺失否定型号存在。
 *    因此本工具结果只用于交叉印证，不替换官方参数；也绝不写进 model_code
 *    （miot 型号形如 xiaomi.airp.sa6，与零售型号代码 MR1692 不是一回事）。
 *
 * 用法：
 *   node scripts/miot-spec.mjs crawl [关键词...]   # 按品类整库抓取（分页），默认抓全部品类
 *   node scripts/miot-spec.mjs search <关键词...>  # 只抓首页，快速看型号
 *   node scripts/miot-spec.mjs product <model...>  # 取某型号的能力项
 *   node scripts/miot-spec.mjs match [--apply]     # 用本地索引给产品补 miot_model / 图片
 */
import fs from 'node:fs'
import path from 'node:path'
import process from 'node:process'

const ROOT = path.resolve(import.meta.dirname, '..')
const CACHE = path.join(ROOT, 'data', '_cache')
const LOG = path.join(CACHE, 'miot-crawl.log')
const UA =
  'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 ' +
  '(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36'

/** 品类 id → miot 检索关键词（关键词决定召回范围，用最通用的品类词） */
const KEYWORDS = {
  'air-purifier': '空气净化器',
  'air-conditioner': '空调',
  humidifier: '加湿器',
  dehumidifier: '除湿机',
  'washing-machine': '洗衣机',
  refrigerator: '冰箱',
  'robot-vacuum': '扫地机器人',
  dishwasher: '洗碗机',
  vacuum: '吸尘器',
  'water-purifier': '净水器',
  'rice-cooker': '电饭煲',
  'air-fryer': '空气炸锅',
  fan: '风扇',
  heater: '电暖器',
  kettle: '电水壶',
  'smart-lock': '智能门锁',
  projector: '投影仪',
  toothbrush: '电动牙刷',
  microwave: '微波炉',
  'pressure-cooker': '电压力锅',
  steamer: '电蒸锅',
  'induction-cooker': '电磁炉',
  blender: '破壁机',
  'coffee-machine': '咖啡机',
  'dryer-rack': '晾衣机',
  'garment-steamer': '挂烫机',
  'mite-remover': '除螨仪',
  'water-heater': '热水器',
  'water-dispenser': '饮水机',
  'hair-dryer': '吹风机',
  shaver: '剃须刀',
  'hair-clipper': '理发器',
  'foot-spa': '足浴器',
  'massage-gun': '筋膜枪',
  'body-scale': '体脂秤',
  camera: '摄像机',
  speaker: '音箱',
  tv: '电视',
}

/** 补充关键词：主词在该站叫法不同或召回不足时使用，只并入本地索引，不改品类映射 */
const EXTRA_KEYWORDS = [
  '电吹风', '熨烫机', '电推剪', '除螨', '料理机', '电烤箱', '空气炸',
  '冷柜', '抽油烟机', '燃气灶', '晾衣架', '加湿', '香薰机', '台灯',
  '智能插座', '开关', '门铃', '路由器', '打印机', '体重秤', '血压计',
  '扫地机', '洗地机', '拖地机', '消毒柜', '垃圾处理器', '取暖器', '浴霸',
]

function log(msg) {
  const line = `${new Date().toISOString().slice(11, 19)}  ${msg}`
  console.log(line)
  fs.mkdirSync(CACHE, { recursive: true })
  fs.appendFileSync(LOG, line + '\n', 'utf8')
}

let lastReq = 0
async function fetchText(url, { retry = 1 } = {}) {
  // 站点单次约 3.5s，串行并发控制在 4，并保证最小间隔，避免被限流
  const wait = 250 - (Date.now() - lastReq)
  if (wait > 0) await new Promise((r) => setTimeout(r, wait))
  lastReq = Date.now()
  try {
    const res = await fetch(url, {
      headers: { 'User-Agent': UA, Accept: 'text/html' },
      signal: AbortSignal.timeout(25000),
    })
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    return await res.text()
  } catch (e) {
    if (retry > 0) {
      await new Promise((r) => setTimeout(r, 1500))
      return fetchText(url, { retry: retry - 1 })
    }
    throw e
  }
}

/** Inertia 页面数据：<script data-page="app" type="application/json">{…}</script> */
function extractPageData(html) {
  const marker = 'type="application/json">'
  const i = html.indexOf(marker)
  if (i < 0) return null
  const end = html.indexOf('</script>', i)
  if (end < 0) return null
  try {
    return JSON.parse(html.slice(i + marker.length, end).trim())
  } catch (e) {
    return { _parseError: e.message }
  }
}

/** 把 miot 的 results.data 规整成我们要的字段 */
function normalize(items) {
  return items.map((it) => ({
    model: it.model,
    name: it.name,
    brand: it.brandName,
    cate: it.attrs?.cate_name ?? null,
    image: it.attrs?.icon_real ?? null,
    verifiedTime: it.attrs?.verified_time ? it.attrs.verified_time * 1000 : null,
    status: it.attrs?.status ?? null,
  }))
}

async function fetchPage(kw, page) {
  const url =
    `https://home.miot-spec.com/s/${encodeURIComponent(kw)}` + (page > 1 ? `?page=${page}` : '')
  const page_ = extractPageData(await fetchText(url))
  return page_?.props?.results ?? null
}

async function crawlKeyword(kw, { allPages = true, maxPages = 12 } = {}) {
  const file = path.join(CACHE, `miot-${kw}.json`)
  if (fs.existsSync(file)) {
    const old = JSON.parse(fs.readFileSync(file, 'utf8'))
    if (old.items?.length && old.total && old.items.length >= Math.min(old.total, 50)) {
      if (!allPages || old.items.length >= old.total || old.pages >= Math.min(old.total ? Math.ceil(old.total / 50) : 1, maxPages)) {
        log(`  ${kw}: 命中缓存 ${old.items.length}/${old.total}`)
        return old
      }
    }
  }
  const first = await fetchPage(kw, 1)
  if (!first) throw new Error('页面结构变化，未取到 results')
  const items = normalize(first.data)
  const total = first.total
  const pages = Math.min(first.last_page ?? 1, maxPages)
  if (allPages) {
    for (let p = 2; p <= pages; p++) {
      const nxt = await fetchPage(kw, p)
      if (nxt?.data) items.push(...normalize(nxt.data))
    }
  }
  const uniq = [...new Map(items.map((i) => [i.model, i])).values()]
  const rec = { keyword: kw, total, pages: allPages ? pages : 1, count: uniq.length, fetchedAt: new Date().toISOString(), items: uniq }
  fs.writeFileSync(file, JSON.stringify(rec, null, 1), 'utf8')
  log(`  ${kw}: ${uniq.length}/${total} 条（${rec.pages} 页）`)
  return rec
}

async function pool(items, limit, fn) {
  const queue = [...items.entries()]
  const workers = Array.from({ length: Math.min(limit, queue.length) }, async () => {
    while (queue.length) {
      const [i, item] = queue.shift()
      try {
        await fn(item, i)
      } catch (e) {
        log(`  ✗ ${item}: ${e.message}`)
      }
    }
  })
  await Promise.all(workers)
}

async function cmdCrawl(args) {
  const force = args.includes('--force')
  if (force) for (const f of fs.readdirSync(CACHE)) if (f.startsWith('miot-') && f.endsWith('.json')) fs.unlinkSync(path.join(CACHE, f))
  const kws = args.filter((a) => !a.startsWith('--'))
  const list = kws.length
    ? kws
    : [...new Set([...Object.values(KEYWORDS), ...EXTRA_KEYWORDS])]
  log(`开始抓取 ${list.length} 个关键词（并发 4）`)
  let done = 0
  await pool(list, 4, async (kw) => {
    await crawlKeyword(kw)
    done++
    log(`  进度 ${done}/${list.length}`)
  })
  log('抓取完成')
}

async function cmdSearch(keywords) {
  for (const kw of keywords) await crawlKeyword(kw, { allPages: false })
}

async function cmdProduct(models) {
  for (const m of models) {
    const file = path.join(CACHE, `miot-p-${m}.json`)
    if (fs.existsSync(file)) {
      log(`  ${m}: 命中缓存`)
      continue
    }
    const page = extractPageData(await fetchText(`https://home.miot-spec.com/p/${m}`))
    const services = (page?.props?.product?.services ?? []).map((s) => ({
      name: s.description,
      type: s.type,
      props: (s.properties ?? []).map((p) => `${p.description}(${p.format ?? ''})`),
    }))
    const rec = {
      model: m,
      name: page?.props?.product?.name ?? null,
      services,
      fetchedAt: new Date().toISOString(),
    }
    fs.writeFileSync(file, JSON.stringify(rec, null, 1), 'utf8')
    log(`  ${m}: ${rec.name ?? '（无名称）'} · ${services.length} 个服务`)
  }
}

/** 建立本地索引：squash(官方名) → 条目 */
function buildIndex() {
  const idx = new Map()
  for (const f of fs.readdirSync(CACHE).filter((x) => x.startsWith('miot-') && x.endsWith('.json') && !x.includes('resolve') && !x.includes('-p-'))) {
    const d = JSON.parse(fs.readFileSync(path.join(CACHE, f), 'utf8'))
    for (const it of d.items ?? []) {
      if (!it.name) continue
      const k = squash(it.name)
      if (!idx.has(k)) idx.set(k, [])
      idx.get(k).push({ ...it, keyword: d.keyword })
    }
  }
  return idx
}

function squash(s) {
  return String(s)
    .replace(/[（(]\d{4}款[)）]/g, '')
    .replace(/\d{4}款/g, '')
    .replace(/小米|米家|Xiaomi|Mijia|Mi\b/gi, '')
    .replace(/[\s()[\]（）【】·,，。.、:：;；!！?？\-—_/｜|+*#~～"']/g, '')
    .toLowerCase()
}

/** 用本地索引给产品补 miot_model / 图片建议 */
function cmdMatch(args) {
  const apply = args.includes('--apply')
  const idx = buildIndex()
  if (!idx.size) throw new Error('没有本地索引，先跑：npm run miot:crawl')
  const cats = JSON.parse(fs.readFileSync(path.join(ROOT, 'data', 'categories.json'), 'utf8'))
  const report = []
  let exact = 0
  let loose = 0
  let none = 0
  for (const c of cats) {
    const file = path.join(ROOT, 'data', c.id, 'products.json')
    const prods = JSON.parse(fs.readFileSync(file, 'utf8'))
    let changed = false
    for (const p of prods) {
      const n = squash(p.name)
      let hit = idx.get(n)
      let kind = 'exact'
      if (!hit?.length) {
        // 退一步：官方名包含我的产品名（或反之），取最短者
        const cands = []
        for (const [k, v] of idx) {
          if (k && (k.includes(n) || n.includes(k))) cands.push(...v.map((x) => ({ ...x, _k: k })))
        }
        if (cands.length) {
          cands.sort((a, b) => a._k.length - b._k.length)
          hit = cands
          kind = 'loose'
        }
      }
      if (!hit?.length) {
        none++
        report.push({ cat: c.id, id: p.id, name: p.name, kind: 'none' })
        continue
      }
      const best = hit[0]
      if (kind === 'exact') exact++
      else loose++
      report.push({
        cat: c.id,
        id: p.id,
        name: p.name,
        kind,
        miot_model: best.model,
        miot_name: best.name,
        image: p.img ? null : best.image,
      })
      if (apply) {
        if (best.model && (!p.miot_model || p.miot_model !== best.model)) {
          p.miot_model = best.model
          changed = true
        }
        if (!p.img && best.image) {
          p.img_pending = best.image
          changed = true
        }
      }
    }
    if (apply && changed) fs.writeFileSync(file, JSON.stringify(prods, null, 1) + '\n', 'utf8')
  }
  fs.writeFileSync(path.join(CACHE, 'miot-match.json'), JSON.stringify(report, null, 1), 'utf8')
  log(`匹配完成：精确 ${exact}，模糊 ${loose}，无结果 ${none}；明细 data/_cache/miot-match.json${apply ? '（已写入）' : ''}`)
}

const [cmd, ...args] = process.argv.slice(2)
try {
  if (cmd === 'crawl') await cmdCrawl(args)
  else if (cmd === 'search') await cmdSearch(args)
  else if (cmd === 'product') await cmdProduct(args)
  else if (cmd === 'match') cmdMatch(args)
  else
    console.log(
      [
        'home.miot-spec.com 查询工具（第三方，仅作交叉印证）',
        '',
        '  crawl [关键词...]     按品类整库抓取（分页，并发 4，增量落盘）',
        '  search <关键词...>    只抓首页，快速看型号',
        '  product <model...>    读取某型号的固件能力项',
        '  match [--apply]       用本地索引补 miot_model 与图片',
        '',
        '注意：verified_time 是协议认证时间，不是上市时间；收录不完整，缺失≠不存在。',
      ].join('\n'),
    )
} catch (e) {
  log(`失败：${e.message}`)
  process.exit(1)
}
