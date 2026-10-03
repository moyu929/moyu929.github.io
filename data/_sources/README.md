# 采集源清单（人工维护）

本目录存放**采集流水线的人工输入与溯源记录**，不是站点数据，不会被 `src/data.ts` 加载。

## images.json — 产品图下载清单

`{ "品类id/产品id": "图片URL" }`。

```json
{
  "air-conditioner/jso_15p": "https://cdn.cnbj1.fds.api.mi-img.com/nr-pub/xxxx.png"
}
```

运行 `npm run mi:images` 会按此清单把官方**原图**下载到 `data/_cache/img-raw/`（不入库）；
再由 `npm run img:webp` 转成 ≤320px WebP 写入 `public/images/<品类id>/`，
并回写 `img` 字段（写回带对象边界守卫，写错会直接报错而不是静默写歪）。

图片 URL 的来源优先级见 [`skills/appliance-data-curation/SKILL.md`](../../skills/appliance-data-curation/SKILL.md)：
官方商城/官网图 > 官方说明书 > 权威第三方。**不要**用来源不明的图。

## provenance.json — 逐条溯源

记录每个产品的数据来自哪些来源、链接与核验时间。`verify_status` 的判定依据要能落到这里
（或 `patches/*.json` 的 `_来源`）。当前竞品条目尚未逐条登记，见 `HANDOFF.md` 未完成清单第 6 条。

## patches/ — 字段补丁留档

`npm run mi:apply` 的输入，结构 `{ "品类/产品id": { 字段: 值 } }`；
文件内用 `_来源` 记录每条数据的出处，便于后续复核。

```json
{
  "heater/ht_kick2": { "power": 2200, "ipx": "IPX4", "size": "1025×134×197.5mm" }
}
```

只写**已核实**的值；不确定就留 `"查不到"`，禁止估算。

## 抓取清单（两个）

- `brand-targets.json`：`scripts/import-brands.py` 的竞品批量导入清单。
- `pconline-targets.json`：`scripts/pconline-specs.py` 的太平洋规格页抓取清单
  （结果落 `data/_cache/pconline-*.json`）。

## shared-model-codes.json — 重复型号例外登记

同一品类内 `model_code` 共用（同机型不同 SKU）的登记与依据；`npm run lint` 会按此放行
（否则会报"重复型号"）。新发现的共用必须先登记依据再放行，不能直接无视报错。