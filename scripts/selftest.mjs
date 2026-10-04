#!/usr/bin/env node
/**
 * 流转工具自检（`npm run selftest`）
 * ------------------------------------------------------------------
 * 在 `.flow-test/` 里搭一套**隔离的**数据副本（FLOW_DATA_DIR 指向它），
 * 把方案 P0 各条的验收标准跑成断言。真实 data/ 不会被触碰。
 *
 * 之所以做成常驻脚本而不是一次性脚本：它是 P0-3/4/5/6/10 的验收证据，
 * 也是后续改 flow 时的回归防线（回调 diff 的人可以一条命令复现结论）。
 *
 * 用法：
 *   npm run selftest          跑全部
 *   npm run selftest -- -v    打印每条子命令的原始输出
 */
import { execFileSync } from 'node:child_process'
import fs from 'node:fs'
import path from 'node:path'
import process from 'node:process'
import { loadLibrary, saveLibrary, serializeLibrary } from './lib/library-io.mjs'

const ROOT = path.resolve(import.meta.dirname, '..')
const TMP = path.join(ROOT, '.flow-test')
const DATA = path.join(TMP, 'data')
const REL_DATA = path.relative(ROOT, DATA).split(path.sep).join('/')
const VERBOSE = process.argv.includes('-v') || process.argv.includes('--verbose')

const FLOW = path.join(ROOT, 'scripts', 'flow.mjs')

// ---------------------------------------------------------------- 测试脚手架

let passed = 0
const failures = []

function check(name, cond, detail = '') {
  if (cond) {
    passed++
    console.log(`  ✓ ${name}`)
  } else {
    failures.push(`${name}${detail ? ` —— ${detail}` : ''}`)
    console.log(`  ✗ ${name}${detail ? ` —— ${detail}` : ''}`)
  }
}

function run(args, { expectFail = false } = {}) {
  let out = ''
  let code = 0
  try {
    out = execFileSync(process.execPath, [FLOW, ...args], {
      env: { ...process.env, FLOW_DATA_DIR: REL_DATA },
      encoding: 'utf8',
      stdio: ['ignore', 'pipe', 'pipe'],
    })
  } catch (e) {
    out = `${e.stdout ?? ''}${e.stderr ?? ''}`
    code = e.status ?? 1
  }
  if (VERBOSE) console.log(`\n$ flow ${args.join(' ')}  [exit ${code}]\n${out.trimEnd()}`)
  if (expectFail && code === 0) throw new Error(`预期失败但成功了：flow ${args.join(' ')}\n${out}`)
  return { code, out }
}

const zonePath = (zone, key) => path.join(DATA, `_${zone}`, ...key.split('/')) + '.json'
const libPath = (key) => path.join(DATA, key.split('/')[0], 'products.json')
const exists = (p) => fs.existsSync(p)
const readJson = (p) => JSON.parse(fs.readFileSync(p, 'utf8'))
const writeJson = (p, v) => {
  fs.mkdirSync(path.dirname(p), { recursive: true })
  fs.writeFileSync(p, `${JSON.stringify(v, null, 2)}\n`, 'utf8')
}

// ---------------------------------------------------------------- 测试夹具

const mkSchema = () => ({
  imageBase: 'images/testcat',
  groupBy: { key: 'brand', label: '品牌', order: ['小米', '美的'], colors: {} },
  facets: [{ key: 'tier', label: '档位', order: ['旗舰', '入门', '未归类'], colors: {} }],
  searchFields: ['name', 'brand'],
  primaryMetric: 'official_price',
  fields: [
    { key: 'name', label: '型号', type: 'text' },
    { key: 'brand', label: '品牌', type: 'text' },
    { key: 'tier', label: '档位', type: 'text' },
    { key: 'official_price', label: '官方价', type: 'number', prefix: '¥', sortable: true, stat: true },
    { key: 'verify_status', label: '核查状态', type: 'text' },
    { key: 'verify_date', label: '核查时间', type: 'text' },
    { key: 'verify_source', label: '来源', type: 'tags' },
    { key: 'verify_url', label: '来源链接', type: 'text' },
    { key: 'change_log', label: '修改记录', type: 'text' },
    { key: 'updated_at', label: '更新', type: 'text' },
  ],
  guide: '',
})

