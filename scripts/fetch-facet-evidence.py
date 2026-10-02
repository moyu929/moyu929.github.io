#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""为「副分组未归类」的竞品批量补抓分类证据（只读 products.json，不改数据）。

背景：classify-facets.py 靠 pconline 缓存里的少数几个分类字段判定副分组，
字段缺失时保持「未归类」。本脚本对每条未归类产品补抓两路证据：

  1. 太平洋产品报价（pconline）完整规格表 —— 取自产品自己的 verify_url，
     输出全部 {参数名: 值}，不再只挑 WANT_FIELDS。
  2. 中关村在线（ZOL）参数页 —— 先按型号搜到产品卡片，再取
     detail.zol.com.cn/<catId>/<proId>/param.shtml 的「重要参数 / 基本参数」，
     其中含「产品类型」「安装方式」等本站 facet 直接需要的分类字段。

输出 JSON：{"<品类>/<产品id>": {"model":..., "pconline": {...}, "zol": {...}, "zol_url":...}}
默认写到 data/_cache/facet-evidence/（该目录已 gitignore，只作抓取缓存）。

用法：
    python scripts/fetch-facet-evidence.py                 # 抓全部未归类竞品
    python scripts/fetch-facet-evidence.py heater kettle    # 只抓指定品类
    python scripts/fetch-facet-evidence.py --out D:/tmp/fe.json --workers 6
