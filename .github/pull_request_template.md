# 批次 PR 模板（方案 P2-6）

> 一个 PR = 一个批次（一波采集 / 一批召回修正），不是一个产品一个 PR。
> 正文里的清单可以直接粘 `npm run flow:log --batch <批次id>` 的输出。
> 合并前请确认 CI 全绿（validate / lint / selftest / typecheck / build）。

## 本批是什么

- **批次 id**：（`flow:log` 里的 `批次 xxxxxxxx`）
- **品类**：
- **产品数**：
- **动作**：采集提交 / 召回修正 / 订正稿 / 图片回补
- **把关人**：（谁做的核验）

## 来源与核验方式

<!-- 每条数据的来源优先级见 skills/appliance-data-curation/SKILL.md：
     官方 > 权威第三方（需两处印证）> 一般媒体（仅印证）。粘摘要即可。 -->

- **来源清单**：
- **`verify_status` 分布**：已核验（多源） N / 已核验（官方商城） N / 已核验（第三方） N / 待核验 N
- **放弃收录的型号及原因**：（查不到 / 海外版 / 依据不足……）

## 需要评审方注意的点

<!-- 例如：某字段两源冲突取谁、某型号疑似同机型不同 SKU、某值按异常阈值剔除 -->

- [ ]

## 自查

- [ ] `npm run check` 本地通过（validate + lint + selftest + audit:check）
- [ ] 我确认为本批的核验负责，且**未直接手改** `data/<品类>/products.json`（只经 `flow:publish`）
- [ ] 提交信息带 `flow` 标记
- [ ] 本 PR 不含 `data/_draft/**`（草稿是私有工作台，不入库；`.gitignore` 已排除，若出现在 diff 里说明被强加了）
- [ ] 若改动了 `schema.json`：**单独一个 commit**，并在下方说明影响面
