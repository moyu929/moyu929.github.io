# -*- coding: utf-8 -*-
"""ZOL 补查：对给定的 {本站id: 检索词}，取 ZOL 商品页（名称/参考报价）
与 param.shtml（参数表），落盘 data/_cache/zol-<品类>.json。

2026-10-04 实测要点：
  * detail.zol.com.cn 无 cookie 会 302 到 service.zol.com.cn/checking（JS 跳转），
    先 GET 一次 checking 拿 `ip_ck` cookie 即可通过（zol-fetch.py 已封装）；
  * param.shtml 的路径是数字品类 id：/1601/1600327/param.shtml，slug 形式 404，
    所以必须先从商品页 HTML 里抽 param 链接；
  * search.zol.com.cn/s/all.php?kword=X&type=product 可按型号搜到商品链接，偶尔限流需重试；
  * 搜索是模糊匹配（搜「苏泊尔SP60S」会混入联想P60），**必须按品类 slug 过滤**——
    破壁机品类是 /Wall-breaking-machine/（大小写都要容），否则会把手机/电饭煲当成命中。

用法（微波炉批次保持默认行为；其他品类传 --targets-file + --out）：
    python scripts/zol-lookup.py                                   # 用内置 TARGETS -> zol-microwave.json
    python scripts/zol-lookup.py --targets-file t.json --out data/_cache/zol-blender.json
"""
import json, os, re, sys, time, argparse, importlib.util

sys.stdout.reconfigure(encoding='utf-8')
spec = importlib.util.spec_from_file_location(
    'zf', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'zol-fetch.py'))
zf = importlib.util.module_from_spec(spec)
spec.loader.exec_module(zf)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'data', '_cache', 'zol-microwave.json')

# 本站id -> 检索词（ZOL 搜索偶尔限流，关键词带品牌词提高命中）
TARGETS = {
    'midea_1513087': 'BS50D0W',
    'midea_1513147': 'BS7051W',
    'midea_1512987': 'BS5051W',
    'midea_2478419': 'G3E',
    'midea_1513027': 'BG3405W',
    'galanz_1927507': '格兰仕 KDES85TMC',
    'galanz_1927527': '格兰仕 KDES50N',
    'galanz_1912287': '格兰仕 G90Q26',
    'galanz_1927587': '格兰仕 D90Q20',
    'galanz_1590687': '格兰仕 DG26T',
    'robam_2779639': '老板 CQ928',
    'robam_2780059': '老板 CQ38',
    'robam_1115201': '老板 R026',
    'robam_1823487': '老板 CQ9363A',
    'robam_1115202': '老板 R075',
    'panasonic_1068716': 'NN-CS1000XPE',
    'panasonic_2478499': 'NN-DS59QM',
    'panasonic_1590787': 'NU-SC86MW',
    'panasonic_1068717': 'NU-SC200W',
    'panasonic_1068527': 'NU-JK200W',
}

CATS = ('steam-box', 'microwave_oven', 'Integrated_steaming_and_baking_machine', 'oven', 'steam_oven',
        # 2026-10-04 破壁机批次：ZOL 破壁机品类 slug（大小写两种写法都实测存在）
        'Wall-breaking-machine', 'wall-breaking-machine',
        # 2026-10-04 即热饮水机批次：ZOL 饮水机品类
        'water_dispenser')


def search_product(kw, tries=2):
    """ZOL 搜索 -> [(商品url, 名称)]。限流时重试。
    2026-10-04：只保留家电/厨电品类的命中，模糊搜索混入的手机等直接丢。"""
    keep = re.compile(
        r'/[A-Za-z_-]*(?:wall|breaking|machine|juicer|soy|blender|kitchen|food|microwave|steam|oven|rice|cooker|kettle|coffee|airfryer|condition|purifier|fan|heater|humidifier|vacuum|cleaning|washing|dish|refriger|freezer|tv|projector|speaker|lamp|water)[A-Za-z_-]*/',
        re.I)
    for i in range(tries):
        t = zf.get('https://search.zol.com.cn/s/all.php?kword=' +
                   kw.replace(' ', '+') + '&type=product')
        hits = [(m.group(1), m.group(2)) for m in re.finditer(
            r'<a[^>]+href="(//detail\.zol\.com\.cn/[A-Za-z_-]+/index\d+\.shtml)"[^>]*>([^<]{4,50})</a>', t)
            if keep.search(m.group(1))]
        if hits:
            return hits
        time.sleep(1.5 * (i + 1))
    return []


