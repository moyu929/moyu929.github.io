#!/usr/bin/env node
/**
 * 小米商城数据采集流水线（官方在售清单 / 官方图 / 官方规格页）
 * ------------------------------------------------------------------
 * 用法：
 *   node scripts/mi-store.mjs enumerate <关键词...>        # 枚举在售商品（需要 playwright）
 *   node scripts/mi-store.mjs detail <productId...>        # 拉取官方商品详情（纯 HTTP）
 *   node scripts/mi-store.mjs specs <url...>               # 抓取官方规格页参数表（纯 HTTP）
 *   node scripts/mi-store.mjs images                       # 按 data/_sources/images.json 下载产品图
 *   node scripts/mi-store.mjs apply <patch.json>           # 把字段补丁安全写入 products.json
 *
 * 设计约定（对应 skills/appliance-data-curation/SKILL.md）：
 *   - 只收录小米/米家国内在售或发布型号；数值必须可溯源，查不到就写「查不到」，禁止估算。
 *   - 本脚本只负责「抓取 + 落地缓存 + 安全回写」，**是否采用某条数据由人判断**。
 *   - 回写 products.json 时严格按 id 定位对象边界，避免「从 id 向后找第一个 img」这类越界写错。
 *
 * 依赖：Node 18+（用内置 fetch）。仅 `enumerate` 需要 Playwright：
 *   npm i -D playwright && npx playwright install chromium
 */
import fs from 'node:fs'
import path from 'node:path'
import process from 'node:process'

const ROOT = path.resolve(import.meta.dirname, '..')
const CACHE = path.join(ROOT, 'data', '_cache')
const SOURCES = path.join(ROOT, 'data', '_sources')
const UA =
  'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 ' +
  '(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36'

// ---------------------------------------------------------------- 基础工具

function ensureDir(dir) {
  fs.mkdirSync(dir, { recursive: true })
}

async function fetchText(url, { timeout = 30000 } = {}) {
  const res = await fetch(url, {
    headers: { 'User-Agent': UA, Referer: 'https://www.mi.com/' },
    signal: AbortSignal.timeout(timeout),
  })
  if (!res.ok) throw new Error(`${res.status} ${res.statusText} — ${url}`)
  return res.text()
}

async function fetchJson(url) {
  return JSON.parse(await fetchText(url))
}

async function fetchBinary(url) {
  const res = await fetch(url, {
    headers: { 'User-Agent': UA, Referer: 'https://www.mi.com/' },
    signal: AbortSignal.timeout(45000),
  })
  if (!res.ok) throw new Error(`${res.status} — ${url}`)
  return Buffer.from(await res.arrayBuffer())
}

function readJson(file, fallback = null) {
  try {
    return JSON.parse(fs.readFileSync(file, 'utf8'))
  } catch {
    return fallback
  }
}

function writeJson(file, data) {
  ensureDir(path.dirname(file))
  fs.writeFileSync(file, JSON.stringify(data, null, 2) + '\n', 'utf8')
}

