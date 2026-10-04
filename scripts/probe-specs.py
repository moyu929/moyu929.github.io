# -*- coding: utf-8 -*-
"""探测一个站点**能不能解析出规格表**——而不是只看 HTTP 通不通。

## 为什么重写探测

2026-10-04 的教训：早先的 `probe-sources.py` 记的是「能否连通」，结果把
科沃斯 / 添可 / 石头官方站标成可用 —— 那三家是 SPA，商品页正文仅两千余字，
`吸力` / `噪音` / `基座` 零命中，无内嵌 JSON。**HTTP 200 ≠ 能取到规格表。**

所以本脚本的判据是**实测抽出的规格字段数**：

  1. 先用纯 HTTP 抓，看服务端渲染出多少 `<dt>/<th>/<td>` 键值对
  2. 服务端渲染不出，才起 Playwright（无头 Chromium）渲染后再数
  3. 再找内嵌 JSON（`__NEXT_DATA__` / `window.__INITIAL_STATE__` /
     `<script type="application/json">`），能解析出键值也算

判据：**抽出的规格字段数 ≥ 5** 才算「可用」。低于这个数的一律记为
「连通但不可用」，避免下一批人白跑。

## ⚠️ 必须探**商品详情页**，首页与列表页一律无效

2026-10-04 踩过的坑：对 12 个站点各探了一个首页/列表页，结果 **12/12 全判不可用**，
其中包括**已知可用的太平洋**。换成一个真实商品详情页
（`https://g.pconline.com.cn/product/air_condition/midea/2826831_detail.html`）
立刻抽出 9 个规格字段命中。

首页和列表页本来就没有规格表 —— 判据「抽到的规格字段数 ≥ 5」在错误的页面上
必然为 0，与站点是否可用无关。**先定位商品详情页，再探测。**

## 用法

    python scripts/probe-specs.py --url "<商品详情页URL>"   # 单站探测
    python scripts/probe-specs.py                      # 跑全部候选（仅连通性参考）
    python scripts/probe-specs.py --only official      # 只测品牌官方站
    python scripts/probe-specs.py --only third         # 只测第三方
    python scripts/probe-specs.py --url <页面地址>      # 测单个 URL
    python scripts/probe-specs.py --render             # 强制走浏览器渲染

输出 JSON 到 data/_cache/probe-specs.json（不入库），人可复核。
"""
import json, os, re, sys, argparse, subprocess, html as htmlmod
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding='utf-8')

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

# 家用电器规格表里高频出现的参数词。命中越多，说明该页是规格表的可能性越大。
SPEC_WORDS = [
    '功率', '尺寸', '重量', '噪音', '容量', '能效', '电压', '续航', '吸力',
    '能效等级', '额定', '净重', '外型', '外形', '产品重量', '工作噪音',
    '制冷量', '洗涤容量', '风量', '转速', '电池', '材质', '档位', '加热',
]


def dp(rel):
    return os.path.join(ROOT, rel)


def decode(b):
    for e in ('utf-8', 'gb18030', 'gbk'):
        try:
            return b.decode(e)
        except Exception:
            pass
    return b.decode('utf-8', 'replace')


# ---------------------------------------------------------------- 服务端渲染

def parse_html_specs(t):
    """从 HTML 抽 {参数名: 值}。两条路径：标签相邻、以及「键：值」文本。"""
    out = {}
    for m in re.finditer(r'>([^<>]{2,16})</(?:dt|th|td|label|strong)>', t):
        k = m.group(1).strip()
        if not k or k in out:
            continue
        v = re.search(r'>([^<>]{1,60})<', t[m.end():m.end() + 300])
        if v:
            val = htmlmod.unescape(v.group(1)).strip()
            if val and val not in ('-', '—'):
                out[k] = val
    for m in re.finditer(r'([一-龥A-Za-z][一-龥A-Za-z0-9（）()]{1,14})\s*[:：]\s*'
                         r'([^\s<>|]{1,40})', t):
        k, v = m.group(1).strip(), m.group(2).strip()
        if k not in out and v and v not in ('-', '—'):
            out[k] = v
    return out


