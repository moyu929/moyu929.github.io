# -*- coding: utf-8 -*-
"""为尚未归类的竞品补抓 pconline 规格表，落到 data/_cache/brand-<目录>-extra.json。

只抓取分类判定需要的字段，不改 products.json；抓完重跑 classify-facets.py 即可。
"""
import json, glob, os, re, sys, subprocess, collections
from concurrent.futures import ThreadPoolExecutor

# 仓库根目录：按脚本自身位置解析，不依赖 cwd（见方案 P0-1）
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def dp(rel):
    """仓库相对路径 → 绝对路径"""
    return os.path.join(ROOT, rel)


sys.stdout.reconfigure(encoding='utf-8')
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

# 与 classify-facets.py 共用的品类->pconline 目录映射（不 import，避免连字符模块名问题）
CAT2PC = {
    'fan': 'fan', 'air-purifier': 'jinghuaqi', 'microwave': 'oven', 'blender': 'juicer',
    'vacuum': 'vacuum_cleaner', 'washing-machine': 'washer', 'water-dispenser': 'water_dispenser',
    'water-heater': 'water_heater', 'dishwasher': 'xiwanji', 'bath-heater': 'yuba',
    'air-conditioner': 'air_condition', 'air-fryer': 'airfryer', 'rice-cooker': 'rice_cooker',
    'heater': 'heater', 'water-purifier': 'water_purifier', 'coffee-machine': 'coffee',
    'projector': 'projector', 'tv': 'lcd_tv', 'dehumidifier': 'chushiji',
    'humidifier': 'humidifier', 'induction-cooker': 'induction_cooker',
    'pressure-cooker': 'pressure_cooker', 'robot-vacuum': 'sweepingrobot',
    'kettle': 'electric_kettle', 'floor-washer': 'cleaning_machine',
}


def pick_id(url):
    m = re.search(r'/([0-9]+)_detail\.html', url or '')
    return m.group(1) if m else None

WANT_FIELDS = [
    '产品类型', '安装方式', '加热方式', '空调类型', '产品类别', '类别', '使用方式',
    '集尘方式', '产品容量', '日除湿量', '容量', '噪音', '产品功率', '功率',
]


def decode(b):
    for e in ('gbk', 'gb18030', 'utf-8'):
        try:
            return b.decode(e)
        except Exception:
            pass
    return b.decode('utf-8', 'replace')


def fetch_specs(url):
    """抓 pconline 规格页，返回 {字段: 值}。失败返回 None。"""
    r = subprocess.run(['curl', '-sL', '-m', '25', '-A', UA, url], capture_output=True)
    t = decode(r.stdout)
    if len(t) < 2000:
        return None
    out = {}
    # 规格表：<th>字段</th> ... <td>值</td>，标签与值间可能隔若干空白标签
    for f in WANT_FIELDS:
        m = re.search(re.escape(f) + r'\s*</[^>]+>\s*(?:<[^>]+>\s*)*([^<]{1,40})<', t)
        if m:
            v = m.group(1).strip()
            if v:
                out[f] = v
    return out or None


def main():
    # 收集所有未归类竞品的 (品类, id, url)
    todo = []
    for f in sorted(glob.glob(dp('data/*/schema.json'))):
        cid = os.path.dirname(f).replace('\\', '/').split('/')[-1]
        s = json.load(open(f, encoding='utf-8'))
        facets = s.get('facets') or []
        if not facets:
            continue
        fk = facets[0]['key']
        pp = dp('data/%s/products.json' % cid)
        for p in json.load(open(pp, encoding='utf-8')):
            if p.get('brand') == '小米':
                continue
            if p.get(fk) not in (None, '未归类', '查不到'):
                continue
            u = p.get('verify_url') or ''
            if 'g.pconline.com.cn/product/' in u and pick_id(u):
                todo.append((cid, p['id'], u))
    print('待抓 %d 条' % len(todo))

    results = {}
    done = [0]

    def job(item):
        cid, pid, url = item
        sp = fetch_specs(url)
        done[0] += 1
        if done[0] % 20 == 0:
            print('  %d/%d' % (done[0], len(todo)), flush=True)
        if sp:
            return (cid, pick_id(url), sp)
        return None

    with ThreadPoolExecutor(max_workers=4) as ex:
        for r in ex.map(job, todo):
            if r:
                cid, pcid, sp = r
                results.setdefault(cid, {})[pcid] = sp

    for cid, data in results.items():
        pc = CAT2PC.get(cid, cid)
        out = dp('data/_cache/brand-%s-extra.json' % pc)
        json.dump([{'id': k, 'specs': v} for k, v in data.items()],
                  open(out, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        print('%-20s 抓到 %3d -> %s' % (cid, len(data), out))


if __name__ == '__main__':
    main()