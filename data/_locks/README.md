# 审核快照锁（已降级为结构冻结工具）

> **2026-10-02 起**：产品级的日常互斥改由「分区流转协议」承担（数据按状态放在
> `_draft` / `_intake` / `_review` / `products.json` 四个物理分区，见 [AGENTS.md](../../AGENTS.md)）。
> 本目录的快照锁不再用于日常审核，仅在**全库结构变更**（schema 大改、批量迁移、脚本全量重写）
> 或**发版验收**前使用；历史快照保留，可用 `audit:list` / `audit:diff` 查询。

本目录存放**审核快照**，用于全库结构变更期间的互斥：在开始变更前把范围
拍成快照，范围内的产品即被冻结，**在快照被 `release` 之前任何一方都不得改动其字段**。

规则与完整流程见仓库根目录 [AGENTS.md](../../AGENTS.md)。

```bash
npm run audit:snapshot -- --label "空气净化器验收" --by agent-b --category air-purifier
npm run audit:status                  # 动手前先查
npm run audit:check                   # 事后查有没有人越界改过
npm run audit:release -- <快照id> --note "审核完成"
```

## 快照文件长什么样

`<YYYY-MM-DD>-<时间戳>-<标签>.json`：

- `scope.keys`：冻结的产品清单（`品类/产品id`）
- `hashes`：快照时刻每款产品的**内容指纹**（范围 ≤150 款时含字段级指纹，用于定位改了哪个字段）
- `status`：`frozen` / `released`；解除时若发现冻结期内有改动，会记进 `violationsAtRelease`

## 注意

- 快照文件**要入库**：它是两个 Agent 之间的共享状态，不入库对方就看不到冻结。
- 不要在快照存在期间手工修改产品数据；确有必须改的理由，先让用户/审核方
  `release`（并在 `--note` 里写明原因），再动数据。
- 冻结的粒度是**单款产品**而不是整个 `products.json`，这样审核期间仍可以往同一品类里**新增**型号。
