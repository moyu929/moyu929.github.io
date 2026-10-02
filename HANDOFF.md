# 交接文档：家电横评站点 —— 品类扩充与数据订正

> 交接背景：站点已扩到 **6 个一级品类 / 40 个小品类 / 1036 款产品 / 51 个品牌**，全部走「schema 驱动」零前端改动。
> 2026-10-01 至 10-02 完成三件大事：①审核报告整改（型号核实、错挂链接清理、品牌同等化）；
> ②视觉重做与首页一级品类导航；③数据分区流转协议落地。详见第 0.1、0.3、0.4 节。
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

## 0.0.1 工具链升级（2026-10-03）—— 动手前请看的五条变化

这一轮把「会悄悄丢数据 / 会互相踩」的问题在工具层做了根治，命令的用法**没有变**，但有五处需要知道：

1. **库文件改成「一行一款」**（原先整个数组压成一行）。目的：两个分支改同一品类时 git 能按行合并，
   冲突只剩「同一款产品被两处改」。**不要**用 `writeFileSync` / `write_text` 直接写 `products.json`——
   写入必须走 `scripts/lib/library-io.mjs`（Node）或 `scripts/lib/library_io.py`（Python），
   它们提供规范序列化 + 写前指纹校验（拒绝覆盖别人刚改过的库）+ 文件锁退避重试。
2. **每条 flow 命令都会打印「操作自证」**：数据根目录 + 当前分支 + actor，并把 `branch` 记进 journal。
   命令开头多这几行是故意的（隔离是软的，越界操作要当场可见）。
3. **批量命令可断点续跑**：结束打印「成功 / 已是目标态 / 失败」，中途失败后**原样重跑**即幂等续上；
   `npm run flow:log --batch <批次id>` 可回查某一批。
4. **提交闸门**：`npm run hooks:install`（**每个 clone / worktree 各一次**）启用后，
   含 `data/_intake/**` 或 `data/_review/**` 的提交必须带 `flow` 标记，否则被拒。
   它挡的是「顺手 `git add -A` 把别人的半成品捎带进自己的提交」。合并提交放行。
5. **两个新命令**：`npm run selftest`（47 条断言，在 `.flow-test/` 隔离副本上跑，不碰真实数据，
   改 `scripts/` 后跑一次）、`npm run lint`（重复型号 / 重复产品名；已并入 `npm run check`）。

另外：**草稿区 `data/_draft/` 自此不入 git**（私有工作台）。备份靠一条纪律换：
**能过校验就 `flow:submit`**（进了待入库区即被跟踪），需要继续改再 `flow:withdraw` 撤回。

排期与剩余事项见 [docs/proposals/P2切换清单与待用户事项_2026-10-03.md](docs/proposals/P2切换清单与待用户事项_2026-10-03.md)
与 [docs/proposals/方案_并发协作与工作流升级_2026-10-03.md](docs/proposals/方案_并发协作与工作流升级_2026-10-03.md)（第 9 节为执行状态）。


## 0.1 最近一轮进展（2026-10-01）

**审核标注字段** —— 每款产品 6 个字段，用于回答「这条数据凭什么可信、什么时候核的、改动过什么」：

| 字段 | 含义 |
| --- | --- |
| `verify_status` | 核查状态：`已核验（多源）` / `已核验（官方商城）` / `已核验（第三方）` / `待核验`（第三档为 2026-10-01 新增，指参数来自单一权威第三方规格站，是非小米品牌的正常状态） |
| `verify_date` | 核查时间 |
| `verify_source` | 信息来源（标签数组，如 小米商城 / 太平洋电脑网 / 米家产品库） |
| `verify_url` | 首选来源链接 |
| `change_log` | 修改记录（本轮补了什么、依据什么） |
| `updated_at` | 最近更新日期 |

判定依据**可追溯**，不是手填：`data/_sources/provenance.json` 记录逐条溯源（来源 + 链接 + 备注），
`data/_sources/patches/*.json` 记录了参数补丁，脚本据此生成状态；没有可追溯来源的早期条目一律标 `待核验`。
（此机制在小规模时期建立，现已并入分区流转协议：`flow:submit` 与 `flow:publish` 会强制校验这 6 个字段。）

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

