/**
 * 已入库区（data/<品类>/products.json）的写入实现 —— Node 侧。
 *
 * 为什么要有这个模块：`products.json` 原本有 5 条互不相识的写入路径
 * （flow.mjs / mi-store.mjs / classify-facets.py / import-brands.py / shrink-images.py），
 * 其中 4 条是「读整个数组 → 改内存 → 覆写整个文件」，两个人同时写同一品类就会**静默丢数据**。
 * 本模块把 Node 侧的写入收敛到一处，并保证三件事（见方案 P0-3 / P1-1）：
 *
 *   1. 序列化规范化 —— 同一组对象在哪条路径下都产出逐字节相同的文本（跨语言一致性见 library_io.py）
 *   2. 写前指纹校验 —— 载入后若文件被别人改过，**立即拒绝**，不做覆盖
 *   3. 文件锁重试     —— Windows 上批量写实测会撞 `UNKNOWN: unknown error, open ...`，
 *                        这类失败退避重试；**与指纹冲突严格分开，绝不共用重试路径**
 *
 * Python 侧的对应实现是 `library_io.py`；两者必须产出逐字节相同的文本，
 * 由 `npm run selftest` 做双向一致性断言。
 */
import crypto from 'node:crypto'
import fs from 'node:fs'
import path from 'node:path'

/**
 * 库文件的序列化格式。
 *   'compact'  —— 整个数组压成一行（历史格式，2026-10-03 之前 40 个文件都是这样）
 *   'per-line' —— 一行一款（**当前采用**）：git 按行三方合并，两个分支改不同产品不会冲突，
 *                冲突只剩"同一款产品被两处改"——那本来就是需要人裁决的合法冲突。
 * 切换时改这一个常量，两个实现（本文件与 library_io.py）必须同时改，并跑 `npm run selftest`。
 */
const FORMAT = 'per-line'

/** 规范序列化：唯一允许的库文件文本生成方式 */
export function serializeLibrary(products) {
  if (FORMAT === 'per-line') {
    return `[\n${products.map((p) => JSON.stringify(p)).join(',\n')}\n]\n`
  }
  return `${JSON.stringify(products)}\n`
}

export function hashText(text) {
  return crypto.createHash('sha256').update(text).digest('hex')
}

/**
 * 载入库文件。文件不存在时返回空数组 + 空指纹（表示"写之前没有基线"）。
 * @returns {{ products: any[], text: string|null, hash: string|null, exists: boolean }}
 */
export function loadLibrary(file) {
  if (!fs.existsSync(file)) return { products: [], text: null, hash: null, exists: false }
  const text = fs.readFileSync(file, 'utf8')
  return { products: JSON.parse(text), text, hash: hashText(text), exists: true }
}

/** 会被退避重试的错误码（文件锁类；不含任何"内容冲突"语义） */
const RETRYABLE = new Set(['EPERM', 'EBUSY', 'EACCES', 'UNKNOWN'])

function sleepSync(ms) {
  const end = Date.now() + ms
  while (Date.now() < end) {
    /* 退避等待：这些是命令行脚本，阻塞可接受，且总时长上限约 1 秒 */
  }
}

/**
 * 批量写库脚本的操作者名（留痕用）：
 * `FLOW_ACTOR` 环境变量优先，否则取当前脚本文件名（如 mi-store.mjs）。
 * 只给**批量工具**用；flow:* 的流转有自己的 journal 条目，不要用它（见 saveLibrary 的 actor 说明）。
 */
export function scriptActor() {
  return process.env.FLOW_ACTOR || path.basename(process.argv[1] ?? '') || 'unknown'
}

/**
 * 批量写库留痕（方案 P1-1 第三要素）。
 *
 * 为什么必须有：B 用批量工具重写整品类（如 classify-facets 一次 517 条）时，
 * 产品级流转日志里**一条记录都没有** —— `flow:log` 出现盲区，只能靠 git log 兜底，
 * 而 git log 说不出「谁在什么时候用哪个脚本改了哪一品类的多少条」。
 *
 * 粒度是**一次写入一条**（不逐产品）：批量工具改的是整个品类，逐条写会把 journal 冲爆。
 */
function journalBatchWrite(file, products, actor) {
  try {
    const cat = path.basename(path.dirname(file))
    const journal = path.join(path.dirname(path.dirname(path.resolve(file))), '_flow', 'journal.jsonl')
    fs.mkdirSync(path.dirname(journal), { recursive: true })
    fs.appendFileSync(
      journal,
      `${JSON.stringify({ ts: new Date().toISOString(), actor, action: 'batch-write', key: `${cat}/products.json`, count: products.length })}\n`,
      'utf8',
    )
  } catch {
    // 留痕失败不应影响写入本身（写入已经成功）；但要让调用者知道
    console.error(`⚠ 写库留痕失败（数据已写入）：${file}`)
  }
}

/**
 * 写入库文件。
 *
 * 两类失败严格分开：
 *   ① 指纹不一致（载入后文件被别人改过）→ 抛 `ELIBRARYCONFLICT`，**立即失败、绝不重试**。
 *      共用重试路径会让守卫被重试架空：重试到某次恰好读不到变化就覆盖了。
 *   ② EPERM/EBUSY 等文件锁 → 有限次退避重试（Windows 实测成因）。
 *
 * @param {string} file
 * @param {any[]} products
 * @param {{ expectHash?: string|null, retries?: number, actor?: string|null }} options
 *   expectHash：loadLibrary() 返回的 hash；调用方必须原样传回，否则拒绝写入
 *   actor：**批量工具必须传**（用 scriptActor()）→ 写入成功后向 journal 追加一条
 *     `batch-write` 粗粒度留痕。flow:* 流转不传（它自己有 publish/recall 等条目，传了会重复记）。
 */
export function saveLibrary(file, products, { expectHash = null, retries = 5, actor = null } = {}) {
  const text = serializeLibrary(products)

  const currentHash = fs.existsSync(file) ? hashText(fs.readFileSync(file, 'utf8')) : null
  if (currentHash !== expectHash) {
    const err = new Error(
      `库文件已被他人修改，拒绝覆盖：${path.basename(path.dirname(file))}/products.json\n` +
        `  载入时指纹：${expectHash ?? '（文件不存在）'}\n` +
        `  磁盘现指纹：${currentHash ?? '（文件不存在）'}\n` +
        `  同一品类的写入必须串行：请重新载入（重跑命令）后再试。`,
    )
    err.code = 'ELIBRARYCONFLICT'
    throw err
  }

  let lastError = null
  for (let i = 0; i <= retries; i++) {
    try {
      fs.mkdirSync(path.dirname(file), { recursive: true })
      fs.writeFileSync(file, text, 'utf8')
      if (actor) journalBatchWrite(file, products, actor)
      return text
    } catch (e) {
      if (!RETRYABLE.has(e.code)) throw e
      lastError = e
      if (i < retries) sleepSync(40 * 2 ** i)
    }
  }
  throw lastError
}
