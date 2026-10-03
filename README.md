# 家电横评

家电参数对比静态站点，Vite + Vue 3 + TypeScript，数据经「分区流转 + 分支 PR」维护，**合并 PR 后**由 GitHub Actions 自动构建发布到 GitHub Pages。

线上地址：https://moyu929.github.io

## 当前规模

| 项 | 数值 |
| --- | ---: |
| 一级品类 / 小品类 | 6 / 40 |
| 产品 | 1055 |
| 品牌 | 57（小米 418 · 其他 637） |
| 有产品图 | 369 |
| 核查状态 | 已核验（多源）160 · 已核验（官方商城）199 · 已核验（第三方）629 · 待核验 67 |

本站是**多品牌横评**：小米/米家与主流家电品牌同等收录、同等展示，分组维度是品牌而不是「小米 vs 竞品」。
数据成熟度与待补项见 [HANDOFF.md](HANDOFF.md)。

## 本地开发

```bash
npm install
npm run dev        # 开发服务器
npm run validate   # 校验 data/ 下的 JSON（schema / 字段 / 图片存在性）
npm run lint       # 数据一致性（重复型号 / 重复产品名）
npm run selftest   # 流转工具自检（隔离副本，不碰真实数据）
npm run check      # = validate + lint + selftest + audit:check，推送前跑
npm run build      # 构建到 dist/
npm run preview    # 预览构建产物
```

> `check` 只跑不依赖 `node_modules` 的项（未 `npm install` 的 worktree 也能跑）；
> `typecheck` 与 `build` 需要依赖，**只在 CI 把关**——改了 `src/**` 或类型定义时，类型错误只会在 CI 暴露，
> 想本地提前发现就先 `npm install` 再跑 `npm run typecheck`。

## 目录结构

```
data/
├─ categories.json           品类清单（两层：一级品类 → 小品类，首页入口）
├─ air-purifier/
│  ├─ schema.json            字段定义：显示位置、单位、能否排序
│  └─ products.json          已入库区：线上唯一数据源（不可直接手改，见下方「多 Agent 并行协作」）
├─ _draft/<品类>/<id>.json    草稿区：收录中的半成品（采集方工作台）
├─ _intake/<品类>/<id>.json   待入库区：收录完成、等待认领（交接队列）
├─ _review/<品类>/<id>.json   修正区：审核修正中（审核方工作台）
├─ _flow/journal.jsonl       流转日志：谁在何时把什么搬到了哪
├─ _sources/                 采集源清单（人工维护）：images.json 图片清单、patches/ 字段补丁与出处
└─ _cache/                   抓取缓存（gitignored，不入库）
public/images/air-purifier/  产品图，文件名 = 产品 id（不随分区流转）
src/
├─ types.ts                  schema 与产品的类型定义
├─ data.ts                   品类数据懒加载
├─ format.ts                 字段值格式化
├─ useProductFilter.ts       筛选 / 排序 / 搜索 / 分组
├─ useCompare.ts             对比队列
├─ components/               卡片、工具条、对比抽屉、分组下拉
└─ views/                    首页、品类页
scripts/
├─ flow.mjs                  分区流转（submit/claim/recall/publish/return/drop）
├─ audit-lock.mjs            审核快照锁（已降级为结构冻结工具）
├─ validate-data.mjs         数据校验
├─ lib/product-check.mjs     校验规则库（validate 与 flow 复用）
├─ mi-store.mjs              小米商城采集流水线（enumerate/detail/specs/images/apply）
├─ mi-store-enumerate.py     同一流水线的 Python 版枚举入口（只装了 Python Playwright 时用）
├─ miot-spec.mjs             MIoT 型号库抓取与匹配
├─ pconline-specs.py         太平洋规格表抓取
├─ classify-facets.py        竞品副分组批量归类
├─ fetch-evidence-2.py       为未归类竞品补抓分类证据（幂等可重跑）
└─ shrink-images.py          图片转 ≤320px WebP
```

## 日常维护

### 添加一款产品

**`data/<品类>/products.json` 是已入库区，任何人都不可直接手改。** 产品数据按状态放在四个物理分区，
文件的位置就是它的状态：

```bash
npm run flow:status                          # 动手前先看各区现状
# 1. 采集方：在 data/_draft/<品类>/<id>.json 写产品（半成品，随便改）
# 2. 提交待审
npm run flow:submit -- air-purifier/7pro --by <你>
# 3. 审核方：认领 → 在 data/_review/<品类>/<id>.json 核验修正 → 入库
npm run flow:claim   -- air-purifier/7pro --by <你>
npm run flow:publish -- air-purifier/7pro --by <你>
```