/** 归一化商品名：去空格、去颜色词、去价格、去「（YYYY款）」后缀，用于跨源匹配 */
const COLOR_WORDS = [
  '星辰黑', '冰晶白', '星锻银', '锻银', '钛金灰', '浪漫紫', '星空黑', '深空灰', '珍珠白',
  '奶油白', '浅金色', '沙金色', '锖金', '锖色', '碳素黑', '陨石灰', '皓月白', '月光白',
  '白色', '黑色', '灰色', '银色', '金色', '绿色', '蓝色', '粉色', '紫色', '红色',
]
export function normalizeName(name) {
  let s = String(name).normalize('NFKC')
  s = s.replace(/\d+(\.\d+)?\s*元/g, '')
  s = s.replace(/[（(]\d{4}款[)）]/g, '')
  s = s.replace(/[（(]新款[)）]/g, '')
  for (const w of COLOR_WORDS) s = s.split(w).join('')
  s = s.replace(/米家小米|小米米家/g, '米家')
  return s.replace(/[\s()[\]（）【】「」·,，。.、:：;；!！?？\-—_/｜|+*#~～"']/g, '')
}

// ------------------------------------------------- 安全回写（对象边界守卫）

/**
 * 在 products.json 文本中定位某个 id 的对象，替换其中一个字段。
 * 若 id 与目标字段之间出现了新的 "id"，说明跨过了对象边界，直接报错而不是硬写。
 */
export function patchFieldInText(text, id, key, valueLiteral) {
  const idToken = `"id": "${id}"`
  const idTokenAlt = `"id":"${id}"`
  const start = text.indexOf(idToken) >= 0 ? text.indexOf(idToken) : text.indexOf(idTokenAlt)
  if (start < 0) throw new Error(`未找到产品 id：${id}`)

  const keyRe = new RegExp(`"${key}"\\s*:\\s*`)
  const km = keyRe.exec(text.slice(start))
  if (!km) throw new Error(`${id} 中未找到字段 ${key}`)

  const valueStart = start + km.index + km[0].length
  const between = text.slice(start + idToken.length, valueStart)
  if (/"id"\s*:/.test(between)) {
    throw new Error(`${id}.${key} 定位越界（中间出现新的 id），已中止`)
  }

  // 找到值的结束位置：字符串 / null / 数字 / 数组 / 对象
  const rest = text.slice(valueStart)
  let end
  if (rest.startsWith('[')) end = matchBalanced(rest, '[', ']')
  else if (rest.startsWith('{')) end = matchBalanced(rest, '{', '}')
  else if (rest.startsWith('"')) end = matchString(rest)
  else end = /^(null|true|false|-?\d+(\.\d+)?)/.exec(rest)?.[0]?.length ?? 0
  if (!end) throw new Error(`${id}.${key} 值解析失败`)

  return text.slice(0, valueStart) + valueLiteral + text.slice(valueStart + end)
}

function matchString(s) {
  for (let i = 1; i < s.length; i++) {
    if (s[i] === '\\') i++
    else if (s[i] === '"') return i + 1
  }
  return 0
}

function matchBalanced(s, open, close) {
  let depth = 0
  for (let i = 0; i < s.length; i++) {
    if (s[i] === '"') {
      i += matchString(s.slice(i)) - 1
      continue
    }
    if (s[i] === open) depth++
    else if (s[i] === close) {
      depth--
      if (depth === 0) return i + 1
    }
  }
  return 0
}

/** 把补丁写回 products.json：{ "<category>/<productId>": { key: value, ... } } */
export function applyPatches(patch) {
  const byCat = new Map()
  for (const [target, fields] of Object.entries(patch)) {
    if (target.startsWith('_')) continue
    const [cat, pid] = target.split('/')
    if (!cat || !pid) continue
    if (!byCat.has(cat)) byCat.set(cat, [])
    byCat.get(cat).push([pid, fields])
  }

  let changed = 0
  const errors = []
  for (const [cat, items] of byCat) {
    const file = path.join(ROOT, 'data', cat, 'products.json')
    if (!fs.existsSync(file)) {
      errors.push(`品类不存在：${cat}`)
      continue
    }
    let before = fs.readFileSync(file, 'utf8')
    for (const [pid, fields] of items) {
      let text = fs.readFileSync(file, 'utf8')
      for (const [key, value] of Object.entries(fields)) {
        try {
          text = patchFieldInText(text, pid, key, JSON.stringify(value))
          changed++
        } catch (e) {
          errors.push(`${cat}/${pid}.${key}: ${e.message}`)
        }
      }
      fs.writeFileSync(file, text, 'utf8')
    }
    const products = JSON.parse(fs.readFileSync(file, 'utf8'))
    const dup = products.map((p) => p.id).filter((v, i, a) => a.indexOf(v) !== i)
    if (dup.length) errors.push(`${cat} id 重复：${dup.join(', ')}`)
    if (before === fs.readFileSync(file, 'utf8')) continue
    console.log(`  ✓ ${cat}：更新 ${items.length} 款`)
  }
  return { changed, errors }
}

// ---------------------------------------------------------------- 子命令

/** enumerate：用 Playwright 打开商城搜索页，抽取商品名/价格/图片/商品ID */
async function cmdEnumerate(keywords) {
  if (!keywords.length) throw new Error('用法：mi-store.mjs enumerate <关键词...>')
  let chromium
  try {
    ;({ chromium } = await import('playwright'))
  } catch {
    console.error(
      '需要 Playwright（仅枚举步骤需要）：\n' +
        '  npm i -D playwright && npx playwright install chromium',
    )
    process.exit(1)
  }

  const browser = await chromium.launch({ headless: true })
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 1200 }, userAgent: UA })
  const page = await ctx.newPage()
  const out = {}

  for (const kw of keywords) {
    await page.goto(`https://www.mi.com/search?keyword=${encodeURIComponent(kw)}`, {
      waitUntil: 'domcontentloaded',
      timeout: 60000,
    })
    await page.waitForTimeout(4500)
    for (let i = 0; i < 3; i++) {
      await page.mouse.wheel(0, 2500)
      await page.waitForTimeout(1100)
    }
    const items = await page.evaluate(() => {
      // 只取搜索结果列表里的卡片：顶部导航/推荐位同样是 a[href*=product_id]，必须按容器限定
      let nodes = [...document.querySelectorAll('.goods-list .goods-item')]
      if (!nodes.length) nodes = [...document.querySelectorAll('a[href*="product_id"]')]
      const seen = new Map()
      for (const node of nodes) {
        const a = node.tagName === 'A' ? node : node.querySelector('a[href*="product_id"]')
        if (!a) continue
        const img = node.querySelector('img')
        const src = img ? img.currentSrc || img.src : ''
        const text = (node.innerText || '').replace(/\s+/g, ' ').trim()
        const pid = new URL(a.href, location.href).searchParams.get('product_id')
        if (!text || !pid || seen.has(pid)) continue
        seen.set(pid, { productId: Number(pid), text, img: src || null, href: a.href })
      }
      return [...seen.values()]
    })
    out[kw] = items
    writeJson(path.join(CACHE, `search-${kw}.json`), items)
    console.log(`  ${kw}: ${items.length} 款（已缓存 data/_cache/search-${kw}.json）`)
  }

  await browser.close()
  return out
}

