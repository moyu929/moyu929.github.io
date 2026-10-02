# 交接文档：家电横评站点 —— 品类扩充与数据订正

> 交接背景：站点已扩到 **41 个品类 / 418 款产品**，全部走「schema 驱动」零前端改动。最近一轮做了三件事：给**全部产品加审核标注字段**、接入 **miot 第三方产品库**核验停产型号、新增**洗地机与浴霸**两个品类。详见第 0.1 节。
>
> 数据采集/核验的完整规范见 [skills/appliance-data-curation/SKILL.md](skills/appliance-data-curation/SKILL.md)，**动手前务必先读它**。

## 0.0 协作协议升级（2026-10-02）：数据分区流转 —— 正在做审核修正的 Agent 请先读这段

**产品数据的手改通道已关闭。** 本仓库改用「分区流转协议」（详见 `AGENTS.md` 第 3 节）：数据按状态放在四个物理分区，文件的位置就是它的状态，各方只写自己的分区——

| 分区 | 位置 | 谁写 |
| --- | --- | --- |
| 草稿区 | `data/_draft/<品类>/<id>.json` | 采集方收录中的半成品 |
| 待入库区 | `data/_intake/<品类>/<id>.json` | 采集方 `flow:submit` 放入、审核方 `flow:claim` 取走 |
| 修正区 | `data/_review/<品类>/<id>.json` | 审核方核验修正中 |
| 已入库区 | `data/<品类>/products.json` | **只能经 `flow:publish` 写入，任何人不直接手改** |

对审核修正方（你）的操作变化：

- 修旧数据：`npm run flow:recall -- <品类>/<id> --reason "…"`（产品暂时下架）→ 在 `_review/` 里改 → `npm run flow:publish -- <品类>/<id>`。不再需要拍快照锁，召回本身就是物理冻结。
- 处理采集方新数据：`npm run flow:claim -- <品类>/<id>...` 认领到修正区；不符收录标准的 `flow:return` 退回，该剔除的（经用户确认）`flow:drop`。
- **不要**再直接编辑 `products.json`——`flow:publish` 会做校验 + 整品类复检（不过关自动回滚），绕过它手改的数据过不了下一轮审计。
- 快照锁已降级为「结构冻结」工具（schema 大改/发版验收才用）；生效期间暂停流转。
- 每个流转命令跑完**当场提交**（含 `data/_flow/journal.jsonl` 日志）；动手前 `npm run flow:status` 看各区现状。

注意：召回会让产品暂时从站点消失，大批量审核请按「召回一批 → 修正 → 入库一批」滚动推进。


## 0.1 最近一轮进展（2026-10-01）

**审核标注字段（全量 418 款）** —— 每款产品新增 6 个字段，用于回答「这条数据凭什么可信、什么时候核的、改动过什么」：

| 字段 | 含义 |
| --- | --- |
| `verify_status` | 核查状态：`已核验（多源）` / `已核验（官方商城）` / `待核验` |
| `verify_date` | 核查时间 |
| `verify_source` | 信息来源（标签数组，如 小米商城 / 太平洋电脑网 / 米家产品库） |
| `verify_url` | 首选来源链接 |
| `change_log` | 修改记录（本轮补了什么、依据什么） |
| `updated_at` | 最近更新日期 |

判定依据**可追溯**，不是手填：`data/_sources/provenance.json` 记录逐条溯源（来源 + 链接 + 备注），
`data/_sources/patches/*.json` 记录了参数补丁，脚本据此生成状态；没有可追溯来源的早期条目一律标 `待核验`（当前 60 款）。

**miot 第三方产品库接入** —— `scripts/miot-spec.mjs`（home.miot-spec.com）：

```bash
node scripts/miot-spec.mjs crawl [关键词...]   # 按品类整库抓取（分页/并发 4/增量落盘），38+ 关键词 → 2585 条本地索引
node scripts/miot-spec.mjs search <关键词...>  # 只抓首页
node scripts/miot-spec.mjs product <model...>  # 取某型号固件能力项
node scripts/miot-spec.mjs match [--apply]     # 用本地索引补 miot_model
```

- 该站是 Inertia 应用，数据在 `<script data-page="app" type="application/json">{…}</script>` 里，需按 JSON 括号配平解析。
- **单次请求约 3.5 秒**，串行会误判为「卡死」；务必用并发 + 日志（`data/_cache/miot-crawl.log`）。
- 实测**没有反爬**：连续 6 次请求全部 HTTP 200。慢是因为站点本身慢。
- 由此为 **146 款**产品写入 `miot_model`（协议型号，如 `xiaomi.airp.sa6`）。
  ⚠️ **miot 型号 ≠ 零售型号代码**，所以用**独立字段** `miot_model` 存放，绝不覆盖 `model_code`。