"""
import argparse
import glob
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UA_DESKTOP = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
CELL = re.compile(r"<t[dh][^>]*>(.*?)</t[dh]>", re.S)
ROW = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S)
TAG = re.compile(r"<[^>]+>")
SCRIPT = re.compile(r"<script.*?</script>|<style.*?</style>", re.S)


def curl(url, referer=None, timeout=25, retries=3):
    """走 curl 取页面（GBK/GB18030 站为主），返回解码后的 str。

    太平洋/ZOL 同一 IP 高频并发会被限流（返回空 body），故失败退避重试。
    """
    import random
    import subprocess
    for attempt in range(retries):
        cmd = ["curl", "-sL", "-m", str(timeout), "-A", UA_DESKTOP, url]
        if referer:
            cmd += ["-H", "Referer: " + referer]
        r = subprocess.run(cmd, capture_output=True)
        raw = r.stdout
        if len(raw) >= 2000:
            for enc in ("gb18030", "utf-8", "gbk"):
                try:
                    return raw.decode(enc)
                except UnicodeDecodeError:
                    continue
            return raw.decode("utf-8", "replace")
        time.sleep(1.5 * (attempt + 1) + random.random())
    return None


def plain(t):
    t = SCRIPT.sub(" ", t)
    t = re.sub(r"<br\s*/?>", "\n", t)
    return t


def clean(s):
    s = s.replace("&nbsp;", " ").replace("&amp;", "&").replace("&yen;", "¥")
    s = re.sub(r"&#\d+;", " ", s)
    return re.sub(r"\s+", " ", TAG.sub(" ", s)).strip()


# ---------------- 太平洋 ----------------

def parse_pconline(html):
    """把太平洋参数表解析成 {参数名: 值}。表格是 th/td 混排，按两列一组配对。"""
    out = {}
    for row in ROW.findall(html):
        cells = [clean(c) for c in CELL.findall(row)]
        cells = [c for c in cells if c]
        for i in range(0, len(cells) - 1, 2):
            k, v = cells[i], cells[i + 1]
            if k and v and len(k) <= 20 and k not in out:
                out[k] = v
    return out


# ---------------- ZOL ----------------

def norm(s):
    return re.sub(r"[^0-9A-Z一-鿿]", "", (s or "").upper())


def zol_search(model):
    """按型号搜 ZOL，返回 [(产品名, index页URL, proId, 卡片摘要)]。"""
    from urllib.parse import quote
    url = "https://search.zol.com.cn/s/all.php?kword=" + quote(model)
    html = curl(url, referer="https://search.zol.com.cn/")
    if not html:
        return []
    # 产品卡片：<a href="//detail.zol.com.cn/<cat>/index<ID>.shtml"><img alt="品牌型号">
    cards = []
    for m in re.finditer(
        r'href="(//detail\.zol\.com\.cn/[a-z_]+/index(\d+)\.shtml)"[^>]*>\s*<img[^>]*alt="([^"]{2,80})"',
        html):
        idx_url, pid, alt = m.group(1), m.group(2), m.group(3)
        # 卡片右侧 info-list 摘要
        tail = html[m.end():m.end() + 2500]
        info = {}
        for li in re.findall(r"<li>([^<]{2,12})：\s*([^<]{0,60})</li>", tail):
            k, v = li[0].strip(), clean(li[1])
            if v and v != "暂无数据":
                info[k] = v
        cards.append({"name": alt, "index": "https:" + idx_url,
                      "proId": pid, "info": info})
    return cards


ZOL_PARAM_STOP = {"具体内容", "进入官网", "查看更多", "纠错", "声明", "重要参数",
                  "售后服务", "基本参数", "其他参数", "附件", "保修信息"}


def parse_zol_param(html):
    """解析 ZOL 参数页的「重要参数 / 基本参数 / 其他参数 / 附件」为 {字段: 值}。"""
    out = {}
    body = plain(html)
    i = body.find("重要参数")
    if i < 0:
        return out
    seg = body[i:]
    j = seg.find("进入官网")
    if j > 0:
        seg = seg[:j]
    # tag 剥掉后是 字段：|值| 纠错| 字段：|值| ... 的序列
    seg = TAG.sub("|", seg)
    parts = [clean(p) for p in seg.split("|")]
    parts = [p for p in parts if p]
    k = None
    for p in parts:
        if p in ZOL_PARAM_STOP:
            k = None
            continue
        if p.endswith("：") or p.endswith(":"):
            k = p.rstrip("：:").strip()
            continue
        if k and len(k) <= 14:
            out.setdefault(k, p)
            k = None
    return out


def model_key(model):
    """把型号压成可比对的键：去分隔符、丢括号备注。"""
    m = re.sub(r"[（(].*?[)）]", " ", model or "")
    m = re.sub(r"\s+", " ", m).strip()
    return norm(m)


def zol_lookup(model, want=None):
    """搜 ZOL 并拉参数页。

    严格按型号匹配卡片标题——ZOL 搜索页会混进同系列别的品类（曾把浴霸搜成音箱、
    除湿机搜成显示器），匹配不上就返回 None，绝不猜。
    """
    cards = zol_search(model)
    if not cards:
        return None
    nm = model_key(model)
    # 型号里的空格/连字符是排版差异，压掉后应完全一致；退而求其次要包含关系
    pick = next((c for c in cards if model_key(c["name"]) == nm), None) or \
        next((c for c in cards if nm and (nm in model_key(c["name"]) or
                                         model_key(c["name"]) in nm)), None)
    if pick is None:
        return None
    param_url = "https://detail.zol.com.cn/%s/%s/param.shtml" % (
        re.search(r"detail\.zol\.com\.cn/([a-z_]+)/", pick["index"]).group(1), pick["proId"])
    html = curl(param_url, referer="https://detail.zol.com.cn/")
    specs = parse_zol_param(html) if html else {}
    if not specs:
        specs = pick["info"]
        param_url = pick["index"]
    return {"url": param_url, "index": pick["index"], "name": pick["name"],
            "specs": specs, "card": pick["info"]}


# ---------------- 主流程 ----------------

def unclassified():
    out = []
    for f in sorted(glob.glob(os.path.join(ROOT, "data", "*", "schema.json"))):
        cid = os.path.basename(os.path.dirname(f))
        s = json.load(open(f, encoding="utf-8"))
        facets = s.get("facets") or []
        if not facets:
            continue
        fk = facets[0]["key"]
        pp = os.path.join(ROOT, "data", cid, "products.json")
        if not os.path.exists(pp):
            continue
        for p in json.load(open(pp, encoding="utf-8")):
            if p.get("brand") == "小米":
                continue
            if p.get(fk) not in (None, "未归类", "查不到"):
                continue
            out.append({"cat": cid, "id": p["id"], "name": p["name"],
                        "brand": p.get("brand"), "facet_key": fk,
                        "verify_url": p.get("verify_url") or "",
                        "price": p.get("ref_price") or p.get("official_price")})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cats", nargs="*", help="只抓指定品类（默认全部）")
    ap.add_argument("--out", default=os.path.join(ROOT, "data", "_cache", "facet-evidence"))
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--no-zol", action="store_true")
    ap.add_argument("--pconline-only", action="store_true",
                    help="只抓太平洋。太平洋同 IP 并发会被限流返回空 body，务必配 --workers 1")
    ap.add_argument("--force", action="store_true", help="已有证据也重抓")
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    path = args.out if args.out.endswith(".json") else os.path.join(args.out, "evidence.json")
    prev = {}
    if os.path.exists(path):
        for r in json.load(open(path, encoding="utf-8")):
            prev[(r["cat"], r["id"])] = r

    todo = [x for x in unclassified() if not args.cats or x["cat"] in args.cats]
    def have(x):
        r = prev.get((x["cat"], x["id"]), {})
        if args.pconline_only:
            return bool(r.get("pconline"))
        if args.no_zol:
            return bool(r.get("pconline"))
        return bool(r.get("pconline")) and bool(r.get("zol"))
    if not args.force:
        todo = [x for x in todo if not have(x)]
    print("共 %d 条，本次待抓 %d 条（已缓存命中跳过）" % (
        len([x for x in unclassified() if not args.cats or x["cat"] in args.cats]), len(todo)))

    def job(item):
        rec = dict(prev.get((item["cat"], item["id"])) or {})
        rec.update({"cat": item["cat"], "id": item["id"], "name": item["name"],
                    "brand": item["brand"], "facet_key": item["facet_key"],
                    "price": item["price"], "verify_url": item["verify_url"],
                    "model": item["name"]})
        u = item["verify_url"]
        if "g.pconline.com.cn/product/" in u and (args.force or not rec.get("pconline")):
            html = curl(u, referer="https://g.pconline.com.cn/")
            if html:
                rec["pconline"] = parse_pconline(html)
        if (not args.no_zol and not args.pconline_only) and (args.force or not rec.get("zol")):
            m = re.sub(r"\s+", " ", re.sub(r"[（(].*?[)）]", " ", item["name"])).strip()
            try:
                z = zol_lookup(m)
                if z:
                    rec["zol"] = z
                elif "zol_miss" not in rec:
                    rec["zol_miss"] = True   # 型号在 ZOL 收录里找不到，别反复重试
            except Exception as e:  # noqa: BLE001
                rec["zol_error"] = str(e)
        return rec

    recs = []
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        for i, r in enumerate(ex.map(job, todo), 1):
            recs.append(r)
            if i % 10 == 0:
                print("  %d/%d" % (i, len(todo)), flush=True)

    merged = dict(prev)
    for r in recs:
        merged[(r["cat"], r["id"])] = r
    out = sorted(merged.values(), key=lambda r: (r["cat"], r["id"]))
    json.dump(out, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    got_pc = sum(1 for r in out if r.get("pconline"))
    got_zol = sum(1 for r in out if r.get("zol"))
    print("写入 %s：%d 条（太平洋规格 %d，ZOL %d）" % (path, len(out), got_pc, got_zol))
    return 0


if __name__ == "__main__":
    sys.exit(main())