/** detail：官方商品详情接口（纯 HTTP，无需浏览器） */
async function cmdDetail(ids) {
  if (!ids.length) throw new Error('用法：mi-store.mjs detail <productId...>')
  const out = {}
  for (const id of ids) {
    const cached = path.join(CACHE, `product-${id}.json`)
    if (fs.existsSync(cached)) {
      out[id] = readJson(cached)
      console.log(`  ${id}: 命中缓存`)
      continue
    }
    const raw = await fetchJson(`https://api2.order.mi.com/product/view?product_id=${id}&version=2`)
    const d = raw?.data ?? {}
    const goods = d.goods_list?.[0]?.goods_info ?? {}
    const info = {
      productId: Number(id),
      name: d.product_info?.name ?? goods.name ?? null,
      price: goods.price ?? null,
      marketPrice: goods.market_price ?? null,
      desc: d.product_info?.product_desc ?? null,
      img: goods.img_url ? `https:${goods.img_url}` : null,
      imgs: (goods.imgs ?? []).map((i) => i.url ?? i).filter(Boolean),
      isSale: goods.is_sale ?? null,
      pageId: goods.page_id ?? null,
    }
    writeJson(path.join(CACHE, `product-${id}.json`), info)
    out[id] = info
    console.log(`  ${id}: ${info.name}  现价=${info.price}  原价=${info.marketPrice}`)
    await new Promise((r) => setTimeout(r, 300))
  }
  return out
}

/** specs：抓官方规格页并解析成 { 参数名: 值 } */
async function cmdSpecs(urls) {
  if (!urls.length) throw new Error('用法：mi-store.mjs specs <url...>')
  const out = {}
  for (const url of urls) {
    const key = url.replace(/^https?:\/\//, '').replace(/[^\w.-]/g, '_')
    const cached = path.join(CACHE, `specs-${key}.json`)
    if (fs.existsSync(cached)) {
      out[url] = readJson(cached)
      console.log(`  ${url}: 命中缓存（${Object.keys(out[url].params).length} 项）`)
      continue
    }
    const html = await fetchText(url)
    const params = parseSpecsHtml(html)
    const record = { url, params, fetchedAt: new Date().toISOString() }
    writeJson(cached, record)
    out[url] = record
    console.log(`  ${url}: 解析出 ${Object.keys(params).length} 项`)
    if (!Object.keys(params).length) {
      console.log('    （该页可能未服务端渲染，需人工核对或改用其他来源）')
    }
    await new Promise((r) => setTimeout(r, 400))
  }
  return out
}

/** 解析官方规格页：<div class="items-text"><p><b>键</b><span>值</span></p>… */
export function parseSpecsHtml(html) {
  const params = {}
  const blockRe = /<div class="items-text[^"]*">([\s\S]*?)<\/div>/g
  let block
  while ((block = blockRe.exec(html))) {
    const pairRe = /<b>([\s\S]*?)<\/b>\s*<span>([\s\S]*?)<\/span>/g
    let pair
    while ((pair = pairRe.exec(block[1]))) {
      const k = stripTags(pair[1]).trim()
      const v = stripTags(pair[2]).trim()
      if (k && v && !(k in params)) params[k] = v
    }
  }
  return params
}

