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
└─ validate-data.mjs         数据校验
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

## 部署

推送到 `main` 即触发 `.github/workflows/deploy.yml`：校验数据 → 构建 → 发布到 Pages。

首次部署需在仓库 **Settings → Pages → Build and deployment → Source** 选择 **GitHub Actions**。

由于 GitHub Pages 没有 SPA 路由回退，构建时会把 `index.html` 复制一份为 `404.html`，保证直接访问 `/air-purifier` 这类子路径也能正常加载。
