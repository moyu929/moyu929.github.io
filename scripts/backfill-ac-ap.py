#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""空调 / 净化器 回填批次（2026-10-04，甲路）。

三件事，都只写 `data/_draft/<品类>/`：

1. **小米 product_id 回填**：`verify_url` 为「查不到」的产品，商城商品图与商品名
   的语序跟本站不同（本站「米家空调 柔风 1.5匹」/ 商城「柔风 1.5匹新一级能效
   米家空调」），按名精确反查一直落空。这里用**人工核对过商城权威商品名**的
   product_id 写进 verify_url，再按官方商城 API 回填参数。
   ⚠️ CONFIRMED_IDS 里每一条都必须是商城 API `goods_info.name` 与本站 name
   逐字对得上的；**滤芯/滤网等配件不算**，配件会被单独剔除。

2. **匹数错位修正**：`cool_power`（制冷功率，单位 W，schema 声明 number 且可排序）
   在 30 款竞品里存的是「3匹」「大3匹」这类匹数字符串，而 `pishu`（匹数）空着。
   这是字段错位：数值与单位都对不上，且把不可排序的字符串塞进了可排序数值列。
   判据是自洽的——凡是 `cool_power` 为 W 数值的 22 款，`pishu` 全都有值；
   凡 `cool_power` 是匹数字符串的，`pishu` 全都空着。故按「匹数归位、
   制冷功率回查不到」处理；**匹数与制冷量明显矛盾的（第三方标错）保持查不到**。

3. **pros / cons 补写**：由该产品已入库参数 + 官方卖点文案推导，
   不引入参数表里没有的数字。

用法：
    python scripts/backfill-ac-ap.py --dry
    python scripts/backfill-ac-ap.py
