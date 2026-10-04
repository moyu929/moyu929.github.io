#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""按型号批量跑 360 搜索，把结果摘要落到缓存，供副分组补证时逐条查阅。

360（so.com）是本机实测能用的少数几个通用检索入口之一，摘要里常直接带
「类别:欧式快热炉」「全自动意式咖啡机」这类分类口径，比正文页更好挖。

用法：
    python scripts/batch-model-search.py                 # 全部未归类的非小米品牌产品
    python scripts/batch-model-search.py heater kettle   # 指定品类
    python scripts/batch-model-search.py --engine baidu
"""
import argparse
import importlib.util
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
spec = importlib.util.spec_from_file_location("snip", os.path.join(ROOT, "scripts", "web-snip.py"))
snip = importlib.util.module_from_spec(spec)
spec.loader.exec_module(snip)

# 品牌中文名，用于让搜索引擎更准地命中商品页
BRAND_HINT = {
    "格力": "格力", "美的": "美的", "飞利浦": "飞利浦", "松下": "松下", "澳柯玛": "澳柯玛",
    "小熊": "小熊 Bear", "沁园": "沁园", "安吉尔": "安吉尔", "海尔": "海尔", "3M": "3M",
    "象印": "象印", "九阳": "九阳", "苏泊尔": "苏泊尔", "克鲁伯": "克鲁伯 KRUPS",
    "北美电器": "北美电器 ACA", "西门子": "西门子", "老板": "老板", "奥克斯": "奥克斯",
    "林内": "林内 Rinnai", "石头": "石头", "大疆": "大疆 DJI", "云鲸": "云鲸", "德业": "德业",
    "多乐信": "多乐信", "欧普": "欧普", "戴森": "戴森 dyson",
}


def model_of(name):
    m = re.sub(r"[（(].*?[)）]", " ", name or "")
    return re.sub(r"\s+", " ", m).strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cats", nargs="*")
    ap.add_argument("--engine", default="so", choices=list(snip.ENG))
    ap.add_argument("--out", default=os.path.join(ROOT, "data", "_cache", "facet-evidence"))
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()

    spec2 = importlib.util.spec_from_file_location(
        "fetch", os.path.join(ROOT, "scripts", "fetch-facet-evidence.py"))
    fetch = importlib.util.module_from_spec(spec2)
    spec2.loader.exec_module(fetch)

    items = [x for x in fetch.unclassified() if not args.cats or x["cat"] in args.cats]
    print("待搜 %d 条" % len(items))
    fn = snip.ENG[args.engine]

    def job(it):
        q = '"%s" %s' % (model_of(it["name"]), BRAND_HINT.get(it["brand"], ""))
        try:
            res = fn(q)
        except Exception as e:  # noqa: BLE001
            res = [{"url": "", "title": "", "site": "", "text": "ERR " + str(e)}]
        return {"cat": it["cat"], "id": it["id"], "name": it["name"],
                "brand": it["brand"], "query": q, "results": res[:8]}

    out = []
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        for i, r in enumerate(ex.map(job, items), 1):
            out.append(r)
            if i % 10 == 0:
                print("  %d/%d" % (i, len(items)), flush=True)
            time.sleep(0.4)

    os.makedirs(args.out, exist_ok=True)
    path = os.path.join(args.out, "search-%s.json" % args.engine)
    json.dump(out, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("写入 %s（%d 条）" % (path, len(out)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
