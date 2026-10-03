#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""发现候选数据源站点（尤其是个人/社区维护的数据站），只读外网，不写数据区。

为什么要这个脚本：本站是「个人维护的家电参数库」，同类站点其实不少
（爱好者整理的型号库、开源数据集、垂直品类数据库）。它们常常覆盖到大站
不收录的老型号与小众品类，但**域名无法靠记忆枚举**——猜域名只会写出一堆
404 和已停运的站。本脚本按「品类 × 意图词」组合去检索，统计结果页里出现
的域名，把搜索引擎自身与已知大站过滤掉，剩下的就是值得实测的小众候选。

⚠️ 实现要点（踩过一次）：百度/360 的搜索结果 `<a href>` 是**自己的跳转包装**
（`baidu.com/link?url=…`、`so.com/link?url=…`），直接取 href 的 host 只会得到
搜索引擎自己（实测 33 条结果里 33 条 host 都是 baidu/so）。因此本脚本不做
结构化解析，而是**从整页 HTML 里正则抽域名**——搜索引擎会在结果里显示来源
域名，这种"弱提取"反而更鲁棒。

用法：
    python scripts/discover-sources.py                       # 跑默认关键词组
    python scripts/discover-sources.py --engine baidu        # 指定搜索入口
    python scripts/discover-sources.py --extra "筋膜枪 参数 大全"
    python scripts/discover-sources.py --out data/_cache/source-discovery.json

输出：控制台 Top 榜单 + JSON（默认 data/_cache/source-discovery.json，已 gitignore）。
拿到候选后再用 `python scripts/probe-sources.py` 实测可达性与抗限流能力。
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time
from collections import defaultdict
from urllib.parse import quote

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

# 默认检索词：品类 × 「参数/型号库/大全/对比」意图
QUERIES = [
    "家电 参数 数据库 个人网站",
    "家电 型号库 查询 网站",
    "家电 参数 对比 独立站 收录",
    "扫地机器人 参数 大全 对比",
    "空气净化器 CADR 型号 大全",
    "洗地机 参数 对比 大全",
    "空调 型号 能效 查询 大全",
    "冰箱 型号 参数 大全",
    "洗衣机 型号 参数 大全",
    "投影仪 参数 对比 数据库",
    "热水器 型号 参数 大全",
    "净水器 型号 参数 大全",
    "除湿机 型号 参数 大全",
    "小米 米家 设备 型号 库",
    "家电 设备 型号 开源 数据 json",
]

# 出现在结果页里的域名：结果正文会显示来源域名，直接抽它
DOMAIN_RE = re.compile(
    r"\b([a-z0-9][a-z0-9\-]{1,62}\.(?:com|cn|net|org|io|cc|me|top|xyz|info|biz|co|dev|app))\b",
    re.I)

# 过滤：搜索引擎自身 + 门户/电商/社交/视频/已知大站（本站已有或风控高，不是"小众数据站"）
BIG_SITES = [
    "baidu.com", "bdstatic.com", "bdimg.com", "hao123.com", "google.com", "bing.com",
    "so.com", "360.cn", "360.com", "360safe.com", "sogou.com", "sogoucdn.com", "sm.cn",
    "zhihu.com", "bilibili.com", "weibo.com", "douban.com", "tieba",
    "jd.com", "tmall.com", "taobao.com", "suning.com", "gome.com.cn", "kaola.com",
    "pconline.com.cn", "zol.com.cn", "mi.com", "xiaomi.com", "huawei.com", "apple.com",
    "smzdm.com", "ithome.com", "163.com", "sina.com", "qq.com", "sohu.com", "toutiao.com",
    "csdn.net", "cnblogs.com", "jianshu.com", "51cto.com", "wikipedia.org", "gov.cn",
    "youtube.com", "douyin.com", "xiaohongshu.com", "kuaishou.com", "alicdn.com",
    "w3.org", "schema.org", "gstatic.com", "googleapis.com", "cloudflare.com",
]
# 单独归类：开源仓库里常有结构化数据文件，值得单独看一眼
REPO_HOSTS = ["github.com", "gitee.com", "gitlab.com", "raw.githubusercontent.com",
              "jsdelivr.net", "npmjs.com", "pypi.org"]