- ⚠️ 该站 `verified_time` 是**协议认证时间**，不是上市时间；收录不完整且含固件改版重复条目，**缺失不作为型号不存在的依据**。

**太平洋规格表工具** —— `scripts/pconline-specs.py` + `data/_sources/pconline-targets.json`：

- 小米商城商品页参数表由 JS 动态加载，纯 HTTP 抓不到（浏览器渲染后正文仅 1.3k 字，无规格区）；
  而太平洋的 `_detail.html` 是服务端渲染的结构化表格，可作第二来源。
- 抓取清单里按 `urlId` 指定型号页；结果落 `data/_cache/pconline-<品类>-<产品>.json`。
- ⚠️ **该站有系统性字段错标**（把「风暖功率」写成 `28W`、把 `2600W` 标成「灯暖功率」、把 `L` 写成 `ml`、`约.6kg` 缺位），
  因此写库时有**异常值剔除规则**（见 `data/_sources/provenance.json` 与生成脚本注释），可疑值一律写 `查不到`。

**新增品类**：洗地机 `floor-washer`（17 款）、浴霸 `bath-heater`（12 款）。

**当前缺口**：41 款无产品图；`model_code` 大面积缺失（miot 补的是另一个字段）；60 款仍为 `待核验`；
洗地机的「吸力/真空度」因源数据单位混乱（Kpa / 毫巴 / 缺零）**本轮故意不收录**。

---

## 0. 快速上手

```bash
npm install          # 先装依赖（当前 node_modules 不存在，必须先装）
npm run validate     # 校验 data/ 下 JSON，必须无 error（warning 可接受）
npm run dev          # 本地开发预览 http://localhost:5173
npm run build        # 生产构建到 dist/（含 vue-tsc 类型检查）
npm run preview      # 预览构建产物
```

- 线上地址：https://moyu929.github.io
- 发布方式：推送到 `main` 触发 `.github/workflows/deploy.yml`（校验 → 构建 → GitHub Pages）。首次需在仓库 Settings → Pages → Source 选 **GitHub Actions**。
- 当前所在分支：`trae/agent-DtJ63m`（工作区干净，改动已提交）。

---

## 0.2 本轮（同日稍后）：图片规格升级 + 媒体来源规则放宽

### 图片改 WebP 并降到 320px

- **依据**：全站最大的图片展示位是卡片缩略图 **96×112 CSS px**（`ProductCard.vue`），DPR 3 需 288px；
  时间轴 56×64、对比抽屉 80×68 更小。此前存 640px JPEG 属**过采样**（像素面积约 4 倍）。
- **结果**：`404 张 / 10MB` → **369 张 WebP / 0.89MB**，比 640px JPEG 小 **85%**，单张平均 2.3KB。
- **工具**：新增 `scripts/shrink-images.py`（`npm run img:webp`）；
  `mi:images` 改为只把官方**原图**下到 `data/_cache/img-raw/`（不入库），再统一转 WebP 入库。
- **加载策略**：首屏前 6 张**有图**的卡片 `loading="eager"` + `fetchpriority="high"`，其余 `lazy`；
  所有 `<img>` 补 `width/height`（320×320）与 `decoding="async"`。
- **踩坑记录（值得记住）**：
  1. 最初用卡片自带的 `index` 判断首屏 —— 分组视图下**每组都从 0 重新计数**，每组的头几张全被当成首屏；
  2. 改成父组件按展示顺序取前 6 后仍然全落空 —— 因为那 6 个产品**根本没有图**，占位图不消耗图片带宽；
  3. 最终按「前 6 张**有图的**」判定，实测 floor-washer 首屏恰好 6 张 eager、其余 lazy。

### 来源规则放宽：媒体可作印证

- 新增来源层级第 3 档「**一般媒体（含 AI 聚合内容）**」：**只能印证，不能单独定值**。
  - 允许：印证已有官方/权威第三方数据；或官方与第三方都没有、且不涉及安全/电气额定/医疗健康时，
    **至少两家彼此独立**的媒体一致可作为补充值录入。
  - 禁止：仅凭一条媒体信息给产品定参数；**媒体互相转载不算多源印证**（很多是同一个源头，AI 聚合更甚）。
  - 标注：媒体名写进 `verify_source`，`change_log` 写明「媒体印证：A、B 一致」，链接登记进 `provenance.json`。