def parse_embedded_json(t):
    """找内嵌 JSON 里的规格表。SPA 常把数据塞在 __NEXT_DATA__ / INITIAL_STATE。"""
    out = {}
    blobs = []
    for pat in (r'<script[^>]+id="__NEXT_DATA__"[^>]*>(.*?)</script>',
                r'window\.__INITIAL_STATE__\s*=\s*(\{.*?\})\s*</script>',
                r'<script[^>]+type="application/json"[^>]*>(.*?)</script>'):
        blobs += re.findall(pat, t, re.S)
    for b in blobs:
        try:
            d = json.loads(htmlmod.unescape(b))
        except Exception:
            continue
        stack = [d]
        while stack:
            cur = stack.pop()
            if isinstance(cur, dict):
                for k, v in cur.items():
                    if isinstance(v, (str, int, float)) and 1 < len(str(k)) < 16:
                        out.setdefault(str(k), str(v))
                    elif isinstance(v, (dict, list)):
                        stack.append(v)
            elif isinstance(cur, list):
                stack.extend(cur)
    return out


def score(specs):
    """规格字段里有多少命中高频参数词 —— 比纯数量更能区分「规格表」与「页面噪声」。"""
    hits = 0
    for k in specs:
        if any(w in k for w in SPEC_WORDS):
            hits += 1
    return hits


def probe_http(url, timeout=20):
    try:
        r = subprocess.run(
            ['curl', '-sL', '-m', str(timeout), '-A', UA,
             '-H', 'Accept-Language: zh-CN,zh;q=0.9', url],
            capture_output=True)
        return decode(r.stdout), r.returncode
    except Exception:
        return '', -1


def probe_render(url, timeout=35000):
    """Playwright 渲染。只在服务端渲染抽不出东西时才值得跑。"""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return None, 'playwright 未安装'
    try:
        with sync_playwright() as pw:
            b = pw.chromium.launch(headless=True)
            pg = b.new_page(user_agent=UA)
            pg.goto(url, timeout=timeout, wait_until='domcontentloaded')
            try:
                pg.wait_for_timeout(2500)
            except Exception:
                pass
            t = pg.content()
            b.close()
            return t, None
    except Exception as e:
        return None, '%s: %s' % (type(e).__name__, str(e)[:80])


def probe(url, force_render=False):
    res = {'url': url, 'host': urlparse(url).netloc}
    t, rc = probe_http(url)
    res['http_len'] = len(t)
    res['http_status'] = 200 if rc == 0 and t else 0
    specs = parse_html_specs(t) if t else {}
    src = '服务端渲染'
    if t:
        emb = parse_embedded_json(t)
        if len(emb) > len(specs):
            specs, src = emb, '内嵌 JSON'
    res['via'] = src
    res['http_fields'] = len(specs)
    res['http_spec_hits'] = score(specs)
    if force_render or res['http_spec_hits'] < 5:
        t2, err = probe_render(url)
        if err:
            res['render'] = err
        else:
            specs2 = parse_html_specs(t2)
            emb2 = parse_embedded_json(t2)
            if len(emb2) > len(specs2):
                specs2, s2 = emb2, '内嵌 JSON（渲染后）'
            else:
                s2 = '浏览器渲染'
            if score(specs2) > res['http_spec_hits']:
                res['render_fields'] = len(specs2)
                res['render_spec_hits'] = score(specs2)
                res['via'] = s2 + '（优于服务端）'
                res['best_spec_hits'] = res['render_spec_hits']
                res['sample'] = list(specs2)[:12]
            else:
                res['render_fields'] = len(specs2)
                res['render_spec_hits'] = score(specs2)
                res['best_spec_hits'] = max(res['http_spec_hits'], res['render_spec_hits'])
                res['sample'] = list(specs)[:12]
    else:
        res['best_spec_hits'] = res['http_spec_hits']
        res['sample'] = list(specs)[:12]
    res['usable'] = res.get('best_spec_hits', 0) >= 5
    res['verdict'] = ('可用：抽到 %d 个规格字段' % res['best_spec_hits']) if res['usable'] \
        else ('连通但不可用：只抽到 %d 个规格字段' % res.get('best_spec_hits', 0))
    return res