每个流转命令跑完**当场提交**（含 `data/_flow/journal.jsonl` 日志）。规则见 [AGENTS.md](AGENTS.md) 第 3 节。

草稿区里的产品长这样，字段照抄同品类的其他产品即可：

```json
{
  "id": "7pro",
  "img": "7pro.webp",
  "name": "米家空气净化器 7 Pro",
  "brand": "小米",
  "tier": "旗舰",
  "official_price": 2299,
  "cadr_pm": 800,
  "verify_status": "已核验（官方商城）",
  "verify_date": "2026-10-03",
  "verify_source": ["小米商城"],
  "verify_url": "https://www.mi.com/shop/buy/detail?product_id=1230802338",
  "change_log": "2026-10-03 建条：参数取自小米商城规格页",
  "updated_at": "2026-10-03"
}
```

- `id` 必须唯一，只用字母数字和 `._-`，它同时是图片文件名与分区文件名
- **`brand` 必填**，`groupBy.key` 固定为 `brand`；品牌值必须在 `schema.groupBy.order` 里
- 品类自身的细分维度（`tier`/`type`/`series` 等）在 `schema.facets[0].order` 里，取值同样要落在其中
- 产品图放到 `public/images/<品类>/`，`img` 填文件名；暂时没图就写 `null`
- 后 6 个审核标注字段（`verify_*` / `change_log` / `updated_at`）是**提交与入库的硬性校验项**，
  `flow:submit` 与 `flow:publish` 会拒绝缺字段的数据

跑 `npm run validate` 检查数据合法性。

### 添加一个字段

在 `data/<品类>/schema.json` 的 `fields` 数组里加一项：

```json
{
  "key": "cadr_hcho",
  "label": "甲醛CADR",
  "unit": "m³/h",
  "type": "number",
  "card": "grid",
  "compare": true,
  "sortable": true
}
```

| 属性 | 说明 |
| --- | --- |
| `key` | 对应 products.json 里的键名 |
| `label` | 界面上的中文名 |
| `type` | `text` / `number` / `tags` |
| `unit` | 单位，追加在值后面 |
| `prefix` | 值前缀，如 `¥` |
| `card` | 卡片上的位置：`title` 标题、`chip` 价格胶囊、`grid` 参数网格、`tag` 底部标签；省略则只出现在对比表 |
| `compare` | 是否进对比表 |
| `sortable` | 是否在工具条出现排序按钮 |
| `stat` | 是否参与顶部统计 |
| `tagVariant` | `tags` 类型的配色：`green` / `red` / `blue` |
| `tagPrefix` | `tags` 类型每个标签的前缀符号 |

### 分组维度：`groupBy` 与 `facets`

界面上有两级筛选：**品牌**（主分组）+ **品类细分维度**（副分组）。

```jsonc
{
  "groupBy": {
    "key": "brand",          // 主分组固定为品牌
    "label": "品牌",
    "order": ["小米", "美的", "格力"],   // 品牌取值顺序 + 徽章配色来源
    "colors": { "小米": "#a8452e" }
  },
  "facets": [                // 副分组，可选，结构与 groupBy 相同
    {
      "key": "tier",
      "label": "档位",
      "order": ["旗舰", "高端", "中端", "入门"],
      "colors": { "旗舰": "#e67e22" }
    }
  ]
}
```

- 产品的 `brand` 值必须在 `groupBy.order` 里，品类维度的值必须在 `facets[0].order` 里，否则不显示
- 本站是多品牌横评，**主分组只能是 `brand`**；不要把品牌以外的维度放进 `groupBy`
- 某维度若有两种以上真实取值，加进 `order` 即可（`validate` 会拦住不在 `order` 里的值）

### 添加一个新品类

1. 新建 `data/<品类id>/schema.json`，可复制 `air-purifier/` 改（此时可以还没有 `products.json`，
   `validate` 对这种未登记目录只提示不报错）
2. 新建 `public/images/<品类id>/` 放产品图
3. 在 `data/categories.json` 里登记。**它是两层结构**：一级品类分组 → 组内小品类。
   新品类挂到语义合适的一级品类下：

```jsonc
{
  "id": "kitchen-big",
  "name": "厨房大家电",
  "icon": "🍳",
  "description": "需要嵌入或占地的厨房与洗衣大宗家电",
  "categories": [
    { "id": "refrigerator", "name": "冰箱", "icon": "🧊", "description": "容积 / 能耗 / 制冷方式" }
  ]
}
```

