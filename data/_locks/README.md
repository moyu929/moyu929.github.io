# 审核快照锁

本目录存放**审核快照**，用于两个 Agent 并行工作时的互斥：审核方（B）在开始审核前把审核范围
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
