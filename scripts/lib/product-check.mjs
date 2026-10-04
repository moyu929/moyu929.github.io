/**
 * 产品级数据校验核心 —— validate-data.mjs（全站校验）与 flow.mjs（分区流转）共用。
 *
 * 抽成公共模块的原因：数据在「草稿区 → 待入库区 → 修正区 → 已入库区」之间流转时，
 * 每一道关口（submit / claim / publish）都要用**同一套标准**校验，避免两份校验逻辑漂移。
 */
import fs from 'node:fs'
import path from 'node:path'

const ROOT = path.resolve(import.meta.dirname, '../..')
const PUBLIC_DIR = path.join(ROOT, 'public')

/**
 * 宽松解析数值：容忍「≤78dB(A)」「约 5.3kg」「0.85Kwh/24h」这类带前缀/后缀的写法。
 * 与前端 src/format.ts 的 numberOf 同口径。
 */
export function parseFloatLoose(v) {
  if (typeof v === 'number') return v
  if (typeof v !== 'string') return NaN
  // 「查不到」「—」是规范里的无值占位，不是数据问题
  if (v === '查不到' || v === '—' || v.trim() === '') return 0
  const m = v.match(/-?\d+(\.\d+)?/)
  return m ? Number.parseFloat(m[0]) : NaN
}

/** schema 自身合法性：groupBy / primaryMetric / searchFields 引用的字段必须已定义 */
export function checkSchema(catId, schema) {
  const errors = []
  if (!Array.isArray(schema.fields) || !schema.groupBy) {
    errors.push(`${catId}：schema.json 缺少 fields 数组或 groupBy 定义`)
    return errors
  }
  const fieldByKey = new Map(schema.fields.map((f) => [f.key, f]))
  if (!fieldByKey.has(schema.groupBy.key)) {
    errors.push(`${catId}：groupBy.key「${schema.groupBy.key}」未在 fields 中定义`)
  }
  if (!fieldByKey.has(schema.primaryMetric)) {
    errors.push(`${catId}：primaryMetric「${schema.primaryMetric}」未在 fields 中定义`)
  }
  for (const key of schema.searchFields ?? []) {
    if (!fieldByKey.has(key)) {
      errors.push(`${catId}：searchFields 中的「${key}」未在 fields 中定义`)
    }
  }
  return errors
}

/** 单款产品对照 schema 的校验。errors 阻断流转/部署，warnings 仅提示。 */
export function checkProduct(catId, schema, p) {
  const errors = []
  const warnings = []
  if (!schema.fields || !schema.groupBy) {
    errors.push(`${catId}：schema 不完整，无法校验产品`)
    return { errors, warnings }
  }
  if (!p.id) {
    errors.push(`${catId}：存在没有 id 的产品（${p.name ?? '未命名'}）`)
    return { errors, warnings }
  }
  const label = `${catId}/${p.id}`

  if (!/^[a-zA-Z0-9._-]+$/.test(p.id)) {
    errors.push(`${catId}：产品 id「${p.id}」含有不适合作文件名的字符`)
  }

  const fieldByKey = new Map(schema.fields.map((f) => [f.key, f]))
  const knownGroups = new Set(schema.groupBy.order)

  // 分组字段必须在 groupBy.order 中，否则对比表和徽章取不到值
  const group = p[schema.groupBy.key]
  if (group && !knownGroups.has(String(group))) {
    errors.push(`${label}：${schema.groupBy.key} 值「${group}」不在 groupBy.order 中，将不会显示`)
  }

  for (const field of schema.fields) {
    const v = p[field.key]
    if (v === undefined || v === null) continue

    // number 字段的字符串值只要能解析出数字就是合法的带单位值
    // （非小米品牌数据常把单位写进值里：「85英寸」「4000mAh」「16套」「4L(4-5人)」）。
    // 展示层 formatValue 会识别并跳过重复的单位追加，排序时 numberOf 也能解析。
    // 只有连数字都解析不出的（纯文字说明）才告警，因为那种排序时真的会沉底。
    if (field.type === 'number' && typeof v !== 'number' && !Number.isFinite(parseFloatLoose(v))) {
      warnings.push(`${label}：${field.key} 声明为 number，实际是「${v}」，排序时会沉底`)
    }
    if (field.type === 'tags' && !Array.isArray(v)) {
      errors.push(`${label}：${field.key} 声明为 tags，必须是数组`)
    }
  }

  for (const key of Object.keys(p)) {
    if (key === 'id' || key === 'img') continue
    if (!fieldByKey.has(key)) {
      warnings.push(`${label}：字段「${key}」未在 schema 中定义，不会显示`)
    }
  }

  if (p.img) {
    const imgPath = path.join(PUBLIC_DIR, schema.imageBase, p.img)
    if (!fs.existsSync(imgPath)) {
      errors.push(`${label}：图片不存在 —— ${imgPath}`)
    }
  } else {
    warnings.push(`${label}：暂无产品图`)
  }

  return { errors, warnings }
}

/**
 * 品类级校验：schema 合法性 + 产品 id 唯一 + 逐产品校验。
 *
 * 供 validate-data.mjs（全站校验）与 flow.mjs（入库后的品类复检）共用。
 * 之所以单独抽出来：这两处曾经各写一份品类循环，改一处忘另一处就会造成
 * 「npm run validate 通过但 flow:publish 失败」（反之亦然）的口径漂移。
 */
export function checkCategory(catId, schema, products) {
  const errors = []
  const warnings = []
  if (!schema) {
    errors.push(`${catId}：schema.json 不存在`)
    return { errors, warnings }
  }
  errors.push(...checkSchema(catId, schema))
  const seen = new Set()
  for (const p of products ?? []) {
    if (p?.id) {
      if (seen.has(p.id)) errors.push(`${catId}：产品 id 重复 —— ${p.id}`)
      seen.add(p.id)
    }
    const r = checkProduct(catId, schema, p)
    errors.push(...r.errors)
    warnings.push(...r.warnings)
  }
  return { errors, warnings }
}

/** 每款产品必带的 6 个审核标注字段（见 skills/appliance-data-curation/SKILL.md） */
export const AUDIT_FIELDS = ['verify_status', 'verify_date', 'verify_source', 'verify_url', 'change_log', 'updated_at']

/** verify_status 的规范取值 */
export const VERIFY_STATUSES = ['已核验（多源）', '已核验（官方商城）', '已核验（第三方）', '待核验']

/** 分区流转关口用的审核字段检查（库内历史数据不做强求，流转中的数据必须齐） */
export function checkAuditFields(p) {
  const errors = []
  for (const f of AUDIT_FIELDS) {
    if (!(f in p)) errors.push(`缺少审核标注字段 ${f}`)
  }
  if ('verify_status' in p && !VERIFY_STATUSES.includes(p.verify_status)) {
    errors.push(`verify_status「${p.verify_status}」不在规范取值内：${VERIFY_STATUSES.join(' / ')}`)
  }
  return errors
}
