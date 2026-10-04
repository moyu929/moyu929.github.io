#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""把丙路两个调查子 Agent 的产出落盘到草稿区（data/_draft/<品类>/<id>.json）。

## 为什么单独一个脚本

子 Agent 只有只读工具（搜索/读取/LSP），**不能执行也不能写文件**，所以它们把调查
结果以 JSON 文本回报，由我（丙路 Lead）审核后落盘。审核是这道工序的重点 —— 子 Agent
的产出里有两类必须拦下来的东西：

1. **`year` 取自 MIoT 的 `verifiedTime`** —— SKILL.md 两处红线写明「该站 verified_time
   是协议认证时间，**不等于上市时间**」。这类值一律剔除，不因为「看起来像年份」就填。
2. **把「数据缺失」写成产品缺点** —— 子 Agent 大量产出 `cons: ["解锁方式未公开",
   "尺寸参数未公开"]`。这是**我们没数据**，不是产品有短板；写进站点会被访客读成缺点。
   凡含「未公开 / 未标注 / 未注明」的 cons 条目一律剔除，只保留有明确否定依据的
   （如 `temp_ctrl=不支持`、`material=塑料`、半自动锁体）。

## 与既有口径的一致性

`official_price` 填第三方「参考价」看起来像口径污染，但 `scripts/fill-params.py`
第 508 行就是这么映射的（`pick_price()` 从 `参考价` 取数写进 `official_price`），
属于项目既有做法，故采纳；同时在 `change_log` 里注明是第三方参考价。

## 用法

    python scripts/apply-bing-patch.py            # 写入 data/_draft/
    python scripts/apply-bing-patch.py --dry      # 只看会改什么，不写文件

