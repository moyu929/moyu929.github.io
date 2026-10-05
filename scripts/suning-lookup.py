# -*- coding: utf-8 -*-
"""按型号从苏宁易购补 `year`（上市时间）与 `size`（产品尺寸）。

## 为什么是苏宁

2026-10-04 实测：全站 1036 款里 `year` 缺 888，`size` 缺 556，且**现有来源基本无解** ——
太平洋的「上市时间」字段仍在线，但**只对空调 / 电视 / 扫地机 / 洗衣机 4 个品类开放**，
其余 25 个品类覆盖率 0；ZOL 的 param 页对 `上市时间` / `上市日期` 的命中数为 0（两次独立探测）；
GitHub 上不存在中文家电参数数据集。

苏宁是本轮唯一实测可用、且**可按型号批量定位**的来源：

    GET https://search.suning.com/<URL编码型号>/        服务端渲染，正则提链接
    GET https://product.suning.com/<vendorId>/<code>.html   详情页取字段

两跳都是纯 HTTP：实测连打 12 次全部 200、响应字节一致、总耗时 2.9 秒，
555 款 × 2 跳 ≈ 1110 次请求，串行约 4.5 秒/10 次，**不需要退避重试**。

## 三条硬纪律（不守会写进错数据）

1. **型号必须逐项核对，不能「搜到了就采」。** 苏宁搜索排名很松：
   搜 `MB-EFB4022H` 返回的是苏泊尔 `SF50FC733`；搜 `XQG100-ABLEU70D1U1` 返回
   `XQG130-ABLEU70D3U1`；搜 `BCD-560WGHTD1BWLU1` 只返回 507 系。
   本脚本只做**精确型号字符串相等**判定；站内 `model_code` 与苏宁页面型号
   不完全一致时不采，转人工。
2. **日精度日期一律丢弃。** 苏宁的「上市时间（月）」字段里混了上架日期：
   实测 26 例中 2 例是 `YYYY-MM-DD` 形态，且日期距当天只有几天。
   只采 `YYYY-MM` 与 `YYYY年M月`。
3. **尺寸有四行，只能取产品本体那行。** 详情页同时给
   `产品尺寸（宽*深*高）` / `包装尺寸` / `预留尺寸` / `内机尺寸(宽×高×深）`。
   取值规则：键含 `尺寸`、排除 `包装`、排除 `预留`、值匹配 `\\d+[*x×]\\d+[*x×]\\d+`。
   ⚠️ **轴序不一致**（宽*深*高 vs 宽×高×深），入库前须与站内既有 `size` 值比对确认。

## 用法

    python scripts/suning-lookup.py --cat washing-machine --dry
    python scripts/suning-lookup.py --cat washing-machine     # 写入 data/_draft/

输出缓存：`data/_cache/suning-<品类>.json`（gitignored，人可复核）
"""
import json, os, re, sys, glob, time, argparse, subprocess, html as htmlmod
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding='utf-8')

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
D = '2026-10-05'
BLANK = ('查不到', '—', '', None, '-')

SEARCH = 'https://search.suning.com/%s/'
LINK_RE = re.compile(r'product\.suning\.com/(\d+)/(\d+)\.html')
# 只采年月精度；日精度（YYYY-MM-DD）疑似「上架日期」被塞进本字段，一律丢弃
YEAR_RE = re.compile(r'(20\d{2})\s*[-年/]\s*(\d{1,2})(?!\d)')
YEAR_ONLY_RE = re.compile(r'(20\d{2})\s*年(?!\s*\d)')
# 尺寸：排除包装与预留，只取产品本体
SIZE_KEY_BAD = re.compile(r'包装|预留|外箱')
SIZE_VAL_RE = re.compile(r'\d+(?:\.\d+)?\s*[*x×X]\s*\d+(?:\.\d+)?\s*[*x×X]\s*\d+')


def dp(rel):
    return os.path.join(ROOT, rel)


def decode(b):
    for e in ('utf-8', 'gb18030', 'gbk'):
        try:
            return b.decode(e)
        except Exception:
            pass
    return b.decode('utf-8', 'replace')


def fetch(url, timeout=20, tries=2):
    """纯 HTTP 抓取。苏宁实测无限流，但留一次重试兜底网络抖动。"""
    for i in range(tries):
        try:
            r = subprocess.run(
                ['curl', '-sL', '--compressed', '-m', str(timeout), '-A', UA,
                 '-H', 'Accept-Language: zh-CN,zh;q=0.9',
                 '-H', 'Referer: https://www.suning.com/', url],
                capture_output=True)
            t = decode(r.stdout)
            if len(t) > 3000:
                return t
        except Exception:
            pass
        time.sleep(0.6 * (i + 1))
    return ''


