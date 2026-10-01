#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""太平洋产品报价：按品类/品牌枚举型号（第三方，参数仅作交叉印证）。

为什么需要它：小米商城只覆盖小米/米家，收录其他品牌必须换数据源。
太平洋的**品牌页**是服务端渲染的，可以直接抓出「型号名 + 参考价 + 参数页 id」；
品类首页是 JS 壳（抓不到），所以必须从品牌页入手。

用法：
    python scripts/pconline-brands.py models <品类目录> <品牌slug>
    python scripts/pconline-brands.py brands <品类目录>
    python scripts/pconline-brands.py probe

已确认可用的品类目录（pconline 自己的路径名，与本站品类 id 不一一对应）：
    cleaning_machine 洗地机/扫地机   vacuum_cleaner 吸尘器   yuba 浴霸
    washer 洗衣机   water_purifier 净水器   rice_cooker 电饭煲
    induction_cooker 电磁炉   electric_kettle 电水壶   fan 风扇
    humidifier 加湿器   water_heater 热水器   projector 投影仪   oven 烤箱
"""
import re
import sys
import time
import urllib.request

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass

BASE = "https://g.pconline.com.cn/product"
# 注意：列表页要用**桌面站**（product.pconline.com.cn），移动站 g.pconline.com.cn 的品类/品牌页是 JS 壳。
DESK = "https://product.pconline.com.cn"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

CANDIDATE_CATS = [
    # 已验证
    "cleaning_machine", "vacuum_cleaner", "yuba", "washer", "water_purifier",
    "rice_cooker", "induction_cooker", "electric_kettle", "fan", "humidifier",
    "water_heater", "projector", "oven",
    # 待探测
    "air_conditioner", "aircon", "kongtiao", "fridge", "bingxiang", "refrigerator",
    "dishwasher", "xiwanji", "tv", "dianshi", "sweeper", "saodijiqiren", "robot",
    "microwave", "weibolu", "soymilk", "doujiangji", "shaver", "tidaxu",
    "electric_toothbrush", "hairdryer", "dehumidifier", "coffee_machine",
    "smart_lock", "camera", "speaker", "body_fat_scale", "blender",
]


def fetch(url, tries=3):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Referer": BASE + "/"})
            with urllib.request.urlopen(req, timeout=25) as r:
                raw = r.read()
            for enc in ("gb18030", "utf-8"):
                try:
                    return raw.decode(enc)
                except UnicodeDecodeError:
                    continue
            return raw.decode("utf-8", "replace")
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(2 + i * 2)
    raise last


def cmd_models(cat, brand):
    """抓品牌页，返回 [(id, 名称, 价格)]。"""
    html = fetch(f"{DESK}/{cat}/{brand}/")
    pat = re.compile(rf"{re.escape(BASE)}/{re.escape(cat)}/{re.escape(brand)}/(\d{{5,9}})\.html")
    out = {}
    for m in pat.finditer(html):
        pid = m.group(1)
        seg = html[m.start() : m.start() + 1200]
        name = None
        for key in ("alt", "title"):
            mm = re.search(rf'{key}="([^"]{{4,80}})"', seg)
            if mm:
                name = mm.group(1).strip()
                break
        if not name:
            # 退回：链接标签内的可见文字
            txt = re.sub(r"<[^>]+>", " ", seg)
            txt = re.sub(r"\s+", " ", txt).strip()
            cand = txt[:60]
            name = cand if len(cand) >= 4 else None
        pm = re.search(r"[¥￥]\s*(\d[\d,]*)", seg)
        price = pm.group(1) if pm else ""
        if name and pid not in out:
            out[pid] = (pid, name, price)
    print(f"{cat}/{brand}：{len(out)} 款")
    for pid, name, price in list(out.values())[:60]:
        print(f"   {pid:<9} {name[:46]:<48} {price}")
    return out


def cmd_brands(cat):
    """品类首页 -> 该品类下所有品牌 slug（按出现次数排序）。"""
    html = fetch(f"{DESK}/{cat}/")
    slugs = {}
    for m in re.finditer(rf"/{re.escape(cat)}/([a-z0-9_]+)/\d{{5,9}}\.html", html):
        slugs[m.group(1)] = slugs.get(m.group(1), 0) + 1
    print(f"品类 {cat}：{len(slugs)} 个品牌")
    for b, n in sorted(slugs.items(), key=lambda x: -x[1]):
        print(f"   {b:<18} {n}")
    return slugs


def cmd_probe():
    """探测哪些品类目录可用：抓桌面站品类首页，数一数里面有多少型号链接。"""
    for c in CANDIDATE_CATS:
        try:
            html = fetch(f"{DESK}/{c}/", tries=1)
            n = len(set(re.findall(rf"/{re.escape(c)}/[a-z0-9_]+/(\d{{5,9}})\.html", html)))
            print(f"  {'OK' if n else '--'} {c:<20} 首页型号链接 {n} 条")
        except Exception as e:  # noqa: BLE001
            print(f"  ✗  {c:<20} {str(e)[:40]}")
        time.sleep(1.0)


if __name__ == "__main__":
    a = sys.argv[1:]
    if not a or a[0] == "probe":
        cmd_probe()
    elif a[0] == "brands" and len(a) > 1:
        cmd_brands(a[1])
    elif a[0] == "models" and len(a) > 2:
        cmd_models(a[1], a[2])
    else:
        print(__doc__)
