#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""给 verify_url 为「查不到」的小米产品反查商城 product_id。

背景：`fill-mi-official.py` 只能靠 `verify_url` 里的 `product_id=` 或本地缓存按名精确
反查，两条都拿不到的空调 19 款 / 净化器 18 款就卡住了。精确匹配失败的原因是
**商城商品名与本站名的语序不同**：

    本站   米家空调 柔风 1.5匹（新一级能效）
    商城   柔风 1.5匹新一级能效 米家空调 2199元 2699元

商城把品牌甩到末尾、把能效写进卖点串、把「（…）」摊平。本脚本按下面三步走，
每一步都比上一步更严，**匹配不上就留空，不猜**：

  1. 从本地 search-*.json 建候选池（品牌 token 剔除后做字符集包含打分）
  2. 逐个候选调商城 API，取回**权威商品名**（goods_info.name）
  3. 用权威商品名与本站名做归一比对，要求「型号词全覆盖且无多余词」

输出 JSON 到 data/_cache/mi-id-candidates.json，只作候选清单供人工确认，
本脚本**不写 products.json**。

用法：
    python scripts/mi-id-match.py --cat air-conditioner,air-purifier
    python scripts/mi-id-match.py --cat air-purifier --apply   # 把确认过的写进 verify_url
"""
import argparse
import glob
import json
import os
import re
import subprocess
import sys
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
API = "https://api2.order.mi.com/product/view?product_id=%s&version=2"

# 品牌 token：商城与本站的位置不同，比对前先剔掉
BRANDS = ("米家空调", "小米空调", "米家中央空调", "小米中央空调",
          "米家新风空调", "米家", "小米", "米家全效空气净化器", "米家空气净化器")
# 能效/口径词：两边写法不同（括号 vs 直接连写），比对前统一剔除
CALIBER = re.compile(
    r"超一级能效|新一级能效|一级能效|新国标|能效|[（(].*?[)）]|白色|黑色|银色|金色|"
    r"\d{4}年?款|\d{4}款|款|新版|升级款|标准版|增强版|Plus|PRO|Pro|pro")
PISHU = re.compile(r"(大?[\d.]+匹)")
# 判别词：产品线名。少了它就分不清同系列不同档，故要求至少命中一个
DISCRIM = ("巨省电", "柔风", "健康风", "人感", "新风", "新风Pro", "自然风", "强劲风",
           "风管机", "上出风", "双出风", "双排铜管", "除湿", "循环风",
           "全效", "净化器", "MAX", "Max", "增强版", "标准版", "Ultra", "ultra",
           "新风Pro", "除甲醛", "除过敏")


def dp(*a):
    return os.path.join(ROOT, *a)


def strip_noise(s):
    """剥品牌 token、括号备注、能效口径，留下可比对的骨架。"""
    s = str(s or "")
    s = re.sub(r"\d+\s*元.*$", "", s)          # 甩掉尾巴上的价格串
    for b in BRANDS:
        s = s.replace(b, "")
    s = CALIBER.sub("", s)
    s = re.sub(r"[（）()【】\[\]，,、·\-\s　]+", "", s)
    return s


def pishu_key(s):
    """匹数是同一产品线内最强的判别位，抽出来单独比对。"""
    m = PISHU.search(str(s or ""))
    return m.group(1).replace("大", "") if m else ""


def fetch_name(pid, retry=2):
    """取商城权威商品名。失败返回 None（不猜）。"""
    for attempt in range(retry + 1):
        try:
            r = subprocess.run(
                ["curl", "-sS", "-m", "20", "-A", UA,
                 "-H", "Referer: https://www.mi.com/",
                 "-H", "Accept-Language: zh-CN,zh;q=0.9", API % pid],
                capture_output=True)
            raw = r.stdout
        except Exception:
            raw = b""
        if len(raw) > 200:
            break
        time.sleep(1.0 * (attempt + 1))
    if len(raw) < 200:
        return None
    try:
        d = json.loads(raw.decode("utf-8", "replace"))
    except Exception:
        return None
    gl = d.get("data", {}).get("goods_list") or []
    if not gl:
        return None
    gi = gl[0].get("goods_info") or {}
    return {"name": str(gi.get("name") or "").strip(),
            "price": gi.get("price"), "market_price": gi.get("market_price")}


def build_pool():
    """候选池：{归一骨架: [(pid, 原始商品名)]}。"""
    pool = {}
    for f in glob.glob(dp("data", "_cache", "search-*.json")):
        try:
            d = json.load(open(f, encoding="utf-8"))
        except Exception:
            continue
        for it in (d if isinstance(d, list) else []):
            pid, txt = it.get("productId"), it.get("text") or ""
            if not (pid and txt):
                continue
            pool.setdefault(strip_noise(txt), []).append((str(pid), txt))
    return pool


def score(lib_name, cand_text):
    """候选打分：骨架完全一致最好，其次要求判别词命中且匹数一致。"""
    a, b = strip_noise(lib_name), strip_noise(cand_text)
    if not a or not b:
        return 0
    if a == b:
        return 100
    pa, pb = pishu_key(lib_name), pishu_key(cand_text)
    if pa and pb and pa != pb:
        return 0                      # 匹数不同 —— 一定是另一款，直接否掉
    if a in b or b in a:
        return 80
    # 判别词必须命中，且剩余字符不能有对方没有的「型号级」差异
    hit = [d for d in DISCRIM if d in lib_name and d in cand_text]
    if hit and pa and pb and pa == pb:
        return 60 - min(len(a) - len(b), 40) // 4
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cat", required=True, help="逗号分隔的品类")
    ap.add_argument("--out", default=dp("data", "_cache", "mi-id-candidates.json"))
    ap.add_argument("--apply", action="store_true",
                    help="把 --confirm 确认过的 pid 写进草稿区的 verify_url")
    ap.add_argument("--confirm", default="",
                    help="形如 cat/id:pid,cat/id:pid —— 人工确认后回填")
    args = ap.parse_args()

    cats = args.cat.split(",")
    pool = build_pool()
    print("候选池：%d 个商品名骨架" % len(pool))

    todo = []
    for cid in cats:
        pf = dp("data", "%s" % cid, "products.json")
        if not os.path.exists(pf):
            continue
        for p in json.load(open(pf, encoding="utf-8")):
            if p.get("brand") != "小米":
                continue
            if re.search(r"product_id=(\d+)", p.get("verify_url") or ""):
                continue          # 已有 id，不用查
            todo.append((cid, p))

    out = []
    for i, (cid, p) in enumerate(todo, 1):
        cands = []
        for key, items in pool.items():
            s = score(p["name"], items[0][1])
            if s <= 0:
                continue
            for pid, txt in items:
                cands.append((score(p["name"], txt), pid, txt))
        cands.sort(reverse=True)
        # 只留前 3 个，避免「小米空调 巨省电 1.5匹」这类撞一堆
        best = cands[:3]
        # 逐个候选取权威名再确认
        checks = []
        for s, pid, txt in best:
            time.sleep(1.2)
            got = fetch_name(pid)
            if not got:
                continue
            nm = got["name"]
            la, na = strip_noise(p["name"]), strip_noise(nm)
            ok = bool(la) and (la == na or la in na or na in la)
            checks.append({"score": s, "pid": pid, "search_text": txt,
                           "api_name": nm, "price": got.get("price"),
                           "market_price": got.get("market_price"),
                           "match": ok})
        out.append({"cat": cid, "id": p["id"], "name": p["name"],
                    "candidates": checks})
        flag = "OK" if any(c["match"] for c in checks) else "--"
        print("  [%d/%d] %s %s/%s" % (i, len(todo), flag, cid, p["id"]), flush=True)
        for c in checks:
            print("        %s pid=%s %r (score %d)" % (
                "✓" if c["match"] else "✗", c["pid"], c["api_name"], c["score"]))

    json.dump(out, open(args.out, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    hit = sum(1 for r in out if any(c["match"] for c in r["candidates"]))
    print("\n%d 款无 id 的小米产品，%d 款找到唯一匹配候选 -> %s"
          % (len(out), hit, os.path.relpath(args.out, ROOT)))
    return 0


if __name__ == "__main__":
    sys.exit(main())