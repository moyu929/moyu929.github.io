#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""型号取证小助手：按型号在可用搜索引擎里捞证据片段（副分组补证用）。

已实测在本机可用的检索入口：
  so      360 搜索 https://www.so.com/s?q=        —— 命中最好，能带出苏宁/太平洋条目摘要
  baidu   百度   https://www.baidu.com/s?wd=
  bing    Bing   https://cn.bing.com/search?q=     —— 需带引号，否则常返回无关缓存
（Bing RSS、搜狗、DDG、Yandex、sm.cn 在本机均被验证码/限流拦截，不要用。）

用法：
    python scripts/web-snip.py so    "AHR4144ZS" 类别
    python scripts/web-snip.py baidu "UR-S5676i" 双出水
    python scripts/web-snip.py get   "https://..." 2000
"""
import re
import subprocess
import sys
from urllib.parse import quote

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")


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
    return ""


def plain(t):
    t = re.sub(r"<script.*?</script>|<style.*?</style>", " ", t, flags=re.S)
    t = re.sub(r"<(br|/p|/li|/div|/h\d|/tr)[^>]*>", "\n", t)
    t = re.sub(r"<[^>]+>", " ", t)
    t = t.replace("&nbsp;", " ").replace("&amp;", "&").replace("&quot;", '"')
    t = re.sub(r"&#\d+;", " ", t)
    return re.sub(r"[ \t]+", " ", t)


def so360(q):
    html = curl("https://www.so.com/s?q=" + quote(q))
    if "请输入验证码" in html or "访问异常" in html:
        # 360 同 IP 高频会被挡；退到百度，别硬冲
        return [dict(r, engine="so->baidu(360验证码)") for r in baidu(q)]
    blocks = re.split(r'(?=<li class="res-list")', html)
    out = []
    for b in blocks[1:]:
        b = b[:4000]
        h = re.search(r'<h3[^>]*>\s*<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', b, re.S)
        if not h:
            continue
        cite = re.search(r'class="res-linkinfo"[^>]*>(.*?)</p>', b, re.S)
        out.append({"url": h.group(1), "title": plain(h.group(2)).strip(),
                    "site": plain(cite.group(1)).strip() if cite else "",
                    "text": re.sub(r"\s+", " ", plain(b))[:700]})
    if not out:  # 版式变了就整页退化成正文
        out = [{"url": "", "title": "", "site": "", "text": re.sub(r"\s+", " ", plain(html))[:3000]}]
    return out


def baidu(q):
    html = curl("https://www.baidu.com/s?wd=" + quote(q))
    out = []
    for m in re.finditer(r'<div[^>]+class="result[^"]*".*?(?=<div[^>]+class="result|<div id="page)', html, re.S):
        b = m.group(0)[:4000]
        h = re.search(r'<h3[^>]*>\s*<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', b, re.S)
        out.append({"url": h.group(1) if h else "", "title": plain(h.group(2)).strip() if h else "",
                    "site": "", "text": re.sub(r"\s+", " ", plain(b))[:700]})
    if not out:
        out = [{"url": "", "title": "", "site": "", "text": re.sub(r"\s+", " ", plain(html))[:3000]}]
    return out


def bing(q):
    html = curl("https://cn.bing.com/search?q=" + quote(q))
    out = []
    for m in re.finditer(r'<li class="b_algo".*?(?=<li class="b_algo"|</ol>)', html, re.S):
        b = m.group(0)
        h = re.search(r'<h2[^>]*>\s*<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', b, re.S)
        if not h:
            continue
        out.append({"url": h.group(1), "title": plain(h.group(2)).strip(), "site": "",
                    "text": re.sub(r"\s+", " ", plain(b))[:700]})
    return out


def smart(q):
    """360 优先，被挡就百度。两者都挡就如实返回空。"""
    r = so360(q)
    if r and "验证码" not in r[0].get("text", ""):
        return r
    b = baidu(q)
    if b and "验证" not in b[0].get("text", "")[:200]:
        return b
    return r or b


ENG = {"so": so360, "baidu": baidu, "bing": bing, "smart": smart}


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "so"
    args = sys.argv[2:]
    if mode == "get":
        for url in args:
            n = 4000
            if url.isdigit():
                continue
            print("### GET", url)
            print(re.sub(r"\n{2,}", "\n", plain(curl(url)))[:n])
        return
    fn = ENG.get(mode)
    if not fn:
        print(__doc__)
        return
    for q in args:
        print("#### %s: %s" % (mode, q))
        for r in fn(q):
            print("-", r["title"], "|", r.get("site", ""), r.get("engine", ""))
            print("  ", r["url"])
            print("  ", r["text"][:500])
        print()


if __name__ == "__main__":
    main()