**新增品类**：洗地机 `floor-washer`、浴霸 `bath-heater`（当时各十余款，现已扩充）。

**当时的缺口**（现状见第 3 节）：无产品图的型号；`model_code` 大面积缺失（miot 补的是另一个字段）；
洗地机的「吸力/真空度」因源数据单位混乱（Kpa / 毫巴 / 缺零）**本轮故意不收录** ——
该决策已在 2026-10-01 被官方 API 核实的数据推翻并修正（见第 0.3 节）。

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
- 当前所在分支：`main`（改动直接提交到 `main`，推送即触发部署）。

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

## 0.3 审核报告整改（2026-10-01）

依据 `docs/audit/审核_全站型号参数_2026-10-01.md` 做了五件事，完整报告见 `docs/audit/整改_全站型号参数_2026-10-01.md`。

### 品牌同等化（用户明确要求）

原先分组维度是「品类维度 + 竞品末位」，等于把其他品牌摆在小米的对立面。改为：

- `groupBy.key` 固定 `brand`，40 个品类的 `竞品` 分组位全部移除
- 品类自身的细分维度（`tier`/`type`/`series`/`door_type`）降为 `schema.facets[]`，界面上是品牌下拉之后的副下拉
- 1036 款全部补齐 `brand`；最终 51 个品牌，小米 418 · 其他 618
- 品类简介、`subtitle`、首页副标题、页脚声明去掉「米家全型号横评」定位
- `已核验（第三方）` 正式纳入状态枚举 —— 非小米品牌往往没有可抓的官方规格页，
  以权威第三方为唯一来源是这一类产品的**实际状况**，不该为「凑官方来源」而降级或编造链接

### F305 重复型号的判定（用户点名）

结论：**不是同一产品，且其中一条型号标错**。依据小米商城官方 API
（`api2.order.mi.com/product/view?product_id=<id>&version=2`，**必须带 `Referer: https://www.mi.com/`**）：

- `fw_5c`（5C）持 `F305`，其规格页 4 项参数与官方逐项吻合 → 型号正确
- `fw_5pro_foam`（5 Pro泡沫版）**不是独立型号**。官方 `product_id=10050233` 的 `buy_option` 显示
  「5 Pro 泡沫版」是 5 Pro 这同一 `product_id` 下的规格选项；泡沫清洁模组是可单独加装的配件
  （`product_id=1230807263`，¥399）。太平洋那条是从 5 Pro 页复制后改了型号栏 —— 参数逐字相同。
- 处理：型号改为 `F302`，**保留独立条目**（有独立 `product_id=1230808690`、独立售价 ¥2199、
  主机 6.5kg vs 5 Pro 6.1kg），用 `tags` 标注「泡沫清洁模组套装」区分。共用型号属同机型不同 SKU。
- 顺带修正同源参数错误：两款水箱清水/污水颠倒（官方 `class_parameters`：净水 1000ml / 污水 700ml）。

### 其余三项

- **型号代码核实**（不只比对型号字符串，把制冷量/风量/噪音与库内数值逐项比对）：订正 4 条 ——
  IH 电饭煲 4L `IHFB01CM`→`IHFB02CM`（前者是 3L）、巨省电Pro 1.5匹 `KFR-35GW/V1A1`→`KFR-35GW-NA20/V1A1`、
  至尊版 508L 冰箱 `BCD-508WSSGPDIN`→`BCD-508WFSGPDIN`（原值是不存在的字母组合）、
  2021 款洗衣机 `XQG100MJ102S`→`XHQG100MJ102S`（XQG 是滚筒前缀，洗烘一体该用 XHQG）
- **错挂来源链接**：用官方 API 逐个核对 `product_id`，发现 11 条官方链接错挂（同一 `product_id`
  被多条产品共用），已置 `查不到` 并记录实际指向。另修 3 条指向别处的第三方链接
- **核查状态订正**：7 条虚标「已核验（多源）」实为单源，逐条降级（其中百度百科、什么值得买属一般媒体，
  本不得单独定值）

### 数据质量

