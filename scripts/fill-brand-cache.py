#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""从竞品缓存（brand-*.json / pconline-*.json）回填丙路品类的空字段。

## 为什么要这个脚本（以及 fill-params.py 为什么跑不出东西）

实测 `python scripts/fill-params.py --cat <丙路品类> --dry` 在 water-purifier /
bath-heater / tv / water-heater 上**全部报「可回填 0 条 / 0 个字段」**，但人工读缓存
原文却能挖出上百条值。根因：

- `brand-*.json` 的结构是 `[{id, name, price, specs:{…}}]`，**`price` 在顶层**；
- 而 `fill-params.py` 的 `pick_price(specs)` 只在 `specs` 里找 `参考价/市场价/价格`，
  顶层 price 它根本不看 → 价格永远 0 命中。

本脚本按 brand 缓存的真实结构取值（顶层 price + specs），并把字段映射按**当前品类的
schema** 校验后再写：schema 里没有的字段一律跳过，所以同一份映射表能安全套用到多个品类。

## 写法

- 匹配：`product.id` 里含缓存条目的 `id`（竞品 id 形如 `sony_2617099`、`tcl_2986362`）。
- 只填**空值**（`null` / `""` / `查不到` / `—`），已有值不覆盖。
- 单位守卫：年份要 4 位且落在 2000–2027；价格 49–999999；浴霸风暖功率 <500W 判错标
  （HANDOFF §0.3 记录的第三方系统性错标）；尺寸串必须含数字与 `×` 或 `mm`。

## 用法

    python scripts/fill-brand-cache.py --dry                 # 只看会填什么
    python scripts/fill-brand-cache.py --cat tv kettle       # 只跑指定品类
    python scripts/fill-brand-cache.py                       # 跑全部丙路品类