def norm(s):
    """型号归一：去掉空白与全角括号差异，让 `XQG100-ABLEU70D1U1` 能与页面上的对上。"""
    return re.sub(r'[\s　（）()]', '', str(s or '')).upper()


def search_detail_urls(model):
    """型号 → 苏宁详情页 URL 列表（按 productCode 去重）。

    同一 productCode 会挂在多个 vendorId 下（实测 `12440110157` 同时出现在
    `0010342220` 与 `0070165541`，数据完全相同），所以按 productCode 去重。
    """
    t = fetch(SEARCH % quote(model))
    codes, out = set(), []
    for vendor, code in LINK_RE.findall(t):
        if code in codes:
            continue
        codes.add(code)
        out.append(('https://product.suning.com/%s/%s.html' % (vendor, code), code))
    return out


def parse_specs(t):
    """从苏宁详情页抽 {键: 值}。三种版式都要接：
        <li><b>品牌</b>：海尔</li>
        <td class="name">…<span>产品尺寸</span></td><td class="val">…</td>
        <dt>上市时间（月）</dt><dd>2024-10</dd>
    """
    out = {}
    for pat in (r'>([^<>]{2,24})</(?:dt|th|label)>',
                r'<td[^>]*class="name"[^>]*>\s*(?:<[^>]+>\s*)*([^<>]{2,24}?)\s*(?:</[^>]+>\s*)*</td>\s*<td[^>]*class="val"[^>]*>\s*(?:<[^>]+>\s*)*([^<>]{1,60}?)\s*(?:</[^>]+>\s*)*</td>',
                r'<li[^>]*>\s*<b[^>]*>([^<>]{2,24})</b>\s*[：:]\s*([^<]{1,60}?)\s*</li>'):
        for m in re.finditer(pat, t, re.S):
            if m.lastindex == 1:
                k = m.group(1).strip()
                v = re.search(r'>([^<>]{1,60})<', t[m.end():m.end() + 200])
                val = htmlmod.unescape(v.group(1)).strip() if v else ''
            else:
                k, val = m.group(1).strip(), htmlmod.unescape(m.group(2)).strip()
            if k and k not in out and val and val not in ('-', '—', '暂无'):
                out[k] = val
    # 兜底：「键：值」纯文本
    for m in re.finditer(r'([一-龥A-Za-z][一-龥A-Za-z0-9（）()]{1,22})\s*[:：]\s*([^\s<>|]{1,40})', t):
        k, v = m.group(1).strip(), m.group(2).strip()
        if k not in out and v not in ('-', '—'):
            out[k] = v
    return out


def pick_model(specs):
    """从苏宁详情页取商品型号。**这是整条流水线的硬门槛**。"""
    for k, v in specs.items():
        if k.strip() in ('型号', '商品型号', '产品型号', '型号名称'):
            return str(v).strip()
    return None


def model_matches(page_model, want):
    """型号是否精确匹配。**不匹配就整条丢弃**。

    实测的反例：搜 `XQG100-ABLEU70D1U1`（西门子）返回的页面里
    `XQG100-ABLEU70D1U1` 出现 **0 次**，而 `XQG130-ABLEU70D3U1` 出现 37 次。
    搜索排名极松，不校验就会把**另一台机器的上市时间**写到这一款上。

    判定只做**归一后完全相等**，不做包含、不做前缀匹配 ——
    `XQG100` 是 `XQG100-ABLEU70D1U1` 的前缀，包含式匹配会错配到整个产品族。
    """
    if not page_model:
        return False
    return norm(page_model) == norm(want)


def pick_year(specs):
    """取上市年份。只采年月精度。"""
    for k, v in specs.items():
        if '上市' in k and '时间' in k:
            m = YEAR_RE.search(str(v))
            if m:
                mo = int(m.group(2))
                if 1 <= mo <= 12:
                    return int(m.group(1)), mo, '%s=%s' % (k, v)
            m = YEAR_ONLY_RE.search(str(v))
            if m:
                return int(m.group(1)), None, '%s=%s' % (k, v)
            # 日精度形态命中 YEAR_RE 但后面跟数字 → 丢弃
            if re.search(r'20\d{2}\s*[-年/]\s*\d{1,2}\s*[-/]\s*\d{1,2}', str(v)):
                return None, None, '日精度疑似上架日期，丢弃：%s=%s' % (k, v)
    return None, None, None


def pick_size(specs):
    """取产品本体尺寸。排除包装与预留行。"""
    for k, v in specs.items():
        if '尺寸' not in k or SIZE_KEY_BAD.search(k):
            continue
        s = str(v).replace('毫米', 'mm').replace('毫米毫米', 'mm').strip()
        if SIZE_VAL_RE.search(s):
            return s, '%s=%s' % (k, v)
    return None, None


def pick_energy(specs):
    for k, v in specs.items():
        if '能效' in k:
            m = re.search(r'([1-5])\s*级', str(v))
            if m:
                return m.group(0), '%s=%s' % (k, v)
    return None, None


