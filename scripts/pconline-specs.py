#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""太平洋产品报价（pconline）规格表抓取——第三方交叉印证用。

用途：小米商城商品页参数表由 JS 动态加载、纯 HTTP 抓不到（见 HANDOFF「证据限制」），
而太平洋的 `_detail.html` 是服务端渲染的规格表，可作为**结构化参数的第二来源**。
写进项目时须在 verify_source 标注「太平洋电脑网」，且只作交叉印证，不与官方冲突时以官方为准。

用法：
    python scripts/pconline-specs.py                 # 抓 data/_sources/pconline-targets.json 里的目标
    python scripts/pconline-specs.py --list          # 只打印目标
清单格式：{ "<品类id>": { "<产品id>": {"name": "...", "urlId": 1234567, "path": "cleaning_machine"} } }
缓存：data/_cache/pconline-<品类id>-<产品id>.json
"""
import json
import pathlib
import re
import sys
import time
import urllib.request

try:  # Windows 控制台默认 GBK，勾号等字符会导致 UnicodeEncodeError
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass

ROOT = pathlib.Path(__file__).resolve().parent.parent
CACHE = ROOT / "data" / "_cache"
TARGETS = ROOT / "data" / "_sources" / "pconline-targets.json"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Referer": "https://g.pconline.com.cn/"})
    with urllib.request.urlopen(req, timeout=25) as r:
        raw = r.read()
    for enc in ("gb18030", "utf-8"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", "replace")


CELL = re.compile(r"<t[dh][^>]*>(.*?)</t[dh]>", re.S)
ROW = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S)


def parse_specs(html):
    """把参数表解析成 {参数名: 值}。太平洋的参数表是两列一组或多列的 th/td 混排。"""
    out = {}
    for row in ROW.findall(html):
        cells = [re.sub(r"<[^>]+>", "", c) for c in CELL.findall(row)]
        cells = [re.sub(r"\s+", " ", c).replace("&nbsp;", " ").strip() for c in cells]
        cells = [c for c in cells if c]
        for i in range(0, len(cells) - 1, 2):
            k, v = cells[i], cells[i + 1]
            if k and v and len(k) <= 20 and k not in out:
                out[k] = v
    return out


def main(argv):
    data = {k: v for k, v in json.loads(TARGETS.read_text(encoding="utf-8")).items() if not k.startswith("_")}
    if "--list" in argv:
        for cat, items in data.items():
            for pid, meta in items.items():
                print(f"  {cat}/{pid}  {meta['name']}  ({meta['path']}/{meta['urlId']})")
        return 0

    CACHE.mkdir(parents=True, exist_ok=True)
    ok = fail = 0
    for cat, items in data.items():
        for pid, meta in items.items():
            dest = CACHE / f"pconline-{cat}-{pid}.json"
            if dest.exists():
                ok += 1
                continue
            url = f"https://g.pconline.com.cn/product/{meta['path']}/mijia/{meta['urlId']}_detail.html"
            try:
                specs = parse_specs(fetch(url))
            except Exception as e:  # noqa: BLE001
                print(f"  ✗ {cat}/{pid}: {e}")
                fail += 1
                time.sleep(2)
                continue
            if not specs:
                print(f"  ! {cat}/{pid}: 未解析出参数（页面结构可能不同）")
                fail += 1
                continue
            dest.write_text(
                json.dumps({"cat": cat, "pid": pid, "name": meta["name"], "url": url, "specs": specs},
                           ensure_ascii=False, indent=1),
                encoding="utf-8",
            )
            print(f"  ✓ {cat}/{pid} {meta['name']}: {len(specs)} 项  {list(specs)[:4]}")
            ok += 1
            time.sleep(1.5)
    print(f"\n成功 {ok}，失败 {fail}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
