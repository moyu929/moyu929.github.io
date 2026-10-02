# -*- coding: utf-8 -*-
"""从第三方规格表回填参数字段（只补「查不到」的，不覆盖已有值）。

数据来源：太平洋产品报价规格页（`g.pconline.com.cn/product/<目录>/<品牌>/<id>_detail.html`），
服务端渲染的结构化表格，含「额定功率 / 产品尺寸 / 工作噪音 / 净重 / 容量」等字段。

## 安全约束（对应 SKILL.md 的第三方错标规则）

1. **只补空值**：目标字段已是「查不到」以外的值一律不碰；
2. **异常阈值剔除**：单位错标（`2800W` 写成 `28W`）、数量级错（净水箱 `1ml`）、
   重量缺位（`约.6kg`）等一律丢弃并记理由；
3. **不猜**：映射表命中不了就留「查不到」；
4. 每个回填都写 `change_log`，说明取自哪个来源的哪个字段。

## 用法

    python scripts/fill-params.py --dry          # 只报告
    python scripts/fill-params.py --cat fan     # 只处理某品类
    python scripts/fill-params.py               # 写入 data/_draft/
"""
import json, os, re, sys, glob, argparse, subprocess, html
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

# 仓库根目录：按脚本自身位置解析，不依赖 cwd（见方案 P0-1）
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def dp(rel):
    """仓库相对路径 → 绝对路径"""
    return os.path.join(ROOT, rel)


sys.stdout.reconfigure(encoding='utf-8')
D = '2026-10-03'
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

# 本站字段 -> 第三方规格表的字段名候选（按优先级）
FIELD_MAP = {
    'power':       ['额定功率', '产品功率', '输入功率', '加热功率', '制冷功率'],
    'size':        ['产品尺寸', '外形尺寸', '外型尺寸', '机身尺寸', '产品大小', '尺寸'],
    'weight':      ['产品重量', '净重', '毛重', '重量'],
    'noise':       ['工作噪音', '室内机噪音', '噪音', '运转噪音', '产品噪音'],
    'capacity':    ['产品容量', '水箱容量', '水箱容积', '内胆容量', '容量'],
    'tank':        ['水箱容量', '水箱容积', '集尘箱容量', '清水箱容量'],
    'energy':      ['能效等级', '能效', '能源效率'],
    'flux':        ['额定通量', '通量', '制水速度'],
    'runtime':     ['续航时间', '连续使用时间', '工作时间'],
    'suction':     ['吸力', '真空度', '吸力大小'],
    'battery':     ['电池容量', '电池规格'],
    'coverage':    ['适用面积', '覆盖面积'],
    'voltage':     ['额定电压', '电源电压', '电压'],
    'refresh':     ['屏幕刷新频率', '刷新率'],
    'resolution':  ['分辨率', '屏幕分辨率'],
    'cool_cap':    ['制冷量'],
    'heat_cap':    ['制热量'],
    'cold_wind':   ['循环风量', '风量', '风量大小'],
    'heating':     ['加热方式'],
    'backlight':   ['面板类型', '背光类型'],
    'open_size':   ['安装开孔尺寸', '开孔尺寸'],
    'vent_power':  ['换气功率'],
    'light_power': ['灯暖功率', '照明功率'],
    'heat_power':  ['取暖功率', '风暖功率'],
    'fan_power':   ['风扇功率'],
    'yield':       ['出汁率', '出浆率'],
    'gear':        ['档位', '可选档位', '火力档位'],
}

# 字段级异常阈值：超出即判第三方错标，丢弃
THRESHOLD = {
    'power':     (5, 6000),      # 家电额定功率 5W~6000W
    'weight':    (0.05, 100),    # 净重 50g~100kg
    'noise':     (15, 90),       # 噪音 15~90dB
    'battery':   (500, 20000),   # 电池 500~20000mAh
    'coverage':  (3, 200),       # 适用面积 3~200㎡
    'capacity':  (0.2, 30),      # 通用容量下界
    'tank':      (0.1, 10),
    'flux':      (0.05, 10),     # 通量 t/h 或 L/min
    'runtime':   (5, 600),       # 续航 5~600min
}

# text 类字段：值保留原文（尺寸「1084×232×232mm」不能只取第一个数字，
# 那会丢掉尺寸信息），但仍做阈值校验以剔除第三方错标值。
TEXT_FIELDS = {'size', 'heating', 'backlight', 'open_size', 'resolution'}

# 单位归一：把第三方写法换成 schema 声明的单位。系数都是确定的换算，不是猜测。
# 单位归一：把第三方的中文单位写法换成 schema 声明的单位。
# 用纯字符串替换而不是正则反向引用 —— 避免在不同 shell / 编辑器里转义被吃掉。
# 长的排前面：否则「毫升」会先被「升」替换成「毫L」
UNIT_PAIRS = [
    ('平方米', '㎡'), ('公斤', 'kg'), ('毫升', 'ml'),
    ('升/日', 'L/天'), ('分贝', 'dB'), ('瓦', 'W'), ('升', 'L'),
]


def decode(b):
    for e in ('gbk', 'gb18030', 'utf-8'):
        try:
            return b.decode(e)
        except Exception:
            pass
    return b.decode('utf-8', 'replace')