const mkProduct = (id, over = {}) => ({
  id,
  img: null,
  name: `测试${id}`,
  brand: '小米',
  tier: '旗舰',
  official_price: 999,
  verify_status: '已核验（官方商城）',
  verify_date: '2026-10-03',
  verify_source: ['小米商城'],
  verify_url: 'https://example.com',
  change_log: '2026-10-03 建条：自检夹具',
  updated_at: '2026-10-03',
  ...over,
})

function setupFixture() {
  fs.rmSync(TMP, { recursive: true, force: true })
  fs.mkdirSync(DATA, { recursive: true })
  fs.writeFileSync(
    path.join(DATA, 'categories.json'),
    `${JSON.stringify([{ id: 'grp', name: '测试组', icon: '01', description: '', categories: [{ id: 'testcat', name: '测试品类', icon: '', description: '' }] }], null, 2)}\n`,
    'utf8',
  )
  writeJson(path.join(DATA, 'testcat', 'schema.json'), mkSchema())
  writeJson(path.join(DATA, 'testcat', 'products.json'), [mkProduct('lib1'), mkProduct('lib2')])
  fs.mkdirSync(path.join(DATA, '_flow'), { recursive: true })
  fs.writeFileSync(path.join(DATA, '_flow', 'journal.jsonl'), '', 'utf8')
}

// ---------------------------------------------------------------- 各组测试

function tSubmit() {
  console.log('\n[P0-4] 提交：批量汇总 + 幂等重跑')
  writeJson(zonePath('draft', 'testcat/a1'), mkProduct('a1'))
  const r1 = run(['submit', 'testcat/a1', '--by', 'collect-x'])
  check('草稿区 → 待入库区', exists(zonePath('intake', 'testcat/a1')) && !exists(zonePath('draft', 'testcat/a1')))
  check('打印批次汇总', /批次 \w+（submit）：共 1 项 —— 成功 1/.test(r1.out), r1.out.slice(-200))
  const batch = r1.out.match(/批次 (\w+)（submit）/)?.[1]
  check('journal 记了 batch id', Boolean(batch) && fs.readFileSync(path.join(DATA, '_flow', 'journal.jsonl'), 'utf8').includes(batch))

  const r2 = run(['submit', 'testcat/a1', '--by', 'collect-x'])
  check('重跑报告「已是目标态」而非报错', r2.code === 0 && /已是目标态 1/.test(r2.out), r2.out.slice(-200))

  writeJson(zonePath('draft', 'testcat/bad'), mkProduct('bad', { brand: '不在 order 里的品牌' }))
  const r3 = run(['submit', 'testcat/bad', '--by', 'collect-x'], { expectFail: true })
  check('校验不过的数据出不了草稿区', r3.code === 1 && exists(zonePath('draft', 'testcat/bad')))
}

function tClaim() {
  console.log('\n[P0-6] 认领：来源可见化 + 自采自审警告 + 按提交人批量')
  const r1 = run(['claim', 'testcat/a1', '--by', 'reviewer'])
  check('待入库区 → 修正区', exists(zonePath('review', 'testcat/a1')))
  check('打印提交人', /提交人 collect-x/.test(r1.out), r1.out.slice(-300))
  check('journal 记 submitActor', /"submitActor":"collect-x"/.test(fs.readFileSync(path.join(DATA, '_flow', 'journal.jsonl'), 'utf8')))

  writeJson(zonePath('draft', 'testcat/a2'), mkProduct('a2'))
  run(['submit', 'testcat/a2', '--by', 'reviewer'])
  const r2 = run(['claim', 'testcat/a2', '--by', 'reviewer'])
  check('自己提交自己认领 → 警告', /你自己提交的/.test(r2.out), r2.out.slice(-300))
  check('journal 记 selfReview', /"selfReview":true/.test(fs.readFileSync(path.join(DATA, '_flow', 'journal.jsonl'), 'utf8')))

  writeJson(zonePath('draft', 'testcat/a3'), mkProduct('a3'))
  run(['submit', 'testcat/a3', '--by', 'collect-y'])
  const r3 = run(['claim', '--from', 'collect-y', '--by', 'reviewer'])
  check('--from 按提交人批量认领', exists(zonePath('review', 'testcat/a3')) && /按提交人认领：collect-y/.test(r3.out))

  const r4 = run(['claim', '--from', 'nobody-here', '--by', 'reviewer'], { expectFail: true })
  check('无可认领时报错退出', r4.code === 1)

  // 多修正方防双领占位（`.claiming` 原子创建：同一文件任一时刻只有一个认领者）
  writeJson(zonePath('draft', 'testcat/a4'), mkProduct('a4'))
  run(['submit', 'testcat/a4', '--by', 'collect-z'])
  const a4Sentinel = `${zonePath('review', 'testcat/a4')}.claiming`
  fs.mkdirSync(path.dirname(a4Sentinel), { recursive: true })
  fs.writeFileSync(a4Sentinel, 'reviewer-2\n', { flag: 'wx' }) // 模拟另一个修正方正在认领
  const r5 = run(['claim', 'testcat/a4', '--by', 'reviewer'], { expectFail: true })
  check('占位存在时认领被拒（防双领）', r5.code === 1 && /已被其他修正方认领/.test(r5.out), r5.out.slice(-300))
  check('被拒时数据仍在待入库区', exists(zonePath('intake', 'testcat/a4')))
  fs.rmSync(a4Sentinel, { force: true }) // 模拟对方放弃（或残留被人工清理）
  const r6 = run(['claim', 'testcat/a4', '--by', 'reviewer'])
  check('占位清除后可正常认领', r6.code === 0 && exists(zonePath('review', 'testcat/a4')))
  check('认领成功后占位被清理（不泄漏）', !exists(a4Sentinel))
  const r7 = run(['claim', 'testcat/a4', '--by', 'reviewer-2'])
  check('已认领后重复认领 → 幂等跳过，并显示认领人', r7.code === 0 && /已在修正区（认领人：reviewer @/.test(r7.out), r7.out.slice(-200))
}

