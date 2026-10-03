# -*- coding: utf-8 -*-
"""电饭煲品类 ZOL 补查（2026-10-04，米家 P1/N1/C1/IH 系列与竞品在售价/尺寸/型号）。

与 zol-lookup.py（微波炉）同一套打法，两点改进：
  * 搜索命中后**校验名称**：ZOL 搜索常把同系列另一容量排在前排
    （微压版 3L/4L、快煮 3L/4L 是两条商品），关键词不落在商品名里的一律不取，
    宁可 MISS 交人工，不冒采到别款的风险；
  * 已知 ZOL id（列表页收割来的）直接取页，不走搜索。

参数页数据口径（2026-10-04 实测）：
  * param.shtml 有 型号 / 产品尺寸 / 产品重量 / 额定功率 / 容积 等行；
  * **没有「上市时间」行**（微波炉批次已确认，电饭煲复测一致），year 别指望它；
  * 米家系 ZOL 商品名的「型号」字段混填（DFB201CM 被标在 C1/快煮/小饭煲 多条上），
    型号字段**必须逐条与商品名互相印证**才可采。

用法：
    python scripts/zol-rice-cooker.py          # 增量跑，落盘 data/_cache/zol-rice-cooker.json
    python scripts/zol-rice-cooker.py <本站id> ...  # 只跑指定条
"""
import json, os, re, sys, time, importlib.util

sys.stdout.reconfigure(encoding='utf-8')
spec = importlib.util.spec_from_file_location(
    'zf', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'zol-fetch.py'))
zf = importlib.util.module_from_spec(spec)
spec.loader.exec_module(zf)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'data', '_cache', 'zol-rice-cooker.json')
IDX = os.path.join(ROOT, 'data', '_cache', 'zol-index.json')

# 本站id -> (检索词, 已知ZOL id)。检索词为 None 时只走已知 id。
TARGETS = {
    'rc_p1_4l':      ('米家智能IH电饭煲P1 4L', None),
    'rc_p1_3l':      ('米家智能IH电饭煲P1 3L', None),
    'rc_ih_4l':      ('米家IH电饭煲4L', None),
    'rc_n1_4l':      ('米家电饭煲N1 4L', None),
    'rc_n1_3l':      ('米家电饭煲N1 3L', None),
    'rc_c1_3l':      (None, '1303035'),        # 米家电饭煲C1（3L）
    'rc_ih2':        ('米家IH电饭煲2', None),
    'rc_weiya':      (None, '1985494'),       # 小米MFB2AM 米家智能电饭煲 微压版-4L
    'rc_bianya_4l':  ('米家智能变压IH电饭煲', None),
    'rc_s1_3l':      ('米家IH电饭煲S1', None),
    'rc_fast_5l':    ('米家智能快煮电饭煲5L', None),
    'rc_fast_34l':   (None, '1985500'),       # 小米DFB201CM 米家快煮电饭煲4L
    'midea_1568847': (None, '1427192'),       # 美的MB-SFB4021H
    'midea_1616847': ('美的MB-EFB4022H', None),
    'midea_2072107': ('美的MB-EFB4026H', None),
    'midea_1994707': ('美的MB-EFB4025H', None),
    'midea_1741447': ('美的MB-HS405', None),
    'supor_2606259': ('苏泊尔SF40Q11', None),
    'supor_1928727': ('苏泊尔SF40HC82', None),
    'supor_1587527': ('苏泊尔SF30HC85', None),
    'supor_2072247': ('苏泊尔SF40HC2928', None),
    'supor_1522107': ('苏泊尔SF40FC386', None),
    'joyoung_2183719': (None, '1427300'),      # 九阳40N1（Pro)
    'joyoung_1900287': ('九阳F40TD-F555', None),
    'joyoung_2690599': ('九阳20N1F', None),
    'joyoung_2469659': ('九阳40N8', None),
    'joyoung_1585667': (None, '1427332'),      # 九阳F-40FS36
    'panasonic_589196': ('松下SR-SPZ183', None),
    'panasonic_589195': ('松下SR-SPZ103', None),
    'panasonic_2657139': ('松下SR-CR10WSQ', None),
    'panasonic_1157036': ('松下SR-HCC107-187', None),
    'panasonic_2227059': ('松下SR-H15NSJ-W', None),
}

CATS = ('rice_cooker',)


def norm(s):
    return re.sub(r'[\s（）()【】/\\·,，.、-]', '', str(s or '')).upper()


def name_hits_kw(zname, kw):
    """商品名必须包含检索词的全部「词块」；ZOL 名常带前缀（品牌词/容量词），
    用包含而非相等判断。"""
    zn = norm(zname)
    return norm(kw) in zn


def search_product(kw, tries=2):
    for i in range(tries):
        t = zf.get('https://search.zol.com.cn/s/all.php?kword=' +
                   kw.replace(' ', '+') + '&type=product')
        hits = [(m.group(1), m.group(2)) for m in re.finditer(
            r'<a[^>]+href="(//detail\.zol\.com\.cn/[A-Za-z_-]+/index\d+\.shtml)"[^>]*>([^<]{4,50})</a>', t)]
        if hits:
            return hits
        time.sleep(1.5 * (i + 1))
    return []


def load_page(zid):
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


def lookup(kw):
    """搜索 -> 命中且名称含关键词的商品页。找不到返回 (None, 候选名列表)。"""
    hits = search_product(kw)
    cands = [h[1] for h in hits]
    for url, zname in hits:
        if name_hits_kw(zname, kw):
            t = zf.get('https:' + url if url.startswith('//') else url)
            if '<title>【' not in t:
                continue
            zid = re.search(r'index(\d+)', url).group(1)
            return finish(zid, zname, t), cands
    return None, cands


def main():
    argv = [a for a in sys.argv[1:]]
    out = {}
    if os.path.exists(OUT):
        out = json.load(open(OUT, encoding='utf-8'))
    idx = {}
    if os.path.exists(IDX):
        idx = json.load(open(IDX, encoding='utf-8'))

    for ours, (kw, zid) in TARGETS.items():
        if argv and ours not in argv:
            continue
        if ours in out:
            print('%-18s skip(已有)' % ours)
            continue
        rec = None
        cands = []
        # 1) 已知 ZOL id 直接取页
        if zid and zid in idx:
            url, t = load_page(zid)
            if t:
                rec = finish(zid, idx[zid]['name'], t)
        # 2) 索引按名匹配（关键词落在商品名里才算）
        if not rec and kw:
            for z, v in idx.items():
                if v['cat'] == 'rice_cooker' and name_hits_kw(v['name'], kw):
                    url, t = load_page(z)
                    if t:
                        rec = finish(z, v['name'], t)
                        break
        # 3) 搜索（同样校验名称）
        if not rec and kw:
            rec, cands = lookup(kw)
        if rec:
            print('%-18s %-28s -> %s ¥%s' % (ours, kw or '', rec['zol_name'], rec['price']))
            out[ours] = rec
            json.dump(out, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        else:
            print('%-18s %-28s MISS  候选: %s' % (ours, kw or '', ' | '.join(cands[:5])))
        time.sleep(0.4)
    print('saved ->', OUT, len(out))


if __name__ == '__main__':
    main()