写入 `data/_draft/<品类>/`，随后 `npm run flow:submit -- …`。
"""
import argparse
import glob
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D = "2026-10-04"

CATS = ["water-purifier", "kettle", "hair-dryer", "shaver", "toothbrush", "hair-clipper",
        "foot-spa", "massage-gun", "body-scale", "smart-lock", "camera", "tv",
        "projector", "speaker", "water-heater", "bath-heater", "dryer-rack", "garment-steamer"]

# 缓存里的键 → 本站字段（**只有该字段存在于当前品类 schema 时才会写**，所以可以通用）
SPEC_MAP = {
    # 通用
    "产品尺寸": "size", "尺寸": "size", "产品重量": "weight", "重量": "weight",
    "产品容量": "capacity", "容量": "capacity",
    "产品功率": "power", "额定功率": "power", "功率": "power",
    "能效等级": "energy", "控制方式": "control", "上市时间": "year", "发布时间": "year",
    "型号": "model_code",
    # 电视
    "屏幕尺寸": "size_inch", "屏幕刷新频率": "refresh", "屏幕分辨率": "resolution",
    "内存容量": "mem", "存储空间": "mem", "背光性能": "backlight", "HDMI接口": "hdmi",
    # 浴霸
    "取暖方式": "warm_mode", "风暖功率": "heat_power", "吹风功率": "fan_power",
    "换气功率": "vent_power", "照明功率": "light_power",
    "安装开孔尺寸": "open_size", "开孔尺寸": "open_size",
    # 净水器
    "净水流量": "flux", "总净水量": "rated_vol", "滤芯级数": "filter_stages",
    # 热水器
    "加热方式": "heat_mode", "安装方式": "install", "内胆材质": "liner",
    # 投影
    "标准分辨率": "resolution", "分辨率": "resolution", "显示芯片": "dmd",
    "梯形校正": "keystone", "对焦方式": "focus", "投射比": "throw_ratio",
}

BLANK = (None, "", "查不到", "—", "-")


def blank(v):
    return v in BLANK or (isinstance(v, list) and not v)


def ok_year(v):
    m = re.search(r"(20\d{2})", str(v))
    return int(m.group(1)) if m and 2000 <= int(m.group(1)) <= 2027 else None


def ok_price(v):
    try:
        n = float(str(v).replace(",", ""))
    except ValueError:
        return None
    return int(n) if 49 <= n <= 999999 else None


def ok_power(field, v):
    m = re.search(r"(\d+(?:\.\d+)?)", str(v).replace(",", ""))
    if not m:
        return None
    n = float(m.group(1))
    # 浴霸风暖功率第三方常少写 100 倍（HANDOFF §0.3：2800W 写成 28W）
    if field == "heat_power" and n < 500:
        return None
    if n <= 0 or n > 20000:
        return None
    return str(v)


def ok_size(v):
    s = str(v)
    return s if re.search(r"\d", s) and ("×" in s or "x" in s.lower() or "mm" in s.lower()) else None


def guard(field, v):
    if field == "year":
        return ok_year(v)
    if field == "official_price":
        return ok_price(v)
    if field == "size":
        return ok_size(v)
    if field in ("power", "heat_power", "fan_power", "vent_power", "light_power"):
        return ok_power(field, v)
    return v if not blank(v) else None


def load_caches(cat):
    """收集与该品类相关的缓存条目：{id: {price, specs, src}}"""
    out = {}
    pats = [os.path.join(ROOT, "data", "_cache", "brand-*.json"),
            os.path.join(ROOT, "data", "_cache", "pconline-*.json")]
    for pat in pats:
        for fp in glob.glob(pat):
            try:
                data = json.load(open(fp, encoding="utf-8"))
            except Exception:  # noqa: BLE001 - 坏缓存跳过，不影响其它
                continue
            items = data if isinstance(data, list) else [data]
            for it in items:
                if not isinstance(it, dict):
                    continue
                iid = str(it.get("id") or "")
                if not iid or not iid.isdigit():
                    continue
                rec = out.setdefault(iid, {"specs": {}, "src": []})
                if it.get("price") is not None and "price" not in rec:
                    rec["price"] = it["price"]
                specs = it.get("specs") or {}
                if isinstance(specs, dict):
                    for k, v in specs.items():
                        rec["specs"].setdefault(k, v)
                fn = os.path.basename(fp)
                if fn not in rec["src"]:
                    rec["src"].append(fn)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cat", nargs="*", default=None, help="只跑指定品类（默认全部丙路）")
    ap.add_argument("--dry", action="store_true")
    args = ap.parse_args()
    cats = args.cat or CATS

    total = {"n": 0, "f": 0}
    plans = {}
    for cat in cats:
        lib = os.path.join(ROOT, "data", cat, "products.json")
        sch = os.path.join(ROOT, "data", cat, "schema.json")
        if not os.path.exists(lib):
            continue
        products = json.load(open(lib, encoding="utf-8"))
        fields = {f.get("key") for f in json.load(open(sch, encoding="utf-8")).get("fields", [])} \
            if os.path.exists(sch) else set()
        caches = load_caches(cat)

        for p in products:
            pid = str(p.get("id") or "")
            # 待入库区已有该产品的订正稿时跳过：再 submit 一份会撞同名文件
            # （批次 1 已提交过 kettle / projector 等品类的一部分产品）
            if os.path.exists(os.path.join(ROOT, "data", "_intake", cat, pid + ".json")):
                continue
            nums = set(re.findall(r"\d{5,}", pid))
            if not nums:
                continue
            hit = next((caches[n] for n in nums if n in caches), None)
            if hit is None:
                continue
            fill = {}
            if "official_price" in fields and blank(p.get("official_price")):
                v = guard("official_price", hit.get("price"))
                if v is not None:
                    fill["official_price"] = (v, hit["src"][0])
            for k, v in hit["specs"].items():
                f = SPEC_MAP.get(k)
                if not f or f not in fields or f in fill:
                    continue
                if not blank(p.get(f)):
                    continue
                gv = guard(f, v)
                if gv is not None:
                    fill[f] = (gv, hit["src"][0])
            if not fill:
                continue
            plans.setdefault(cat, {})[pid] = fill
            total["n"] += 1
            total["f"] += len(fill)

    print(f"\n竞品缓存回填{'（--dry 未写文件）' if args.dry else ''}："
          f"{total['n']} 款 / {total['f']} 个字段\n")
    cmds = []
    for cat, items in sorted(plans.items()):
        print(f"  {cat}: {len(items)} 款")
        if not args.dry:
            for pid, fill in items.items():
                lib = json.load(open(os.path.join(ROOT, "data", cat, "products.json"),
                                     encoding="utf-8"))
                src = next((p for p in lib if p.get("id") == pid), None)
                if src is None:
                    continue
                prod = dict(src)
                labels = set()
                for f, (v, fn) in fill.items():
                    prod[f] = v
                    labels.add("小米商城" if fn.startswith(("search-", "product-"))
                               else "太平洋电脑网")
                vs = prod.get("verify_source") or []
                if isinstance(vs, str):
                    vs = [vs] if vs else []
                for lb in labels:
                    if lb not in vs:
                        vs.append(lb)
                prod["verify_source"] = vs
                prod["verify_date"] = D
                prod["updated_at"] = D
                note = f"{D} 补 {'、'.join(fill)}（来源：{'、'.join(sorted(labels))}）"
                old = prod.get("change_log") or ""
                prod["change_log"] = (old + "；" if old else "") + note
                if labels and prod.get("verify_status") == "待核验":
                    prod["verify_status"] = "已核验（第三方）"
                out = os.path.join(ROOT, "data", "_draft", cat)
                os.makedirs(out, exist_ok=True)
                with open(os.path.join(out, pid + ".json"), "w", encoding="utf-8") as fh:
                    json.dump(prod, fh, ensure_ascii=False, indent=2)
                    fh.write("\n")
            ids = " ".join(f"{cat}/{i}" for i in sorted(items))
            cmds.append(f"npm run flow:submit -- {ids} --by bing")
    if cmds:
        sh = os.path.join(ROOT, "data", "_cache", "_bing_submit2.ps1")
        open(sh, "w", encoding="utf-8").write("\n".join(cmds) + "\n")
        print(f"\n  提交命令：{os.path.relpath(sh, ROOT)}（{len(cmds)} 条）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