# ---------------------------------------------------------------- 候选清单

# ⚠️ 下列是**站点首页**，只用于粗筛连通性。要判「能否解析规格表」，
# 必须换成一个真实商品详情页 —— 首页没有规格表，探它必然 0 字段。
CANDIDATES = {
    'official': [
        ('美的', 'https://www.midea.cn/'),
        ('格力', 'https://www.gree.com/'),
        ('TCL', 'https://www.tcl.com/'),
        ('海信', 'https://www.hisense.com/'),
        ('海尔', 'https://www.haier.com/'),
        ('老板电器', 'https://www.robam.com/'),
        ('方太', 'https://www.fotile.com/'),
        ('华帝', 'https://www.vatti.com.cn/'),
        ('苏泊尔', 'https://www.supor.com/'),
        ('九阳', 'https://www.joyoung.com/'),
        ('飞利浦', 'https://www.philips.com.cn/'),
        ('科沃斯', 'https://www.ecovacs.cn/'),
        ('石头', 'https://www.roborock.com/'),
        ('添可', 'https://www.tineco.cn/'),
        ('追觅', 'https://www.dreametech.com/'),
        ('戴森', 'https://www.dyson.cn/'),
        ('松下', 'https://www.panasonic.cn/'),
        ('西门子', 'https://www.siemens-home.bsh-group.cn/'),
        ('博世', 'https://www.bosch-home.cn/'),
        ('小天鹅', 'https://www.littleswan.com/'),
    ],
    'third': [
        ('ZOL-空调', 'https://detail.zol.com.cn/air_conditioner/'),
        ('ZOL-冰箱', 'https://detail.zol.com.cn/refrigerator/'),
        ('ZOL-洗衣机', 'https://detail.zol.com.cn/washer/'),
        ('IT168', 'https://product.it168.com/'),
        ('天极网', 'https://product.yesky.com/'),
        ('太平洋产品库', 'https://g.pconline.com.cn/product/'),
        ('苏宁易购', 'https://product.suning.com/'),
        ('国美', 'https://www.gome.com.cn/'),
        ('慢慢买', 'https://www.manmanbuy.com/'),
        ('什么值得买', 'https://www.smzdm.com/'),
        ('中国能效标识网', 'http://www.energylabelrecord.com/'),
        ('京东商品', 'https://item.jd.com/'),
    ],
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--only', choices=['official', 'third'])
    ap.add_argument('--url')
    ap.add_argument('--render', action='store_true')
    args = ap.parse_args()

    jobs = []
    if args.url:
        jobs = [(args.url, args.url)]
    else:
        for grp in ([args.only] if args.only else list(CANDIDATES)):
            for name, url in CANDIDATES[grp]:
                jobs.append((name, url))

    print('探测 %d 个候选（判据：抽到的规格字段数 ≥ 5）\n' % len(jobs))
    results = []
    with ThreadPoolExecutor(max_workers=4) as ex:
        for (name, _u), r in zip(jobs, ex.map(lambda j: probe(j[1], args.render), jobs)):
            results.append(dict(r, name=name))
            flag = '✓' if r['usable'] else '✗'
            print('%s %-14s %-42s %s' % (flag, name, r['host'][:42], r['verdict']))
            if r['usable']:
                print('    路径=%s 字段=%s 样本=%s'
                      % (r['via'], r.get('render_fields') or r['http_fields'],
                         r.get('sample', [])[:6]))

    out = dp('data/_cache/probe-specs.json')
    os.makedirs(os.path.dirname(out), exist_ok=True)
    json.dump(results, open(out, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    ok = sum(1 for r in results if r['usable'])
    print('\n可用 %d / %d —— 详情见 data/_cache/probe-specs.json' % (ok, len(results)))


if __name__ == '__main__':
    main()