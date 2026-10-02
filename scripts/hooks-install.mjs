#!/usr/bin/env node
/**
 * 启用随仓库分发的 git 钩子（方案 P0-8）：`npm run hooks:install`
 *
 * 为什么需要这一步：`.git/hooks/` 不被 git 跟踪，钩子必须放在 `scripts/hooks/`
 * 才能随仓库分发；但 git 找到钩子后**只认带执行位的文件**，没有执行位会**静默跳过**
 * （不报错、也不提示）——这是最容易被忽略的失效方式，所以安装脚本必须同时置位。
 *
 * 每个 clone / worktree 各需启用一次（`core.hooksPath` 是本机配置，不入库）。
 */
import { execFileSync } from 'node:child_process'
import fs from 'node:fs'
import path from 'node:path'
import process from 'node:process'

const ROOT = path.resolve(import.meta.dirname, '..')
const HOOKS_REL = 'scripts/hooks'
const HOOKS = path.join(ROOT, HOOKS_REL)

if (!fs.existsSync(HOOKS)) {
  console.error(`✗ 找不到 ${HOOKS_REL}/`)
  process.exit(1)
}

function git(argv, opts = {}) {
  return execFileSync('git', argv, { cwd: ROOT, encoding: 'utf8', ...opts }).trim()
}

// 1) 置执行位（git 的 find_hook() 会跳过没有执行位的钩子，且不报错）
const hooks = fs.readdirSync(HOOKS)
for (const f of hooks) fs.chmodSync(path.join(HOOKS, f), 0o755)
console.log(`· 已给 ${hooks.length} 个钩子置执行位：${hooks.join('、')}`)

// 2) 若钩子已入库，把执行位记进索引 —— 否则新克隆 / 新 worktree 检出时又变回不可执行
try {
  const tracked = git(['ls-files', HOOKS_REL]).split('\n').filter(Boolean)
  if (tracked.length) {
    execFileSync('git', ['update-index', '--chmod=+x', ...tracked], { cwd: ROOT, stdio: 'inherit' })
    console.log(`· 已把执行位记入索引：${tracked.join('、')}`)
  } else {
    console.log(`· 提示：${HOOKS_REL}/ 尚未入库，先 git add 再重跑本命令可把执行位固化`)
  }
} catch {
  console.log('· 提示：未能写入索引（不影响本机使用）')
}

// 3) 让 git 使用仓库内的钩子目录
git(['config', 'core.hooksPath', HOOKS_REL])
console.log(`✓ 已启用分区流转提交闸门：core.hooksPath = ${HOOKS_REL}`)
console.log('')
console.log('  自检（应被拒绝）：')
console.log('    git add data/_intake/<品类>/<id>.json && git commit -m "data: 随手提交"')
console.log('  边界：合并提交不检查；--no-verify 可绕过；真正的门是 PR 上的 CI。')