function tPublish() {
  console.log('\n[P0-3/4] 入库：行级状态幂等 + 空目录清理')
  const r1 = run(['publish', 'testcat/a1', '--by', 'reviewer'])
  check('修正区 → 已入库区', r1.code === 0 && !exists(zonePath('review', 'testcat/a1')))
  check('库内出现该产品', readJson(path.join(DATA, 'testcat', 'products.json')).some((p) => p.id === 'a1'))
  check('空的分区品类目录被清掉（P0-10）', !exists(path.join(DATA, '_review', 'testcat')) || fs.readdirSync(path.join(DATA, '_review', 'testcat')).length > 0)

  const r2 = run(['publish', 'testcat/a1', '--by', 'reviewer'])
  check('重跑报告「已是目标态」（断点续跑）', r2.code === 0 && /已是目标态 1/.test(r2.out), r2.out.slice(-200))

  // 内容相同也跳过
  writeJson(zonePath('review', 'testcat/lib1'), readJson(path.join(DATA, 'testcat', 'products.json')).find((p) => p.id === 'lib1'))
  const r3 = run(['publish', 'testcat/lib1', '--by', 'reviewer'])
  check('内容与库内一致 → 跳过入库', /已完全一致/.test(r3.out), r3.out.slice(-200))
  fs.rmSync(zonePath('review', 'testcat/lib1'))
}

function tLegacy() {
  console.log('\n[P0-5] 历史遗留问题与「本批写坏」分离')
  // 往库里塞一条历史遗留的坏数据（品牌值不在 groupBy.order 里）
  const lib = readJson(path.join(DATA, 'testcat', 'products.json'))
  lib.push(mkProduct('legacy_bad', { brand: '历史遗留的错品牌' }))
  writeJson(path.join(DATA, 'testcat', 'products.json'), lib)

  writeJson(zonePath('review', 'testcat/a2'), mkProduct('a2'))
  const r1 = run(['publish', 'testcat/a2', '--by', 'reviewer'], { expectFail: true })
  check('本批数据本身入库成功（未被历史问题回滚）', readJson(path.join(DATA, 'testcat', 'products.json')).some((p) => p.id === 'a2'))
  check('明确报出「历史遗留 + 不是你造成的」', /历史遗留/.test(r1.out) && /不是你本批造成的/.test(r1.out), r1.out.slice(-400))
  check('默认阻塞（退出码非零）', r1.code === 1)

  writeJson(zonePath('review', 'testcat/a3'), mkProduct('a3'))
  const r2 = run(['publish', 'testcat/a3', '--by', 'reviewer', '--skip-legacy'])
  check('--skip-legacy 可放行', r2.code === 0, r2.out.slice(-200))

  // 清掉历史坏数据
  const clean = readJson(path.join(DATA, 'testcat', 'products.json')).filter((p) => p.id !== 'legacy_bad')
  writeJson(path.join(DATA, 'testcat', 'products.json'), clean)
}

