#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""探测候选数据源站点的可用性与抗限流能力（只读外网，不写数据区）。

为什么要这个脚本：本站竞品 617/618 款的参数来源**只有太平洋一家**
（ZOL 仅在 fetch-facet-evidence.py 里补分类证据，没有独立抓取流水线）。
单点依赖意味着太平洋一改版或一限流，整个竞品采集就停摆，且规范要求的
「权威第三方需两处相互印证」实际上做不到。扩充来源前必须先知道：
候选站**能不能抓**（服务端渲染还是纯 JS）、**抗不抗造**（连续请求会不会限流）。

做法：对每个候选 URL 连续发 `ROUNDS` 次请求（间隔 `GAP` 秒），逐次记录
HTTP 码、下载字节数与「是否含规格关键词」。三次里后段劣化的即判为限流。

用法：
    python scripts/probe-sources.py                    # 探测全部候选
    python scripts/probe-sources.py --only third       # 只探测某个分组
    python scripts/probe-sources.py --only official --rounds 5
    python scripts/probe-sources.py --out data/_cache/source-probe.json

输出：控制台摘要表 + JSON（默认 data/_cache/source-probe.json，已 gitignore）。
本脚本不写 data/ 下的任何产品数据，可以放心跑。
"""
import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UA_DESKTOP = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

# 规格表特征词：命中说明页面是服务端渲染的、参数可直接解析（不必开浏览器）
SPEC_HINTS = ["规格参数", "产品参数", "基本参数", "重要参数", "能效等级",
              "产品类型", "产品类别", "额定功率", "CADR", "制冷剂"]
# 风控特征词：命中说明被拦在人机验证 / WAF 上
BLOCK_HINTS = ["验证码", "人机验证", "访问验证", "访问受限", "请您稍后再试",
               "安全检测", "security check", "Are you a robot", "滑动验证"]

# ---------------------------------------------------------------- 候选站点
# kind 分组：third=权威第三方规格站 / official=品牌官方 / verify=权威核验 / media=媒体印证
# note 写「预期能产出什么」，探测后由数据说话，不靠印象下结论
CANDIDATES = [
    # —— 权威第三方规格站（目标：第二家能与太平洋互证的结构化来源）——
    {"id": "zol", "kind": "third", "name": "中关村在线 ZOL",
     "url": "https://search.zol.com.cn/s/all.php?kword=KFR-35GW",
     "note": "已有解析器（fetch-facet-evidence.py）；param.shtml 含产品类型等分类栏"},
    {"id": "suning", "kind": "third", "name": "苏宁易购",
     "url": "https://search.suning.com/%E7%A9%BA%E8%B0%83/",
     "note": "家电覆盖全，自营商品页有规格表"},
    {"id": "gome", "kind": "third", "name": "国美",
     "url": "https://www.gome.com.cn/",
     "note": "家电起家，商品页含参数"},
    {"id": "jd", "kind": "third", "name": "京东",
     "url": "https://search.jd.com/Search?keyword=%E7%A9%BA%E8%B0%83",
     "note": "覆盖最广，但风控较强，需实测"},
    {"id": "it168", "kind": "third", "name": "IT168 产品库",
     "url": "https://product.it168.com/",
     "note": "3C 为主，家电也有参数页"},
    {"id": "yesky", "kind": "third", "name": "天极网产品库",
     "url": "https://product.yesky.com/",
     "note": "老牌 IT 媒体产品库"},
    {"id": "ea3w", "kind": "third", "name": "万维家电网",
     "url": "https://www.ea3w.com/",
     "note": "家电垂直站，有产品库"},
    {"id": "cheaa", "kind": "third", "name": "中国家电网",
     "url": "https://www.cheaa.com/",
     "note": "行业站，偏资讯，可作品类与新品线索"},
    {"id": "manmanbuy", "kind": "third", "name": "慢慢买",
     "url": "https://www.manmanbuy.com/",
     "note": "比价站，价格口径线索"},

    # —— 品牌官方（来源优先级最高，但每家结构不同）——
    {"id": "midea", "kind": "official", "name": "美的",
     "url": "https://www.midea.cn/", "note": "官方商城/规格"},
    {"id": "haier", "kind": "official", "name": "海尔",
     "url": "https://www.haier.com/", "note": "官网/智家商城"},
    {"id": "gree", "kind": "official", "name": "格力",
     "url": "https://www.gree.com/", "note": "官网/格力商城"},
    {"id": "tcl", "kind": "official", "name": "TCL",
     "url": "https://www.tcl.com/", "note": "官网"},
    {"id": "hisense", "kind": "official", "name": "海信",
     "url": "https://www.hisense.com/", "note": "官网"},
    {"id": "panasonic", "kind": "official", "name": "松下中国",
     "url": "https://www.panasonic.com/cn/", "note": "官网 + 说明书 PDF（额定值最权威）"},
    {"id": "dyson", "kind": "official", "name": "戴森中国",
     "url": "https://www.dyson.cn/", "note": "官网规格"},
    {"id": "ecovacs", "kind": "official", "name": "科沃斯",
     "url": "https://www.ecovacs.cn/", "note": "官网规格"},
    {"id": "roborock", "kind": "official", "name": "石头科技",
     "url": "https://www.roborock.com/", "note": "官网规格"},
    {"id": "dreame", "kind": "official", "name": "追觅",
     "url": "https://www.dreame.cn/", "note": "官网规格"},
    {"id": "tineco", "kind": "official", "name": "添可",
     "url": "https://www.tineco.com/", "note": "官网规格"},
    {"id": "supor", "kind": "official", "name": "苏泊尔",
     "url": "https://www.supor.com/", "note": "官网规格"},
    {"id": "joyoung", "kind": "official", "name": "九阳",
     "url": "https://www.joyoung.com/", "note": "官网规格"},
    {"id": "philips", "kind": "official", "name": "飞利浦中国",
     "url": "https://www.philips.com.cn/", "note": "官网 + 说明书"},
    {"id": "robam", "kind": "official", "name": "老板电器",
     "url": "https://www.robam.com/", "note": "官网规格"},

    # —— 已在用的来源（基线：用来和候选做同口径对比）——
    {"id": "pconline", "kind": "current", "name": "太平洋产品报价",
     "url": "https://g.pconline.com.cn/product/cleaning_machine/mijia/",
     "note": "竞品参数的唯一主力流水线，单点依赖，需第二家互证"},
    {"id": "mi", "kind": "current", "name": "小米商城 / 官方 API",
     "url": "https://www.mi.com/", "note": "小米系官方来源"},
    {"id": "miot-spec", "kind": "current", "name": "home.miot-spec.com",
     "url": "https://home.miot-spec.com/", "note": "社区维护的 MIoT 协议型号库，仅作交叉印证"},
    {"id": "smzdm", "kind": "current", "name": "什么值得买",
     "url": "https://www.smzdm.com/", "note": "媒体，只能印证不能单独定值"},

    # —— 权威核验（型号存在性 / 能效 / 家商用判定的硬证据）——
    {"id": "energylabel", "kind": "verify", "name": "中国能效标识网",
     "url": "https://www.energylabel.cn/", "note": "能效备案查询：型号 + 能效等级"},
    {"id": "cnca", "kind": "verify", "name": "全国认证认可信息公共服务平台",
     "url": "https://cx.cnca.cn/", "note": "CCC 证书查询：核对型号与制造商"},
    {"id": "qybz", "kind": "verify", "name": "企业标准信息公共服务平台",
     "url": "https://www.qybz.org.cn/", "note": "企标备案，可核参数口径"},
]

KIND_LABEL = {"current": "在用的", "third": "权威第三方", "official": "品牌官方",
              "verify": "权威核验", "media": "媒体印证", "community": "社区/个人"}


def fetch(url, timeout=20):
    """单次请求。返回 (http_code, bytes, text)；失败返回 (None, 0, None)。"""
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".html")
    tmp.close()
    try:
        cmd = ["curl", "-sL", "-m", str(timeout), "-A", UA_DESKTOP,
               "-o", tmp.name, "-w", "%{http_code} %{size_download}", url]
        r = subprocess.run(cmd, capture_output=True)
        meta = (r.stdout or b"").decode("utf-8", "replace").strip().split()
        code = int(meta[0]) if meta and meta[0].isdigit() else None
        size = int(meta[1]) if len(meta) > 1 and meta[1].isdigit() else 0
        raw = open(tmp.name, "rb").read()
        text = None
        for enc in ("utf-8", "gb18030", "gbk"):
            try:
                text = raw.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        return code, len(raw), text
    except Exception as e:  # noqa: BLE001 - 探测脚本，失败要记下来而不是中断
        return None, 0, f"ERROR: {e}"
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass


def probe_one(cand, rounds, gap):
    """连续 rounds 次请求，逐次记录；返回结构化结果。"""
    results = []
    for i in range(rounds):
        code, size, text = fetch(cand["url"])
        hit_spec = bool(text) and any(h in text for h in SPEC_HINTS)
        hit_block = bool(text) and any(h in text for h in BLOCK_HINTS)
        results.append({"code": code, "size": size,
                        "spec": hit_spec, "block": hit_block})
        if i < rounds - 1:
            time.sleep(gap)

    codes = [r["code"] for r in results]
    sizes = [r["size"] for r in results]
    first_ok = codes[0] == 200 and sizes[0] >= 2000
    later_bad = any((c != 200 or s < 2000) for c, s in zip(codes[1:], sizes[1:]))
    blocked = any(r["block"] for r in results) or (codes[0] is not None and codes[0] >= 400)

    if codes[0] is None:
        verdict = "unreachable"     # 域名不通 / 超时
    elif blocked:
        verdict = "blocked"         # 被 WAF 或人机验证拦住
    elif not first_ok:
        verdict = "empty"           # 通但拿不到内容（多为纯 JS 渲染）
    elif later_bad:
        verdict = "rate-limited"    # 首次可抓，连续请求后劣化
    else:
        verdict = "ok"

    return {
        **{k: cand[k] for k in ("id", "kind", "name", "url", "note")},
        "verdict": verdict,
        "codes": codes,
        "sizes": sizes,
        "specRendered": any(r["spec"] for r in results),
        "rounds": rounds,
    }


def progress(done, total, width=28):
    filled = int(width * done / total) if total else 0
    bar = "█" * filled + "░" * (width - filled)
    return f"\r  探测中 |{bar}| {done}/{total} ({100 * done // max(total, 1)}%)"


def main():
    ap = argparse.ArgumentParser(description="探测候选数据源站点")
    ap.add_argument("--only", default=None, help="只探测某个分组：third/official/verify")
    ap.add_argument("--rounds", type=int, default=3, help="每站连续请求次数（默认 3）")
    ap.add_argument("--gap", type=float, default=1.0, help="同站两次请求间隔秒（默认 1）")
    ap.add_argument("--workers", type=int, default=5, help="并发站点数（默认 5）")
    ap.add_argument("--out", default=os.path.join(ROOT, "data", "_cache", "source-probe.json"))
    args = ap.parse_args()

    cands = CANDIDATES if not args.only else [c for c in CANDIDATES if c["kind"] == args.only]
    if not cands:
        print(f"✗ --only {args.only} 没有匹配的候选（可选：third/official/verify）")
        return 1

    print(f"\n数据源探测：{len(cands)} 个站点，每站 {args.rounds} 次请求（间隔 {args.gap}s）\n")
    sys.stdout.write(progress(0, len(cands)))
    sys.stdout.flush()

    out = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futs = {pool.submit(probe_one, c, args.rounds, args.gap): c for c in cands}
        for i, f in enumerate(as_completed(futs), 1):
            out.append(f.result())
            sys.stdout.write(progress(i, len(cands)))
            sys.stdout.flush()
    print("\n")

    order = {"ok": 0, "rate-limited": 1, "empty": 2, "blocked": 3, "unreachable": 4}
    out.sort(key=lambda r: (r["kind"], order.get(r["verdict"], 9), r["id"]))

    label = {"ok": "可用", "rate-limited": "连续请求劣化", "empty": "纯JS/无内容",
             "blocked": "被拦", "unreachable": "不通"}
    print(f"{'分组':<10}{'站点':<22}{'判定':<16}{'HTTP':<16}{'规格表':<8}")
    print("-" * 74)
    for r in out:
        print(f"{KIND_LABEL.get(r['kind'], r['kind']):<10}{r['name']:<22}"
              f"{label.get(r['verdict'], r['verdict']):<16}"
              f"{str(r['codes']):<16}{'是' if r['specRendered'] else '—':<8}")

    summary = {}
    for r in out:
        summary[r["verdict"]] = summary.get(r["verdict"], 0) + 1
    print("\n汇总：" + " · ".join(f"{label.get(k, k)} {v}" for k, v in
                                sorted(summary.items(), key=lambda x: order.get(x[0], 9))))

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump({"ts": time.strftime("%Y-%m-%d %H:%M:%S"),
                   "rounds": args.rounds, "gap": args.gap, "results": out},
                  f, ensure_ascii=False, indent=2)
    print(f"\n明细已写入 {os.path.relpath(args.out, ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