- 竞品 CADR 里 14 处未解码的 HTML 实体 `m&#179;/h` → `m³/h`
- 带单位数值重复渲染单位（`85英寸英寸`、`4000mAhmAh`）→ `formatValue` 加 `carriesUnit()`
- 校验器噪声：「排序时会沉底」告警从 1867 条降到 0（能解析数字的带单位值与「查不到」占位不再告警）
- 补齐竞品字段的 schema 声明（`model_code`/`power`/`area`/`noise` 等原先有数据但界面不显示）
- 顺带发现 `heater/panasonic_1648387`（松下 FV-30BQS1）是**浴霸错放在电暖器品类**，
  已按流转协议 recall → 重建 → publish 归位

## 0.4 视觉重做 + 首页一级品类（2026-10-01 至 10-02）

### 首页改为一级品类分组导航

40 个品类平铺太繁杂，改为 6 个一级品类分组：环境与空气 / 厨房大家电 / 厨房小家电 / 清洁电器 /
个护健康 / 居家智能。`data/categories.json` 从扁平数组改成**两层结构**（一级品类 + `categories` 数组），
首页左侧竖排一级品类（宽屏 sticky，移动端横向滚动）、右侧显示该组小品类。

⚠️ `src/data.ts` 因此导出 `categoryGroups`（不再是 `categories`），`validate-data.mjs` 适配两层结构并加了
反向检查（`data/` 下有 `products.json` 的目录必须登记进 `categories.json`）。

### 视觉重做：去掉生成式站点的典型指纹

用户反馈「太平淡、AI 风格明显」。诊断出指纹集中在**设计令牌层**，改那里杠杆最大：

| 指纹 | 处理 |
| --- | --- |
| 紫蓝渐变（`--brand: #6c5ce7`，Flat UI Colors 的 purple） | 换陶土红 `#a8452e` 单一强调色，`--brand-gradient` 改实色 |
| 渐变色球 + `gradientFlow` 背景动画 | 删；hero 改顶部一道 3px 强调色横线 |
| 46 个 emoji 当品类图标 | 一级品类改 `01`–`06` 编号（目录感），品类卡改纯文字 + 箭头 |
| 三层 mesh 渐变背景 | 极淡方格纸纹 + 内联 SVG 噪点（`feTurbulence`，零外部请求） |
| 默认字体栈 | 标题走系统衬线（`--font-display`，零加载成本）+ 全局 `tabular-nums` |
| 纯黑低透明度阴影 | 全部带暖色调 |
| 胶囊标签 | 标签类改小圆角；关闭按钮/计数点是圆形语义保留 |
| 卡片边框+阴影双重堆叠 | 改底色 + 细边框分层（一屏十几张卡时阴影全是噪音） |

### 交互修复

- **滚动动画抖动**（分组 `<section>` 挂 `.reveal`，每组独立触发导致整块随滚动上下移动、行间距看起来忽宽忽窄）：
  分组 section 去掉 reveal；`ProductCard` 入场序号改为跨组单调递增（新增 `seq` prop）
- **对比浮标拖动卡顿**：`pointermove` 改 rAF 节流 + 拖动期直接写 DOM 绕过 Vue 响应式；
  拖动期禁用 `backdrop-filter` 折射（每帧重算背景位移贴图是主因）
- **价格颜色**：原本用 `--danger` 红色（本站红色是「缺点」标签语义，价格标红会被误读成警示）→ 改强调色
- **筛选栏挤扁搜索框**：排序项多时（除湿机 6 个）搜索框被压到 140px → 基准宽度提到 220px

### 声明弹窗

免责声明从页脚按钮改为右上角常驻操作组（与主题切换并排），页脚只留一行居中文案。
首页每次访问自动弹出，底部按钮区与滚动主体分离（`panel-body` 滚、`panel-foot` 固定）；
「今日不再弹出」按当天日期存 localStorage。关闭动画走 macOS 神奇效果近似（下边缘不动、上边缘向下收窄）。
⚠️ 弹窗组件挂在 `App.vue` 上**不会随路由切换重新 mount**，所以用 `route` watcher 判断首页，
否则从首页点进品类页时弹窗会一直挂着。

## 1. 项目速览

