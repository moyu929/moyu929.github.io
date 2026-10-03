# .git 瘦身方案

## 现状（2026-10-01 测得）

| 阶段 | 体积 |
| --- | --- |
| 整理前 | 41.03 MiB（**几乎全是散落对象**，pack 仅 2.05 MiB） |
| 执行 `git gc` 后 | **38.66 MiB**（全部打包，仅省 2.4MB） |

打包省得少的根本原因：**JPEG/PNG/WebP 本身已压缩、不同图片之间无法差分压缩**，
所以"打包"对图片仓库几乎没有效果。要真正瘦身，只能把历史里的大对象**删掉**。

体积构成（按历史对象排序）：

- 3 × `.trae-html-share-packages/index.html.zip` ≈ **6 MB**（Trae 分享包，已不再入库）
- 旧格式产品图：640px JPEG + 早期 PNG ≈ **10~15 MB**（现已全部换成 ≤320px WebP，共 0.89MB）
- 当前产品图（WebP）0.89 MB

## 已做的事（安全，无需审批）

```bash
git gc              # 把散落对象打包；不删除任何可达数据
```

## 需要审批才能做的事（重写历史）

以下步骤会**改写提交历史**，需要所有协作者重新拉仓库，且必须**强制推送**，
因此在客户端里属于风险操作，等你在场时再执行：

```bash
# 1) 备份一份，出问题可回退
git clone --mirror . ..\repo-backup.git

# 2) 安装（任选其一）
pip install git-filter-repo        # 推荐
# 或 brew install git-filter-repo

# 3) 从全部历史中剔除大对象与大目录
git filter-repo --invert-paths \
  --path .trae-html-share-packages/ \
  --path-glob 'public/images/*.png' \
  --path-glob 'public/images/*.jpg'

# 4) 本地瘦身
git reflog expire --expire=now --all
git gc --prune=now --aggressive

# 5) 强制推送（带租约，避免覆盖他人新提交）
git push --force-with-lease origin main
```

**前置条件**：执行前请确认
① 另一个 Agent 没有未推送的改动（`git log --oneline origin/main..main` 应为空）；
② 当前没有正在进行的审核快照工作（`npm run audit:list` 里没有 `frozen`，或已 release）。

**执行后**：所有协作方需 `git fetch --all && git reset --hard origin/main`
（或重新 clone），否则本地历史会与远端分叉。

## 不做也能接受的理由

38 MB 对 GitHub Pages（软上限 1 GB，仓库建议 < 1 GB）没有实际影响，
也不影响构建与访问速度——**图片体积已经从 10MB 降到 0.89MB，那是收益的大头**。
所以这一步属于"锦上添花"，可以等你睡醒、确认另一 Agent 状态后再做。