async function tConflict() {
  console.log('\n[P0-3] 指纹守卫：拒绝覆盖别人刚改过的库')
  const { loadLibrary, saveLibrary } = await import('./lib/library-io.mjs')
  const file = path.join(DATA, 'testcat', 'products.json')
  const lib = loadLibrary(file)
  // 模拟"载入之后、写回之前，别人改了库"
  fs.writeFileSync(file, `${JSON.stringify(lib.products.concat([mkProduct('intruder')]))}\n`, 'utf8')
  let code = null
  const t0 = Date.now()
  try {
    saveLibrary(file, lib.products, { expectHash: lib.hash })
  } catch (e) {
    code = e.code
  }
  const elapsed = Date.now() - t0
  check('指纹不一致时抛 ELIBRARYCONFLICT', code === 'ELIBRARYCONFLICT', String(code))
  check('冲突时不做任何覆盖（intruder 还在）', readJson(file).some((p) => p.id === 'intruder'))
  // 冲突路径绝不能进重试：重试会消耗 40+80+160+320+640ms，明显超过这个阈值
  check('冲突立刻失败、不进重试路径', elapsed < 500, `耗时 ${elapsed}ms`)
  fs.writeFileSync(file, `${JSON.stringify(lib.products)}\n`, 'utf8')
}

function tRecallReturnDrop() {
  console.log('\n[P0-6] recall / return / withdraw / drop 与日志回查')
  const r1 = run(['recall', 'testcat/lib1', '--reason', '自检召回', '--by', 'reviewer'])
  check('召回后库内移除、修正区出现', r1.code === 0 && !readJson(path.join(DATA, 'testcat', 'products.json')).some((p) => p.id === 'lib1') && exists(zonePath('review', 'testcat/lib1')))
  const r2 = run(['recall', 'testcat/lib1', '--reason', '重复召回', '--by', 'reviewer'])
  check('重复召回报告「已是目标态」', /已是目标态 1/.test(r2.out), r2.out.slice(-200))

  const r3 = run(['drop', 'testcat/lib1', '--reason', '自检剔除', '--by', 'reviewer'])
  check('drop 后修正区文件消失', r3.code === 0 && !exists(zonePath('review', 'testcat/lib1')))

  writeJson(zonePath('draft', 'testcat/w1'), mkProduct('w1'))
  run(['submit', 'testcat/w1', '--by', 'collect-x'])
  const r4 = run(['withdraw', 'testcat/w1', '--by', 'collect-x'])
  check('撤回：待入库区 → 草稿区', r4.code === 0 && exists(zonePath('draft', 'testcat/w1')))
  run(['submit', 'testcat/w1', '--by', 'collect-x'])
  const r5 = run(['return', 'testcat/w1', '--reason', '自检退回', '--by', 'reviewer'])
  check('退回：待入库区 → 草稿区', r5.code === 0 && exists(zonePath('draft', 'testcat/w1')))

  const batch = r1.out.match(/批次 (\w+)（recall）/)?.[1]
  const r6 = run(['log', '--batch', batch])
  check('flow:log --batch 可回查本批', r6.out.includes('testcat/lib1'), r6.out.slice(-300))
}

function tRecallRestoresPosition() {
  console.log('\n[P1-2 配套] 召回后入库放回原位（否则尾部追加会与别的分支撞成同一处冲突）')
  const file = path.join(DATA, 'testcat', 'products.json')
  const before = readJson(file)
  const indexBefore = 1
  const target = before[indexBefore]
  run(['recall', `testcat/${target.id}`, '--reason', '位置烟测', '--by', 'reviewer'])
  check('召回后库内少一款', readJson(file).length === before.length - 1 && !readJson(file).some((p) => p.id === target.id))
  run(['publish', `testcat/${target.id}`, '--by', 'reviewer'])
  const after = readJson(file)
  check(
    '重新入库回到原索引',
    after[indexBefore]?.id === target.id,
    `期望 ${target.id}，实际 ${after[indexBefore]?.id}；当前顺序 ${after.map((p) => p.id).join(',')}`,
  )
}