- 技术栈：Vite + Vue 3 + TypeScript 静态站，路由用 vue-router。
- **数据全靠手写 JSON**，页面（卡片 / 对比表 / 筛选 / 排序 / 顶部统计）全部由 schema 驱动，**新增品类/字段不需要写任何 Vue 代码**。
- 数据懒加载：`src/data.ts` 用 `import.meta.glob('../data/*/schema.json')` 自动发现品类，所以只要目录结构对，前端零改动。

目录约定：

```
data/categories.json                 品类清单（两层：一级品类 → 小品类，首页入口）
data/<category-id>/
  ├─ schema.json                     字段定义：显示位置、单位、能否排序
  └─ products.json                   已入库区：线上唯一数据源（不可直接手改，只能经 flow:publish）
data/_draft/<品类>/<id>.json         草稿区：收录中的半成品（采集方工作台）
data/_intake/<品类>/<id>.json        待入库区：收录完成、等待认领（交接队列）
data/_review/<品类>/<id>.json        修正区：审核修正中（审核方工作台）
data/_flow/journal.jsonl            流转日志（谁在何时把什么搬到了哪）
public/images/<category-id>/         产品图，文件名 = 产品 id（不随分区流转）
scripts/validate-data.mjs            数据校验脚本
scripts/lib/product-check.mjs        校验规则库（validate 与 flow 复用）
```

更细的字段属性说明（`card`/`compare`/`sortable`/`stat`/`tagVariant` 等）与 `groupBy`/`facets` 分组维度
说明见 [README.md](README.md)。

---

## 2. 收录范围与关键规范（摘要，细节以 SKILL.md 为准）

1. **多品牌横评**：收录中国大陆的小米/米家自有品牌**与**主流家电品牌（美的、海尔、格力、戴森、追觅、石头、
   科沃斯、云鲸、添可、松下、苏泊尔、九阳、飞利浦、西门子、老板、海信、TCL 等），**同等收录、同等展示**。
   不收海外版/港台版、白牌/非主流生态链品牌。
   - 分组维度是**品牌**，任何品牌都不作为「小米的竞品」呈现；品类简介、选购建议、文案里不要出现这类说法。
   - 每款产品必须有 `brand` 字段。小米/米家系（产品名以「米家」「小米」「Xiaomi」开头）统一填 `小米`。
   - **`brand` 按零售商品名牌归类，不按代工/协议厂商划分**：`miot_model` 的厂商前缀（zhimi、dmaker、chunmi、
     fengmi、leshow、deerma、loock、lumi、viomi、yeelink 等）只说明生态链代工方，零售挂牌仍是米家/小米，`brand` 不变。
   - ⚠️ **本条已于 2026-10-01 取代**更早的「只收录小米自有品牌」口径（见第 8 节历史说明）。
2. 同一硬件不同固件改版视为**同一型号**；同一商品名称/系列跨年份有**实质性迭代**（型号代码、核心性能、能效、结构或关键功能变化）才拆成不同版本。
3. **版本后缀命名**：`name` 用「（YYYY款）」结尾，如 `米家空调 巨省电Pro 大1匹（2025款）`；年份查不到用「新款 / 旧款」并在后续补齐。不得因促销/颜色/固件等无关变更拆分。
4. 来源优先级：**官方**（品牌商城 / 官网规格页 / 说明书 PDF）> **权威第三方**（ZOL / 太平洋 / 苏宁 / 京东，需两处相互印证）> **一般媒体**（只能印证，不能单独定值）> **仅作交叉印证**（miot-spec 等，不能以其缺失否定型号存在）。
5. **禁止编造/估算**：查不到就写 `"查不到"` 或 `"—"`，数值字段确实无值也给 `"—"`（校验会提示「排序时沉底」，属已知提示）。
6. **额定 vs 实测双口径**：同一型号两者都存在时拆两列分别标注，不可混用。
7. 去重先按**型号代码**再按名称；海外版判据：大陆官方渠道检索不到 + 可确认面向海外/港台。
8. **竞品副分组**：竞品同样要落进品类的副分组维度（`schema.facets[0]`）。没有分类依据的保持「未归类」，
   不猜；批量归类用 `python scripts/classify-facets.py`，补证据用 `python scripts/fetch-evidence-2.py`。

---

## 3. 当前进度

### 已完成（数据规模）