function stripTags(s) {
  return s
    .replace(/<[^>]+>/g, '')
    .replace(/&nbsp;/g, ' ')
    .replace(/&amp;/g, '&')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&quot;/g, '"')
}

/** images：按 data/_sources/images.json 下载产品图并回写 img 字段 */
async function cmdImages() {
  const manifestFile = path.join(SOURCES, 'images.json')
  const manifest = readJson(manifestFile)
  if (!manifest) {
    console.error(
      `缺少 ${path.relative(ROOT, manifestFile)}。\n` +
        '格式：{ "品类id/产品id": "https://…png", … }',
    )
    process.exit(1)
  }
  const patch = {}
  const pending = []
  for (const [target, url] of Object.entries(manifest)) {
    if (target.startsWith('_')) continue
    const [cat, pid] = target.split('/')
    // 站上只保留 ≤320px WebP（最大展示位 96×112 CSS px，见 scripts/shrink-images.py）
    const webp = path.join(ROOT, 'public', 'images', cat, `${pid}.webp`)
    if (fs.existsSync(webp)) {
      patch[target] = { img: `${pid}.webp` }
      continue
    }
    // 官方原图先落到 data/_cache/img-raw/（不入库），再由 img:webp 统一转换入库
    const ext = /\.jpe?g($|\?)/i.test(url) ? '.jpg' : '.png'
    const rawDir = path.join(CACHE, 'img-raw', cat)
    ensureDir(rawDir)
    const raw = path.join(rawDir, `${pid}${ext}`)
    if (!fs.existsSync(raw)) {
      try {
        fs.writeFileSync(raw, await fetchBinary(url))
        console.log(
          `  ✓ ${target} → 原图缓存 ${path.relative(ROOT, raw)} (${(fs.statSync(raw).size / 1024).toFixed(0)}KB)`,
        )
      } catch (e) {
        console.log(`  ✗ ${target}: ${e.message}`)
        continue
      }
      await new Promise((r) => setTimeout(r, 200))
    }
    pending.push(target)
  }
  const { errors } = applyPatches(patch)
  for (const e of errors) console.log(`  ! ${e}`)
  console.log(`已就绪 ${Object.keys(patch).length} 条`)
  if (pending.length) {
    console.log(`另有 ${pending.length} 条只有原图：跑 npm run img:webp 转成 ≤320px WebP 后就会写入 img 字段`)
  }
}

// ---------------------------------------------------------------- 入口

const [cmd, ...args] = process.argv.slice(2)

try {
  switch (cmd) {
    case 'enumerate':
      await cmdEnumerate(args)
      break
    case 'detail':
      await cmdDetail(args)
      break
    case 'specs':
      await cmdSpecs(args)
      break
    case 'images':
      await cmdImages()
      break
    case 'apply': {
      const file = args[0]
      if (!file) throw new Error('用法：mi-store.mjs apply <patch.json>')
      const { changed, errors } = applyPatches(readJson(path.resolve(file)))
      for (const e of errors) console.log(`  ! ${e}`)
      console.log(`已写入 ${changed} 个字段`)
      break
    }
    default:
      console.log(
        [
          '小米商城数据采集流水线',
          '',
          '  enumerate <关键词...>    枚举在售商品（需要 playwright）',
          '  detail <productId...>    拉取官方商品详情（纯 HTTP）',
          '  specs <url...>           抓取官方规格页参数表（纯 HTTP）',
          '  images                   按 data/_sources/images.json 下载产品图',
          '  apply <patch.json>       把字段补丁安全写入 products.json',
        ].join('\n'),
      )
  }
} catch (e) {
  console.error(`失败：${e.message}`)
  process.exit(1)
}
