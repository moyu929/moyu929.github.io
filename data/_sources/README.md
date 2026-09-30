# 采集源清单（人工维护）

本目录存放**采集流水线的人工输入**，不是站点数据，不会被 `src/data.ts` 加载。

## images.json

产品图下载清单：`{ "品类id/产品id": "图片URL" }`。

```json
{
  "air-conditioner/jso_15p": "https://cdn.cnbj1.fds.api.mi-img.com/nr-pub/xxxx.png"
}
```

运行 `npm run mi:images` 会按此清单下载到 `public/images/<品类id>/<产品id>.<ext>`，
并把文件名写回 `products.json` 的 `img` 字段（写回带对象边界守卫，写错会直接报错而不是静默写歪）。

图片 URL 的来源优先级见 `.trae/skills/appliance-data-curation/SKILL.md`：
官方商城/官网图 > 官方说明书 > 权威第三方。**不要**用来源不明的图。

## specs-urls.json

官方规格页清单：`{ "品类id": { "产品id或型号": "https://www.mi.com/xxx/specs" } }`。

运行 `npm run mi:specs <url>` 会把规格页解析成 `{ 参数名: 值 }` 并缓存到 `data/_cache/`，
再由人工（或 `mi:apply`）判断映射到 schema 的哪个字段。

> 注意：不是所有官方规格页都服务端渲染。TV/投影等新页是前端渲染的，`specs` 子命令会提示
> 「解析出 0 项」，此时改用 `web_fetch` 类工具或第三方参数页（需两处印证）。

## 字段补丁（patch.json）

`mi:apply` 接受如下结构，按 `品类/产品id` 精确定位后写入：

```json
{
  "heater/ht_kick2": { "power": 2200, "ipx": "IPX4", "size": "1025×134×197.5mm" }
}
```

只写**已核实**的值；不确定就留 `"查不到"`，禁止估算。
