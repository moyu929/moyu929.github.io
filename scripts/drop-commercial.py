# -*- coding: utf-8 -*-
"""按「仅收录家用电器」口径找出应剔除的商用/工业机型。

判据（任一命中即视为商用，见 SKILL.md「收录范围」）：
  ① 第三方规格表「产品类别/产品类型/类别」含 工业 / 商用 / 工程
  ② 电源电压 380V（家用为 220V 单相）
  ③ 整机重量 ≥100kg 或额定功率 ≥8000W

防误报：判据 ③ 必须**逐条回看产品名**——单位会丢（`338g` 被读成 338kg）、
字段会串（破壁机容量被当除湿量）、数值域会撞（热水器 60L 是升数）。

用法：
    python scripts/drop-commercial.py            # 列出命中清单
    python scripts/drop-commercial.py --json     # 机器可读（供批量 recall/drop）
"""
import json, glob, os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding='utf-8')

# 已人工核实的误报：产品 id -> 误报原因
KNOWN_FALSE_POSITIVE = {
    'hd_h501_std': '规格表为 338g，家用吹风机；重量判据的正则丢了单位',
}


def dp(rel):
    return os.path.join(ROOT, rel)


def num(v):
    m = re.search(r'(-?\d+(?:\.\d+)?)', str(v or '').replace(',', ''))
    return float(m.group(1)) if m else None


def pid_of(url):
    m = re.search(r'/([0-9]+)_detail\.html', url or '')
    return m.group(1) if m else None


def load_cache():
    out = {}
    for f in glob.glob(dp('data/_cache/brand-*.json')):
        try:
            d = json.load(open(f, encoding='utf-8'))
        except Exception:
            continue
        for it in d:
            if it.get('id'):
                out.setdefault(str(it['id']), {}).update(it.get('specs') or {})
    return out


def reasons(cache, p):
    sp = cache.get(pid_of(p.get('verify_url')), {})
    r = []
    blob = ' '.join(str(sp.get(k, '')) for k in ('产品类别', '产品类型', '类别'))
    m = re.search(r'工业|商用|工程', blob)
    if m:
        r.append('第三方标注「%s」' % blob.strip()[:14])
    v = str(sp.get('电源电压') or sp.get('额定电压') or '')
    if '380' in v:
        r.append('电源电压 380V 三相电（家用为 220V 单相）')
    w = num(p.get('weight'))
    if w and w >= 100:
        r.append('整机 %skg（家用机极少破 60kg）' % w)
    pw = num(p.get('power'))
    if pw and pw >= 8000:
        r.append('额定功率 %sW（家用机极少破 4000W）' % pw)
    return r


def main():
    cache = load_cache()
    hits = []
    for f in glob.glob(dp('data/*/products.json')):
        cid = os.path.basename(os.path.dirname(f))
        if cid.startswith('_'):
            continue
        for p in json.load(open(f, encoding='utf-8')):
            r = reasons(cache, p)
            if not r:
                continue
            if p['id'] in KNOWN_FALSE_POSITIVE:
                continue
            hits.append({'cat': cid, 'id': p['id'], 'name': p['name'],
                         'brand': p.get('brand'), 'reasons': r})

    if '--json' in sys.argv:
        print(json.dumps(hits, ensure_ascii=False, indent=1))
        return

    from collections import Counter
    print('命中 %d 款：' % len(hits))
    print(dict(Counter(h['cat'] for h in hits)))
    print()
    for h in hits:
        print('  %s/%-20s %-24s %s' % (
            h['cat'], h['id'], h['name'][:22], '；'.join(h['reasons'])))
    print('\n已排除的已知误报：')
    for k, v in KNOWN_FALSE_POSITIVE.items():
        print('  %s —— %s' % (k, v))


if __name__ == '__main__':
    main()