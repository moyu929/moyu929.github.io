# 交接文档：家电横评站点

> **本文档是「当前状态索引」，只写现行有效的信息。** 接手项目先读它，再读两份规范：
> [AGENTS.md](AGENTS.md)（协作与数据流转规则）、[skills/appliance-data-curation/SKILL.md](skills/appliance-data-curation/SKILL.md)（数据收录与核验规范）。
> 升级改造的设计与评审过程（2026-10，6 轮）已浓缩为 [docs/archive/升级决策纪要_2026-10.md](docs/archive/升级决策纪要_2026-10.md)。
> 历史沿革（已被取代的旧口径）集中在第 6 节；历史审核报告在 `docs/audit/`（**不删不改**，其结论可能已过时）。

## 0. 当前状态（2026-10-04）

| 指标 | 数值 |
| --- | --- |
| 一级品类 / 小品类 | 6 / 40 |
| 产品 | **1055 款**（2026-10-03 起仅收录家用电器，商用/工业机型已剔除） |
| 品牌 | 57（小米 418 · 其他 637） |
| 产品图 | 369 张（≤320px WebP，共约 0.9MB） |
| 核查状态 | 已核验（多源）160 · 已核验（官方商城）199 · 已核验（第三方）629 · 待核验 67 |
| 校验 | `npm run check` 全绿；`npm run selftest` 60 项断言全绿 |

6 个一级品类分组与 40 个小品类：

| 一级品类 | 小品类 |
| --- | --- |
| 环境与空气 | 空气净化器 / 空调 / 除湿机 / 加湿器 / 电风扇 / 电暖器 |
| 厨房大家电 | 冰箱 / 洗碗机 / 洗衣机 |
| 厨房小家电 | 电饭煲 / 电压力锅 / 微波炉 / 空气炸锅 / 电磁炉 / 破壁机 / 咖啡机 / 电水壶 / 电蒸锅 / 即热饮水机 / 净水器 |
| 清洁电器 | 扫地机器人 / 无线吸尘器 / 洗地机 / 除螨仪 |
| 个护健康 | 吹风机 / 剃须刀 / 电动牙刷 / 理发器 / 足浴器 / 筋膜枪 / 体脂秤 |
| 居家智能 | 智能门锁 / 智能摄像机 / 电视 / 投影仪 / 智能音箱 / 热水器 / 浴霸 / 晾衣机 / 挂烫机 |

### 0.1 协作方式（动手前必读）

- **数据流程——分区流转**：产品按状态放在四个物理分区（**文件位置即状态**）：
  `data/_draft/` 草稿 → `data/_intake/` 待入库 → `data/_review/` 修正 → `data/<品类>/products.json` 已入库。
  命令：`npm run flow:submit / claim / recall / publish / return / drop`；库文件**唯一写入规范**是
  `scripts/lib/library-io.mjs`（Node）与 `scripts/lib/library_io.py`（Python）。**规则详见 AGENTS.md §3。**
- **改动流程——分支 + PR**：`main` 已启用分支保护（**直推会被服务器拒绝**）；**合并 PR 才部署**；
  合并由**编排方代理**（常规批次 CI 绿即合；剔除 / 口径类先呈报用户）。**规则详见 AGENTS.md §3.6。**
- **多工作者**：每个会话一个独立 worktree（`wt-collect-<NN>` / `wt-review-<NN>` / `wt-orch-<NN>`），
  同一品类同一时刻至多 1 采集 + 1 修正；**开工先跑 `npm run flow:workers`** 看谁占了哪个工作台。
- **提交纪律**：流转命令跑完当场提交（数据提交带 `flow` 标记）；推送前 `npm run check`。

### 0.2 常用命令