新建一级品类时才加一个顶层对象（含 `categories` 数组）；只是新增小品类时，往对应分组的
`categories` 数组里追加一项即可。首页左侧竖排一级品类、右侧显示该组小品类，由 `src/data.ts`
的 `categoryGroups` 驱动，**不需要写任何 Vue 代码** —— 卡片、对比表、筛选排序都由 schema 驱动生成。

## 数据采集流水线

新增品类或补数据时，用 `scripts/mi-store.mjs` 从官方渠道取数，避免手抄：

```bash
npm run mi:enumerate -- 洗碗机 净水器        # 枚举在售商品（需 Playwright）
python scripts/mi-store-enumerate.py 空调    # 等价入口（只有 Python Playwright 时用）
npm run mi:detail -- 19142 24615            # 官方商品详情（名称/现价/划线价/官方图）
npm run mi:specs -- https://www.mi.com/induction-cooker/specs   # 官方规格页 → 参数表
npm run mi:images                            # 按 data/_sources/images.json 下载官方原图到 _cache（不入库，见下「产品图规格」）
npm run mi:apply -- data/_sources/patches/xxx.json              # 写入字段补丁
```

官方渠道拿不到时的补充来源（**禁止照抄，需按异常阈值过滤**）：

```bash
npm run miot:crawl                     # 抓 home.miot-spec.com 型号库（分页/并发，缓存 + 日志）
npm run miot:match                     # 按官方名精确匹配，补 miot_model 字段
npm run pconline:specs                 # 抓太平洋规格表（清单：data/_sources/pconline-targets.json）
python scripts/import-brands.py        # 从太平洋批量导入竞品（清单：data/_sources/brand-targets.json）
python scripts/classify-facets.py      # 竞品副分组批量归类（无依据的保持「未归类」）
python scripts/fetch-evidence-2.py     # 为未归类的竞品补抓分类证据（幂等可重跑）
```

- 枚举结果缓存在 `data/_cache/`（已 gitignore），可反复复查。
- 字段补丁放在 `data/_sources/patches/`，文件内用 `_来源` 记录出处；`mi:apply` 按 `品类/产品id` 定位写入，越界会报错而不是写歪。
- 采集与核验规则见 `skills/appliance-data-curation/SKILL.md`（来源优先级、禁止估算、去重口径、第三方错标陷阱与同义叫法对照表）。
- 每条产品都带 6 个审核标注字段（`verify_status` / `verify_date` / `verify_source` / `verify_url` / `change_log` / `updated_at`），逐条溯源记录在 `data/_sources/provenance.json`。
  `verify_status` 的合法取值是 `已核验（多源）` / `已核验（官方商城）` / `已核验（第三方）` / `待核验` ——
  其中 `已核验（第三方）` 指参数来自单一权威第三方规格站，是非小米品牌（往往没有可抓的官方规格页）的正常状态，
  但每个值仍须通过字段白名单与异常阈值校验，通不过的写 `查不到`。

### 产品图规格：≤320px WebP

站上图片统一存 **WebP、长边 ≤320px、质量 80**，实测比同内容的 640px JPEG 小 **85%**。

尺寸不是拍脑袋定的：全站最大的图片展示位是卡片缩略图 **96×112 CSS px**（`ProductCard.vue`），
按 DPR 3 计需要 288px 宽；时间轴缩略图 56×64、对比抽屉 80×68 都更小。
此前存 640px 属于过采样（像素面积约 4 倍）。

```bash
npm run mi:images     # 1) 按 data/_sources/images.json 下载官方原图 → data/_cache/img-raw/（不入库）
npm run img:webp      # 2) 转成 ≤320px WebP 写入 public/images/ 并回写 img 字段
```

- 转换脚本 `scripts/shrink-images.py`；不会放大小图（168×168 的官方缩略图保持原样）。
- 站上**只保留一份**图：需要更大尺寸时按 `images.json` 重新拉取即可，不做双份存储。
- 图片不写前端代码，`img` 字段始终是「文件名 = 产品 id」。

### 图片加载策略

- 首屏按展示顺序取前 6 张**有图**的卡片用 `loading="eager"` + `fetchpriority="high"`，其余 `loading="lazy"`；
  全部懒加载会让首屏图片排在关键渲染之后，出现可见的空白闪烁。
  ⚠️ 两个坑（`CategoryView.vue` 的 `eagerIds` 有注释）：**不能按卡片自己的 `index` 判断** ——
  分组视图下每组都从 0 重新计数；也**不能按前 6 个产品判断** —— 占位图不消耗带宽，
  6 个产品恰好都没图时首屏会一张 eager 都没有。
