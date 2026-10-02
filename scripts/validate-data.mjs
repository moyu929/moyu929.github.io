/**
 * 校验 data/ 下的数据文件，防止手改 JSON 时出错。
 *
 *   npm run validate
 *
 * 检查项：
 *   - categories.json 里的每个品类都有 schema.json + products.json
 *   - 产品 id 唯一、可安全用作文件名
 *   - schema 中标记 sortable/stat 的字段确实是数值型
 *   - 产品里出现了 schema 未定义的字段（提示，不算错误）
 *   - img 指向的图片文件真实存在
 *   - 三个流转分区（_draft 草稿区 / _intake 待入库区 / _review 修正区）里的产品
 *     同样对照所属品类 schema 校验（流转关口 flow:submit/claim/publish 会拦，
 *     这里兜底拦「绕过工具的手改」）
 */
import fs from 'node:fs'
import path from 'node:path'
import { checkProduct, checkSchema } from './lib/product-check.mjs'

const DATA_DIR = 'data'
const PUBLIC_DIR = 'public'

const errors = []
const warnings = []

function readJson(file) {
  try {
    return JSON.parse(fs.readFileSync(file, 'utf8'))
  } catch (e) {
    errors.push(`${file}：JSON 解析失败 —— ${e.message}`)
    return null
  }
}

const groups = readJson(path.join(DATA_DIR, 'categories.json'))
if (!Array.isArray(groups)) {
  console.error('categories.json 必须是数组')
  process.exit(1)
}

// categories.json 是两层结构：一级品类分组 -> 小品类。校验只关心小品类。
const categories = groups.flatMap((g) => {
  if (!Array.isArray(g?.categories)) {
    errors.push(`一级品类「${g?.id ?? '未知'}」缺少 categories 数组`)
    return []
  }
  if (!g.id || !g.name) errors.push(`一级品类缺少 id 或 name`)
  return g.categories
})
{
  // 分组只做结构校验，字段校验都在下面的品类循环里
  const ids = categories.map((c) => c.id)
  const dup = ids.filter((id, i) => ids.indexOf(id) !== i)
  if (dup.length) errors.push(`品类 id 重复：${[...new Set(dup)].join('、')}`)
  // 反向检查：data/ 下每个品类目录都要登记进 categories.json，否则前端入口缺一块。
  // 例外：只有 schema.json 还没有 products.json 的目录，视为「收录中」（分区流转允许
  // 草稿先行），降为提示；一旦 products.json 出现就必须登记。
  for (const entry of fs.readdirSync(DATA_DIR, { withFileTypes: true })) {
    if (!entry.isDirectory()) continue
    if (entry.name.startsWith('_')) continue
    if (!ids.includes(entry.name)) {
      const hasProducts = fs.existsSync(path.join(DATA_DIR, entry.name, 'products.json'))
      if (hasProducts) {
        errors.push(`data/${entry.name} 未登记进 categories.json`)
      } else {
        warnings.push(`data/${entry.name} 只有 schema.json、未登记进 categories.json（收录中？登记后方可入库展示）`)
      }
    }
  }
}

for (const category of categories) {
  const dir = path.join(DATA_DIR, category.id)
  const schemaFile = path.join(dir, 'schema.json')
  const productsFile = path.join(dir, 'products.json')

  if (!fs.existsSync(schemaFile) || !fs.existsSync(productsFile)) {
    errors.push(`品类「${category.id}」缺少 schema.json 或 products.json`)
    continue
  }

  const schema = readJson(schemaFile)
  const products = readJson(productsFile)
  if (!schema || !products) continue

  errors.push(...checkSchema(category.id, schema))

  const seenIds = new Set()
  for (const p of products) {
    if (p.id && seenIds.has(p.id)) {
      errors.push(`${category.id}：产品 id 重复 —— ${p.id}`)
    }
    seenIds.add(p.id)

    const { errors: e, warnings: w } = checkProduct(category.id, schema, p)
    errors.push(...e)
    warnings.push(...w)
  }

  console.log(`✓ ${category.name}（${category.id}）：${products.length} 款产品，${schema.fields.length} 个字段`)
}

// ---------------- 流转分区：_draft / _intake / _review ----------------

const ZONES = [
  ['_draft', '草稿区'],
  ['_intake', '待入库区'],
  ['_review', '修正区'],
]
const zoneSummary = []

for (const [dir, name] of ZONES) {
  const zoneDir = path.join(DATA_DIR, dir)
  let count = 0
  if (fs.existsSync(zoneDir)) {
    for (const cat of fs.readdirSync(zoneDir, { withFileTypes: true })) {
      if (!cat.isDirectory()) continue
      const catId = cat.name
      const schemaFile = path.join(DATA_DIR, catId, 'schema.json')
      const schema = fs.existsSync(schemaFile) ? readJson(schemaFile) : null
      // 草稿区可以先于 schema（收录刚起步）；进了交接队列就必须有 schema（flow:submit 已强制）
      if (!schema) {
        const msg = `${name}/${catId}：data/${catId}/schema.json 不存在，分区内容无法校验`
        if (dir === '_draft') warnings.push(msg)
        else errors.push(msg)
        continue
      }
      for (const f of fs.readdirSync(path.join(zoneDir, cat.name))) {
        if (!f.endsWith('.json')) continue
        const product = readJson(path.join(zoneDir, cat.name, f))
        if (!product) continue
        count++
        if (product.id && product.id !== f.slice(0, -5)) {
          errors.push(`${name}/${catId}/${f}：文件名与产品 id「${product.id}」不一致`)
        }
        const { errors: e, warnings: w } = checkProduct(catId, schema, product)
        errors.push(...e.map((x) => `${name}·${x}`))
        warnings.push(...w.map((x) => `${name}·${x}`))
      }
    }
  }
  zoneSummary.push(`${name} ${count}`)
}

if (warnings.length) {
  console.log(`\n提示 ${warnings.length} 条：`)
  for (const w of warnings) console.log(`  · ${w}`)
}

if (errors.length) {
  console.error(`\n错误 ${errors.length} 条：`)
  for (const e of errors) console.error(`  ✗ ${e}`)
  process.exit(1)
}

console.log(`\n流转分区：${zoneSummary.join(' / ')} / 已入库区见上方各品类`)
console.log('数据校验通过')