| 命令 | 用途 |
| --- | --- |
| `npm run dev` / `build` / `preview` | 本地开发 / 生产构建（含类型检查）/ 预览产物 |
| `npm run flow:status` | 四个分区现状 + 最近流转（动手前先跑） |
| `npm run flow:workers` | 工作者视图：谁在哪个工作台、改动涉及哪些目录 |
| `npm run flow:log [-n N] [--batch <id>]` | 流转日志（可按批次回查） |
| `npm run validate` / `lint` / `selftest` | 数据校验 / 一致性检查 / 流转工具自检（60 项） |
| `npm run check` | 推送前总检 = validate + lint + selftest + audit:check（**不含 typecheck/build**——那两项需依赖、只在 CI 把关） |
| `npm run hooks:install` | 启用提交闸门（每个 clone / worktree 各一次） |

采集流水线（`mi:*` / `miot:*` / `pconline:specs` / `img:webp`）见 SKILL.md「采集流水线」，此处不重复。

### 0.3 部署

- 合并 PR → `main` 更新 → `.github/workflows/deploy.yml`（validate → build → Pages）自动部署。
- PR 上自动跑 CI（`.github/workflows/ci.yml`：validate / lint / selftest / typecheck / build）。
- 线上 <https://moyu929.github.io>；Pages Source 已配置为 GitHub Actions。

---

## 1. 项目速览

- 技术栈：Vite + Vue 3 + TypeScript 静态站（vue-router）。
- **数据全靠手写 JSON**，页面（卡片 / 对比表 / 筛选 / 排序 / 顶部统计）全部 schema 驱动，
  **新增品类 / 字段不需要写任何 Vue 代码**。
- `src/data.ts` 用 `import.meta.glob('../data/*/schema.json')` 自动发现品类。

目录约定：

```
data/categories.json                 品类清单（两层：一级品类 → 小品类，首页入口）
data/<category-id>/
  ├─ schema.json                     字段定义：显示位置、单位、能否排序
  └─ products.json                   已入库区：线上唯一数据源（不可直接手改，只能经 flow:publish）
data/_draft/<品类>/<id>.json         草稿区：收录中的半成品（采集方工作台，不入 git）
data/_intake/<品类>/<id>.json        待入库区：收录完成、等待认领（交接队列）
data/_review/<品类>/<id>.json        修正区：审核修正中（审核方工作台）
data/_flow/journal.jsonl            流转日志（append-only 共享事实）
data/_sources/                      采集源清单：images.json / patches/ / provenance.json 等（见 _sources/README）
public/images/<category-id>/         产品图，文件名 = 产品 id（不随分区流转）
scripts/flow.mjs                     分区流转工具
scripts/lib/library-io.mjs           库文件唯一写入规范（另一实现 library_io.py）
scripts/lib/product-check.mjs        校验规则库（validate 与 flow 复用）
```

字段属性（`card`/`compare`/`sortable`/`stat`/`tagVariant`）与 `groupBy`/`facets` 细节见 [README.md](README.md)。

---

## 2. 收录范围与关键规范（摘要，细节以 SKILL.md 为准）

1. **多品牌横评**：小米/米家与主流家电品牌**同等收录、同等展示**。分组维度是**品牌**，不出现「小米 vs 竞品」的说法。
   - **仅收录家用电器，商用/工业机型一律排除**（2026-10-03 用户裁决；判据见 SKILL.md）。
   - 不收海外版/港台版、白牌/非主流生态链品牌。每款必须有 `brand` 字段（按**零售商品名牌**归类，不按代工方）。
2. 同一硬件不同固件改版视为**同一型号**；实质性迭代（型号代码 / 性能 / 能效 / 结构变化）才拆版本。
3. **版本后缀命名**：`name` 用「（YYYY款）」结尾；年份查不到用「新款 / 旧款」。不得因促销 / 颜色 / 固件拆分。
4. 来源优先级：**官方** > **权威第三方**（需两处印证）> **一般媒体（仅印证，不得单独定值）** > 仅作交叉印证。
5. **禁止编造 / 估算**：查不到写 `"查不到"` 或 `"—"`；不换算、不补零（校验提示「排序沉底」属已知）。
6. **额定 vs 实测双口径**：两者都有时拆两列，不可混用。
7. 去重先按**型号代码**再按名称；海外版判据 = 大陆官方渠道检索不到 + 可确认面向海外/港台。
8. **竞品副分组**：竞品要落进 `schema.facets[0]`；没有分类依据的保持「未归类」，不猜。