function tBatchTrail() {
  console.log('\n[P1-1 第三要素] 批量写库留痕（actor → journal 的 batch-write）')
  const file = path.join(DATA, 'testcat', 'products.json')
  const journalFile = path.join(DATA, '_flow', 'journal.jsonl')
  const readLines = () => fs.readFileSync(journalFile, 'utf8').split('\n').filter(Boolean)
  const before = readLines().length

  const lib = loadLibrary(file)
  saveLibrary(file, lib.products, { expectHash: lib.hash, actor: 'classify-facets.py' })
  const lines = readLines()
  check('传 actor → 追加一条留痕', lines.length === before + 1, `${before} → ${lines.length}`)
  const entry = JSON.parse(lines[lines.length - 1])
  check(
    '条目含 action/key/count/actor',
    entry.action === 'batch-write' &&
      entry.key === 'testcat/products.json' &&
      entry.count === lib.products.length &&
      entry.actor === 'classify-facets.py',
    JSON.stringify(entry),
  )

  const lib2 = loadLibrary(file)
  saveLibrary(file, lib2.products, { expectHash: lib2.hash })
  check('不传 actor → 不追加（flow:* 自有条目，避免重复记）', readLines().length === lines.length, `${lines.length} → ${readLines().length}`)

  // Python 侧实现也要能留痕（classify-facets / import-brands / shrink-images 都是 Python）
  const pyCode = [
    'import sys, json',
    `sys.path.insert(0, ${JSON.stringify(path.join(ROOT, 'scripts', 'lib'))})`,
    'import library_io as L',
    `f = ${JSON.stringify(file)}`,
    'lib = L.load(f)',
    "L.save(f, lib['products'], expect_hash=lib['hash'], actor=L.script_actor())",
  ].join('\n')
  const beforePy = readLines().length
  execFileSync('python', ['-c', pyCode], { encoding: 'utf8', env: { ...process.env, FLOW_ACTOR: 'py-tool' } })
  const afterPy = readLines()
  check('Python 侧传 actor → 同样追加留痕', afterPy.length === beforePy + 1, `${beforePy} → ${afterPy.length}`)
  const pyEntry = JSON.parse(afterPy[afterPy.length - 1])
  check(
    'Python 留痕的 actor/action/key 正确（FLOW_ACTOR 优先于脚本名）',
    pyEntry.actor === 'py-tool' && pyEntry.action === 'batch-write' && pyEntry.key === 'testcat/products.json' && /Z$/.test(pyEntry.ts),
    JSON.stringify(pyEntry),
  )
}

function tWorkers() {
  console.log('\n[多工作者] 工作者视图（flow:workers，只读）')
  const r = run(['workers'])
  check('命令可运行且列出至少一个工作台', r.code === 0 && /◆ /.test(r.out), r.out.slice(0, 300))
  check('每个工作台都显示分支与改动', /分支 /.test(r.out) && /改动 /.test(r.out))
  check('结尾说明「一人一个 worktree」的前提', /一个 worktree/.test(r.out), r.out.slice(-300))
}

function tStatusFilters() {
  console.log('\n[P0-6/7/10] status 归属视图与过滤')
  // 先放一款在待入库区，让"提交人"断言基于确定的状态（而不是靠 journal 尾部的偶然命中）
  writeJson(zonePath('draft', 'testcat/w2'), mkProduct('w2'))
  run(['submit', 'testcat/w2', '--by', 'collect-z'])
  const r1 = run(['status'])
  check('status 打印操作自证', /操作自证：数据/.test(r1.out) && /分支/.test(r1.out), r1.out.slice(0, 200))
  check('按品类计数、空品类不出现', /待入库区/.test(r1.out) && !/air-conditioner/.test(r1.out))
  check('待入库区列出提交人', /testcat\/w2（提交人 collect-z/.test(r1.out), r1.out.slice(0, 900))
  const r2 = run(['status', '--by', 'collect-z'])
  // 只在"分区现状"段里断言：后面的"最近流转"尾巴总会提到 w2，不能用来判过滤是否生效
  const zonePart = (out) => out.split('最近流转')[0]
  check('--by 过滤生效', /按提交人过滤：collect-z/.test(zonePart(r2.out)) && /testcat\/w2/.test(zonePart(r2.out)), zonePart(r2.out).slice(0, 500))
  const r3 = run(['status', '--by', 'nobody'])
  check('--by 过滤排除他人', !/testcat\/w2/.test(zonePart(r3.out)), zonePart(r3.out).slice(0, 500))
}