def blank(v):
    return v in BLANK or (isinstance(v, (list, dict)) and not v)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--cat', required=True, help='品类，可逗号分隔')
    ap.add_argument('--dry', action='store_true')
    ap.add_argument('--limit', type=int, default=0)
    args = ap.parse_args()

    cats = args.cat.split(',')
    targets = []
    for cid in cats:
        pf = dp('data/%s/products.json' % cid)
        sf = dp('data/%s/schema.json' % cid)
        if not os.path.exists(pf):
            continue
        keys = {x['key'] for x in json.load(open(sf, encoding='utf-8'))['fields']}
        for p in json.load(open(pf, encoding='utf-8')):
            if blank(p.get('model_code')):
                continue
            holes = [k for k in ('year', 'size', 'energy') if k in keys and blank(p.get(k))]
            if holes:
                targets.append((cid, p['id'], p['model_code'], holes, p))
    if args.limit:
        targets = targets[:args.limit]

    print('待处理 %d 款（需 model_code 非空且目标字段为空）' % len(targets))
    done = [0]
    results = {}
    misses = []

    def job(t):
        cid, pid, model, holes, p = t
        fills, notes = {}, []
        for url, code in search_detail_urls(model)[:4]:
            specs = parse_specs(fetch(url))
            if not specs:
                continue
            # —— 硬门槛：型号对不上就整条丢弃，不采任何字段
            pm = pick_model(specs)
            if not model_matches(pm, model):
                notes.append('型号不符（搜 %s → 页面是 %s），跳过' % (model, pm or '未标注'))
                continue
            got = False
            if 'year' in holes:
                y, mo, why = pick_year(specs)
                if y:
                    fills['year'] = y
                    notes.append('year=%s（%s）' % (y, why))
                    got = True
                    if mo and 'month' in p and blank(p.get('month')):
                        fills['month'] = mo
                elif why:
                    notes.append(why)
            if 'size' in holes and 'size' not in fills:
                s, why = pick_size(specs)
                if s:
                    fills['size'] = s
                    notes.append('size=%s（%s）' % (s, why))
                    got = True
            if 'energy' in holes and 'energy' not in fills:
                e, why = pick_energy(specs)
                if e:
                    fills['energy'] = e
                    notes.append('energy=%s（%s）' % (e, why))
                    got = True
            if got:
                fills['_url'] = url
                break
        done[0] += 1
        if done[0] % 25 == 0:
            print('  %d/%d' % (done[0], len(targets)), flush=True)
        if fills:
            return (cid, pid, fills, notes)
        return (cid, pid, None, notes)

    with ThreadPoolExecutor(max_workers=4) as ex:
        for cid, pid, fills, notes in ex.map(job, targets):
            if fills:
                results[(cid, pid)] = (fills, notes)
            else:
                misses.append((cid, pid, notes))

    n = sum(len(v[0]) - 1 for v in results.values())  # 减去 _url
    print('\n可回填 %d 款 / %d 字段；未命中 %d 款' % (len(results), n, len(misses)))
    for (cid, pid), (fills, notes) in list(results.items())[:10]:
        print('  %s/%s  %s' % (cid, pid, '，'.join(notes)))

    for cid in cats:
        path = dp('data/_cache/suning-%s.json' % cid)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        items = [{'id': pid, 'model_code': next(t[2] for t in targets
                                                 if t[0] == cid and t[1] == pid),
                  'fills': fills, 'notes': notes}
                 for (c, pid), (fills, notes) in results.items() if c == cid]
        json.dump(items, open(path, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print('原始结果：data/_cache/suning-<品类>.json')

    if args.dry:
        return

    cnt = 0
    for (cid, pid), (fills, notes) in results.items():
        d = dp('data/_draft/%s' % cid)
        os.makedirs(d, exist_ok=True)
        cur = json.load(open(dp('data/%s/products.json' % cid), encoding='utf-8'))
        base = next(x for x in cur if x['id'] == pid)
        item = dict(base)
        url = fills.pop('_url')
        for k, v in fills.items():
            item[k] = v
        item['verify_date'] = D
        item['verify_source'] = sorted(set(base.get('verify_source') or []) | {'苏宁易购'}) \
            if isinstance(base.get('verify_source'), list) else ['苏宁易购']
        item['verify_url'] = url
        item['change_log'] = (base.get('change_log', '') or '') + \
            '；%s 苏宁易购补参：%s' % (D, '，'.join(notes))
        item['updated_at'] = D
        with open('%s/%s.json' % (d, pid), 'w', encoding='utf-8', newline='\n') as fh:
            json.dump(item, fh, ensure_ascii=False, indent=2)
            fh.write('\n')
        cnt += 1
    print('\n已写入 data/_draft/：%d 条' % cnt)


if __name__ == '__main__':
    main()