---

## 3. 数据来源与采集方式（已固化进仓库）

流水线在 `scripts/mi-store.mjs`（另有等价 Python 枚举入口 `mi-store-enumerate.py`），用法见 SKILL.md：

```bash
npm run mi:enumerate -- <关键词...>      # 枚举在售商品（需 Playwright）
npm run mi:detail -- <productId...>      # 官方商品详情（纯 HTTP）
npm run mi:specs -- <规格页URL...>       # 官方规格页 → 参数表（纯 HTTP）
npm run mi:images                        # 按 images.json 下载官方原图到 _cache（不入库）
npm run img:webp                         # 原图 → ≤320px WebP 写入 public/images/ 并回写 img 字段
npm run mi:apply -- data/_sources/patches/xxx.json   # 写字段补丁
```

- 缓存 `data/_cache/`（gitignore）；图片清单与补丁在 `data/_sources/`。
- 两条踩过的坑：① **回写必须锚定对象边界**（`mi:apply` 会断言 id 与目标字段之间不出现 `"id"`，越界报错）；
  ② **枚举必须按容器限定**（只取 `.goods-list .goods-item`，否则混入手机平板等噪音）。

---

## 4. 未完成（后续可做）

1. **零售型号代码（`model_code`）大量缺失**——逐款查官方规格页 / 说明书 PDF / 铭牌补全。
   ⚠ `miot_model`（协议型号）**不能替代**零售型号代码。
2. **部分产品无图**——多为已停产型号与竞品（`img: null`），符合规范；有官方图时按流水线补。
3. **缺失技术字段按品类分批补**——每项登记来源到 `data/_sources/provenance.json`；补前
   `npm run flow:status --category <品类>` 确认没有在修产品（schema 是共享基础设施）。
4. **竞品副分组仍有「未归类」条目**——`npm run flow:status --unclassified` 查看；没有依据的不猜。
5. **无 `verify_url` 的已核验记录需补参数级溯源**——部分 `verify_source` 只证明图片来源，不证明参数来源。
6. **竞品 provenance 未逐条登记**（`data/_sources/provenance.json`）。
7. **价格口径未统一**：`official_price`（采集时点官方商城价）与 `ref_price`（第三方报价）语义不同，不可混用
   （排序与统计已用 `priceOf()` 回退）。
8. **《型号漏收录初筛报告》**里的候选（15kg 分区洗烘、430L/610L/216L 冰箱、蓝氧智投等）未获官方目录证实，
   待查历史发布材料或说明书才能定论。

---

## 5. 已知坑与环境问题

1. **别只看「校验通过」**：`validate` 会反向检查 `data/` 下有 `products.json` 的目录是否都登记进了
   `categories.json`——但只遍历已登记的品类，新品类忘登记会报错而不是静默跳过。
2. **数值字段与 `"—"`**：schema 声明 `number` 却填 `"—"` 的产品排序沉底，属预期提示，不必强修。
3. **第三方同义叫法会静默匹配落空**（找资料 / 写映射表时注意）：咖啡机第三方写「意大利式」、
   电暖器油汀写「欧式快热炉 / 铝片散热式」、嵌入式空调写「风管机 / 天花机」等——对照表见 SKILL.md。
4. **小米商城官方 API 必须带 Referer**：`api2.order.mi.com/product/view` 不带 `Referer: https://www.mi.com/`
   会返回「请求来源不合法」。它返回 `class_parameters`（官方额定参数）与 `buy_option`（判断某「型号」是否
   只是同一 product_id 下的规格选项）——比官网页面好用得多。
5. **型号核实不能只比对型号字符串**：把型号页的制冷量 / 风量 / 噪音等与库内数值**逐项比对**，全等才判确认
   （太平洋与 ZOL 都有录入错误）。