| 指标 | 数值 |
| --- | --- |
| 一级品类 / 小品类 | **6 / 40**（见 `data/categories.json`，两层结构） |
| 产品 | **1036 款** |
| 品牌 | **51 个**（小米 418 · 其他 618） |
| 官方产品图 | **369 张**（≤320px WebP，共约 0.89MB） |
| 竞品副分组归类率 | **590 / 618 = 95.5%**（28 条无依据保持「未归类」） |
| `npm run validate` | 通过，0 error |

核查状态分布：已核验（多源）152 · 已核验（官方商城）199 · 已核验（第三方）618 · 待核验 67。

6 个一级品类分组与 40 个小品类：

| 一级品类 | 小品类 |
| --- | --- |
| 环境与空气 | 空气净化器 / 空调 / 除湿机 / 加湿器 / 电风扇 / 电暖器 |
| 厨房大家电 | 冰箱 / 洗碗机 / 洗衣机 |
| 厨房小家电 | 电饭煲 / 电压力锅 / 微波炉 / 空气炸锅 / 电磁炉 / 破壁机 / 咖啡机 / 电水壶 / 电蒸锅 / 即热饮水机 / 净水器 |
| 清洁电器 | 扫地机器人 / 无线吸尘器 / 洗地机 / 除螨仪 |
| 个护健康 | 吹风机 / 剃须刀 / 电动牙刷 / 理发器 / 足浴器 / 筋膜枪 / 体脂秤 |
| 居家智能 | 智能门锁 / 智能摄像机 / 电视 / 投影仪 / 智能音箱 / 热水器 / 浴霸 / 晾衣机 / 挂烫机 |

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
- 图片：`public/images/<品类>/<产品id>.webp`，统一压缩为 ≤320px WebP。

> 两条踩过的坑：
> 1. **回写必须锚定对象边界**。早期用「从 `"id": "X"` 向后找第一个 `"img": null`」的正则，当 X 本身已有图时会越界写到下一个产品上（曾把空净 6 款产品挂错图）。现在 `mi:apply` 会断言 id 与目标字段之间不出现 `"id"`，越界直接报错。
> 2. **枚举必须按容器限定**。商城搜索页顶部导航/推荐位同样是 `a[href*=product_id]`，只取 `.goods-list .goods-item`，否则会混入手机、平板等无关商品（实测每个关键词都会多出 100+ 条噪音）。

### 未完成（后续可做）

按优先级排：

1. **940 款缺零售型号代码**（1036 款里只有 96 款有）。需逐款查官方规格页 / 说明书 PDF / 铭牌补全。
   ⚠️ MIoT 协议型号（`miot_model`）**不能替代**零售型号代码，两者含义不同。
2. **667 款无产品图**。多数是已停产型号（官方商城无在售条目）与竞品（`img: null`），
   符合规范（校验会提示，属已知提示）。官方老页面里的图多是 CSS 背景，无法可靠对应到具体型号，未采用。
3. **约 1 万个缺失技术字段**：按品类分批补，每项登记来源到 `data/_sources/provenance.json`。
   补之前先跑 `npm run flow:status` 看有没有在修的产品（schema 是共享基础设施）。
4. **竞品副分组剩余 28 条未归类**：加湿器 6、净水器 5、除湿机 4（3 条是工业机，与家用分档维度不匹配）、
   洗碗机 2、咖啡机 2、扫地机器人 3，以及风扇/电暖器/微波炉/冰箱/饮水机/空调各 1。
   第三方比价站在这些字段上普遍不给，需补品牌官方规格页、说明书 PDF、能效标识备案平台。
5. **151 条无 `verify_url` 的已核验记录**：`verify_source` 多为「小米商城（官方产品图）」，
   只证明图片来源不证明参数来源，需补参数级溯源。
6. **竞品 provenance 未逐条登记**：618 款竞品的来源还没写进 `data/_sources/provenance.json`。
7. **价格口径未统一**：`official_price` 是「采集时点的官方商城价」（部分老条目保留的是上市指导价）。
   竞品普遍只有 `ref_price`（第三方报价），两者语义不同不可混用 —— 排序与统计已用 `priceOf()` 做回退。
8. **《型号漏收录初筛报告》已逐条复核**，结论写回该文件末尾；其中 15kg 分区洗烘、430L/610L/216L 冰箱、
   蓝氧智投等候选**未获官方目录证实**，未收录，需查历史发布材料或说明书才能定论。

