#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""把丙路调查子 Agent 产出的 pros / cons 落盘到草稿区。

## 与批次 1 的区别

这次的基底**不是库**，而是 `data/_draft/<品类>/<id>.json`——批次 2 的数值回填订正稿
（tv / water-heater / water-purifier / bath-heater 共 91 款）已撤回草稿区等待合并，
所以必须先撤回再合并，否则同一产品会出现两份订正稿（一份补数值、一份补卖点），
B 认领时会被「修正区已有该产品的文件」挡住。

## 审核时剔除的东西

子 Agent 最初把「数据缺失」写成了产品缺点（`cons: ["解锁方式未公开", "尺寸未公开"]`）。
那是**我们没数据**，不是产品短板，写进站点会被访客读成缺点。凡含
「未公开 / 未标注 / 未注明」的 cons 一律不采纳；只保留有明确否定依据的
（`material=塑料`、`energy=二级`、半自动需下压把手、开孔非通用尺寸 等）。

## 用法

    python scripts/apply-bing-proscons.py            # 写入 data/_draft/
    python scripts/apply-bing-proscons.py --dry      # 只看会写什么

随后按生成的 `data/_cache/_bing_submit3.ps1` 提交。
"""
import argparse
import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D = "2026-10-04"

# (pros, cons) —— 已剔除「数据缺失冒充缺点」的 cons
PC = {
    # —— C3：water-purifier ——
    "water-purifier/wp2_1600": (["1600G 大通量", "RO 反渗透过滤"], ["单出水无生活水路"]),
    "water-purifier/wp2_1200": (["1200G 大通量", "RO 反渗透过滤"], ["单出水无生活水路"]),
    "water-purifier/wp_dual_core": (["1200G 大通量", "RO 反渗透过滤"], ["单出水无生活水路"]),
    "water-purifier/wp_n1_800": (["800G 通量", "RO 反渗透过滤"], ["单出水无生活水路"]),
    "water-purifier/wp2_boil": (["即热出热水", "RO 反渗透过滤"], []),
    "water-purifier/qinyuan_1940207": (["净水流量 3L", "厨下安装不占台面"], []),
    "water-purifier/qinyuan_1940227": (["净水流量 2t/h", "厨下安装不占台面"], []),
    "water-purifier/qinyuan_1818167": (["净水流量 2.5升/分", "厨下安装不占台面"], []),
    "water-purifier/qinyuan_1818127": (["净水流量 2.5升/分", "厨下安装不占台面"], []),
    "water-purifier/angel_2479859": (["纯水 2.1L/min", "净水 4T/h"], []),
    "water-purifier/angel_2479779": (["纯水 2L/min", "全屋中央式净水"], []),
    "water-purifier/midea_2502559": (["净水流量 2.5t/h", "厨下安装不占台面"], []),
    "water-purifier/midea_1802907": (["净水流量 1.5升/分", "厨下安装不占台面"], []),
    "water-purifier/midea_1518087": (["净水流量 3L/分", "厨下安装不占台面"], []),
    "water-purifier/haier_2014307": (["净水流量 2t/h", "厨下安装不占台面"], []),
    "water-purifier/haier_2539159": (["净水流量 3t/h", "厨下安装不占台面"], []),
    "water-purifier/haier_2605519": (["净水流量 2.4t/h", "厨下安装不占台面"], []),
    "water-purifier/haier_2303199": (["净水流量 2t/h", "厨下安装不占台面"], []),
    "water-purifier/3m_1915127": (["净水流量 3升/分", "厨下安装不占台面"], []),
    "water-purifier/3m_1915107": (["净水流量 3升/分", "厨下安装不占台面"], []),
    "water-purifier/3m_1915147": (["净水流量 1.84升/分", "厨下安装不占台面"], []),
    # —— C3：bath-heater ——
    "bath-heater/bath_base": (["2400W 风暖功率", "48W 吹风功率", "41W 换气功率"], []),
    "bath-heater/bath_pro": (["2800W 风暖功率", "风暖式取暖", "30W 换气功率"], []),
    "bath-heater/bath_s1": (["2800W 风暖功率", "风暖式取暖", "适配300×600吊顶"], []),
    "bath-heater/bath_n1": (["2600W 风暖功率", "风暖式取暖", "适配300×600吊顶"], []),
    "bath-heater/bath_p1": (["适配300×600吊顶", "24W 照明功率"], []),
    "bath-heater/bath_p1_human": (["适配300×600吊顶", "24W 照明功率"], []),
    "bath-heater/bath_g10": (["灯暖+风暖双模式", "36W 换气功率", "适配300×600吊顶"], []),
    "bath-heater/bath_g20": (["2800W 风暖功率", "33W 换气功率", "适配300×600吊顶"], []),
    "bath-heater/bath_2": (["适配300×600吊顶", "22W 吹风功率"], []),
    "bath-heater/bath_2c": (["24W 吹风功率", "24W 换气功率", "适配300×600吊顶"], []),
    "bath-heater/aupu_638077": (["2600W 风暖功率", "30W 吹风功率", "30W 换气功率"], ["开孔 559×275 非通用"]),
    "bath-heater/aupu_1949227": (["2700W 风暖功率", "55W 吹风功率", "55W 换气功率"], []),
    "bath-heater/aupu_1949247": (["2700W 风暖功率", "55W 吹风功率", "55W 换气功率"], []),
    "bath-heater/aupu_1949327": (["2600W 风暖功率", "55W 吹风功率", "55W 换气功率"], []),
    "bath-heater/aupu_1949347": (["2800W 风暖功率", "55W 吹风功率", "55W 换气功率"], []),
    "bath-heater/opple_1221559": (["35W 换气功率", "15W 照明功率", "适配300×600吊顶"], []),
    "bath-heater/opple_1417684": (["35W 吹风功率", "35W 换气功率", "适配300×600吊顶"], []),
    "bath-heater/opple_637819": (["2000W 风暖功率", "30W 换气功率", "适配300×600吊顶"], ["2000W 取暖功率偏低"]),
    "bath-heater/opple_1409503": (["32W 照明功率", "30W 吹风功率", "适配300×600吊顶"], []),
    "bath-heater/opple_1417606": (["30W 换气功率", "15W 照明功率", "适配300×600吊顶"], []),
    "bath-heater/panasonic_1956267": (["2650W 风暖功率", "适配300×600吊顶"], []),
    "bath-heater/panasonic_1956167": (["2650W 风暖功率", "适配300×600吊顶"], []),
    "bath-heater/panasonic_1956087": (["2650W 风暖功率", "适配300×600吊顶"], []),
    "bath-heater/panasonic_638199": (["2100W 风暖功率", "25W 换气功率", "照明强弱两档"], ["2100W 取暖功率偏低"]),
    "bath-heater/panasonic_1955667": (["2650W 风暖功率", "24W 换气功率", "适配600×300吊顶"], []),
    "bath-heater/nvc_1950787": (["2800W 风暖功率", "40W 吹风功率", "40W 换气功率"], []),
    "bath-heater/nvc_1950847": (["2800W 风暖功率", "40W 吹风功率", "40W 换气功率"], []),
    "bath-heater/nvc_1950107": (["3000W 风暖功率", "30W 吹风功率", "适配300×600吊顶"], []),
    "bath-heater/nvc_1950687": (["2800W 风暖功率", "40W 吹风功率", "40W 换气功率"], []),
    "bath-heater/nvc_1950747": (["3000W 风暖功率", "30W 吹风功率", "30W 换气功率"], []),
    "bath-heater/midea_1953287": (["2800W 风暖功率", "40W 吹风功率", "45W 换气功率"], []),
    "bath-heater/midea_1951267": (["2800W 风暖功率", "50W 吹风功率", "36W 换气功率"], []),
    "bath-heater/midea_1962747": (["2800W 风暖功率", "45W 换气功率", "5kg 机身重量"], []),
    "bath-heater/midea_1953227": (["2800W 风暖功率", "45W 吹风功率", "45W 换气功率"], []),
    "bath-heater/midea_1951327": (["2800W 风暖功率", "45W 吹风功率", "45W 换气功率"], []),
    # —— C4a：tv ——
    "tv/hisense_2632599": (["85 英寸大屏", "8GB+128GB 内存", "Mini LED 背光"], ["165Hz 刷新偏低", "HDMI 仅 3 个"]),
    "tv/hisense_2964350": (["100 英寸大屏", "300Hz 高刷新", "HDMI 4 个"], ["3GB+64GB 内存偏小"]),
    "tv/hisense_2687959": (["100 英寸大屏", "4GB+128GB 内存", "HDMI 4 个"], []),
    "tv/hisense_2700859": (["85 英寸大屏", "300Hz 高刷新", "4GB+64GB 内存"], []),
    "tv/hisense_2689279": (["98 英寸大屏", "4GB+128GB 内存", "288Hz 刷新"], ["LED 背光非 Mini LED", "HDMI 仅 2 个"]),
    "tv/tcl_2986362": (["85 英寸大屏", "300Hz 高刷新", "Mini LED 背光"], ["3GB+64GB 内存偏小"]),
    "tv/tcl_2805391": (["75 英寸大屏", "300Hz 高刷新", "Mini LED 背光"], []),
    "tv/tcl_2816671": (["98 英寸大屏", "4GB+128GB 内存", "Mini LED 背光"], []),
    "tv/tcl_2816651": (["85 英寸大屏", "Mini LED 背光", "HDMI 4 个"], []),
    "tv/tcl_2719659": (["85 英寸大屏", "QD-Mini LED 背光", "HDMI 4 个"], ["2024 年上市较早"]),
    "tv/skyworth_2975422": (["100 英寸大屏", "480Hz 高刷新", "机身厚 27mm"], ["售价 35999 元最高"]),
    "tv/skyworth_2838551": (["480Hz 高刷新", "85 英寸大屏", "Mini LED 背光"], ["HDMI 仅 2 个"]),
    "tv/skyworth_2799371": (["480Hz 高刷新", "4GB+128GB 内存", "Mini LED 背光"], []),
    "tv/skyworth_2755039": (["100 英寸大屏", "4GB+128GB 内存", "300Hz 高刷新"], ["HDMI 仅 3 个"]),
    "tv/skyworth_2727819": (["85 英寸大屏", "300Hz 高刷新", "Mini LED 背光"], ["HDMI 仅 3 个"]),
    "tv/sony_2912771": (["85 英寸大屏", "HDMI 2.1 双接口", "RGB LED 背光"], ["120Hz 刷新偏低", "85 英寸段价最高"]),
    "tv/sony_2617099": (["98 英寸大屏", "HDMI 2.1 双接口", "Mini LED 背光"], ["120Hz 刷新偏低", "存储仅 32GB"]),
    "tv/sony_2193939": (["77 英寸大屏", "OLED 面板背光", "3840×2160 分辨率"], ["2024 年上市较早"]),
    "tv/sony_2912751": (["75 英寸大屏", "HDMI 2.1 双接口", "RGB LED 背光"], ["120Hz 刷新偏低", "75 英寸段价最高"]),
    "tv/sony_2913151": (["OLED 面板背光", "HDMI 2.1 双接口", "65 英寸机型"], ["120Hz 刷新偏低", "65 英寸段价最高"]),
    "tv/haier_2999742": (["85 英寸大屏", "Mini LED 背光", "288Hz 刷新"], []),
    "tv/haier_2926791": (["85 英寸大屏", "Mini LED 背光", "HDMI 4 个"], []),
    "tv/haier_2506839": (["75 英寸大屏", "4GB+64GB 内存", "144Hz 刷新"], ["144Hz 刷新偏低", "HDMI 仅 2 个", "2024 年上市较早"]),
    "tv/haier_2926751": (["85 英寸大屏", "Mini LED 背光", "HDMI 4 个"], []),
    "tv/haier_2926811": (["75 英寸大屏", "Mini LED 背光", "HDMI 4 个"], []),
    "tv/changhong_65_x90h": (["480Hz 高刷新", "Mini LED 背光", "4GB+64GB 内存"], ["HDMI 仅 3 个"]),
    "tv/changhong_75_d7h_pro": (["6GB+64GB 内存", "Mini LED 背光", "75 英寸大屏"], ["HDMI 仅 3 个"]),
    "tv/hisense_65_e8q_pro": (["330Hz 高刷新", "4GB+128GB 内存", "Mini LED 背光"], []),
    "tv/hisense_75_e8q": (["330Hz 高刷新", "Mini LED 背光", "HDMI 4 个"], []),
    "tv/konka_65_d7j": (["Mini LED 背光", "4GB+64GB 内存", "288Hz 刷新"], ["HDMI 仅 2 个"]),
    "tv/konka_75_d7j": (["4GB+128GB 内存", "Mini LED 背光", "75 英寸大屏"], ["HDMI 仅 2 个"]),
    "tv/tcl_65_t7l_ultra": (["Mini LED 背光", "288Hz 刷新", "HDMI 4 个"], []),
    "tv/tcl_75_t7l_ultra": (["Mini LED 背光", "288Hz 刷新", "HDMI 4 个"], []),
    # —— C4b：water-heater ——
    "water-heater/wh_gas_pro": (["16L 升数", "燃气即开即热"], ["需燃气管道与强排条件"]),
    "water-heater/wh_ele_pro": (["60L 容量", "无需燃气管道"], ["储水式需预热"]),
    "water-heater/wh_ele_2": (["60L 容量", "无需燃气管道"], ["储水式需预热"]),
    "water-heater/wh_ele_n1": (["60L 容量", "官方价 999 元"], ["储水式需预热"]),
    "water-heater/wh_ele_c": (["60L 容量", "官方价 799 元"], ["储水式需预热"]),
    "water-heater/wh_ele_s1": (["60L 容量", "双胆节省空间"], ["储水式需预热"]),
    "water-heater/wh_ele_p1": (["60L 容量", "双胆节省空间"], ["储水式需预热"]),
    "water-heater/haier_1221253": (["80L 大容量", "一级能效", "3000W 加热"], ["机身长 835mm"]),
    "water-heater/haier_1448547": (["60L 容量", "一级能效", "3300W 加热"], ["机身长 833mm"]),
    "water-heater/haier_1450507": (["50L 容量", "一级能效", "5000W 速热"], ["5000W 需专线"]),
    "water-heater/haier_2627119": (["80-100L 大容量", "一级能效", "机身厚仅 310mm"], ["机身长 890mm"]),
    "water-heater/haier_2627199": (["60-79L 容量", "一级能效", "机身厚仅 310mm"], []),
    "water-heater/midea_2726059": (["60-79L 容量", "一级能效", "机身厚仅 320mm"], []),
    "water-heater/midea_2649239": (["60-79L 容量", "5000W 速热", "机身厚仅 260mm"], ["能效为二级", "5000W 需专线"]),
    "water-heater/midea_2585299": (["60-79L 容量", "一级能效", "机身厚仅 320mm"], []),
    "water-heater/midea_2626959": (["60-79L 容量", "一级能效", "机身厚仅 316mm"], []),
    "water-heater/midea_2626979": (["80-100L 大容量", "一级能效", "3300W 加热"], []),
    "water-heater/rinnai_1045252": (["24L 升数", "机身厚仅 160mm"], ["能效为二级", "需燃气管道与强排条件"]),
    "water-heater/rinnai_1045180": (["20L 升数", "机身厚仅 160mm"], ["能效为二级", "需燃气管道与强排条件"]),
    "water-heater/rinnai_1921687": (["60-79L 容量", "3200W 加热"], ["能效为二级", "机身长 1000mm"]),
    "water-heater/rinnai_1039594": (["16L 升数", "机身厚仅 144mm"], ["能效为二级", "需燃气管道与强排条件"]),
    "water-heater/rinnai_1921667": (["60-79L 容量", "3200W 加热"], ["能效为二级", "机身长 1000mm"]),
    "water-heater/aosmith_13_tec": (["13L 升数", "热负荷 25.5kW"], ["能效为二级", "需燃气管道与强排条件"]),
    "water-heater/aosmith_16_bjewi": (["16L 升数", "一级能效", "热负荷 27.5kW"], ["需燃气管道与强排条件"]),
    "water-heater/macro_16_j9r1": (["16L 升数", "热负荷 30kW"], ["能效为二级", "需燃气管道与强排条件"]),
    "water-heater/macro_16_tlu5": (["16L 升数", "一级能效", "支持 APP 操控"], ["需燃气管道与强排条件"]),
    "water-heater/nenglv_13_g31": (["13L 升数", "支持语音控制"], ["能效为二级", "需燃气管道与强排条件"]),
    "water-heater/nenglv_16_g31": (["14-16L 升数", "热负荷 31kW"], ["能效为二级", "需燃气管道与强排条件"]),
    "water-heater/vanward_16_ls5pro": (["16L 升数", "一级能效", "热负荷 27kW"], ["需燃气管道与强排条件"]),
    "water-heater/vanward_16_v6pro": (["16L 升数", "支持 APP 操控"], ["能效为二级", "需燃气管道与强排条件"]),
}


def blank(v):
    return v in (None, "", "查不到", "—", "-") or (isinstance(v, list) and not v)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true")
    args = ap.parse_args()

    written, skipped, cats = 0, [], {}
    for key, (pros, cons) in sorted(PC.items()):
        cat, pid = key.split("/", 1)
        # 基底优先用草稿区（批次 2 撤回的数值订正稿），没有再退回库
        draft = os.path.join(ROOT, "data", "_draft", cat, pid + ".json")
        lib = os.path.join(ROOT, "data", cat, "products.json")
        base = draft if os.path.exists(draft) else lib
        if not os.path.exists(base):
            skipped.append((key, "库里没有这个产品"))
            continue
        products = json.load(open(lib, encoding="utf-8"))
        src = next((p for p in products if p.get("id") == pid), None)
        if src is None:
            skipped.append((key, "库内没有这个 id"))
            continue
        prod = json.load(open(draft, encoding="utf-8")) if os.path.exists(draft) else dict(src)

        touched = []
        if blank(prod.get("pros")) and pros:
            prod["pros"] = pros
            touched.append("pros")
        if blank(prod.get("cons")) and cons:
            prod["cons"] = cons
            touched.append("cons")
        if not touched:
            skipped.append((key, "pros/cons 已有值"))
            continue

        prod["verify_date"] = D
        prod["updated_at"] = D
        note = f"{D} 补 {'、'.join(touched)}（由已入库参数推导，不引入新数值）"
        old = prod.get("change_log") or ""
        prod["change_log"] = (old + "；" if old else "") + note

        cats.setdefault(cat, []).append(pid)
        written += 1
        if not args.dry:
            out = os.path.join(ROOT, "data", "_draft", cat)
            os.makedirs(out, exist_ok=True)
            with open(os.path.join(out, pid + ".json"), "w", encoding="utf-8") as f:
                json.dump(prod, f, ensure_ascii=False, indent=2)
                f.write("\n")

    print(f"\npros/cons 落盘{'（--dry 未写文件）' if args.dry else ''}：{written} 款\n")
    for cat, ids in sorted(cats.items()):
        print(f"  {cat}: {len(ids)} 款")
    if skipped:
        print(f"\n  跳过 {len(skipped)} 项：")
        for k, why in skipped[:10]:
            print(f"    · {k}：{why}")
    cmds = ["npm run flow:submit -- " + " ".join(f"{c}/{i}" for i in sorted(ids)) + " --by bing"
            for c, ids in sorted(cats.items())]
    sh = os.path.join(ROOT, "data", "_cache", "_bing_submit3.ps1")
    open(sh, "w", encoding="utf-8").write("\n".join(cmds) + "\n")
    print(f"\n  提交命令：{os.path.relpath(sh, ROOT)}（{len(cmds)} 条）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
