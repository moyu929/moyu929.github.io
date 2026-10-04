# -*- coding: utf-8 -*-
"""从 ZOL 商品页/列表页的 data-compare 侧栏收割 {ZOL商品id: (名称, 品类路径, 参考报价)}。

2026-10-04 实测：ZOL 页面每个商品条目带
    data-compare='1203276,松下NU-JD100B,/steam-box/index1203276.shtml,https://…,1160'
名称/链接/参考价齐全，是建「型号 → ZOL id + 价格」索引最省请求的路径。
价格是 ZOL「参考报价」（跟着京东自营/官方渠道走），写库时注明来源。
"""
import json, os, re, sys, importlib.util

sys.stdout.reconfigure(encoding='utf-8')
spec = importlib.util.spec_from_file_location(
    'zf', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'zol-fetch.py'))
zf = importlib.util.module_from_spec(spec)
spec.loader.exec_module(zf)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'data', '_cache', 'zol-index.json')

SEEDS = [
    # 微波炉
    'https://detail.zol.com.cn/microwave_oven/',
    'https://detail.zol.com.cn/microwave_oven/panasonic/',
    'https://detail.zol.com.cn/microwave_oven/galanz/',
    'https://detail.zol.com.cn/microwave_oven/midea/',
    # 蒸烤箱
    'https://detail.zol.com.cn/steam-box/',
    'https://detail.zol.com.cn/steam-box/panasonic/',
    'https://detail.zol.com.cn/steam-box/galanz/',
    'https://detail.zol.com.cn/steam-box/midea/',
    'https://detail.zol.com.cn/steam-box/robam/',
    # 电烤箱
    'https://detail.zol.com.cn/electric_oven/',
    'https://detail.zol.com.cn/electric_oven/robam/',
    'https://detail.zol.com.cn/electric_oven/galanz/',
    'https://detail.zol.com.cn/electric_oven/panasonic/',
    'https://detail.zol.com.cn/electric_oven/midea/',
    # 商品页侧栏（同品牌产品带参考价，是价格的主要收割面）
    'https://detail.zol.com.cn/steam-box/index1258819.shtml',
    'https://detail.zol.com.cn/steam-box/index1307558.shtml',
    'https://detail.zol.com.cn/microwave_oven/index1406333.shtml',
]


def harvest(url, idx):
    t = zf.get(url)
    n0 = len(idx)
    for m in re.finditer(
            r"data-compare=[\"'](\d+),([^,]{2,60}),(/[A-Za-z_-]+/index\d+\.shtml),[^,]*?,([0-9]{2,6}|暂无)[\"']", t):
        zid, name, path, price = m.group(1), m.group(2).strip(), m.group(3), m.group(4)
        cat = re.search(r'/([A-Za-z_-]+)/', path).group(1)
        idx[zid] = {'name': name, 'cat': cat,
                    'price': int(price) if price.isdigit() else None}
    # 商品链接（列表页正文/侧栏）：href 指向 /<品类>/index<id>.shtml，名称取 inner text 或 title
    # re.S：ZOL 列表页的 <a> 常跨行（内嵌 <img>/<span>），不用 re.S 会整页匹配失败
    # 2026-10-04 破壁机批次：路径大小写不敏感 —— 破壁机品类是 /Wall-breaking-machine/，
    # 小写正则会把整个品类列表页全部漏掉
    for m in re.finditer(r'<a[^>]+href="(?:https?:)?(?://[a-z.]*zol\.com\.cn)?(/[A-Za-z_-]+/index(\d+)\.shtml)"([^>]*)>(.{0,200}?)</a>', t, re.S):
        path_, zid, attrs, inner = m.group(1), m.group(2), m.group(3), m.group(4)
        name = re.search(r'title="([^"]{4,60})"', attrs)
        name = (name.group(1) if name else re.sub(r'<[^>]+>', '', inner)).strip()
        if not name or len(name) < 4:
            continue
        if zid not in idx:
            idx[zid] = {'name': name, 'cat': re.search(r'/([A-Za-z_-]+)/index', path_).group(1),
                        'price': None}
    return len(idx) - n0


def main():
    idx = {}
    if os.path.exists(OUT):
        idx = json.load(open(OUT, encoding='utf-8'))
    # 2026-10-04 破壁机批次：支持命令行追加种子 URL（追加但不覆盖内置清单，
    # 已在索引里的 id 自然去重，重复跑无害）
    seeds = SEEDS + [a for a in sys.argv[1:] if a.startswith('http')]
    for url in seeds:
        try:
            got = harvest(url, idx)
            print('%-55s +%d (total %d)' % (url, got, len(idx)), flush=True)
        except Exception as e:
            print('%-55s FAIL %s' % (url, e), flush=True)
    json.dump(idx, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print('saved ->', OUT, len(idx))


if __name__ == '__main__':
    main()