- 规范落在 `skills/appliance-data-curation/SKILL.md`（来源优先级第 3 档 + 核心规则第 1 条）与 `AGENTS.md` 红线第 6 条；
  `docs/audit/README.md` 标明早期报告里「严禁用媒体参数补齐」的口径**已被取代**（历史报告不改写）。

## 1. 项目速览

- 技术栈：Vite + Vue 3 + TypeScript 静态站，路由用 vue-router。
- **数据全靠手写 JSON**，页面（卡片 / 对比表 / 筛选 / 排序 / 顶部统计）全部由 schema 驱动，**新增品类/字段不需要写任何 Vue 代码**。
- 数据懒加载：`src/data.ts` 用 `import.meta.glob('../data/*/schema.json')` 自动发现品类，所以只要目录结构对，前端零改动。

目录约定：

```
data/categories.json                 品类清单（首页入口）
data/<category-id>/
  ├─ schema.json                     字段定义：显示位置、单位、能否排序
  └─ products.json                   产品数据（日常只改这个）
public/images/<category-id>/         产品图，文件名 = 产品 id
scripts/validate-data.mjs            数据校验脚本
```

更细的字段属性说明（`card`/`compare`/`sortable`/`stat`/`tagVariant` 等）见 [README.md](file:///workspace/README.md#L62-L91)。

---

## 2. 收录范围与关键规范（摘要，细节以 SKILL.md 为准）

1. **只收录米家/小米（小米自有品牌）的国内（中国大陆）型号**；不收海外版/港台版、其他品牌、白牌生态链品牌。
2. 同一硬件不同固件改版视为**同一型号**；同一商品名称/系列跨年份有**实质性迭代**（型号代码、核心性能、能效、结构或关键功能变化）才拆成不同版本。
3. **版本后缀命名**：`name` 用「（YYYY款）」结尾，如 `米家空调 巨省电Pro 大1匹（2025款）`；年份查不到用「新款 / 旧款」并在后续补齐。不得因促销/颜色/固件等无关变更拆分。
4. 来源优先级：**官方**（小米商城 / 官网规格页 / 说明书 PDF）> **权威第三方**（ZOL / 太平洋 / 苏宁 / 京东，需两处相互印证）> **仅作交叉印证**（miot-spec 等，不能以其缺失否定型号存在）。
5. **禁止编造/估算**：查不到就写 `"查不到"` 或 `"—"`，数值字段确实无值也给 `"—"`（校验会提示「排序时沉底」，属已知提示）。
6. **额定 vs 实测双口径**：同一型号两者都存在时拆两列分别标注，不可混用。
7. 去重先按**型号代码**再按名称；海外版判据：大陆官方渠道检索不到 + 可确认面向海外/港台。

---

## 3. 当前进度

### 已完成（数据规模）

| 指标 | 数值 |
| --- | --- |
| 品类 | **38 个**（见 `data/categories.json`） |
| 产品 | **389 款** |
| 官方产品图 | **320 张**（≤640px JPEG，压缩后共约 5MB） |
| 字段填充率 | **46.4%**（2937 / 6326，`查不到` / `null` 不计入） |
| `npm run validate` | 通过，0 error（提示均为「暂无产品图 / 非数值沉底」） |

38 个品类：空气净化器 / 空调 / 加湿器 / 除湿机 / 电风扇 / 电暖器 / 冰箱 / 洗碗机 / 微波炉 /
电饭煲 / 电压力锅 / 电蒸锅 / 空气炸锅 / 电磁炉 / 破壁机 / 咖啡机 / 电水壶 / 洗衣机 / 晾衣机 /
挂烫机 / 扫地机器人 / 无线吸尘器 / 除螨仪 / 热水器 / 即热饮水机 / 吹风机 / 剃须刀 / 电动牙刷 /
理发器 / 足浴器 / 筋膜枪 / 体脂秤 / 智能摄像机 / 净水器 / 智能门锁 / 电视 / 投影仪 / 智能音箱。

高密度品类（字段填充率）：空气净化器 92%、扫地机器人 82%、空调 81%、冰箱 64%、洗衣机 54%。

### 数据来源与采集方式（已固化进仓库）

流水线都在 `scripts/mi-store.mjs`（另有等价的 Python 枚举入口 `scripts/mi-store-enumerate.py`），
用法与注意事项见 README「数据采集流水线」与 SKILL.md「采集流水线」两节。常用命令：

```bash
npm run mi:enumerate -- <关键词...>      # 枚举在售商品（需 Playwright）
npm run mi:detail -- <productId...>      # 官方商品详情（纯 HTTP）
npm run mi:specs -- <规格页URL...>       # 官方规格页 → 参数表（纯 HTTP）
npm run mi:images                        # 按 data/_sources/images.json 下载官方图
npm run mi:apply -- data/_sources/patches/xxx.json   # 写字段补丁
```

- 枚举缓存：`data/_cache/`（已 gitignore）。
- 图片清单：`data/_sources/images.json`；字段补丁与出处：`data/_sources/patches/`。
- 图片：`public/images/<品类>/<产品id>.jpg`，统一压缩为 ≤640px JPEG。

> 两条踩过的坑：
> 1. **回写必须锚定对象边界**。早期用「从 `"id": "X"` 向后找第一个 `"img": null`」的正则，当 X 本身已有图时会越界写到下一个产品上（曾把空净 6 款产品挂错图）。现在 `mi:apply` 会断言 id 与目标字段之间不出现 `"id"`，越界直接报错。
> 2. **枚举必须按容器限定**。商城搜索页顶部导航/推荐位同样是 `a[href*=product_id]`，只取 `.goods-list .goods-item`，否则会混入手机、平板等无关商品（实测每个关键词都会多出 100+ 条噪音）。

### 未完成（后续可做）

1. **产品图缺口 69 款**：主要是已停产型号（空净 Pro H/4 Max/1代/2代、吸尘器 K10/G10/G20/Lite、投影仪 2 Pro/青春版、门锁 E20/E2/Pro 等），官方商城已无在售条目，`img` 保持 `null` 符合规范（校验会提示，属已知提示）。官方老页面（`www.mi.com/vacuum-cleaner` 等）里的图是 CSS 背景，无法可靠对应到具体型号，未采用。
2. **数据补全**：低密度品类仍需逐型号查官方参数页；官方规格页解析器已就绪（`mi:specs`），但电视/投影的新页是前端渲染的，需换来源。
3. **价格口径**：`official_price` 目前是「采集时点的官方商城价」（部分老条目保留的是上市指导价），两者未做统一。如需统一，可跑一次「按 `data/_cache/search-*.json` 现价刷新」的批处理。
4. **《型号漏收录初筛报告》已逐条复核**，结论写回该文件末尾；其中 15kg 分区洗烘、430L/610L/216L 冰箱、蓝氧智投等候选**未获官方目录证实**，未收录，需查历史发布材料或说明书才能定论。
5. **提交状态**：本地 `main` 领先 `origin/main`，部署由 Agent 执行（`validate → build → push`）。



---

## 4. 本轮已完成（原待办）

### 4.1 三个 schema.json 已创建

| 品类 | id | groupBy.key | groupBy.order | primaryMetric | imageBase |
| --- | --- | --- | --- | --- | --- |
| 洗衣机 | `washing-machine` | `type` | 滚筒洗烘一体 / 洗烘套装 / 波轮 | `official_price` | `images/washing-machine` |
| 冰箱 | `refrigerator` | `door_type` | 法式多门 / 十字门 / 对开门 / 三门 / 两门 | `official_price` | `images/refrigerator` |
| 扫地机器人 | `robot-vacuum` | `tier` | 入门 / 中端集尘 / 全能基站 / 全能上下水 | `official_price` | `images/robot-vacuum` |

- `groupBy.order` 已按 products.json 中实际出现的分组值补全（顺序即界面分组顺序）。
- 全部字段 key 已定义；`official_price` = `number`+`chip`+`sortable`+`stat`，`year` = `number`+`sortable`，`pros/cons/tags` = `tags` + `tagVariant`（green/red/blue）。
- 三个品类都补了 `guide`（按场景选购建议），文案只引用 products.json 里已有的参数，未新增臆测数据。

### 4.2 品类已注册

`data/categories.json` 现为 5 条：空气净化器 / 空调 / 洗衣机 / 冰箱 / 扫地机器人（顺序即首页展示顺序）。

### 4.3 图片目录已建

`public/images/{air-conditioner,washing-machine,refrigerator,robot-vacuum}/` 均已创建（含 `.gitkeep` 占位）。
产品图文件名必须 = 该产品的 `id`（如 `wash_dry_108.jpg`）+ 后缀，`img` 填文件名；暂无图写 `null`。

### 4.4 液态玻璃对比浮标

- 新增 `src/components/LiquidGlass.vue`：SVG `feImage` + `feDisplacementMap` 生成位移图，`backdrop-filter: url(#id)` 做折射；支持指针拖动（阈值 6px 区分点击/拖动）、位置写入 `localStorage.compareFabPos`、点击派发 `activate`。
- `CategoryView.vue` 改用该组件，删除了内联 FAB 的状态与样式。
- 收尾项：`--lg-size` 改为按 `size` prop 动态注入、层级从 `9999` 调整为 `350`（高于工具条 300、低于对比抽屉 399/400，与旧 FAB 行为一致）、补 `--brand-glass-tint` 明暗主题令牌。
- 顺带给 `CompareDrawer` 补了 **Esc 关闭**（此前只能点 X 或遮罩）。

### 4.5 校验与构建

```bash
npm run validate    # 38 个品类全部通过，0 error（提示均为「暂无产品图 / 非数值沉底」）
npm run typecheck   # 通过
npm run build       # 通过
```

浏览器实测（Playwright）确认：首页 38 个品类入口正常；全站 302 张产品卡（当时数据量）逐页渲染数与 `products.json` 完全一致，产品图零破图，对比抽屉、时间轴、明暗主题均正常，控制台无 error、无 4xx/5xx 请求。

### 4.6 发布

改动推送到 `main` 即可触发部署（`.github/workflows/deploy.yml`：校验 → 构建 → Pages）。
**注意**：本轮工作只在本地提交，**未执行 push / build / 服务启停**（等待统一手动批准后再做生产部署与验收）。

---

## 5. 已知坑与环境问题

1. **环境不稳定**：本会话多次丢失上下文、`Write` 大文件偶发被截断。建议：
   - 写大 JSON 时用紧凑格式（一行一对象）分块写入，写完后**立刻 `Read` 回读校验长度与结尾**；
   - 每完成一步就跑一次 `npm run validate` 固化进度；
   - 及时 `git commit`，避免只剩工作区改动时被环境重置。
2. **别只看「校验通过」**：`validate` 只遍历 `categories.json` 里列出的品类。新品类若忘了注册，脚本根本不会校验它，输出照样是「数据校验通过」。
3. **数值字段与 `"—"`**：schema 声明为 `number` 却填 `"—"` 的产品排序会沉底，属预期提示，不必强修。
4. **历史数据坑（供参考）**：
   - 空气净化器宠物款曾误用国际版 `AC-M30-SC`，已改为国内在售 `AC-M31-SC`；
   - 6 Max 的 CADR 曾出现 ZOL(1655/1151) 与太平洋(1500/1000) 冲突，最终按 ZOL 取值；
   - miot-spec 类参考站存在大量固件重复条目且收录不全，**只用于交叉印证，不能当准绳**。
5. **提交信息**：仓库历史提交信息目前不规整（多为同一句），后续建议按 `feat/fix/docs` 规范提交。

---

## 6. 数据现状清单（三新品类已收录型号）

**洗衣机（7 款）**：互联网洗烘一体 10kg（2019款）、互联网直驱洗烘一体 10kg（2021款）、超净洗滚筒洗烘一体 10kg（2024款）、洗烘套装Pro 蓝氧洗 热泵烘 10+10kg（2025款）、波轮 尊享版 10kg（2019款）、波轮 Pro 10kg（2025款）、波轮 10kg（2024款）。

**冰箱（8 款）**：Pro 微冰鲜双系统 法式平嵌560L（2025款）、分储鲜Pro 十字508L（2024款）、Pro 至尊版 十字508L（2025款）、Pro 双系统 十字606L（2024款）、十字对开门603L 冰晶岩（2023款）、对开636L（2023款）、186L两门风冷（2020款）、三门210L（2020款）。

**扫地机器人（9 款）**：3C增强版、4、5C（2024款）、M40 S（2025款）、5 Pro（2025款）、6（2025款）、6 Pro（2026款）、6 Max（2026款）、7C（2025款）。

> 注意：以上名称已按版本后缀规范处理，但**部分型号代码/参数仍是「查不到」**（如冰箱 Pro 至尊版十字508L、扫地机器人 7C、3C增强版等），有官方来源时请补齐。
>
> 这三个品类目前**都没有产品图**（`img` 全为 `null`），`schema.imageBase` 已分别指向 `images/washing-machine`、`images/refrigerator`、`images/robot-vacuum`。

---

## 7. 参考

- 收录规范：[skills/appliance-data-curation/SKILL.md](skills/appliance-data-curation/SKILL.md)
- 字段/维护说明：[README.md](file:///workspace/README.md)
- 校验脚本：[scripts/validate-data.mjs](file:///workspace/scripts/validate-data.mjs)
- 部署流程：[.github/workflows/deploy.yml](file:///workspace/.github/workflows/deploy.yml)