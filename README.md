# 家电横评

家电参数对比静态站点，Vite + Vue 3 + TypeScript，数据靠手改 JSON 维护，推送到 `main` 由 GitHub Actions 自动构建发布到 GitHub Pages。

线上地址：https://moyu929.github.io

## 本地开发

```bash
npm install
npm run dev        # 开发服务器
npm run validate   # 校验 data/ 下的 JSON
npm run build      # 构建到 dist/
npm run preview    # 预览构建产物
```

## 目录结构

```
data/
├─ categories.json           品类清单（首页入口）
└─ air-purifier/
   ├─ schema.json            字段定义：显示位置、单位、能否排序
   └─ products.json          产品数据（日常只改这个）
public/images/air-purifier/  产品图，文件名 = 产品 id
src/
├─ types.ts                  schema 与产品的类型定义
├─ data.ts                   品类数据懒加载
├─ format.ts                 字段值格式化
├─ useProductFilter.ts       筛选 / 排序 / 搜索
├─ useCompare.ts             对比队列
├─ components/               卡片、工具条、对比抽屉
└─ views/                    首页、品类页
scripts/
├─ extract-legacy.mjs        从旧单文件 HTML 提取数据（一次性迁移）
├─ validate-data.mjs         数据校验
├─ mi-store.mjs              小米商城采集流水线（enumerate/detail/specs/images/apply）
└─ mi-store-enumerate.py     同一流水线的 Python 版枚举入口（只装了 Python Playwright 时用）
data/_sources/              采集源清单（人工维护）：images.json 图片清单、patches/ 字段补丁与出处
```

## 日常维护

### 添加一款产品

编辑 `data/<品类>/products.json`，追加一个对象。字段照抄同品类的其他产品即可：

```json
{
  "id": "7pro",
  "img": "7pro.jpg",
  "name": "米家空气净化器 7 Pro",
  "tier": "旗舰",
  "official_price": 2299,
  "cadr_pm": 800
}
```

- `id` 必须唯一，只用字母数字和 `._-`，它同时也是图片文件名
- 产品图放到 `public/images/<品类>/`，`img` 填文件名；暂时没图就写 `null`
- `tier` 的值必须在 `schema.json` 的 `groupBy.order` 里，否则不会显示

改完跑 `npm run validate` 检查。

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

### 添加一个新品类

1. 新建 `data/<品类id>/schema.json` 和 `products.json`，可复制 `air-purifier/` 改
2. 新建 `public/images/<品类id>/` 放产品图
3. 在 `data/categories.json` 里加一行：

```json
{
  "id": "refrigerator",
  "name": "冰箱",
  "icon": "🧊",
  "description": "容积 / 能耗 / 制冷方式"
}
```

不需要写任何 Vue 代码 —— 卡片、对比表、筛选排序都由 schema 驱动生成。

## 数据采集流水线

新增品类或补数据时，用 `scripts/mi-store.mjs` 从官方渠道取数，避免手抄：

```bash
npm run mi:enumerate -- 洗碗机 净水器        # 枚举在售商品（需 Playwright）
python scripts/mi-store-enumerate.py 空调    # 等价入口（只有 Python Playwright 时用）
npm run mi:detail -- 19142 24615            # 官方商品详情（名称/现价/划线价/官方图）
npm run mi:specs -- https://www.mi.com/induction-cooker/specs   # 官方规格页 → 参数表
npm run mi:images                            # 按 data/_sources/images.json 下载产品图
npm run mi:apply -- data/_sources/patches/xxx.json              # 写入字段补丁
```

官方渠道拿不到时的两个补充来源（**只作交叉印证，禁止照抄**）：

```bash
npm run miot:crawl                     # 抓 home.miot-spec.com 型号库（分页/并发，缓存 + 日志）
npm run miot:match                     # 按官方名精确匹配，补 miot_model 字段
npm run pconline:specs                 # 抓太平洋规格表（清单：data/_sources/pconline-targets.json）
```

- 枚举结果缓存在 `data/_cache/`（已 gitignore），可反复复查。
- 字段补丁放在 `data/_sources/patches/`，文件内用 `_来源` 记录出处；`mi:apply` 按 `品类/产品id` 定位写入，越界会报错而不是写歪。
- 采集与核验规则见 `skills/appliance-data-curation/SKILL.md`（来源优先级、禁止估算、去重口径、第三方错标陷阱等）。
- 每条产品都带 6 个审核标注字段（`verify_status` / `verify_date` / `verify_source` / `verify_url` / `change_log` / `updated_at`），逐条溯源记录在 `data/_sources/provenance.json`。

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

- 首屏前 6 张卡片用 `loading="eager"` + `fetchpriority="high"`，其余 `loading="lazy"`；
  全部懒加载会让首屏图片排在关键渲染之后，出现可见的空白闪烁。
- 所有 `<img>` 都带 `width`/`height`（内在 320×320）与 `decoding="async"`，配合 `.thumb` 固定尺寸避免布局抖动。
- 缩略图容器自带底色（`--surface-alt`），图片未到时不会白闪。

## 多 Agent 并行协作

本仓库可能同时有多个 Agent 在工作（一个采集/更新，一个按用户指令审核）。
协作规范见 **[AGENTS.md](AGENTS.md)**，核心是「审核冻结协议」：

```bash
npm run audit:status                   # 动手前先查：哪些产品正被审核冻结
npm run audit:snapshot -- --label "空气净化器验收" --by agent-b --category air-purifier
npm run audit:check                    # 检测冻结范围内是否有人越界改过
npm run audit:release -- <快照id>       # 审核完成，解除冻结
npm run check                          # = validate + audit:check，推送前跑
```

被快照覆盖的产品在 `release` 之前**任何一方都不得改动**，避免一方按过期数据审核、另一方已改过。
审核报告归档在 `docs/audit/`。

## 目录速览

```
AGENTS.md                 多 Agent 协作规范（先读这个）
HANDOFF.md                阶段交接记录
skills/                   技能定义（客户端无关；.trae/.claude 下只放指针）
docs/audit/               审核报告归档
data/<品类>/{schema,products}.json
data/_sources/            溯源、补丁、图片清单（入库）
data/_cache/              抓取缓存（不入库）
data/_locks/              审核快照锁（两个 Agent 的共享状态）
scripts/                  采集、校验、审核锁工具
```

## 部署

推送到 `main` 即触发 `.github/workflows/deploy.yml`：校验数据 → 构建 → 发布到 Pages。

首次部署需在仓库 **Settings → Pages → Build and deployment → Source** 选择 **GitHub Actions**。

由于 GitHub Pages 没有 SPA 路由回退，构建时会把 `index.html` 复制一份为 `404.html`，保证直接访问 `/air-purifier` 这类子路径也能正常加载。
