#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""A2 路：竞品补源——中关村在线（ZOL）产品库。

为什么不用 `scripts/fetch-facet-evidence.py` 里的 `zol_lookup`：它走
`search.zol.com.cn/s/all.php?kword=<型号>`，那是**全站搜索**，实测对本品类
（风扇 / 取暖器 / 除湿机 / 加湿器 / 除螨机）检索不到对应商品——用 AMS150J-GM 去搜
返回的是相机镜头卡片，`detail.zol.com.cn/index.php?c=SearchList` 直接返回空 body。

可用的入口是**产品库**（服务端渲染）：
  品类页https://detail.zol.com.cn/<zcat>/
  品牌页   https://detail.zol.com.cn/<zcat>/<brand_slug>/      ~40 款/页
  品类 slug：electric_fan 电风扇 / electric_heater 电暖器 / exsiccator 除湿机 /
             humidifier 加湿器 / mites_machine 除螨机
匹配规则：**型号代码必须逐字出现在 ZOL 商品名里**（压掉空格与括号备注后比较），
匹配不上就不取——绝不按「同系列/相似型号」猜。

输出：data/_cache/zol-<zcat>.json（gitignored），人工核对后再决定写不写进库。

用法：
    python scripts/a2-zol-competitor.py fan heater --workers 3
    python scripts/a2-zol-competitor.py --parse-only        # 只解析已抓到的缓存