"""
import argparse
import importlib.util
import json
import os
import re
import sys
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATE = "2026-10-04"

# 取数值的正则：`-` 只有在前一位不是数字时才当负号，否则「26-45㎡」这种
# 适用面积区间会被读成 26 和 -45，守卫就永远判不中。
NUM_RE = r"(?<![\d.])-?\d+(?:\.\d+)?"


def dp(*a):
    return os.path.join(ROOT, *a)


def load_fmo():
    """复用 fill-mi-official 的 API 抓取与参数解析，避免两份实现漂移。"""
    spec = importlib.util.spec_from_file_location(
        "fmo", dp("scripts", "fill-mi-official.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


# --------------------------------------------------------------------------
# 1. 人工核对过的商城 product_id
#    每条的依据：调 api2.order.mi.com/product/view 取回的 goods_info.name
#    与本站 products.json 的 name 逐字对应（去掉品牌位置差异后完全一致）。
# --------------------------------------------------------------------------
CONFIRMED_IDS = {
    # air-conditioner
    "jso_pro_2p": "1230803610",       # 巨省电Pro 2匹 超一级能效 米家空调（2025）
    "jso_pro_cab_3p": "1230806650",   # 巨省电Pro 立式大3匹 超一级能效 米家空调
    "fresh_pro_cab_3p": "1230802385", # 新风Pro 双出风 立式3匹超一级能效 米家空调
    "duct_pro_15p": "1230802993",     # Pro风管机 1.5匹 超一级能效 米家中央空调
    "jso_15p_copper": "1230805717",   # 巨省电 大1.5匹 双排铜管 米家空调
    "acsens_15p": "1230803797",       # Pro 人感上出风 1.5匹超一级能效 米家空调
    "acsens_std_15p": "1230806657",   # 人感风 1.5匹 米家空调
    "acsens_duct_4p": "1230807607",   # 风管机 人感风 双出风 大4匹 米家中央空调
    "acsens_cab_3p": "1230803798",    # 新风Pro 人感双出风 立式3匹超一级能效 米家空调
    "roufeng_15p": "1230800001",     # 柔风 1.5匹新一级能效 米家空调
    "health_15p": "1230804526",       # 健康风 1.5匹新一级能效 米家空调
    # air-purifier
    "ultra_std": "1230805550",        # 米家全效空气净化器 Ultra
    "quanxiao_std": "1230800043",     # 米家全效空气净化器
    "6": "1230807875",                # 米家空气净化器 6 白色
    "5": "1230803990",                # 米家空气净化器 5
}

# 归一后两边都剥空了、无法机械判同的，靠人工定义「标准版 = 基础款」这类等式。
# 每条都要写清依据，写进 change_log 备查。
CONFIRMED_BY_JUDGMENT = {
    "quanxiao_std": "本站名「米家全效空气净化器(标准版)」剥掉品牌与「标准版」后为空，"
                    "商城「米家全效空气净化器」即基础款，与「标准版」同物",
}

# --------------------------------------------------------------------------
# 2. 匹数错位修正里需要人工判定的：第三方把匹数标错了，不能照搬
#    判据：1 匹 ≈ 2500W。偏差超过 ±35% 说明第三方标的匹数与本行制冷量对不上。
# --------------------------------------------------------------------------
PISHU_REJECT = {
    # KFR-72LW 是 3 匹柜机（制冷量 7325W），第三方却标 1.5 匹 —— 明显错标
    "haier_2674679": "第三方标 1.5 匹，但本行制冷量 7325W 属 3 匹柜机，判为错标",
}

# 配件关键词：商城搜出来的「滤芯」「滤网」是耗材，不是整机
ACCESSORY = re.compile(r"滤芯|滤网|滤片|滤罩|除味盒|炭包")


def compose_energy(grade, apf):
    """本站 energy 的既有写法是「一级(APF4.72)」——能效等级与 APF 合写一列。"""
    grade = (grade or "").strip()
    apf = (apf or "").strip()
    if grade and apf:
        return "%s(APF%s)" % (grade, apf)
    return grade or (("APF" + apf) if apf else None)


def first_num(v):
    m = re.search(NUM_RE, str(v or "").replace(",", ""))
    return float(m.group()) if m else None


def apply_guards(item, fills):
    """剔除「写了等于没写」和「同一数值落进两列」的填法。

    两类坑都是实测踩到的：

    1. **额定/实测同值重复**。商城同一个商品，颗粒物 CADR 标「810m³/h」（额定）
       而甲醛 CADR 标「390（实测值）」（实测）；390 这个数库里本来就记在
       `cadr_hcho`。照抄就会让同一个数同时出现在额定列和实测列，横向对比时被
       计两次。数值相同即判为重复，丢掉 `_real` 那一路。
    2. **区间被单值覆盖**。库内适用面积记的是区间「49-84㎡」，商城只给上限
       「84㎡」。用单值覆盖区间会丢掉下限，纯属倒退。商城值已包含在原值里就跳过。
    """
    dropped = []
    for real_key, rated_key in (("cadr_pm_real", "cadr_pm"),
                                ("cadr_hcho_real", "cadr_hcho")):
        if real_key in fills:
            a, b = first_num(fills[real_key][0]), first_num(item.get(rated_key))
            if a is not None and b is not None and abs(a - b) < 0.51:
                dropped.append("%s=%s 与额定列 %s 同值，不重复写" % (real_key, a, b))
                fills.pop(real_key)
    if "area" in fills:
        new = first_num(fills["area"][0])
        olds = [float(x) for x in re.findall(
            NUM_RE, str(item.get("area") or "").replace(",", ""))]
        if new is not None and any(abs(new - o) < 0.51 for o in olds):
            dropped.append("area=%s 已在原值 %r 内，不覆盖区间" % (new, item.get("area")))
            fills.pop("area")
    return dropped


def fix_existing(cats, dry=False):
    """把同一套守卫补到「已经躺在草稿区」的记录上。

    `fill-mi-official.py` 不区分「补空」还是「覆盖已有值」，于是会出现两类
    回退：把区间适用面积覆盖成单值上限、把与额定列同值的 CADR 再写进实测列。
    这里对草稿区里每条记录重跑 apply_guards，命中的字段还原成库里的原值。
    """
    import glob
    touched = 0
    for cid in cats:
        lib = {p["id"]: p for p in
               json.load(open(dp("data", cid, "products.json"), encoding="utf-8"))}
        for fp in sorted(glob.glob(dp("data", "_draft", cid, "*.json"))):
            item = json.load(open(fp, encoding="utf-8"))
            base = lib.get(item["id"])
            if not base:
                continue
            # 还原成库内原值后再重跑守卫，才能看出「这次回填写了什么」
            probe = dict(item)
            for k in ("cadr_pm_real", "cadr_hcho_real", "area"):
                probe[k] = base.get(k)
            fills = {}
            for k in ("cadr_pm_real", "cadr_hcho_real", "area"):
                if item.get(k) != base.get(k):
                    fills[k] = (item[k], "fill-mi-official 回填值")
            if not fills:
                continue
            dropped = apply_guards(probe, dict(fills))
            if not dropped:
                continue
            for msg in dropped:
                key = msg.split("=")[0]
                item[key] = base.get(key)
                print("  %-18s %-16s 还原：%s" % (cid, item["id"], msg))
            item["change_log"] = (item.get("change_log") or "") + \
                "；%s 守卫还原：%s" % (DATE, "；".join(dropped))
            touched += 1
            if not dry:
                with open(fp, "w", encoding="utf-8", newline="\n") as fh:
                    json.dump(item, fh, ensure_ascii=False, indent=2)
                    fh.write("\n")
    print("\n守卫还原 %d 条草稿" % touched)
    return touched


PISHU_RE = re.compile(r"^(大)?(\d+(?:\.\d+)?)\s*[匹P]$")


def draft_path(cid, pid):
    return os.path.join(dp("data", "_draft", cid, "%s.json" % pid))


def load_base(cid, pid):
    """以草稿区为准、没有草稿才回落到库文件。

    批次里多个阶段是先后作用于同一条记录的（fill-params 补尺寸 → 商城 API 补价格
    → 守卫还原 → 匹数归位）。后一阶段若从库文件起步，就会把前一阶段的结果整片覆盖掉。
    """
    p = draft_path(cid, pid)
    if os.path.exists(p):
        return json.load(open(p, encoding="utf-8"))
    return None


def save_draft(cid, item):
    d = dp("data", "_draft", cid)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "%s.json" % item["id"]), "w",
              encoding="utf-8", newline="\n") as fh:
        json.dump(item, fh, ensure_ascii=False, indent=2)
        fh.write("\n")


def fix_pishu(cid="air-conditioner", dry=False):
    """把错位在 `cool_power`（制冷功率，W）里的匹数归位到 `pishu`。

    库里的现状是自洽的证据链：`cool_power` 为 W 数值的 22 款，`pishu` 全有值；
    `cool_power` 为匹数字符串的 30 款，`pishu` 全空。同一字段两种写法，
    说明后者本就该是匹数落错了列。

    归位前还要过一道自洽检查：1 匹 ≈ 2500W，第三方标的匹数与本行制冷量
    偏差超过 ±35% 的判为错标，匹数与制冷功率一起写「查不到」。
    """
    lib = {p["id"]: p for p in
           json.load(open(dp("data", cid, "products.json"), encoding="utf-8"))}
    moved = rejected = 0
    for pid, base in lib.items():
        cp = base.get("cool_power")
        if not isinstance(cp, str):
            continue
        m = PISHU_RE.match(cp.strip())
        if not m:
            # 制冷功率本身就是「查不到」的，匹数一并补成「查不到」，
            # 别留成缺字段（缺字段与「查不到」在卡片上表现不同）
            if cp.strip() in ("查不到", "—") and not base.get("pishu"):
                item = load_base(cid, pid) or dict(base)
                item["pishu"] = "查不到"
                item["change_log"] = (item.get("change_log") or base.get("change_log") or "") + \
                    "；%s pishu 补为「查不到」（制冷功率亦无值，不留缺字段）" % DATE
                print("  %-18s pishu 缺字段 -> '查不到'" % pid)
                if not dry:
                    save_draft(cid, item)
                rejected += 1
            continue
        # 已在草稿区就以草稿为底，避免覆盖前面阶段填的尺寸/价格
        item = load_base(cid, pid) or dict(base)
        pishu = cp.strip().replace("P", "匹")
        # 「3.0P」归一成库内既有写法「3匹」（本站 pishu 只出现整数与 1.5）
        if re.fullmatch(r"\d+\.0匹", pishu):
            pishu = pishu[:-3] + "匹"
        num = float(m.group(2))
        cap = first_num(base.get("cool_cap"))
        why = ""
        if pid in PISHU_REJECT:
            why = PISHU_REJECT[pid]
        elif cap:
            # 1 匹 ≈ 2500W，留 ±35% 容差
            implied = cap / 2500.0
            if abs(implied - num) / max(implied, num) > 0.35:
                why = ("第三方标 %s，但制冷量 %sW 折合约 %.1f 匹，偏差过大判为错标"
                       % (pishu, base.get("cool_cap"), implied))
        if why:
            new_pishu, new_cp, rejected = "查不到", "查不到", rejected + 1
        else:
            new_pishu, new_cp = pishu, "查不到"
            moved += 1
        item["pishu"] = new_pishu
        item["cool_power"] = new_cp
        item["verify_date"] = DATE
        item["change_log"] = (item.get("change_log") or base.get("change_log") or "") + \
            "；%s 字段归位：制冷功率 cool_power 原记「%s」（匹数误入 W 列），" \
            "移至 pishu=%s，制冷功率回填「查不到」%s" % (
                DATE, cp, new_pishu, ("；%s" % why) if why else "")
        item["updated_at"] = DATE
        print("  %-18s cool_power %r -> %r，pishu -> %r%s"
              % (pid, cp, new_cp, new_pishu, "  ⚠ %s" % why if why else ""))
        if not dry:
            save_draft(cid, item)
    print("\n匹数归位 %d 款，判为错标保持查不到 %d 款" % (moved, rejected))
    return moved + rejected


# schema 声明 type=number 且带 unit 的字段，库里的竞品却存成「1800m3/h」
# 「7350(900-9700)W」这类带单位/带区间的字符串——数值列因此不可排序、不可筛选，
# 横向对比直接失效。单位由 schema 的 unit 负责渲染，这里只把数值剥出来。
# 只认下面这几种写法，其余（查不到 / — / 文本）一律不动，绝不硬转。
NUM_STRING = re.compile(
    r"^\s*(\d+(?:\.\d+)?)\s*(?:\([^)]*\))?\s*"
    r"(?:W|m3/h|m³/h|立方米/小时|立方米每小时)?\s*$")


def fix_number_fields(cats, dry=False):
    """把 number 字段里带单位的字符串还原成数值。"""
    total = 0
    for cid in cats:
        sch = json.load(open(dp("data", cid, "schema.json"), encoding="utf-8"))
        keys = [f["key"] for f in sch["fields"]
                if f.get("type") == "number" and f.get("unit")]
        lib = {p["id"]: p for p in
               json.load(open(dp("data", cid, "products.json"), encoding="utf-8"))}
        for pid, base in lib.items():
            item = load_base(cid, pid) or dict(base)
            changed = []
            for k in keys:
                v = item.get(k)
                if not isinstance(v, str):
                    continue
                m = NUM_STRING.match(v)
                if not m:
                    continue
                n = float(m.group(1))
                n = int(n) if n == int(n) else n
                item[k] = n
                changed.append((k, v, n))
            if not changed:
                continue
            item["verify_date"] = DATE
            item["change_log"] = (item.get("change_log") or base.get("change_log") or "") + \
                "；%s 数值字段归一：%s（schema 已声明单位，由字段渲染，不再把单位写进值）" % (
                    DATE, "，".join("%s %r->%r" % c for c in changed))
            item["updated_at"] = DATE
            print("  %-18s %s" % (pid, "，".join("%s %r->%r" % c for c in changed)))
            total += len(changed)
            if not dry:
                save_draft(cid, item)
    print("\n数值字段归一 %d 处" % total)
    return total


# --------------------------------------------------------------------------
# 3. pros / cons
#    全部由该产品**已入库的参数**推出：能效等级、匹数、制冷/制热量、循环风量、
#    噪音区间、CADR、适用面积、参考价、机型。不引入参数表里没有的数字——
#    出现的数字一律能在同一行的字段里对上。
#    cons 允许写「某某查不到」，与库内既有写法一致（如小米 1 代的
#    「噪音参数查不到」）：如实标出资料缺口比编一个卖点有用。
# --------------------------------------------------------------------------
PROS_CONS = {
    # ---------------- air-conditioner：小米系（补上 product_id 后参数齐全）
    "jso_15p_copper": (["双排铜管散热", "一级能效APF5.45", "适用16-20㎡", "冷暖双制"],
                       ["噪音参数查不到", "循环风量未标"]),
    "acsens_15p": (["人感上出风", "一级能效APF5.65", "适用15-20㎡", "挂机省空间"],
                   ["参考价4999偏高", "噪音参数查不到", "循环风量未标"]),
    "acsens_std_15p": (["人感风送风", "一级能效APF5.32", "适用16-20㎡", "挂机省空间"],
                       ["参考价3899偏高", "噪音参数查不到", "循环风量未标"]),
    "acsens_duct_4p": (["隐藏式安装", "双出风", "适用40-50㎡", "大4匹"],
                       ["需吊顶施工", "制冷量查不到", "参考价10999偏高"]),
    "acsens_cab_3p": (["新风Pro", "人感双出风", "制冷量7320W", "一级能效APF5.01"],
                      ["柜机占地大", "噪音参数查不到", "循环风量未标"]),
    "roufeng_15p": (["柔风送风", "一级能效APF5.27", "适用16-20㎡", "参考价2699"],
                     ["噪音参数查不到", "循环风量未标"]),
    "health_15p": (["健康风送风", "一级能效APF5.32", "适用15-20㎡", "参考价2999"],
                   ["噪音参数查不到", "循环风量未标"]),
    # ---------------- air-conditioner：竞品
    "midea_2826831": (["一级能效", "3匹柜机", "制冷量7330W", "循环风量1800m³/h"],
                      ["噪音参数查不到", "室外机尺寸查不到"]),
    "midea_2673299": (["一级能效", "低至22dB", "循环风量1800m³/h", "适用32-48㎡"],
                      ["室外机尺寸查不到", "整机重量查不到"]),
    "midea_2982042": (["1.5匹小冷量", "中央空调隐藏式安装"],
                      ["三级能效", "噪音50dB", "适用面积仅15㎡", "制热量查不到"]),
    "midea_2633479": (["一级能效", "制冷量7350W", "适用30-46㎡"],
                      ["循环风量查不到", "噪音47dB"]),
    "midea_2673219": (["一级能效", "制热量10550W", "循环风量1820m³/h", "低至22dB"],
                      ["噪音上限47dB", "室外机尺寸查不到"]),
    "midea_2826851": (["一级能效", "循环风量1800m³/h", "低至22dB", "参考价6799"],
                      ["噪音上限47dB", "室外机尺寸查不到"]),
    "gree_2774339": (["一级能效", "支持WiFi", "制冷量7320W", "适用30-40㎡"],
                     ["参考价13499最高", "噪音46dB"]),
    "gree_2925991": (["一级能效", "制冷量7350W", "适用30-40㎡"],
                     ["循环风量1310偏低", "噪音43-47dB"]),
    "gree_2949951": (["一级能效", "低至35dB", "挂机省空间", "外机尺寸完整"],
                     ["循环风量800偏低", "参考价9228偏高"]),
    "gree_2774279": (["一级能效", "支持WiFi", "循环风量1760m³/h", "制冷量7330W"],
                     ["噪音46dB", "室外机尺寸查不到"]),
    "gree_2925971": (["一级能效", "4匹大冷量", "制热量11200W", "适用35-55㎡"],
                      ["噪音45-49dB", "柜机占地大"]),
    "gree_2673499": (["一级能效", "低至29dB", "制冷量7330W"],
                     ["循环风量1300偏低", "噪音上限47dB"]),
    "haier_2890951": (["一级能效", "循环风量2000m³/h", "制热量10600W", "低至22dB"],
                      ["参考价13999最高", "噪音上限47dB"]),
    "haier_2674639": (["一级能效", "低至20dB", "循环风量1850m³/h", "适用30-45㎡"],
                      ["噪音上限47dB", "室外机尺寸查不到"]),
    "haier_2781199": (["一级能效", "低至20dB", "制热量10560W", "Pro版本"],
                      ["噪音上限46dB", "室外机尺寸查不到"]),
    "haier_2781259": (["一级能效", "低至20dB", "循环风量1820m³/h", "参考价7874"],
                      ["噪音上限46dB", "室外机尺寸查不到"]),
    "haier_2674599": (["一级能效", "适用33-50㎡", "Pro版本", "参考价7699"],
                      ["循环风量1600一般", "噪音上限47dB"]),
    "haier_2674679": (["一级能效", "适用33-50㎡", "参考价6999"],
                      ["匹数第三方标注有误", "循环风量1510一般"]),
    "hisense_1538127": (["制冷量17000W", "适用60-80㎡", "大空间柜机"],
                        ["二级能效", "噪音57dB", "参考价38000最高", "制热量查不到"]),
    "hisense_2828131": (["一级能效", "制热量10700W", "循环风量1810m³/h", "低至22dB"],
                        ["参考价11999偏高", "室外机尺寸查不到"]),
    "hisense_2794971": (["一级能效", "循环风量1810m³/h", "适用30-50㎡"],
                        ["噪音参数查不到", "参考价10999偏高"]),
    "hisense_1390727": (["一级能效", "挂机省空间", "低至24dB", "循环风量1350m³/h"],
                        ["适用面积查不到", "噪音上限47dB"]),
    "hisense_2781439": (["一级能效", "制热量10700W", "循环风量1810m³/h", "低至22dB"],
                        ["噪音上限45dB", "室外机尺寸查不到"]),
    "hisense_2839831": (["一级能效", "低至20dB", "循环风量1810m³/h", "参考价7057"],
                        ["噪音上限45dB", "室外机尺寸查不到"]),
    "changhong_2675079": (["一级能效", "循环风量1880m³/h", "参考价5999", "制冷量7350W"],
                          ["噪音上限47dB", "室外机尺寸查不到"]),
    "changhong_2829171": (["4匹大冷量", "适用40-60㎡", "参考价4999", "制热量12000W"],
                          ["二级能效", "柜机占地大", "噪音上限47dB"]),
    "changhong_2675199": (["一级能效", "参考价4999", "低至22dB", "制热量10250W"],
                          ["噪音上限44dB", "室外机尺寸查不到"]),
    "changhong_2829051": (["一级能效", "参考价4699最低", "低至22dB", "3匹柜机"],
                          ["噪音上限47dB", "室外机尺寸查不到"]),
    "changhong_2895831": (["一级能效", "低至20dB", "2匹大冷量", "挂机省空间"],
                          ["适用面积查不到", "循环风量920偏低"]),
    "changhong_2675239": (["一级能效", "参考价4199最低", "低至22dB", "制热量10250W"],
                          ["噪音上限47dB", "室外机尺寸查不到"]),
    # ---------------- air-purifier：竞品（22 款，第三方规格，CADR 为额定口径）
    "honeywell_1124159": (["颗粒物CADR 833", "大容量立式"],
                          ["参考价16999最高", "甲醛CADR查不到", "适用面积查不到",
                           "滤芯价格查不到"]),
    "honeywell_2052547": (["颗粒物CADR 1000", "甲醛CADR 700", "适用70-120㎡", "功耗77W"],
                          ["噪音参数查不到", "滤芯价格查不到", "官方价查不到"]),
    "honeywell_1588807": (["颗粒物CADR 620", "甲醛CADR 400", "功耗11.5W", "适用74㎡"],
                          ["噪音参数查不到", "滤芯价格查不到"]),
    "honeywell_1588827": (["颗粒物CADR 560", "甲醛CADR 350", "适用67㎡"],
                          ["噪音参数查不到", "滤芯价格查不到", "官方价查不到"]),
    "honeywell_1124158": (["颗粒物CADR 600", "甲醛CADR 280", "功耗52W"],
                          ["适用面积查不到", "噪音参数查不到", "滤芯价格查不到"]),
    "midea_1587267": (["颗粒物CADR 800", "甲醛CADR 400", "适用96㎡", "Pro版本"],
                      ["噪音参数查不到", "滤芯价格查不到", "整机高度仅710mm"]),
    "midea_2591539": (["适用150㎡", "卧式横置机型", "功耗92W", "Pro版本"],
                      ["颗粒物CADR查不到", "噪音参数查不到", "滤芯价格查不到"]),
    "midea_1086127": (["颗粒物CADR 405", "甲醛CADR 280", "功耗37W", "适用28-48㎡"],
                      ["噪音参数查不到", "滤芯价格查不到"]),
    "midea_2591499": (["适用146㎡", "卧式横置机型", "功耗92W"],
                      ["颗粒物CADR查不到", "噪音参数查不到", "滤芯价格查不到"]),
    "midea_1445697": (["入门价位", "颗粒物CADR 170", "体积小巧"],
                      ["颗粒物CADR 170偏低", "适用面积仅20㎡", "噪音参数查不到",
                       "滤芯价格查不到"]),
    "haier_2251599": (["颗粒物CADR 1905.5", "甲醛CADR 1525", "适用200㎡", "大户型"],
                      ["功耗230W", "噪音参数查不到", "滤芯价格查不到"]),
    "haier_1084868": (["功耗80W", "窄身立式"],
                      ["颗粒物CADR查不到", "适用面积查不到", "噪音参数查不到",
                       "滤芯价格查不到"]),
    "haier_1587767": (["颗粒物CADR 903.1", "甲醛CADR 553.1", "适用96㎡", "功耗85W"],
                      ["噪音参数查不到", "滤芯价格查不到"]),
    "haier_2251519": (["颗粒物CADR 643", "甲醛CADR 580", "适用100㎡", "功耗64W"],
                      ["噪音参数查不到", "滤芯价格查不到"]),
    "haier_1587787": (["甲醛CADR 666.7", "适用81㎡", "功耗60W", "体积小巧"],
                      ["颗粒物CADR低于甲醛CADR", "噪音参数查不到", "滤芯价格查不到"]),
    "dreame_2578899": (["颗粒物CADR 400", "甲醛CADR 220", "适用81-100㎡"],
                       ["尺寸查不到", "噪音参数查不到", "滤芯价格查不到",
                        "参考价7999偏高"]),
    "dreame_2581359": (["颗粒物CADR 300", "适用81-100㎡"],
                       ["尺寸查不到", "噪音参数查不到", "滤芯价格查不到",
                        "参考价6999偏高"]),
    "dyson_2051287": (["适用100㎡", "甲醛CADR 50", "功耗220W"],
                      ["颗粒物CADR 300偏低", "尺寸查不到", "噪音参数查不到",
                       "滤芯价格查不到"]),
    "dyson_2051267": (["适用100㎡", "颗粒物CADR 300"],
                      ["甲醛CADR仅50", "尺寸查不到", "噪音参数查不到",
                       "滤芯价格查不到"]),
    "dyson_2401539": (["颗粒物CADR 162.3", "甲醛CADR 67.8", "入门机型"],
                      ["颗粒物CADR 162.3偏低", "适用面积查不到", "尺寸查不到",
                       "滤芯价格查不到"]),
    "dyson_2401519": (["颗粒物CADR 160.4", "甲醛CADR 62.9", "入门机型"],
                      ["颗粒物CADR 160.4偏低", "适用面积查不到", "尺寸查不到",
                       "滤芯价格查不到"]),
    "dyson_1233832": (["颗粒物CADR 150", "适用27㎡", "体积小巧"],
                      ["颗粒物CADR 150偏低", "甲醛CADR查不到", "噪音参数查不到",
                       "滤芯价格查不到"]),
}


def fix_pros_cons(cats, dry=False):
    """给 pros / cons 同时为空的裸卡补标签。"""
    n = 0
    for cid in cats:
        lib = {p["id"]: p for p in
               json.load(open(dp("data", cid, "products.json"), encoding="utf-8"))}
        for pid, (pros, cons) in PROS_CONS.items():
            if pid not in lib:
                continue
            base = lib[pid]
            item = load_base(cid, pid) or dict(base)
            if item.get("pros") and item.get("cons"):
                continue
            item["pros"] = pros
            item["cons"] = cons
            item["updated_at"] = DATE
            if not item.get("verify_date") or item["verify_date"] == "—":
                item["verify_date"] = DATE
            item["change_log"] = (item.get("change_log") or base.get("change_log") or "") + \
                "；%s 补 pros/cons（依据本行已入库参数推导，未引入参数表以外的数值）" % DATE
            print("  %-18s %-2d 优 / %-2d 缺" % (pid, len(pros), len(cons)))
            n += 1
            if not dry:
                save_draft(cid, item)
    print("\npros/cons 补写 %d 款" % n)
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cat", default="air-conditioner,air-purifier")
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--fix-existing", action="store_true",
                    help="只对草稿区已有记录跑守卫还原")
    ap.add_argument("--fix-pishu", action="store_true",
                    help="把错位在 cool_power 里的匹数归位到 pishu")
    ap.add_argument("--fix-number", action="store_true",
                    help="把 number 字段里带单位的字符串归一成数值")
    ap.add_argument("--fix-proscons", action="store_true",
                    help="给 pros/cons 同时为空的裸卡补标签")
    args = ap.parse_args()
    cats = args.cat.split(",")

    if args.fix_existing:
        fix_existing(cats, args.dry)
        return 0
    if args.fix_pishu:
        fix_pishu(dry=args.dry)
        return 0
    if args.fix_number:
        fix_number_fields(cats, args.dry)
        return 0
    if args.fix_proscons:
        fix_pros_cons(cats, args.dry)
        return 0

    fmo = load_fmo()
    nfiles = 0
    nfields = 0
    report = []

    for cid in cats:
        pf = dp("data", cid, "products.json")
        sch = json.load(open(dp("data", cid, "schema.json"), encoding="utf-8"))
        keys = {f["key"] for f in sch["fields"]}
        types = {f["key"]: f["type"] for f in sch["fields"]}
        lib = json.load(open(pf, encoding="utf-8"))
        draft_dir = dp("data", "_draft", cid)
        os.makedirs(draft_dir, exist_ok=True)

        for base in lib:
            pid = CONFIRMED_IDS.get(base["id"])
            if not pid:
                continue
            item = dict(base)
            fills = {}
            # verify_url：查不到 -> 商城商品页（这是 id 的出处，必须留痕）
            if not re.search(r"product_id=\d+", item.get("verify_url") or ""):
                item["verify_url"] = "https://www.mi.com/shop/buy/detail?product_id=%s" % pid

            d = fmo.fetch(pid)
            time.sleep(1.5)
            gi = ((d or {}).get("data", {}).get("goods_list") or [{}])[0].get("goods_info") or {}
            gname = str(gi.get("name") or "").strip()
            if not gname:
                report.append((cid, base["id"], "API 无响应", 0))
                continue
            if ACCESSORY.search(gname):
                # 配件不是整机，宁可留空
                report.append((cid, base["id"], "配件误命中 %s" % gname, 0))
                continue

            # 权威商品名要与本站名对得上，否则可能是同系列另一款
            la = fmo_strip(base["name"])
            na = fmo_strip(gname)
            if not name_same(la, na) and base["id"] not in CONFIRMED_BY_JUDGMENT:
                report.append((cid, base["id"], "型号对不上：商城=%r" % gname, 0))
                continue

            now = fmo.num_of(gi.get("price") or "")
            mkt = fmo.num_of(gi.get("market_price") or "")
            if now and 49 <= now <= 999999 and "official_price" in keys:
                fills["official_price"] = (int(now), "商城 API price=%s" % gi.get("price"))
            if mkt and now and mkt != now and "ref_price" in keys:
                fills["ref_price"] = (int(mkt), "商城 API market_price=%s" % gi.get("market_price"))

            for k, v in fmo.pick_from_params(gi.get("class_parameters"),
                                             keys | {"energy_apf"}).items():
                if types.get(k) == "number":
                    n = fmo.num_of(v[0])
                    if n is None:
                        continue
                    v = (int(n) if n == int(n) else n, v[1])
                fills.setdefault(k, v)

            # 能效与 APF 合写一列（本站既有写法）
            if "energy_apf" in fills:
                apf = fills.pop("energy_apf")[0]
                grade = fills["energy"][0] if "energy" in fills else None
                ce = compose_energy(grade, apf)
                if ce and "energy" in keys:
                    fills["energy"] = (ce, "商城关键参数「能效」+「APF值」")

            if not fills:
                report.append((cid, base["id"], "商城未给可写参数", 0))
                continue
            dropped = apply_guards(item, fills)
            if not fills:
                report.append((cid, base["id"],
                               "商城值均已入库（%s）" % "；".join(dropped), 0))
                continue
            for k, (v, _why) in fills.items():
                item[k] = v
            item["verify_date"] = DATE
            item["verify_status"] = "已核验（官方商城）"
            src = item.get("verify_source")
            if isinstance(src, list):
                item["verify_source"] = sorted(set(src) | {"小米商城"})
            elif not src:
                item["verify_source"] = ["小米商城"]
            item["change_log"] = (base.get("change_log") or "") + \
                "；%s 小米官方商城 API 回填（product_id=%s，商城名 %r）：%s" % (
                    DATE, pid, gname, "，".join("%s=%s" % (k, v) for k, (v, _) in fills.items()))
            if base["id"] in CONFIRMED_BY_JUDGMENT:
                item["change_log"] += "；product_id 判定依据：%s" % CONFIRMED_BY_JUDGMENT[base["id"]]
            if dropped:
                item["change_log"] += "（未写入：%s）" % "；".join(dropped)
            item["updated_at"] = DATE

            if args.dry:
                for k, (v, _w) in sorted(fills.items()):
                    print("    %-14s %-8s %r" % (base["id"], k, v))
            else:
                fp = os.path.join(draft_dir, "%s.json" % base["id"])
                with open(fp, "w", encoding="utf-8", newline="\n") as fh:
                    json.dump(item, fh, ensure_ascii=False, indent=2)
                    fh.write("\n")
                nfiles += 1
                nfields += len(fills)
            report.append((cid, base["id"], gname, len(fills)))

    print("\n== 小米 product_id 回填 ==")
    for cid, pid, why, n in report:
        print("  %-18s %-18s %2d 字段  %s" % (cid, pid, n, why[:60]))
    print("写入草稿 %d 款 / 回填 %d 个字段" % (nfiles, nfields))
    return 0


def fmo_strip(s):
    """本站名与商城名的归一：去价格串、去括号、能效口径词统一。"""
    s = re.sub(r"\d+\s*元.*$", "", str(s or ""))
    for b in ("米家空调", "小米空调", "米家中央空调", "米家新风空调",
              "米家全效空气净化器", "米家空气净化器", "米家", "小米"):
        s = s.replace(b, "")
    s = re.sub(r"超一级能效|新一级能效|一级能效|新国标|能效|[（(].*?[)）]"
               r"|\d{4}年?款|\d{4}款|款|白色|黑色", "", s)
    return re.sub(r"[\s　（）()【】\[\]，,、·\-\s]+", "", s)


def name_same(a, b):
    """本站名与商城名是否指同一款。

    语序常常不同（本站「风管机Pro 1.5匹」/ 商城「Pro风管机 1.5匹」），
    所以除子串包含外再退一步比「字符多重集」——判别词、匹数、系列名
    都在里面，顺序不同但字符一致基本就是同一款。长度差过大的不认。
    """
    if not a or not b:
        return False
    if a == b or a in b or b in a:
        return True
    if sorted(a) == sorted(b):
        return True
    # 允许商城多出「Pro」这类前后缀词，但不允许差太多
    if abs(len(a) - len(b)) <= 4 and set(a) <= set(b) or set(b) <= set(a):
        return abs(len(a) - len(b)) <= 4
    return False


if __name__ == "__main__":
    sys.exit(main())