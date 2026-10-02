#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""把三路证据（太平洋规格 / ZOL 参数 / 360 搜索摘要）汇成按品类分文件的证据摘要。

产物在 data/_cache/facet-evidence/digest-<品类>.md，只作人工复核用，不入库。
用法：python scripts/build-facet-digest.py heater kettle
"""
import importlib.util
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, "data", "_cache", "facet-evidence")

spec = importlib.util.spec_from_file_location("f", os.path.join(ROOT, "scripts", "fetch-facet-evidence.py"))
F = importlib.util.module_from_spec(spec)
spec.loader.exec_module(F)

# facet 判定真正用得上的字段，排前面
KEY_HINT = ["产品类型", "类别", "产品类别", "安装方式", "使用方式", "加热方式", "取暖方式",
            "控制方式", "空调类型", "使用类型", "工作方式", "雾化方式", "加湿方式",
            "制冷类型", "结构类型", "门型", "开门方式", "外形", "摆位", "放置方式",
            "净水机原理", "滤芯种类", "日除湿量", "水箱容积", "加湿量", "产品容量",
            "套数", "餐具容量", "噪音", "能效等级", "主要特点", "其它性能", "其他性能",
            "产品功率", "功率", "输入功率", "额定功率", "灯暖功率", "取暖功率", "风暖功率",
            "型号", "特点"]


def pick(specs):
    if not specs:
        return []
    out = [(k, v) for k, v in specs.items() if k in KEY_HINT]
    out += [(k, v) for k, v in specs.items() if k not in KEY_HINT and k not in dict(out)]
    return out


def main():
    cats = sys.argv[1:]
    ev = json.load(open(os.path.join(CACHE, "evidence.json"), encoding="utf-8"))
    se = {}
    p = os.path.join(CACHE, "search-so.json")
    if os.path.exists(p):
        for r in json.load(open(p, encoding="utf-8")):
            se[(r["cat"], r["id"])] = r
    by = {}
    for r in ev:
        by.setdefault(r["cat"], []).append(r)
    for cid in sorted(by):
        if cats and cid not in cats:
            continue
        s = json.load(open(os.path.join(ROOT, "data", cid, "schema.json"), encoding="utf-8"))
        fk = s["facets"][0]["key"]
        lines = ["# %s  副分组=%s  可选值=%s" % (cid, fk, s["facets"][0]["order"]), ""]
        for r in by[cid]:
            lines.append("## %s | %s | %s | ref_price=%s" % (
                r["id"], r["name"], r["brand"], r.get("price")))
            lines.append("- verify_url: %s" % r["verify_url"])
            if r.get("pconline"):
                lines.append("- 太平洋规格:")
                for k, v in pick(r["pconline"]):
                    lines.append("    - %s: %s" % (k, v))
            else:
                lines.append("- 太平洋规格: （未取到）")
            z = r.get("zol")
            if z:
                lines.append("- ZOL[%s]: %s" % (z.get("name"), z.get("url")))
                for k, v in pick(z.get("specs") or {}):
                    lines.append("    - %s: %s" % (k, v))
            else:
                lines.append("- ZOL: （未匹配到该型号）")
            sr = se.get((cid, r["id"]))
            if sr:
                lines.append("- 360 搜索 [%s]:" % sr["query"])
                for it in sr["results"][:6]:
                    t = re.sub(r"\s+", " ", it.get("text", ""))
                    lines.append("    * %s | %s" % (it.get("title", "")[:110], it.get("site", "")))
                    lines.append("      %s" % t[:420])
            lines.append("")
        dest = os.path.join(CACHE, "digest-%s.md" % cid)
        open(dest, "w", encoding="utf-8", newline="\n").write("\n".join(lines))
        print("写入 %s（%d 条）" % (dest, len(by[cid])))


if __name__ == "__main__":
    main()