"""
import argparse
import glob
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import importlib.util  # noqa: E402

# 复用 fetch-facet-evidence.py 里的 curl / parse_zol_param（文件名带连字符，只能按路径加载）
_spec = importlib.util.spec_from_file_location(
    'fetch_facet_evidence', os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                         'fetch-facet-evidence.py'))
_ffe = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_ffe)
clean, curl, norm, parse_zol_param = _ffe.clean, _ffe.curl, _ffe.norm, _ffe.parse_zol_param

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

CATS = ['fan', 'heater', 'dehumidifier', 'humidifier', 'mite-remover']
# 本站品类 -> ZOL 品类库 slug
ZCAT = {
    'fan': 'electric_fan',
    'heater': 'electric_heater',
    'dehumidifier': 'exsiccator',
    'humidifier': 'humidifier',
    'mite-remover': 'mites_machine',
}
# 本站品牌 -> ZOL 品牌库 slug（slug 来自 https://detail.zol.com.cn/<zcat>/ 的品牌列表）
BRAND = {
    '美的': 'midea', '格力': 'gree', '戴森': 'dyson', '艾美特': 'airmate',
    '飞利浦': 'philips', '松下': 'panasonic', '小熊': 'bear', '澳柯玛': 'aucma',
    '德尔玛': 'deerma', 'TCL': 'tcl', '小米': 'xiaomi',
}

# ZOL 卡片链接的大小写不固定（/Fan/index…、/electric_fan/index…），
# 有时是站点绝对路径、有时是相对路径，两种都要接。
CARD = re.compile(
    r'<a[^>]+href="(?:https?:)?(?://detail\.zol\.com\.cn)?/([A-Za-z_]+)/index(\d+)\.shtml"[^>]*>([^<]{2,60})</a>')


def dp(rel):
    return os.path.join(ROOT, rel)


def model_key(s):
    """型号可比对键：去括号备注、去分隔符、大写。"""
    s = re.sub(r'[（(].*?[)）]', ' ', s or '')
    return norm(s)


def fetch_cards(zcat, brand):
    """抓 ZOL 品牌页，返回 [(商品名, 参数页URL)]。"""
    url = 'https://detail.zol.com.cn/%s/%s/' % (zcat, brand)
    html = curl(url, referer='https://detail.zol.com.cn/%s/' % zcat)
    if not html:
        return None
    out, seen = [], set()
    for cat, pid, name in CARD.findall(html):
        name = clean(name)
        if not name or pid in seen:
            continue
        seen.add(pid)
        out.append((name, 'https://detail.zol.com.cn/%s/index%s.shtml' % (cat, pid)))
    return out


PARAM_LINK = re.compile(r'href="(/(\d+)/(\d+)/param\.shtml)"')


def param_url(index_url):
    """ZOL 的参数页不是 <品类>/<proId>/param.shtml，而是 /<内部类目id>/<proId>/param.shtml，
    内部类目 id 只在 index 页里给出，所以要先抓 index 页再取参数页链接。"""
    html = curl(index_url, referer='https://detail.zol.com.cn/')
    if not html:
        return None
    m = PARAM_LINK.search(html)
    return 'https://detail.zol.com.cn' + m.group(1) if m else None


def targets(cats):
    """待查的竞品（只取非小米系）→ [(cid, id, brand, model_code)]。"""
    out = []
    for cid in cats:
        pf = dp('data/%s/products.json' % cid)
        if not os.path.exists(pf):
            continue
        for p in json.load(open(pf, encoding='utf-8')):
            b = p.get('brand')
            mc = p.get('model_code')
            if b in BRAND and b != '小米' and mc and mc not in ('查不到', '—', None):
                out.append((cid, p['id'], b, mc))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('cats', nargs='*', default=CATS)
    ap.add_argument('--workers', type=int, default=3)
    ap.add_argument('--parse-only', action='store_true')
    args = ap.parse_args()
    cats = [c for c in (args.cats or CATS) if c in CATS]

    # 1) 抓品牌页，建 {model_key(name): (name, url)}
    idx = {}
    for cid in cats:
        zc = ZCAT[cid]
        brands = sorted({BRAND[b] for c, _, b, _ in targets([cid])})
        cache = dp('data/_cache/zol-cards-%s.json' % zc)
        cards = json.load(open(cache, encoding='utf-8')) if os.path.exists(cache) else {}
        todo = [b for b in brands if b not in cards]
        if todo and not args.parse_only:
            with ThreadPoolExecutor(max_workers=args.workers) as ex:
                for b, r in zip(todo, ex.map(lambda x: fetch_cards(zc, x), todo)):
                    cards[b] = r or []
                    print('  品牌页 %s/%s：%d 款' % (zc, b, len(cards[b])), flush=True)
                    time.sleep(0.3)
            json.dump(cards, open(cache, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        for b, lst in cards.items():
            for name, url in lst or []:
                idx.setdefault(model_key(name), (name, url))
        print('%s：品牌页合计 %d 款，型号键 %d' % (zc, sum(len(v or []) for v in cards.values()), len(idx)))

    # 2) 按型号逐字匹配
    hits, miss = [], []
    for cid, pid, brand, mc in targets(cats):
        k = model_key(mc)
        hit = idx.get(k)
        # 退而求其次：ZOL 商品名里逐字包含型号（型号常与品牌名连写）
        if not hit:
            hit = next(((n, u) for kk, (n, u) in idx.items()
                        if k and (k in kk or kk in k)), None)
        (hits if hit else miss).append((cid, pid, brand, mc, hit))

    print('\n型号逐字命中 %d / %d' % (len(hits), len(hits) + len(miss)))
    for cid, pid, brand, mc, hit in hits:
        print('  ✓ %s/%s %s %s -> %s' % (cid, pid, brand, mc, hit[0]))
    for cid, pid, brand, mc, _ in miss:
        print('  ✗ %s/%s %s %s' % (cid, pid, brand, mc))

    # 3) 拉参数页
    if args.parse_only:
        return 0
    out = dp('data/_cache/zol-specs-a2.json')
    recs = json.load(open(out, encoding='utf-8')) if os.path.exists(out) else {}

    def job(h):
        cid, pid, brand, mc, hit = h
        name, index_url = hit
        purl = param_url(index_url)
        html = curl(purl, referer=index_url) if purl else None
        specs = parse_zol_param(html) if html else {}
        return (cid, pid), {'brand': brand, 'model_code': mc, 'zol_name': name,
                            'zol_index_url': index_url, 'zol_url': purl, 'specs': specs}

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        for r in ex.map(job, hits):
            recs['%s/%s' % r[0]] = r[1]
    json.dump(recs, open(out, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    withspecs = sum(1 for v in recs.values() if v['specs'])
    print('\n写入 %s：%d 条（解析出参数 %d）' % (out, len(recs), withspecs))
    return 0


if __name__ == '__main__':
    sys.exit(main())