# GitHub 检索词：个人/社区数据站有一大批以**开源仓库**形式存在（设备库、固件库、
# 抓取器、数据集）。这些在通用搜索引擎里排名极低（实测搜出来的多是电商与黄页），
# 但用 gh 检索命中率高得多，且能看到 star / 最近更新时间（判断有没有停维护）。
GH_QUERIES = [
    "miot device",
    "xiaomi device list",
    "mi home appliance",
    "air purifier CADR",
    "robot vacuum database",
    "home appliance specification",
    "appliance dataset",
    "家电 参数",
    "米家 设备",
    "smart home device database",
]


def curl(url, referer=None, timeout=25):
    cmd = ["curl", "-sL", "-m", str(timeout), "-A", UA, url]
    if referer:
        cmd += ["-H", "Referer: " + referer]
    raw = subprocess.run(cmd, capture_output=True).stdout
    for enc in ("utf-8", "gb18030", "gbk"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", "replace")


def search_html(q, engine):
    """取搜索结果页 HTML。360 命中最好，被验证码挡就退百度。"""
    if engine in ("smart", "so"):
        html = curl("https://www.so.com/s?q=" + quote(q))
        if html and "请输入验证码" not in html and "访问异常" not in html and len(html) > 5000:
            return html, "so"
        if engine == "so":
            return "", "so"
    if engine in ("smart", "baidu"):
        return curl("https://www.baidu.com/s?wd=" + quote(q)), "baidu"
    return curl("https://cn.bing.com/search?q=" + quote(q)), "bing"


def is_filtered(host):
    return (not host) or any(b in host for b in BIG_SITES)


def is_repo(host):
    return any(h in host for h in REPO_HOSTS)


def gh_search(query, limit=10):
    """用本机已登录的 gh CLI 检索仓库（比通用搜索引擎命中率高得多）。

    返回 [] 表示 gh 不可用或未登录——不中断主流程，只是这条发现路径没结果。
    """
    cmd = ["gh", "search", "repos", query, "--limit", str(limit),
           "--json", "fullName,description,stargazersCount,updatedAt,url"]
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=60)
    except Exception:  # noqa: BLE001 - gh 不存在/超时都按"无结果"处理
        return []
    try:
        return json.loads(r.stdout.decode("utf-8", "replace"))
    except Exception:  # noqa: BLE001
        return []


def run_github(limit, gap):
    print(f"\n== GitHub 检索（{len(GH_QUERIES)} 组，用本机 gh CLI）==")
    found = {}
    sys.stdout.write(progress(0, len(GH_QUERIES)))
    sys.stdout.flush()
    for i, q in enumerate(GH_QUERIES, 1):
        for r in gh_search(q, limit):
            name = r.get("fullName")
            if not name:
                continue
            rec = found.setdefault(name, {
                "fullName": name, "stars": r.get("stargazersCount", 0),
                "updatedAt": (r.get("updatedAt") or "")[:10],
                "url": r.get("url", ""), "description": r.get("description") or "",
                "queries": []})
            if q not in rec["queries"]:
                rec["queries"].append(q)
        sys.stdout.write(progress(i, len(GH_QUERIES)))
        sys.stdout.flush()
        if i < len(GH_QUERIES):
            time.sleep(gap)
    print("\n")
    if not found:
        print("  （未发现；若 gh 未安装或未登录，GitHub 这条发现路径会静默返回空）")
        return []
    top = sorted(found.values(), key=lambda r: -r["stars"])[:20]
    for r in top:
        print(f"  {r['stars']:>6}★  {r['fullName'][:46]:<46} 更新 {r['updatedAt']}")
        if r["description"]:
            print(f"          {(r['description'])[:88]}")
    return top


def progress(done, total, width=28):
    filled = int(width * done / total) if total else 0
    bar = "█" * filled + "░" * (width - filled)
    return f"\r  检索中 |{bar}| {done}/{total} ({100 * done // max(total, 1)}%)"


