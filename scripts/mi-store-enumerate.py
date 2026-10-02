#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""小米商城「在售清单枚举」——Python 版入口（与 scripts/mi-store.mjs enumerate 等价）。

为什么要两个入口：枚举必须走浏览器（商城搜索页是前端渲染的）。
本机若装了 Python 版 Playwright 而没装 Node 版，用这个脚本即可；两者写同一份缓存：

    data/_cache/search-<关键词>.json
    [ { "productId": 19142, "text": "米家石墨烯踢脚线电暖器 2 白色 399元 449元",
        "img": "https://cdn...png", "href": "https://www.mi.com/shop/buy/detail?product_id=19142" } ]

用法：
    python scripts/mi-store-enumerate.py 空调 冰箱 洗衣机
    python scripts/mi-store-enumerate.py --all        # 用 data/categories.json 的名称逐个枚举

依赖：pip install playwright && playwright install chromium
"""
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
CACHE = ROOT / "data" / "_cache"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

EXTRACT_JS = """
() => {
  // 只取搜索结果列表里的卡片：顶部导航/推荐位同样是 a[href*=product_id]，必须按容器限定
  let nodes = [...document.querySelectorAll('.goods-list .goods-item')];
  if (!nodes.length) nodes = [...document.querySelectorAll('a[href*="product_id"]')];
  const seen = new Map();
  for (const node of nodes) {
    const a = node.tagName === 'A' ? node : node.querySelector('a[href*="product_id"]');
    if (!a) continue;
    const img = node.querySelector('img');
    const src = img ? (img.currentSrc || img.src || '') : '';
    const text = (node.innerText || '').replace(/\\s+/g, ' ').trim();
    const pid = new URL(a.href, location.href).searchParams.get('product_id');
    if (!text || !pid || seen.has(pid)) continue;
    seen.set(pid, { productId: Number(pid), text, img: src || null, href: a.href });
  }
  return [...seen.values()];
}
"""


def main(argv):
    keywords = [a for a in argv if not a.startswith("--")]
    if "--all" in argv:
        # categories.json 是两层结构（一级品类 -> 小品类），要摊平后再遍历
        groups = json.loads((ROOT / "data" / "categories.json").read_text(encoding="utf-8"))
        cats = [c for g in groups for c in g.get("categories", [])]
        keywords = [c["name"] for c in cats]
    if not keywords:
        print(__doc__)
        return 1

    from playwright.sync_api import sync_playwright

    CACHE.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1440, "height": 1200}, user_agent=UA)
        page = ctx.new_page()
        for kw in keywords:
            try:
                page.goto(
                    f"https://www.mi.com/search?keyword={kw}",
                    wait_until="domcontentloaded",
                    timeout=60000,
                )
                page.wait_for_timeout(4500)
                for _ in range(3):
                    page.mouse.wheel(0, 2500)
                    page.wait_for_timeout(1100)
                items = page.evaluate(EXTRACT_JS)
            except Exception as e:  # noqa: BLE001
                print(f"  {kw}: 失败 {e}")
                continue
            out = CACHE / f"search-{kw}.json"
            out.write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")
            print(f"  {kw}: {len(items)} 款 → {out.relative_to(ROOT)}")
        browser.close()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