### 提交与部署

改动直接提交到 `main`，推送即触发部署（`.github/workflows/deploy.yml`：validate → build → Pages）。
推送前必须 `npm run check`（= `validate` + `audit:check`）无 error。



---

## 4. 历史归档：建站初期的工作（2026-09）

> ⚠️ **本节是历史记录**。表中的 `groupBy.key` 是当时的结构（品类维度直接做主分组），
> 2026-10-01 起 `groupBy.key` 统一为 `brand`，这些维度已移到 `schema.facets[0]`。
> 其余设计经验（字段属性约定、`guide` 写法、`imageBase` 指向）仍适用。

### 4.1 三个 schema.json 已创建

| 品类 | id | 当时的 groupBy.key | 分组值 | primaryMetric | imageBase |
| --- | --- | --- | --- | --- | --- |
| 洗衣机 | `washing-machine` | `type` | 滚筒洗烘一体 / 洗烘套装 / 波轮 | `official_price` | `images/washing-machine` |
| 冰箱 | `refrigerator` | `door_type` | 法式多门 / 十字门 / 对开门 / 三门 / 两门 | `official_price` | `images/refrigerator` |
| 扫地机器人 | `robot-vacuum` | `tier` | 入门 / 中端集尘 / 全能基站 / 全能上下水 | `official_price` | `images/robot-vacuum` |

- 分组值已按 products.json 中实际出现的值补全（顺序即界面分组顺序）。
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

### 4.5 校验与构建（2026-09，当时 38 个品类）

```bash
npm run validate    # 38 个品类全部通过，0 error（提示均为「暂无产品图 / 非数值沉底」）
npm run typecheck   # 通过
npm run build       # 通过
```

> 下列数字均为**当时**（2026-09）的状态，现已完全不同，见第 3 节。

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
2. **别只看「校验通过」**：`validate` 会反向检查 `data/` 下的品类目录是否都登记进了 `categories.json`（新增于 2026-10-02），
   但**只遍历已登记的品类** —— 新品类目录里若已放了 `products.json` 却忘了登记，会报错而不是静默跳过。
3. **数值字段与 `"—"`**：schema 声明为 `number` 却填 `"—"` 的产品排序会沉底，属预期提示，不必强修。
4. **历史数据坑（供参考）**：
   - 空气净化器宠物款曾误用国际版 `AC-M30-SC`，已改为国内在售 `AC-M31-SC`；
   - 6 Max 的 CADR 曾出现 ZOL(1655/1151) 与太平洋(1500/1000) 冲突，最终按 ZOL 取值；
   - miot-spec 类参考站存在大量固件重复条目且收录不全，**只用于交叉印证，不能当准绳**。
5. **提交信息**：仓库历史提交信息目前不规整（多为同一句），后续建议按 `feat/fix/docs` 规范提交。
6. **第三方同义叫法会静默匹配落空**（2026-10-02 批量归类时踩了 6 处，写映射表务必注意）：
   - 咖啡机写的是「**意大利式**」不是「意式」——`'意式' in '意大利式'` 为 **False**
   - 电暖器的油汀在第三方那叫「**欧式快热炉**」「铝片散热式」
   - 嵌入式空调标的是「**嵌入式空调**」不是「中央空调」
   - 完整对照表见 `skills/appliance-data-curation/SKILL.md`「太平洋产品报价」节的同义叫法表。
7. **小米商城官方 API 必须带 Referer**：`api2.order.mi.com/product/view` 不带
   `-H "Referer: https://www.mi.com/"` 会返回「请求来源不合法」。这个接口比官网页面好用得多 ——
   返回 `class_parameters`（官方额定参数）与 `buy_option`（能判断某「型号」是否只是同一 product_id
   下的规格选项，F305 的判定就是靠它）。
8. **型号核实不能只比对型号字符串**：太平洋与 ZOL 都有录入错误（把 72LW 匹数标成 1.5匹、
   命名混乱）。正确做法是**把该型号页的制冷量/制热量/风量/噪音与库内数值逐项比对**，
   全等才判确认 —— 空调/冰箱/洗衣机型号核实就是这么做的。
