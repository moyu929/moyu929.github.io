/**
 * 从旧的单文件 air_purifier_compare.html 中提取产品数据与内嵌图片。
 *
 *   node scripts/extract-legacy.mjs
 *
 * 输出：
 *   data/air-purifier/products.json   —— 产品数据（img 字段改为图片文件名）
 *   public/images/air-purifier/*.jpg  —— 从 base64 还原的产品图
 *
 * 这是一次性迁移脚本，保留在仓库中以便日后核对来源。
 */
import fs from 'node:fs'
import path from 'node:path'

const LEGACY_HTML = process.argv[2] || 'air_purifier_compare.html'
const IMAGE_DIR = 'public/images/air-purifier'
const DATA_DIR = 'data/air-purifier'

if (!fs.existsSync(LEGACY_HTML)) {
  console.error(`找不到源文件：${LEGACY_HTML}`)
  process.exit(1)
}

const src = fs.readFileSync(LEGACY_HTML, 'utf8')
const start = src.indexOf('const PRODUCTS = [')
if (start < 0) {
  console.error('源文件中找不到 `const PRODUCTS = [`')
  process.exit(1)
}
const end = src.indexOf('];', start)
const products = new Function(
  'return ' + src.slice(start + 'const PRODUCTS = '.length, end + 1),
)()

fs.mkdirSync(IMAGE_DIR, { recursive: true })
fs.mkdirSync(DATA_DIR, { recursive: true })

const EXT_BY_MIME = { jpeg: 'jpg', jpg: 'jpg', png: 'png', webp: 'webp', gif: 'gif' }

let extracted = 0
const missing = []

const cleaned = products.map((p) => {
  const { img, ...rest } = p
  const match = /^data:image\/([a-z]+);base64,/.exec(img || '')

  if (!match) {
    missing.push(p.id)
    return { ...rest, img: null }
  }

  const ext = EXT_BY_MIME[match[1]] || match[1]
  const filename = `${p.id}.${ext}`
  fs.writeFileSync(
    path.join(IMAGE_DIR, filename),
    Buffer.from(img.slice(match[0].length), 'base64'),
  )
  extracted++

  return { ...rest, img: filename }
})

fs.writeFileSync(
  path.join(DATA_DIR, 'products.json'),
  JSON.stringify(cleaned, null, 2) + '\n',
  'utf8',
)

console.log(`产品：${cleaned.length} 款 → ${DATA_DIR}/products.json`)
console.log(`图片：${extracted} 张 → ${IMAGE_DIR}/`)
if (missing.length) {
  console.log(`无图（img 置为 null）：${missing.join(', ')}`)
}