随后：npm run flow:submit -- <品类>/<产品id> ...
"""
import argparse
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D = "2026-10-04"

# ---------------------------------------------------------------- 审核后的补丁
# 说明：以下数据来自两个只读调查子 Agent 的回报，已经过上面两道剔除。
# 每条 values 的 source 用缓存文件名表达，脚本据此推断来源标签与 change_log 文案。

PROSCONS = {
    # —— C1：小米系 12 品类 ——
    "smart-lock/lock_2_cateye":   {"pros": ["全自动锁体", "内置猫眼可视"], "cons": []},
    "smart-lock/lock_4pro":       {"pros": ["全自动锁体", "双摄猫眼"], "cons": []},
    "smart-lock/lock_e30":        {"pros": ["大屏猫眼可视"], "cons": ["半自动需下压把手"]},
    "smart-lock/lock_g300":       {"pros": ["全自动锁体", "内置猫眼可视"], "cons": []},
    "smart-lock/lock_2_vein":     {"pros": ["全自动锁体", "指静脉识别"], "cons": []},
    "smart-lock/lock_m20_cateye": {"pros": ["大屏猫眼可视"], "cons": ["半自动需下压把手"]},
    "hair-dryer/hd_water_ion":      {"pros": ["水离子护发"], "cons": []},
    "hair-dryer/hd_water_ion_std":  {"pros": ["水离子护发"], "cons": []},
    "hair-dryer/hd_h701":           {"pros": ["水离子护发"], "cons": []},
    "hair-dryer/hd_h301":           {"pros": ["负离子护发"], "cons": []},
    "hair-dryer/hd_h300":           {"pros": ["负离子护发", "速干设计"], "cons": []},
    "hair-dryer/hd_h101":           {"pros": ["便携机身"], "cons": []},
    "shaver/sh_portable_pro": {"pros": ["便携机身"], "cons": []},
    "shaver/sh_s100":         {"pros": ["云纹刀网"], "cons": []},
    "camera/cam_call2":       {"pros": ["视频通话功能"], "cons": []},
    "camera/cam_call":        {"pros": ["视频通话功能"], "cons": []},
    "camera/cam_baby":        {"pros": ["母婴看护定位", "视频通话功能"], "cons": []},
    "toothbrush/tb_sweep_pro":    {"pros": ["声波扫振清洁"], "cons": []},
    "toothbrush/tb_sweep":        {"pros": ["声波扫振清洁"], "cons": []},
    "toothbrush/tb_t302_cushion": {"pros": ["缓震刷头设计"], "cons": []},
    "speaker/sp_family10":  {"pros": ["带触屏显示"], "cons": []},
    "body-scale/bs_s400pro": {"pros": ["四电极测量"], "cons": []},
    "foot-spa/fs_ster2":       {"pros": ["杀菌功能"], "cons": []},
    "foot-spa/fs_ster_smart":  {"pros": ["杀菌功能"], "cons": []},
    "foot-spa/fs_ster_old":    {"pros": ["杀菌功能"], "cons": []},
    "massage-gun/mg_h3mini":   {"pros": ["热敷功能"], "cons": []},
    "massage-gun/mg_h3":       {"pros": ["热敷功能"], "cons": []},
    "garment-steamer/gs_boost": {"pros": ["增压蒸汽"], "cons": []},

    # —— C2：kettle 竞品（cons 只保留有明确否定依据的）——
    "kettle/midea_638749":      {"pros": ["1.9L 容量", "1800W 功率", "304 不锈钢材质"], "cons": []},
    "kettle/midea_2515919":     {"pros": ["5L 容量", "1600W 功率", "支持控温"], "cons": []},
    "kettle/supor_2520819":     {"pros": ["5L 容量", "316L 不锈钢材质", "1200W 功率"], "cons": []},
    "kettle/supor_2644219":     {"pros": ["5L 容量", "1200W 功率", "支持控温"], "cons": []},
    "kettle/supor_2520979":     {"pros": ["5L 容量", "316L 不锈钢材质", "1200W 功率"], "cons": []},
    "kettle/joyoung_638202":    {"pros": ["5L 容量", "1000W 功率", "不锈钢材质"], "cons": []},
    "kettle/zojirushi_1122350": {"pros": ["4L 容量", "304 不锈钢材质", "660W 功率"], "cons": []},
    "kettle/zojirushi_1054977": {"pros": ["2.0 升以上容量", "680W 功率", "不锈钢材质"], "cons": []},
    "kettle/zojirushi_1067191": {"pros": ["4.0L 容量", "支持控温"], "cons": []},
    "kettle/philips_638337":    {"pros": ["1.7L 容量", "1800W 功率"], "cons": ["塑料壶身"]},
    "kettle/philips_638336":    {"pros": ["1.2-1.5L 容量", "1800W 功率", "玻璃壶身"], "cons": []},
    "kettle/philips_638611":    {"pros": ["1.7L 容量", "1910W 功率", "不锈钢壶身"], "cons": []},
    "kettle/philips_638335":    {"pros": ["1.7L 容量", "1910W 功率", "不锈钢壶身"], "cons": []},
}

# (值, 来源缓存文件) —— 来源决定 verify_source 标签
VALUES = {
    # —— C1：miot_model（精确名称匹配，已剔除全部 year）——
    "body-scale/bs_s200":      {"miot_model": ("xiaomi.scales.ms112", "miot-match.json")},
    "camera/cam_out4":         {"miot_model": ("xiaomi.camera.cw301", "miot-match.json")},
    "camera/cam_out4_std":     {"miot_model": ("isa.camera.cw501", "miot-match.json")},

    # —— C2：kettle 价格（第三方参考价，与 fill-params.py 口径一致）——
    "kettle/kt_ysh_p1":     {"official_price": (199, "search-电水壶.json")},
    "kettle/kt_temp_3pro":  {"official_price": (199, "search-电水壶.json")},
    "kettle/kt_bottle_pro": {"official_price": (699, "search-电水壶.json")},
    "kettle/midea_2515659": {"official_price": (899, "brand-electric_kettle-midea.json")},
    "kettle/midea_2515699": {"official_price": (589, "brand-electric_kettle-midea.json")},
    "kettle/midea_638749":  {"official_price": (499, "brand-electric_kettle-midea.json")},
    "kettle/midea_2515899": {"official_price": (439, "brand-electric_kettle-midea.json")},
    "kettle/midea_2515919": {"official_price": (399, "brand-electric_kettle-midea.json")},
    "kettle/supor_2520819": {"official_price": (699, "brand-electric_kettle-supor.json")},
    "kettle/supor_2644219": {"official_price": (599, "brand-electric_kettle-supor.json")},
    "kettle/supor_2520759": {"official_price": (579, "brand-electric_kettle-supor.json")},
    "kettle/supor_2520859": {"official_price": (479, "brand-electric_kettle-supor.json")},
    "kettle/supor_2520979": {"official_price": (419, "brand-electric_kettle-supor.json")},
    "kettle/joyoung_2427599": {"official_price": (399, "brand-electric_kettle-joyoung.json")},
    "kettle/joyoung_638202":  {"official_price": (299, "brand-electric_kettle-joyoung.json")},
    "kettle/joyoung_1359668": {"official_price": (199, "brand-electric_kettle-joyoung.json")},
    "kettle/joyoung_2531339": {"official_price": (169, "brand-electric_kettle-joyoung.json")},
    "kettle/joyoung_1121731": {"official_price": (169, "brand-electric_kettle-joyoung.json")},
    "kettle/zojirushi_1122350": {"official_price": (3699, "brand-electric_kettle-zojirushi.json")},
    "kettle/zojirushi_1067192": {"official_price": (3499, "brand-electric_kettle-zojirushi.json")},
    "kettle/zojirushi_1054977": {"official_price": (3399, "brand-electric_kettle-zojirushi.json")},
    "kettle/zojirushi_1067191": {"official_price": (2599, "brand-electric_kettle-zojirushi.json")},
    "kettle/zojirushi_1054999": {"official_price": (2399, "brand-electric_kettle-zojirushi.json")},
    "kettle/philips_638337": {"official_price": (699, "brand-electric_kettle-philips.json")},
    "kettle/philips_638336": {"official_price": (399, "brand-electric_kettle-philips.json")},
    "kettle/philips_2379859": {"official_price": (329, "brand-electric_kettle-philips.json")},
    "kettle/philips_638611": {"official_price": (299, "brand-electric_kettle-philips.json")},
    "kettle/philips_638335": {"official_price": (299, "brand-electric_kettle-philips.json")},

    # —— C2：kettle 规格（pconline / brand 缓存）——
    "kettle/philips_638611": {"official_price": (299, "brand-electric_kettle-philips.json"),
                              "size": ("156×240×225mm", "pconline-electric_kettle-philips-638611.json")},
    "kettle/philips_638335": {"official_price": (299, "brand-electric_kettle-philips.json"),
                              "size": ("156×240×225mm", "pconline-electric_kettle-philips-638335.json"),
                              "temp_ctrl": ("支持", "pconline-electric_kettle-philips-638335.json")},
    "kettle/philips_638336": {"temp_ctrl": ("不支持保温", "pconline-electric_kettle-philips-638336.json")},
    "kettle/zojirushi_1054977": {"temp_ctrl": ("支持", "pconline-electric_kettle-zojirushi-1054977.json")},
    "kettle/midea_2515659": {"capacity": ("4L", "brand-electric_kettle-midea.json"),
                             "power": ("2180W", "brand-electric_kettle-midea.json")},
    "kettle/midea_2515699": {"capacity": ("5L", "brand-electric_kettle-midea.json"),
                             "power": ("1600W", "brand-electric_kettle-midea.json")},
    "kettle/midea_2515899": {"capacity": ("5L", "brand-electric_kettle-midea.json"),
                             "power": ("1600W", "brand-electric_kettle-midea.json")},
    "kettle/supor_2520759": {"capacity": ("5L", "brand-electric_kettle-supor.json"),
                             "power": ("1200W", "brand-electric_kettle-supor.json")},
    "kettle/supor_2520859": {"capacity": ("5L", "brand-electric_kettle-supor.json"),
                             "power": ("1200W", "brand-electric_kettle-supor.json")},
    "kettle/joyoung_1359668": {"capacity": ("5L", "brand-electric_kettle-joyoung.json"),
                               "power": ("1200W", "brand-electric_kettle-joyoung.json"),
                               "temp_ctrl": ("支持", "brand-electric_kettle-joyoung.json")},
    "kettle/joyoung_2531339": {"capacity": ("1.7L", "brand-electric_kettle-joyoung.json"),
                               "power": ("1800W", "brand-electric_kettle-joyoung.json")},
    "kettle/joyoung_1121731": {"capacity": ("1.7L", "brand-electric_kettle-joyoung.json"),
                               "power": ("1800W", "brand-electric_kettle-joyoung.json")},
    "kettle/joyoung_2427599": {"capacity": ("1.7L", "brand-electric_kettle-joyoung.json"),
                               "power": ("1800W", "brand-electric_kettle-joyoung.json")},
    "kettle/zojirushi_1067192": {"capacity": ("2.0升以上", "brand-electric_kettle-zojirushi.json")},
    "kettle/zojirushi_1054999": {"capacity": ("5.0L", "brand-electric_kettle-zojirushi.json"),
                                 "power": ("730W", "brand-electric_kettle-zojirushi.json"),
                                 "temp_ctrl": ("支持", "brand-electric_kettle-zojirushi.json")},
    "kettle/philips_2379859": {"capacity": ("1.7L", "brand-electric_kettle-philips.json"),
                               "power": ("1850W", "brand-electric_kettle-philips.json")},

    # —— C2：projector（坚果 5 款 pconline 规格 + 价格）——
    "projector/jmgo_1090711": {"official_price": (34999, "brand-projector-jmgo.json"),
                               "resolution": ("1080P", "pconline-projector-jmgo-1090711.json"),
                               "dmd": ("0.65英寸DMD", "pconline-projector-jmgo-1090711.json"),
                               "keystone": ("垂直±40°", "pconline-projector-jmgo-1090711.json"),
                               "focus": ("自动对焦", "pconline-projector-jmgo-1090711.json"),
                               "throw_ratio": ("0.25:1", "pconline-projector-jmgo-1090711.json")},
    "projector/jmgo_1090710": {"official_price": (25999, "brand-projector-jmgo.json"),
                               "resolution": ("1080P", "pconline-projector-jmgo-1090710.json"),
                               "dmd": ("0.65英寸DMD", "pconline-projector-jmgo-1090710.json"),
                               "keystone": ("垂直±40°", "pconline-projector-jmgo-1090710.json"),
                               "focus": ("自动对焦", "pconline-projector-jmgo-1090710.json"),
                               "throw_ratio": ("0.25:1", "pconline-projector-jmgo-1090710.json")},
    "projector/jmgo_1090693": {"official_price": (9999, "brand-projector-jmgo.json"),
                               "size": ("480×362×165mm", "pconline-projector-jmgo-1090693.json"),
                               "resolution": ("1080P", "pconline-projector-jmgo-1090693.json"),
                               "dmd": ("0.47英寸DMD", "pconline-projector-jmgo-1090693.json"),
                               "keystone": ("垂直/水平±45°", "pconline-projector-jmgo-1090693.json"),
                               "focus": ("手动聚焦", "pconline-projector-jmgo-1090693.json"),
                               "throw_ratio": ("1.1:1", "pconline-projector-jmgo-1090693.json")},
    "projector/jmgo_1090713": {"official_price": (9998, "brand-projector-jmgo.json"),
                               "size": ("416×310×100mm", "pconline-projector-jmgo-1090713.json"),
                               "resolution": ("1080P", "pconline-projector-jmgo-1090713.json"),
                               "dmd": ("0.47英寸DMD", "pconline-projector-jmgo-1090713.json"),
                               "focus": ("电动对焦", "pconline-projector-jmgo-1090713.json"),
                               "throw_ratio": ("0.233:1", "pconline-projector-jmgo-1090713.json")},
    "projector/jmgo_1090694": {"official_price": (5999, "brand-projector-jmgo.json"),
                               "resolution": ("1080P", "pconline-projector-jmgo-1090694.json"),
                               "dmd": ("0.47英寸DMD", "pconline-projector-jmgo-1090694.json"),
                               "keystone": ("水平±30°，垂直±35°", "pconline-projector-jmgo-1090694.json"),
                               "focus": ("电动聚焦", "pconline-projector-jmgo-1090694.json")},
    "projector/dangbei_1592947": {"official_price": (5999, "brand-projector-dangbei.json")},
    "projector/dangbei_1471467": {"official_price": (4999, "brand-projector-dangbei.json")},
    "projector/dangbei_1471468": {"official_price": (2999, "brand-projector-dangbei.json")},
}

# 来源文件名 → verify_source 标签
def source_label(fn):
    if fn.startswith("miot-"):
        return "米家产品库(miot-spec)"
    if fn.startswith("search-") or fn.startswith("product-"):
        return "小米商城"
    return "太平洋电脑网"


def blank(v):
    return v in (None, "", "查不到", "—", "-") or (isinstance(v, list) and not v)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true", help="只看会改什么，不写文件")
    args = ap.parse_args()

    keys = sorted(set(PROSCONS) | set(VALUES))
    stats = {"written": 0, "fields": 0, "skipped": []}
    cats = {}

    for key in keys:
        cat, pid = key.split("/", 1)
        lib_path = os.path.join(ROOT, "data", cat, "products.json")
        schema_path = os.path.join(ROOT, "data", cat, "schema.json")
        if not os.path.exists(lib_path):
            stats["skipped"].append((key, "品类不存在"))
            continue
        products = json.load(open(lib_path, encoding="utf-8"))
        fields = set()
        if os.path.exists(schema_path):
            fields = {f.get("key") for f in
                      json.load(open(schema_path, encoding="utf-8")).get("fields", [])}
        src = next((p for p in products if p.get("id") == pid), None)
        if src is None:
            stats["skipped"].append((key, "库内没有这个 id"))
            continue

        prod = dict(src)
        touched = []
        labels = set()

        for f, (val, fn) in VALUES.get(key, {}).items():
            if fields and f not in fields:
                stats["skipped"].append((key, f"schema 无字段 {f}"))
                continue
            if not blank(prod.get(f)):
                stats["skipped"].append((key, f"{f} 已有值 {prod.get(f)}，不覆盖"))
                continue
            prod[f] = val
            touched.append(f)
            labels.add(source_label(fn))

        pc = PROSCONS.get(key)
        if pc:
            if blank(prod.get("pros")) and pc["pros"]:
                prod["pros"] = pc["pros"]
                touched.append("pros")
            if blank(prod.get("cons")) and pc["cons"]:
                prod["cons"] = pc["cons"]
                touched.append("cons")

        if not touched:
            stats["skipped"].append((key, "无可填字段（都已有值）"))
            continue

        # 审核标注字段：来源、日期、变更记录
        vs = prod.get("verify_source") or []
        if isinstance(vs, str):
            vs = [vs] if vs else []
        for lb in labels:
            if lb not in vs:
                vs.append(lb)
        prod["verify_source"] = vs
        prod["verify_date"] = D
        prod["updated_at"] = D
        note = f"{D} 补 {'、'.join(touched)}（来源：{'、'.join(sorted(labels)) or '已入库参数推导'}）"
        old = prod.get("change_log") or ""
        prod["change_log"] = (old + "；" if old else "") + note
        if labels and prod.get("verify_status") == "待核验":
            prod["verify_status"] = "已核验（第三方）"

        cats.setdefault(cat, []).append(pid)
        stats["written"] += 1
        stats["fields"] += len(touched)
        if not args.dry:
            out_dir = os.path.join(ROOT, "data", "_draft", cat)
            os.makedirs(out_dir, exist_ok=True)
            with open(os.path.join(out_dir, pid + ".json"), "w", encoding="utf-8") as f:
                json.dump(prod, f, ensure_ascii=False, indent=2)
                f.write("\n")

    print(f"\n丙路补丁落盘{'（--dry 未写文件）' if args.dry else ''}")
    print(f"  写入草稿区：{stats['written']} 款 / {stats['fields']} 个字段\n")
    for cat, ids in sorted(cats.items()):
        print(f"  {cat}: {len(ids)} 款 → data/_draft/{cat}/")
        print(f"    提交：npm run flow:submit -- " + " ".join(f"{cat}/{i}" for i in ids[:12])
              + (" …" if len(ids) > 12 else ""))
    if stats["skipped"]:
        print(f"\n  跳过 {len(stats['skipped'])} 项（前 15 条）：")
        for k, why in stats["skipped"][:15]:
            print(f"    · {k}：{why}")

    # 每个品类一条 submit 命令，写进脚本文件（id 多，手工拼容易漏）
    cmds = ["npm run flow:submit -- " + " ".join(f"{cat}/{i}" for i in ids) + " --by bing"
            for cat, ids in sorted(cats.items())]
    sh = os.path.join(ROOT, "data", "_cache", "_bing_submit.ps1")
    open(sh, "w", encoding="utf-8").write("\n".join(cmds) + "\n")
    print(f"\n  提交命令已生成（{len(cmds)} 条，每品类一条）：{os.path.relpath(sh, ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