9. **小米商城站内搜索接口已失效**：`www.mi.com/search?keyword=` 返回的是**全站推荐位**
   （音箱/手机/显示器），不是搜索结果，不能用来找 `product_id`。

---

## 6. 历史归档：首批三个品类（2026-09 建立，当时全站仅 5 个品类）

> ⚠️ **本节是历史记录，不是当前状态**。当前规模见第 3 节（40 个小品类 / 1036 款）。
> 保留是为了记录建站初期的 schema 设计与踩坑，实际数据以 `data/*/products.json` 为准。

**洗衣机**：`groupBy.type` = 滚筒洗烘一体 / 洗烘套装 / 波轮；`primaryMetric` = `official_price`

**冰箱**：`groupBy.door_type` = 法式多门 / 十字门 / 对开门 / 三门 / 两门；`primaryMetric` = `official_price`

**扫地机器人**：`groupBy.tier` = 入门 / 中端集尘 / 全能基站 / 全能上下水；`primaryMetric` = `official_price`

三个品类建立时的共同点（现在仍是通例）：

- `groupBy.order` 按 `products.json` 中实际出现的分组值补全，顺序即界面分组顺序
- `official_price` = `number` + `card: chip` + `sortable` + `stat`；`year` = `number` + `sortable`；
  `pros`/`cons`/`tags` = `tags` + `tagVariant`（green/red/blue）
- 都补了 `guide`（按场景选购建议），**文案只引用 `products.json` 里已有的参数，不新增臆测数据**
- `schema.imageBase` 指向对应的 `images/<品类>/`

---

## 7. 参考

- 收录规范：[skills/appliance-data-curation/SKILL.md](skills/appliance-data-curation/SKILL.md)
- 字段/维护说明：[README.md](README.md)
- 协作规范：[AGENTS.md](AGENTS.md)
- 校验脚本：[scripts/validate-data.mjs](scripts/validate-data.mjs)
- 流转工具：[scripts/flow.mjs](scripts/flow.mjs)
- 部署流程：[.github/workflows/deploy.yml](.github/workflows/deploy.yml)

---

## 8. 口径变更历史（旧口径已被取代）

按规范，**历史审核报告不改写**，但下面这些口径已被取代，新工作一律按现行版执行：

| 旧口径 | 现行口径 | 变更时间 |
| --- | --- | --- |
| 「只收录米家/小米（小米自有品牌），不收其他品牌」 | 多品牌同等收录同等展示，`groupBy` 为品牌 | 2026-10-01 |
| 「品类维度末位放一个『竞品』分组」 | 竞品进品牌主分组；品类维度降为 `facets` 副分组 | 2026-10-01 |
| `verify_status` 只有三档（多源 / 官方商城 / 待核验） | 四档，增 `已核验（第三方）` | 2026-10-01 |
| 「严禁用媒体参数补齐」 | 媒体**可作印证**（两家独立媒体一致），但不能单独定值 | 2026-10-01 |
| 「直接编辑 `products.json` 追加产品」 | 走分区流转，只有 `flow:publish` 能写已入库区 | 2026-10-02 |
| 「审核前拍快照锁冻结范围」 | 快照锁降级为结构冻结工具；日常互斥由分区天然保证 | 2026-10-02 |
| 图片 ≤640px JPEG | ≤320px WebP（卡片展示位 96×112 CSS px，DPR 3 只需 288px） | 2026-10-01 |
| 「`tier` 等值必须在 `groupBy.order` 里」 | 品类维度值在 `facets[0].order` 里；`groupBy` 固定 `brand` | 2026-10-01 |
| `brand` 按代工方划分（云米代工的米家商品算云米） | `brand` 按**零售商品名牌**划分，协议厂商前缀只作溯源线索 | 2026-10-01 |
| 洗地机「吸力/真空度」因单位混乱不收录 | 已按官方 `class_parameters` 核实并回填 | 2026-10-01 |
| `categories.json` 是扁平数组，加一行即新增品类 | 两层结构（一级品类 → `categories` 数组） | 2026-10-01 |

对应的历史报告仍在 `docs/audit/`（**不删不改**），但结论可能已过时 —— 以本文档与 `AGENTS.md` 为准。