function tUnclassified() {
  console.log('\n[P0-6⑤] 未归类清单')
  const lib = readJson(path.join(DATA, 'testcat', 'products.json'))
  lib[0].tier = '未归类' // 小米自有 → 应只进"另有 N 款"的计数
  lib.push(mkProduct('rival1', { brand: '美的', tier: '未归类' })) // 非小米品牌 → 应进主清单
  writeJson(path.join(DATA, 'testcat', 'products.json'), lib)
  const r = run(['status', '--unclassified'])
  check('主清单列出非小米品牌未归类', /未归类产品/.test(r.out) && /testcat\/rival1/.test(r.out), r.out.slice(-400))
  check('小米自有的单独计数', /另有 1 款小米自有产品/.test(r.out), r.out.slice(-200))
}

function tPruneEmptyDirs() {
  console.log('\n[P0-10] 空目录清理')
  const zones = ['_draft', '_intake', '_review']
  let empties = 0
  for (const z of zones) {
    const base = path.join(DATA, z)
    if (!exists(base)) continue
    for (const d of fs.readdirSync(base)) {
      if (fs.readdirSync(path.join(base, d)).length === 0) empties++
    }
  }
  check('分区内无残留空目录', empties === 0, `仍有 ${empties} 个`)
}

/** 用 Python 侧的规范序列化器处理同一组对象 */
function pySerialize(objects) {
  return execFileSync('python', [path.join(ROOT, 'scripts', 'lib', 'library_io.py')], {
    input: JSON.stringify(objects),
    encoding: 'utf8',
  })
}

function tCrossLanguage() {
  console.log('\n[P1-1] 跨语言序列化一致性（Node ↔ Python 逐字节相等）')
  const samples = [
    {
      id: 'a1',
      name: '米家空气净化器 7 Pro（2026款）',
      price: 399.0,
      ratio: 0.85,
      tags: ['中文', '带"引号"', '带\n换行', '带\\反斜杠', '带/斜杠'],
      nested: { z: 1, a: [1, 2.5, true, null, ''] },
    },
    { id: 'a2', price: 1299, detail: '制表\t符与 emoji 🍳', empty: [], obj: {} },
  ]

  let pyText = null
  try {
    pyText = pySerialize(samples)
  } catch (e) {
    check('Python 侧可执行', false, e.message)
    return
  }
  check('两侧序列化逐字节相同（构造样本）', serializeLibrary(samples) === pyText, `\n  JS: ${JSON.stringify(serializeLibrary(samples))}\n  PY: ${JSON.stringify(pyText)}`)

  // 真实库文件：里面本来就有 399.0 这类整值浮点，是最有说服力的样本
  let realChecked = 0
  for (const cat of ['camera', 'shaver', 'washing-machine', 'air-conditioner']) {
    const file = path.join(ROOT, 'data', cat, 'products.json')
    if (!fs.existsSync(file)) continue
    const objects = JSON.parse(fs.readFileSync(file, 'utf8'))
    const same = serializeLibrary(objects) === pySerialize(objects)
    check(`真实库文件 ${cat}（${objects.length} 款）两侧一致`, same)
    realChecked++
  }
  check('至少校验了一个真实库文件', realChecked > 0, '没找到可用的品类文件')

  // 整值浮点确实被归一（这是消除字节漂移的关键一步）
  const floats = [{ id: 'f', price: 399.0, w: 12.0 }]
  check('整值浮点被归一为整型', !serializeLibrary(floats).includes('.0'), serializeLibrary(floats))
}

// ---------------------------------------------------------------- 入口

async function main() {
  console.log(`流转工具自检 —— 使用隔离数据副本 ${REL_DATA}（真实 data/ 不受影响）`)
  setupFixture()
  tSubmit()
  tClaim()
  tPublish()
  tLegacy()
  await tConflict()
  tRecallReturnDrop()
  tRecallRestoresPosition()
  tBatchTrail()
  tStatusFilters()
  tWorkers()
  tUnclassified()
  tPruneEmptyDirs()
  tCrossLanguage()

  console.log('\n' + '-'.repeat(60))
  if (failures.length) {
    console.error(`自检未通过：${passed} 通过 / ${failures.length} 失败`)
    for (const f of failures) console.error(`  ✗ ${f}`)
    process.exit(1)
  }
  console.log(`自检全部通过：${passed} 项断言`)
  console.log('（清理临时副本：.flow-test/）')
  fs.rmSync(TMP, { recursive: true, force: true })
}

main().catch((e) => {
  console.error(`自检异常：${e.stack ?? e.message}`)
  process.exit(1)
})
