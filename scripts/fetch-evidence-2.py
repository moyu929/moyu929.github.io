# -*- coding: utf-8 -*-
"""为仍未归类的竞品补抓证据，追加进 data/_cache/facet-evidence/evidence.json。

比 fetch-facet-evidence.py 更宽：不再只抓分类字段，而是把整张规格表的
字段名与值都留下来（限定白名单，避免把包装清单之类的噪声也存进来）。
并发 4 + 逐条落盘，抓完可随时重跑（已抓到的不重复请求）。
"""
import json, os, re, subprocess, sys, glob, collections
from concurrent.futures import ThreadPoolExecutor

sys.stdout.reconfigure(encoding='utf-8')

# 仓库根目录：按脚本自身位置解析，不依赖 cwd。
# 多 Agent 各自 worktree 时，从别处的 cwd 调用不会再把数据写到别的树（见方案 P0-1）。
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def dp(rel):
    """仓库相对路径 → 绝对路径"""
    return os.path.join(ROOT, rel)


UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
EVIDENCE = dp('data/_cache/facet-evidence/evidence.json')

# 只留对分类/参数判定有用的字段，噪声字段（包装清单、电线长度、颜色…）不要
WANT = re.compile(
    r'(类型|类别|安装|加热|使用方式|控制方式|除湿|容量|功率|出水|适用面积|'
    r'噪音|档位|系列|能效|制冷|制热|噪音|干衣|净重|尺寸|电压|模式|风量|档)'
)


def decode(b):
    for e in ('gbk', 'gb18030', 'utf-8'):
        try:
            return b.decode(e)
        except Exception:
            pass
    return b.decode('utf-8', 'replace')


def fetch(url):
    r = subprocess.run(['curl', '-sL', '-m', '25', '-A', UA, url], capture_output=True)
    return decode(r.stdout)


def parse_pconline(html):
    """规格表：<th>字段</th> … <td>值</td>。返回 {字段: 值}。"""
    out = {}
    # 标签名与值之间可能隔若干空白标签，逐个宽松匹配
    for m in re.finditer(r'>([^<>]{2,12})</(?:th|td|dt|dd|strong|b|span)>', html):
        key = m.group(1).strip()
        if not WANT.search(key):
            continue
        tail = html[m.end():m.end() + 400]
        v = re.search(r'>([^<>]{1,40})<', tail)
        if v:
            val = v.group(1).strip()
            if val and val not in ('-', '—'):
                out.setdefault(key, val)
    return out


def main():
    # 读已有证据
    items = {}
    if os.path.exists(EVIDENCE):
        for it in json.load(open(EVIDENCE, encoding='utf-8')):
            items[f"{it['cat']}/{it['id']}"] = it

    # 找仍未归类且尚无证据的产品
    todo = []
    for f in sorted(glob.glob(dp('data/*/schema.json'))):
        cid = os.path.basename(os.path.dirname(f))
        schema = json.load(open(f, encoding='utf-8'))
        facets = schema.get('facets') or []
        if not facets:
            continue
        fk = facets[0]['key']
        for p in json.load(open(dp('data/%s/products.json' % cid), encoding='utf-8')):
            if p.get('brand') == '小米':
                continue
            if p.get(fk) not in (None, '未归类', '查不到'):
                continue
            key = '%s/%s' % (cid, p['id'])
            it = items.get(key)
            if it and (it.get('pconline') or it.get('zol')):
                continue
            url = p.get('verify_url') or ''
            if 'g.pconline.com.cn/product/' not in url:
                continue
            todo.append((key, cid, p['id'], p['name'], p.get('brand'),
                         p.get('ref_price'), url))

    print('待抓 %d 条' % len(todo))
    done = [0]

    def job(t):
        key, cid, pid, name, brand, price, url = t
        rec = items.setdefault(key, {
            'cat': cid, 'id': pid, 'name': name, 'brand': brand,
            'facet_key': None, 'price': price, 'verify_url': url, 'model': name,
        })
        html = fetch(url)
        specs = parse_pconline(html) if len(html) > 2000 else {}
        if specs:
            rec['pconline'] = specs
        done[0] += 1
        if done[0] % 15 == 0:
            print('  %d/%d' % (done[0], len(todo)), flush=True)
            save(items)
        return specs

    with ThreadPoolExecutor(max_workers=4) as ex:
        for r in ex.map(job, todo):
            pass

    save(items)
    got = sum(1 for it in items.values() if it.get('pconline') or it.get('zol'))
    print('证据库 %d 条，其中有证据 %d' % (len(items), got))


def save(items):
    with open(EVIDENCE, 'w', encoding='utf-8', newline='\n') as f:
        json.dump(list(items.values()), f, ensure_ascii=False, indent=1)


if __name__ == '__main__':
    main()