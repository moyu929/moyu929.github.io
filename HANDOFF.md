# 交接文档：家电横评站点 —— 品类扩充与数据订正

> 交接背景：当前环境不稳定（会话多次中断、文件写入偶发截断），上一轮工作把「洗衣机 / 冰箱 / 扫地机器人」三个新品类的**产品数据**写好了，但**字段定义（schema）和品类注册没做完**，站点上还看不到这三个品类。
> 接手人请按本文第 5 节的顺序把剩余步骤做完即可。
>
> 数据采集/核验的完整规范见 [.trae/skills/appliance-data-curation/SKILL.md](file:///workspace/.trae/skills/appliance-data-curation/SKILL.md)，**动手前务必先读它**。

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

### 已完成

| 品类 | products.json | schema.json | 已注册进 categories.json | 图片目录 |
| --- | :---: | :---: | :---: | :---: |
| 空气净化器 air-purifier | ✅ 27 款 | ✅ 25 字段 | ✅ | ✅ 20 张图 |
| 空调 air-conditioner | ✅ 14 款 | ✅ 22 字段 | ✅ | ✅ 目录已建（无图，img 全为 null） |
| 洗衣机 washing-machine | ✅ 7 款 | ✅ 18 字段 | ✅ | ✅ 目录已建（无图） |
| 冰箱 refrigerator | ✅ 8 款 | ✅ 18 字段 | ✅ | ✅ 目录已建（无图） |
| 扫地机器人 robot-vacuum | ✅ 9 款 | ✅ 17 字段 | ✅ | ✅ 目录已建（无图） |

- 空气净化器：已删除海外版、修正错误与缺失数据，共 27 款。
- 空调：已按版本后缀规范修订名称（补年份后缀），共 14 款。
- 三个新品类：`schema.json` 已补齐并注册进 `categories.json`，`npm run validate` 现在会校验它们（5 个品类全部通过，0 error）。
- UI：对比浮标重写为「液态玻璃」组件 `src/components/LiquidGlass.vue`（可拖动 + 位置持久化），`CategoryView.vue` 已改为引用它；同时给对比抽屉补了 Esc 关闭。

### 未完成（后续可做）

1. **产品图**：`public/images/<品类>/` 目录已建（含 `.gitkeep`），但三个新品类与空调均无图，`img` 保持 `null`；有图后把文件名填进 `img` 即可。
2. **数据补全**：部分型号代码/参数仍是「查不到」（如冰箱 Pro 至尊版十字508L、扫地机器人 7C / 3C增强版、洗衣机波轮尊享版等），有官方来源时补齐。
3. 已跑通 `npm run validate`、`npm run build`、`npm run typecheck`。


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
npm run validate    # 5 个品类全部通过，0 error（46 条提示均为「暂无产品图 / 非数值沉底」）
npm run typecheck   # 通过
npm run build       # 通过
```

浏览器实测（Playwright）确认：首页 5 个品类入口正常；三个新品类分别渲染 7 / 8 / 9 款产品，分组、统计（均值·区间）、时间轴视图、对比抽屉（含 3 款产品 15 行参数）、明暗主题均正常，控制台无 error/warning。

### 4.6 发布

改动提交到 `main` 即可触发部署（`.github/workflows/deploy.yml`：校验 → 构建 → Pages）。

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

- 收录规范：[.trae/skills/appliance-data-curation/SKILL.md](file:///workspace/.trae/skills/appliance-data-curation/SKILL.md)
- 字段/维护说明：[README.md](file:///workspace/README.md)
- 校验脚本：[scripts/validate-data.mjs](file:///workspace/scripts/validate-data.mjs)
- 部署流程：[.github/workflows/deploy.yml](file:///workspace/.github/workflows/deploy.yml)