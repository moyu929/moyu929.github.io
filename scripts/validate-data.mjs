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
 */
import fs from 'node:fs'
import path from 'node:path'

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

const categories = readJson(path.join(DATA_DIR, 'categories.json'))
if (!Array.isArray(categories)) {
  console.error('categories.json 必须是数组')
  process.exit(1)
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

  const fieldByKey = new Map(schema.fields.map((f) => [f.key, f]))

  // 分组字段必须在 fields 中定义，否则对比表和徽章取不到值
  if (!fieldByKey.has(schema.groupBy.key)) {
    errors.push(`${category.id}：groupBy.key「${schema.groupBy.key}」未在 fields 中定义`)
  }
  if (!fieldByKey.has(schema.primaryMetric)) {
    errors.push(`${category.id}：primaryMetric「${schema.primaryMetric}」未在 fields 中定义`)
  }
  for (const key of schema.searchFields) {
    if (!fieldByKey.has(key)) {
      errors.push(`${category.id}：searchFields 中的「${key}」未在 fields 中定义`)
    }
  }

  const seenIds = new Set()
  const knownGroups = new Set(schema.groupBy.order)

  for (const p of products) {
    if (!p.id) {
      errors.push(`${category.id}：存在没有 id 的产品（${p.name ?? '未命名'}）`)
      continue
    }
    if (seenIds.has(p.id)) {
      errors.push(`${category.id}：产品 id 重复 —— ${p.id}`)
    }
    seenIds.add(p.id)

    if (!/^[a-zA-Z0-9._-]+$/.test(p.id)) {
      errors.push(`${category.id}：产品 id「${p.id}」含有不适合作文件名的字符`)
    }

    const group = p[schema.groupBy.key]
    if (group && !knownGroups.has(String(group))) {
      errors.push(
        `${category.id}/${p.id}：${schema.groupBy.key} 值「${group}」不在 groupBy.order 中，将不会显示`,
      )
    }

    for (const field of schema.fields) {
      const v = p[field.key]
      if (v === undefined || v === null) continue

      if (field.type === 'number' && typeof v !== 'number' && Number.isNaN(Number.parseFloat(v))) {
        warnings.push(
          `${category.id}/${p.id}：${field.key} 声明为 number，实际是「${v}」，排序时会沉底`,
        )
      }
      if (field.type === 'tags' && !Array.isArray(v)) {
        errors.push(`${category.id}/${p.id}：${field.key} 声明为 tags，必须是数组`)
      }
    }

    for (const key of Object.keys(p)) {
      if (key === 'id' || key === 'img') continue
      if (!fieldByKey.has(key)) {
        warnings.push(`${category.id}/${p.id}：字段「${key}」未在 schema 中定义，不会显示`)
      }
    }

    if (p.img) {
      const imgPath = path.join(PUBLIC_DIR, schema.imageBase, p.img)
      if (!fs.existsSync(imgPath)) {
        errors.push(`${category.id}/${p.id}：图片不存在 —— ${imgPath}`)
      }
    } else {
      warnings.push(`${category.id}/${p.id}：暂无产品图`)
    }
  }

  console.log(`✓ ${category.name}（${category.id}）：${products.length} 款产品，${schema.fields.length} 个字段`)
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

console.log('\n数据校验通过')