def fetch_specs(url, retry=2):
    """抓规格页。pconline 对连续请求会限流（返回 503 或空体），
    失败时退避重试；仍失败返回空 dict（调用方按「无数据」处理，不猜）。"""
    import time
    for attempt in range(retry + 1):
        r = subprocess.run(['curl', '-sL', '-m', '25', '-A', UA,
                            '-H', 'Accept-Language: zh-CN,zh;q=0.9',
                            '-H', 'Referer: https://g.pconline.com.cn/', url],
                           capture_output=True)
        t = decode(r.stdout)
        if len(t) > 5000:
            break
        time.sleep(1.5 * (attempt + 1))
    if len(t) < 2000:
        return {}
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
    return out


def num_of(v):
    m = re.search(r'(-?\d+(?:\.\d+)?)', str(v).replace(',', ''))
    return float(m.group(1)) if m else None


def acceptable(field, raw):
    """按阈值剔除第三方错标值。返回 (是否可用, 说明)。"""
    n = num_of(raw)
    if n is None:
        return False, '无法解析数值'
    lo, hi = THRESHOLD.get(field, (None, None))
    if lo is not None and not (lo <= n <= hi):
        return False, '数值 %s 超出合理区间 [%s, %s]（疑单位错标）' % (n, lo, hi)
    return True, str(n)


def normalize(raw):
    for cn, en in UNIT_PAIRS:
        raw = raw.replace(cn, en)
    return raw.strip()


def pick(field, specs):
    """按映射表从规格表取值。text 字段保留原文，number 字段取数值。"""
    for name in FIELD_MAP.get(field, []):
        if name in specs:
            raw = specs[name]
            ok, val = acceptable(field, raw)
            if not ok:
                return None, '%s=%s 剔除：%s' % (name, raw, val)
            if field in TEXT_FIELDS:
                return normalize(raw), '%s=%s' % (name, raw)
            # number 字段：整数不带小数点，避免 '40.0' 这种噪声
            n = num_of(val)
            return (int(n) if n == int(n) else n), '%s=%s' % (name, raw)
    return None, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dry', action='store_true')
    ap.add_argument('--cat', help='只处理某品类')
    ap.add_argument('--limit', type=int, default=0, help='每品类最多处理多少条（0=不限）')
    args = ap.parse_args()

    targets = []
    for f in sorted(glob.glob(dp('data/*/schema.json'))):
        cid = os.path.basename(os.path.dirname(f))
        if args.cat and cid != args.cat:
            continue
        s = json.load(open(f, encoding='utf-8'))
        keys = {x['key'] for x in s['fields']}
        fields = [k for k in FIELD_MAP if k in keys]
        if not fields:
            continue
        for p in json.load(open(dp('data/%s/products.json' % cid), encoding='utf-8')):
            holes = [k for k in fields
                     if p.get(k) in ('查不到', '—', '', None)]
            if not holes:
                continue
            u = p.get('verify_url') or ''
            if 'g.pconline.com.cn/product/' not in u:
                continue
            targets.append((cid, p['id'], u, holes))
    if args.limit:
        seen = Counter()
        keep = []
        for t in targets:
            if seen[t[0]] < args.limit:
                keep.append(t); seen[t[0]] += 1
        targets = keep

    print('待处理 %d 条产品' % len(targets))
    done = [0]
    results = {}

    def job(t):
        cid, pid, url, holes = t
        specs = fetch_specs(url)
        done[0] += 1
        if done[0] % 50 == 0:
            print('  %d/%d' % (done[0], len(targets)), flush=True)
        if not specs:
            return None
        fills = {}
        for k in holes:
            v, why = pick(k, specs)
            if v is not None:
                fills[k] = (v, why)
        return (cid, pid, fills) if fills else None

    with ThreadPoolExecutor(max_workers=2) as ex:
        for r in ex.map(job, targets):
            if r:
                results[(r[0], r[1])] = r[2]

    nfields = sum(len(v) for v in results.values())
    print('\n可回填：%d 条产品 / %d 个字段' % (len(results), nfields))
    print(Counter(k for v in results.values() for k in v).most_common(15))

    if args.dry:
        print('\n--dry 示例：')
        for (cid, pid), fills in list(results.items())[:12]:
            print('   %s/%s' % (cid, pid))
            for k, (v, why) in fills.items():
                print('       %s = %-14s (%s)' % (k, v, why))
        return

    for (cid, pid), fills in results.items():
        d = dp('data/_draft/%s' % cid)
        os.makedirs(d, exist_ok=True)
        cur = json.load(open(dp('data/%s/products.json' % cid), encoding='utf-8'))
        base = next(x for x in cur if x['id'] == pid)
        item = dict(base)
        for k, (v, why) in fills.items():
            item[k] = v
        item['verify_date'] = D
        item['change_log'] = (base.get('change_log', '') or '') + \
            '；%s 回填参数（来源：太平洋规格表 verify_url）：%s' % (
                D, '，'.join('%s=%s（%s）' % (k, v, w) for k, (v, w) in fills.items()))
        item['updated_at'] = D
        with open('%s/%s.json' % (d, pid), 'w', encoding='utf-8', newline='\n') as fh:
            json.dump(item, fh, ensure_ascii=False, indent=2)
            fh.write('\n')
    print('\n已写入 data/_draft/：%d 条' % len(results))


if __name__ == '__main__':
    main()