- 所有 `<img>` 都带 `width`/`height`（内在 320×320）与 `decoding="async"`，配合 `.thumb` 固定尺寸避免布局抖动。
- 缩略图容器自带底色（`--surface-alt`），图片未到时不会白闪。

## 多 Agent 并行协作

本仓库支持**多个采集方与修正方同时工作**（每人一个 worktree）。协作规范见 **[AGENTS.md](AGENTS.md)**，两条主线：

- **数据按状态分区（文件位置即状态）**：`_draft` 草稿 → `_intake` 待入库 → `_review` 修正 → `products.json` 已入库。
  线上数据只能经 `flow:publish` 写入，任何人不直接手改。

```bash
npm run flow:status                    # 动手前先查：数据现在分布在哪些区
npm run flow:workers                   # 再看一眼：谁占了哪个工作台（防互相踩）
npm run flow:submit -- heater/ht_x     # 采集方：草稿区 → 待入库区（收录完成，提交待审）
npm run flow:claim   -- heater/ht_x    # 修正方：待入库区 → 修正区（认领核验）
npm run flow:recall  -- heater/ht_x    # 修正方：已入库区 → 修正区（召回复审）
npm run flow:publish -- heater/ht_x    # 修正方：修正区 → 已入库区（入库上线）
npm run check                          # = validate + lint + selftest + audit:check，推送前跑
```

- **改动走分支 + PR，合并 PR 即上线**：`main` 受分支保护（直推被拒）；合并由编排方代理
  （常规批次 CI 绿即合，剔除/口径类先呈报用户——规则见 AGENTS.md §3.6）。
- **一人一个 worktree**（`wt-collect-<NN>` / `wt-review-<NN>`）：同一目录被两个会话共用会互相踩分支；
  开工先跑 `flow:workers` 看谁在工作、改动涉及哪些目录。

关键规范（详见 [AGENTS.md](AGENTS.md) 与 [HANDOFF.md](HANDOFF.md) 第 0 节）：

- **库文件「一行一款」**：便于 git 按行三方合并；写入必须走
  `scripts/lib/library-io.mjs` / `library_io.py`（规范序列化 + 写前指纹校验 + 文件锁重试），
  不要自己 `writeFileSync`。
- **批量命令可断点续跑**：结束打印「成功 / 已是目标态 / 失败」，中途失败原样重跑即幂等续上；
  `npm run flow:log --batch <批次id>` 可回查某一批，`flow:status --by <提交人>` 可按归属过滤。
- **提交闸门**：`npm run hooks:install`（每个 clone / worktree 各一次）后，含
  `data/_intake` / `data/_review` 文件的提交必须带 `flow` 标记；草稿区 `data/_draft/` 不入库。
- 流转全程记录在 `data/_flow/journal.jsonl`；审核报告归档在 `docs/audit/`。

配套命令：`npm run selftest`（60 条断言，在隔离副本上跑，不碰真实数据）、
`npm run lint`（重复型号 / 重复产品名）。

## 目录速览

```
AGENTS.md                 多 Agent 协作规范（先读这个）
HANDOFF.md                当前状态索引（接手先读）
skills/                   技能定义（客户端无关；.trae/.claude 下只放指针）
docs/audit/               审核报告归档
data/<品类>/{schema,products}.json
data/_draft/              草稿区：收录中的半成品（采集方工作台）
data/_intake/             待入库区：收录完成、等待认领（交接队列）
data/_review/             修正区：审核修正中（审核方工作台）
data/_flow/               流转日志 journal.jsonl（谁把什么搬到了哪）
data/_sources/            溯源、补丁、图片清单（入库）
data/_cache/              抓取缓存（不入库）
data/_locks/              审核快照锁（已降级为结构冻结工具）
scripts/                  采集、校验、流转、审核锁工具
```

## 部署

**合并 PR** 即触发 `.github/workflows/deploy.yml`：校验数据 → 构建 → 发布到 Pages（直推 `main` 会被分支保护拒绝）。

首次部署需在仓库 **Settings → Pages → Build and deployment → Source** 选择 **GitHub Actions**。

由于 GitHub Pages 没有 SPA 路由回退，构建时会把 `index.html` 复制一份为 `404.html`，保证直接访问 `/air-purifier` 这类子路径也能正常加载。