def load_page(zid):
    """探测品类 slug 拿商品页。返回 (url, html) 或 (None, None)。"""
    for cat in CATS:
        url = 'https://detail.zol.com.cn/%s/index%s.shtml' % (cat, zid)
        t = zf.get(url)
        if '<title>【' in t:
            return url, t
    return None, None


def get_param_url(t):
    m = re.search(r'href="(/[^"]*?/param\.shtml)"', t)
    return 'https://detail.zol.com.cn' + m.group(1) if m else None


def price_of(t):
    i = t.find('price-type')
    if i < 0:
        return None, None
    pm = re.search(r'>([^<]{1,24})<', t[i:i + 300])
    if not pm:
        return None, None
    note = pm.group(1).strip()
    n = re.search(r'([0-9]{3,6})', note)
    return (int(n.group(1)) if n else None), note


def lookup(kw):
    """返回 (结果或 None, 全部候选)。2026-10-04：不再盲取 hits[0]——
    模糊搜索会把同词的其他品类排前面（搜「苏泊尔SP60S」中过联想P60），
    只有名称含检索词核心 token 的命中才可信；没有就 MISS 并留候选供人工核对。"""
    hits = search_product(kw)
    if not hits:
        return None, hits
    tokens = sorted((t for t in re.split(r'[\s、，]+', kw) if len(t) >= 2),
                    key=len, reverse=True)
    url = zname = None
    for h_url, h_name in hits:
        if any(tok.lower() in h_name.lower().replace(' ', '') for tok in tokens):
            url, zname = h_url, h_name
            break
    if not url:
        return None, hits
    t = zf.get('https:' + url if url.startswith('//') else url)
    if '<title>【' not in t:
        return None, hits
    zid = re.search(r'index(\d+)', url).group(1)
    return finish(zid, zname, t), hits


def finish(zid, zname, t):
    price, pnote = price_of(t)
    ttl = re.search(r'<title>【([^】]{2,60})', t)
    purl = get_param_url(t)
    params = {}
    if purl:
        tp = zf.get(purl)
        _, params = zf.parse_param(tp)
    return {'zol_id': zid, 'zol_name': zname,
            'title': ttl.group(1) if ttl else None,
            'price': price, 'price_note': pnote,
            'param_url': purl, 'params': params}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--targets-file', help='{本站id: 检索词} 的 JSON 文件（覆盖内置 TARGETS）')
    ap.add_argument('--out', help='结果落盘路径（默认 data/_cache/zol-microwave.json）')
    args = ap.parse_args()
    targets = TARGETS
    if args.targets_file:
        targets = json.load(open(args.targets_file, encoding='utf-8'))
    out_path = args.out or OUT
    out = {}
    if os.path.exists(out_path):
        out = json.load(open(out_path, encoding='utf-8'))
    for ours, kw in targets.items():
        if ours in out:
            continue
        rec = None
        # 先查本地 zol-index（收割来的），有 id 就直接取页
        idxf = os.path.join(ROOT, 'data', '_cache', 'zol-index.json')
        if os.path.exists(idxf):
            idx = json.load(open(idxf, encoding='utf-8'))
            for zid, v in idx.items():
                if kw.replace(' ', '') in v['name'].replace(' ', ''):
                    url, t = load_page(zid)
                    if t:
                        rec = finish(zid, v['name'], t)
                        break
        hits = []
        if not rec:
            rec, hits = lookup(kw)
        print('%-18s %-20s %s' % (ours, kw, '-> ' + (rec['zol_name'] + ' ¥%s' % rec['price']) if rec else 'MISS'), flush=True)
        if rec or hits:
            entry = dict(rec) if rec else {'zol_name': None, 'search_kw': kw,
                                           'candidates': [{'name': n, 'url': u} for u, n in hits[:5]]}
            if rec:
                entry['search_kw'] = kw
            out[ours] = entry
            json.dump(out, open(out_path, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        time.sleep(0.4)
    print('saved ->', out_path, len(out))


if __name__ == '__main__':
    main()