def main():
    ap = argparse.ArgumentParser(description="发现候选数据源站点")
    ap.add_argument("--engine", default="smart", choices=["smart", "so", "baidu", "bing"])
    ap.add_argument("--github", action="store_true",
                    help="改用 gh CLI 检索开源仓库/数据集（个人站常以仓库形式存在，命中率更高）")
    ap.add_argument("--extra", nargs="*", default=[], help="追加自定义检索词")
    ap.add_argument("--gap", type=float, default=2.0, help="两次检索间隔秒（默认 2）")
    ap.add_argument("--out", default=os.path.join(ROOT, "data", "_cache", "source-discovery.json"))
    args = ap.parse_args()

    if args.github:
        top = run_github(args.limit if hasattr(args, "limit") else 8, args.gap)
        os.makedirs(os.path.dirname(args.out), exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump({"ts": time.strftime("%Y-%m-%d %H:%M:%S"), "mode": "github",
                       "queries": GH_QUERIES, "repos": top}, f, ensure_ascii=False, indent=2)
        print(f"\n明细已写入 {os.path.relpath(args.out, ROOT)}")
        return 0

    queries = QUERIES + list(args.extra)
    print(f"\n数据源发现：{len(queries)} 组检索词（入口 {args.engine}，间隔 {args.gap}s）\n")
    sys.stdout.write(progress(0, len(queries)))
    sys.stdout.flush()

    hits = defaultdict(lambda: {"count": 0, "queries": []})
    repo_hits = defaultdict(lambda: {"count": 0, "queries": []})
    all_hosts = defaultdict(int)
    raw = []
    used = defaultdict(int)

    for i, q in enumerate(queries, 1):
        try:
            html, eng = search_html(q, args.engine)
        except Exception as e:  # noqa: BLE001 - 单次失败不应中断整轮
            html, eng = "", f"error:{e}"
        used[eng] += 1
        if not html:
            sys.stdout.write(progress(i, len(queries)))
            sys.stdout.flush()
            time.sleep(args.gap)
            continue
        for m in DOMAIN_RE.finditer(html):
            h = m.group(1).lower()
            all_hosts[h] += 1
            raw.append({"query": q, "host": h, "engine": eng})
            if is_repo(h):
                b = repo_hits[h]
            elif is_filtered(h):
                continue
            else:
                b = hits[h]
            b["count"] += 1
            if q not in b["queries"]:
                b["queries"].append(q)
        sys.stdout.write(progress(i, len(queries)))
        sys.stdout.flush()
        if i < len(queries):
            time.sleep(args.gap)
    print("\n")

    print("== （诊断）过滤前域名分布 Top 15 ==")
    for h, c in sorted(all_hosts.items(), key=lambda kv: -kv[1])[:15]:
        mark = "repo" if is_repo(h) else ("过滤" if is_filtered(h) else "★保留")
        print(f"  {c:>3}×  {h}  [{mark}]")
    print(f"\n  实际使用的检索入口：" + " · ".join(f"{k} {v}" for k, v in used.items()))

    def show(bucket, title, limit=25):
        print(f"\n== {title} ==")
        if not bucket:
            print("  （未发现）")
            return
        for host, b in sorted(bucket.items(), key=lambda kv: -kv[1]["count"])[:limit]:
            qs = "、".join(b["queries"][:3])
            print(f"  {b['count']:>3}×  {host}\n        命中词：{qs}")

    show(hits, "小众 / 个人 / 垂直数据站候选（按出现次数）")
    show(repo_hits, "开源仓库 / 数据集候选", limit=15)

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump({"ts": time.strftime("%Y-%m-%d %H:%M:%S"), "engine": args.engine,
                   "queries": queries, "enginesUsed": dict(used),
                   "sites": {k: v for k, v in hits.items()},
                   "repos": {k: v for k, v in repo_hits.items()},
                   "rawCount": len(raw)}, f, ensure_ascii=False, indent=2)
    print(f"\n共解析 {len(raw)} 条域名命中，明细已写入 {os.path.relpath(args.out, ROOT)}")
    print("下一步：把候选域名补进 scripts/probe-sources.py 的 CANDIDATES 实测后，再决定是否收录。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
