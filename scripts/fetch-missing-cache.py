# -*- coding: utf-8 -*-
"""为缓存未命中的产品补抓 pconline 规格表，写入 data/_cache/brand-<目录>-extra.json。

背景：drop-commercial.py 依赖本地缓存判定商用品，而 71 款产品没有对应缓存
（新采集的竞品、部分小米机），这些条目在商用扫描里是盲区 —— 实测
德业 DY-6480/A 与 DY-6138EB 被判为「家用」，实为工业除湿机（380V/230kg）。

本脚本把盲区补上，让商用判定不依赖「恰好抓过」。

用法：
    python scripts/fetch-missing-cache.py --dry    # 只列出待抓
    python scripts/fetch-missing-cache.py         # 抓取并落缓存
"""
import json, glob, os, re, sys, subprocess, time
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding='utf-8')
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
D = '2026-10-03'


def dp(rel):
    return os.path.join(ROOT, rel)


def cached_ids():
    """已有**非空** specs 的 id。

    注意不能只看「id 是否存在」：实测 deye 的 641660/641658 在缓存里有条目但
    specs 是空 {}，这类「有条目无内容」同样判不出商用品，会漏检
    （它们实为 380V/230kg 的工业除湿机）。
    """
    out = set()
    for f in glob.glob(dp('data/_cache/brand-*.json')):
        try:
            d = json.load(open(f, encoding='utf-8'))
        except Exception:
            continue
        for it in (d if isinstance(d, list) else []):
            if it.get('id') and (it.get('specs') or {}):
                out.add(str(it['id']))
    return out


def pcon_path(url):
    """从 verify_url 抽出 (pconline 品类目录, 品牌 slug, id)"""
    m = re.search(r'g\.pconline\.com\.cn/product/([^/]+)/([^/]+)/([0-9]+)_detail\.html', url or '')
    return m.groups() if m else None


def decode(b):
    for e in ('gb18030', 'utf-8', 'gbk'):
        try:
            return b.decode(e)
        except Exception:
            pass
    return b.decode('utf-8', 'replace')


def fetch_specs(url, retry=2):
    """抓规格页并解析成 {字段: 值}。抓不到返回 None（调用方按缺失处理，不猜）。"""
    for attempt in range(retry + 1):
        r = subprocess.run(['curl', '-sL', '-m', '25', '-A', UA,
                            '-H', 'Accept-Language: zh-CN,zh;q=0.9',
                            '-H', 'Referer: https://g.pconline.com.cn/', url],
                           capture_output=True)
        t = decode(r.stdout)
        if len(t) > 5000:
            break
        time.sleep(1.2 * (attempt + 1))
    if len(t) < 2000:
        return None
    out = {}
    for m in re.finditer(r'>([^<>]{2,14})</(?:th|td|dt|dd|strong|b|span)>', t):
        k = m.group(1).strip()
        if not k or k in out:
            continue
        v = re.search(r'>([^<>]{1,48})<', t[m.end():m.end() + 400])
        if v:
            val = v.group(1).strip()
            if val and val not in ('-', '—'):
                out[k] = val
    return out or None


def main():
    have = cached_ids()
    todo = []
    for f in glob.glob(dp('data/*/products.json')):
        cid = os.path.basename(os.path.dirname(f))
        if cid.startswith('_'):
            continue
        for p in json.load(open(f, encoding='utf-8')):
            parts = pcon_path(p.get('verify_url'))
            if not parts:
                continue
            if parts[2] in have:
                continue
            todo.append({'cat': cid, 'id': p['id'], 'parts': parts,
                         'url': p['verify_url']})
    print('缓存未命中 %d 款' % len(todo))
    if '--dry' in sys.argv:
        for t in todo[:12]:
            print('  %s/%s  %s' % (t['cat'], t['id'], t['url']))
        return

    buckets = {}
    done = [0]

    def job(t):
        specs = fetch_specs(t['url'])
        done[0] += 1
        if done[0] % 15 == 0:
            print('  %d/%d' % (done[0], len(todo)), flush=True)
        if specs:
            key = (t['parts'][0], t['parts'][1])
            buckets.setdefault(key, []).append({'id': t['parts'][2], 'specs': specs})
        return t['id'], bool(specs)

    ok = fail = 0
    with ThreadPoolExecutor(max_workers=2) as ex:
        for _pid, good in ex.map(job, todo):
            ok, fail = (ok + 1, fail) if good else (ok, fail + 1)

    n = 0
    for (pcat, slug), items in buckets.items():
        path = dp('data/_cache/brand-%s-%s-extra.json' % (pcat, slug))
        json.dump(items, open(path, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        n += len(items)
        print('写入 %s：%d 条' % (os.path.basename(path), len(items)))
    print('\n抓到 %d 条 / 抓取失败 %d 条（失败者仍缺规格，商用判定需人工看）' % (n, fail))


if __name__ == '__main__':
    main()