6. **小米商城站内搜索接口已失效**：`www.mi.com/search?keyword=` 返回的是全站推荐位，不能用它找 `product_id`。
7. **miot-spec 类参考站**：有固件重复条目且收录不全，**只用于交叉印证，不能当准绳**（其缺失不能否定型号存在）。
8. **gh 环境自检**：报 command not found → 进程启动早于安装，重启客户端即可（临时可用全路径）；
   报未登录 → 凭据在 Windows 凭据管理器、应自动可用。详见 AGENTS.md §3.6。
9. **worktree 沙箱**：worktree 目录必须在客户端「允许写入」范围内，否则写入 / 删除会被拦。详见 AGENTS.md §3.6。
10. **写大文件后回读校验**：编辑器偶发截断；写完大 JSON 后立刻 `Read` 回读长度与结尾，勤提交。

---

## 6. 口径变更历史（旧口径已被取代）

历史报告不改写，但下列口径已变，新工作一律按现行版执行：

| 旧口径 | 现行口径 | 变更时间 |
| --- | --- | --- |
| 「只收录米家/小米（小米自有品牌），不收其他品牌」 | 多品牌同等收录同等展示，`groupBy` 为品牌 | 2026-10-01 |
| 「品类维度末位放一个『竞品』分组」 | 竞品进品牌主分组；品类维度降为 `facets` 副分组 | 2026-10-01 |
| `verify_status` 只有三档（多源 / 官方商城 / 待核验） | 四档，增 `已核验（第三方）` | 2026-10-01 |
| 「严禁用媒体参数补齐」 | 媒体**可作印证**（两家独立媒体一致），但不能单独定值 | 2026-10-01 |
| 「直接编辑 `products.json` 追加产品」 | 走分区流转，只有 `flow:publish` 能写已入库区 | 2026-10-02 |
| 「审核前拍快照锁冻结范围」 | 快照锁降级为结构冻结工具；日常互斥由分区天然保证 | 2026-10-02 |
| 图片 ≤640px JPEG | ≤320px WebP（卡片展示位 96×112 CSS px，DPR 3 只需 288px） | 2026-10-01 |
| `tier` 等值必须在 `groupBy.order` 里 | 品类维度值在 `facets[0].order` 里；`groupBy` 固定 `brand` | 2026-10-01 |
| `brand` 按代工方划分 | `brand` 按**零售商品名牌**划分，协议厂商前缀只作溯源线索 | 2026-10-01 |
| 洗地机「吸力/真空度」因单位混乱不收录 | 已按官方 `class_parameters` 核实并回填 | 2026-10-01 |
| `categories.json` 是扁平数组 | 两层结构（一级品类 → `categories` 数组） | 2026-10-01 |
| 「改动直接提交 `main`，推送即部署」 | **分支 + PR**，合并由编排方代理；直推 `main` 被服务器拒绝 | 2026-10-03 |
| 「单修正方（B 唯一操作者）」 | **多工作者并行**：每人一个 worktree，品类为分配单元 | 2026-10-03 |
| 商用 / 工业机型与家用机型同收 | **仅收录家用电器**（工业除湿机、商用冷柜、工业吸尘机等已剔除） | 2026-10-03 |

---

## 7. 参考

- 协作规范：[AGENTS.md](AGENTS.md)（§3 分区流转 / §3.6 分支、多工作者、合并规则）
- 数据规范：[skills/appliance-data-curation/SKILL.md](skills/appliance-data-curation/SKILL.md)
- 设计过程纪要：[docs/archive/升级决策纪要_2026-10.md](docs/archive/升级决策纪要_2026-10.md)
- 历史审核报告：`docs/audit/`（不删不改；结论可能过时，阅读注意口径差异）
- 工具：[scripts/flow.mjs](scripts/flow.mjs)、[scripts/lib/](scripts/lib/)、[scripts/validate-data.mjs](scripts/validate-data.mjs)