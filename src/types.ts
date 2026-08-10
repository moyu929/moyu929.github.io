/** 字段值类型：决定排序与对比时如何比较 */
export type FieldType = 'text' | 'number' | 'tags'

/** 字段在卡片上的呈现位置 */
export type CardSlot =
  | 'title' // 卡片标题
  | 'chip' // 标题下方的价格胶囊
  | 'grid' // 参数网格（两列对齐）
  | 'tag' // 底部标签区

export type TagVariant = 'green' | 'red' | 'blue'

export interface FieldDef {
  /** 对应 products.json 中的键名 */
  key: string
  /** 展示用的中文名 */
  label: string
  /** 数值单位，如 m³/h；渲染时追加在值后面 */
  unit?: string
  type: FieldType
  /** 值前缀，如价格的 ¥ */
  prefix?: string
  /** 出现在卡片的哪个区域；省略则只在对比表中出现 */
  card?: CardSlot
  /** 是否进入对比表 */
  compare?: boolean
  /** 是否可作为排序依据 */
  sortable?: boolean
  /** 是否参与顶部统计（均价、区间等，仅 number 生效） */
  stat?: boolean
  /** type 为 tags 时的配色 */
  tagVariant?: TagVariant
  /** type 为 tags 时每个标签的前缀符号 */
  tagPrefix?: string
}

/** 分组维度定义，如空净的「档位」 */
export interface GroupByDef {
  key: string
  label: string
  /** 分组展示顺序 */
  order: string[]
  /** 各分组的主题色 */
  colors: Record<string, string>
}

export interface GuideItem {
  scene: string
  advice: string
}

export interface CategorySchema {
  id: string
  name: string
  subtitle: string
  /** 图片目录，相对于 public/ */
  imageBase: string
  groupBy: GroupByDef
  /** 参与关键词搜索的字段 */
  searchFields: string[]
  /** 默认排序所用的数值字段 */
  primaryMetric: string
  fields: FieldDef[]
  guide?: {
    title: string
    items: GuideItem[]
  }
}

/** 单个产品：固定 id/name/img，其余字段由 schema 定义 */
export interface Product {
  id: string
  name: string
  /** 图片文件名；null 表示暂无图片 */
  img: string | null
  [key: string]: unknown
}

/** categories.json 中的品类条目 */
export interface CategoryMeta {
  id: string
  name: string
  icon: string
  description: string
}

/** 一个品类的完整数据 */
export interface CategoryData {
  schema: CategorySchema
  products: Product[]
}
