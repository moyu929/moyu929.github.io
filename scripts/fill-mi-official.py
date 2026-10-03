# -*- coding: utf-8 -*-
"""从小米官方商城 API 回填参数（只补「查不到」的，不覆盖已有值）。

## 为什么单独一个脚本

2026-10-04 的可达性测算：4434 个映射字段上的空值里，第三方缓存能自动补的只有 79 个
（1.8%），2653 个（59.8%）是 pconline 压根没发布该字段，1547 个（34.9%）的产品
连第三方链接都没有 —— 后者里绝大多数是小米系。小米系走的是官方商城 API 这条路。

## 接口

    https://api2.order.mi.com/product/view?product_id=<id>&version=2

**必须带 `-H "Referer: https://www.mi.com/"`**，否则返回空 body。这是实测出来的，
漏掉这个头会得到 200 + 空体，很容易被误判成「商品不存在」。

返回 `data.goods_list[0].goods_info`：
  - `name` / `price`（现价，元）/ `market_price`（划线价，元）
  - `class_parameters` = `[{name, value, is_page_show}]`，是商城的「关键参数」，
    含 CADR、建议最大适用面积、能效等级、滤网类型等。**只取 `is_page_show` 为真的**。
  - `ext_buy_option` 揭示 SKU 变体关系（同一型号不同色/容量），不去重、只用于对齐型号

## 额定 vs 实测（SKILL.md 核心规则 2）

`class_parameters` 里大量值带「（实测值）」后缀（例：`颗粒物CADR 830（实测值）m³/h`）。
这类一律写进带 `_real` 后缀的字段，**不与额定值混在一列**。

## 用法

    python scripts/fill-mi-official.py --cat air-purifier --dry
    python scripts/fill-mi-official.py --cat air-purifier     # 写入 data/_draft/
    python scripts/fill-mi-official.py --report               # 只列出哪些产品没有 product_id
"""
import json, os, re, sys, glob, time, argparse, subprocess
from concurrent.futures import ThreadPoolExecutor
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding='utf-8')
for _s in (sys.stdin, sys.stdout):
    try:
        _s.reconfigure(encoding='utf-8')
    except (AttributeError, ValueError):
        pass

BLANK = ('查不到', '—', '', None, '-')
D = '2026-10-04'
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
API = 'https://api2.order.mi.com/product/view?product_id=%s&version=2'


def dp(rel):
    return os.path.join(ROOT, rel)


def blank(v):
    return v in BLANK or (isinstance(v, (list, dict)) and not v)


# 商城「关键参数」的 name -> 本站字段。
#
# 键名两边写法不一致，按 2026-10-04 实际抓到的 418 款商品归纳：
#   * 空调的匹数商城写「匹数」，净化器写「建议最大适用面积」
#   * CADR 带「（实测值）」的走 *_real，不带的走额定列（见 pick 里的分流）
KEY_MAP = {
    # —— 通用
    '能效等级': 'energy',
    '噪音': 'noise', '产品噪音': 'noise', '工作噪音': 'noise', '运转噪音': 'noise',
    '产品尺寸': 'size', '机身尺寸': 'size', '外形尺寸': 'size', '外型尺寸': 'size',
    '产品重量': 'weight', '重量': 'weight', '净重': 'weight',
    '额定功率': 'power', '产品功率': 'power', '最大功率': 'power',
    '室内机噪音': 'noise', '室外机噪音': 'noise',
    '室内机尺寸': 'size_indoor', '室外机尺寸': 'size_outdoor',
    '循环风量': 'airflow', '风量': 'airflow',
    '制冷量': 'cool_cap', '制热量': 'heat_cap', '制冷功率': 'cool_power',
    '匹数': 'pishu', '建议匹数': 'pishu',
    '适用面积': 'area', '建议最大适用面积': 'area', '适用面积范围': 'area',
    '颗粒物CADR': 'cadr_pm', '固态污染物CADR': 'cadr_pm', '甲醛CADR': 'cadr_hcho',
    '甲醛CADR': 'cadr_hcho', '花粉CADR': 'cadr_pollen',
    '滤网类型': 'filter', '滤网': 'filter', '滤芯类型': 'filter',
    '水箱容量': 'tank', '水箱容积': 'tank', '集尘箱容量': 'dust_cup',
    '尘杯容量': 'dust_cup', '续航时间': 'runtime', '连续使用时间': 'runtime',
    '电池容量': 'battery', '电池续航': 'battery',
    '吸力': 'suction', '真空度': 'vacuum', '吸尘能力': 'suction',
    '日除湿量': 'dehumid', '除湿量': 'dehumid', '加湿量': 'humid_rate',
    '加热方式': 'heating', '加热功率': 'heat_power',
    '能效比': 'energy', 'APF': 'energy',
    '制冷剂': 'refrigerant', '压缩机制冷': 'compressor',
    '显示屏': 'display', '屏幕': 'display', '屏幕尺寸': 'size_inch',
    '分辨率': 'resolution', '刷新率': 'refresh',
    '噪音值': 'noise', '待机功率': 'standby_power',
    # —— 洗衣机（2026-10-04 补：商城「关键参数」的洗衣机字段名，
    #     按米家 21 款在售洗衣机实测归纳；脱水容量≠烘干容量，前者不入库）
    '洗涤容量': 'wash_cap', '烘干容量': 'dry_cap',
    '洗净比': 'wash_ratio',
    '最高转速': 'spin_rpm', '脱水速度': 'spin_rpm', '脱水转速': 'spin_rpm',
    '甩干脱水速度': 'spin_rpm',
    '宽*深*高': 'size', '宽×深×高': 'size', '宽X深X高': 'size',
    '除菌方式': 'sterilize', '抗菌类型': 'sterilize',
    '洗涤噪音值': 'noise', '洗涤噪音': 'noise', '脱水噪音': 'noise',
    '智能互联': 'smart', '智能功能': 'smart',
    # —— 冰箱（2026-10-04 补：按米家在售冰箱实测归纳。
    #     注意商城的 name 与 top_title 可能不同（name=「尺寸」/top_title=「产品尺寸」），
    #     脚本优先读 name，所以两套写法都要映射。
    #     「总容量」多数商品 is_page_show=False，脚本按守卫跳过；
    #     总容积由人工从官方商品名回填（商品名自带容量，非推算）。
    #     「变温室容积」有「/L」占位值（无变温室的机型），number 字段解析不出数值会被跳过）
    '尺寸': 'size',
    '总容量': 'total_vol', '总容积': 'total_vol',
    '冷藏室容积': 'fridge_vol', '冷藏容积': 'fridge_vol',
    '冷冻室容积': 'freezer_vol', '冷冻容积': 'freezer_vol',
    '变温室容积': 'var_vol', '变温容积': 'var_vol',
    '耗电量': 'power_use', '综合耗电量': 'power_use',
    '制冷方式': 'cooling',
    '净化技术': 'sterilize', '除菌技术': 'sterilize', '净味技术': 'sterilize',
    '抗菌技术': 'sterilize',
}

# 过滤明显不是「可写入库参数」的营销行
SKIP_KEYS = re.compile(r'包装清单|保修|产地|颜色|尺寸对照|安装服务|注意事项|常见问题')


def product_id_of(p):
    """从 verify_url 取 product_id。取不到返回 None。"""
    u = p.get('verify_url') or ''
    m = re.search(r'product_id=(\d+)', u)
    return m.group(1) if m else None


def norm(s):
    """商品名归一：去掉营销后缀、空白与全角符号，让「米家空气净化器 5 Pro」
    和商城文案「米家空气净化器 5 Pro 599元 起」能对上。"""
    s = re.sub(r'[\d]+\s*元.*$', '', str(s or ''))
    return re.sub(r'[\s　（）()·、,，/]', '', s)


def build_name_index():
    """从本地 search-*.json / product-*.json 建 {归一名: product_id}。

    222 款小米产品的 `verify_url` 是「查不到」，product_id 拿不到。
    先在已有的商城搜索缓存里按商品名反查，比重新跑 Playwright 枚举便宜得多；
    反查不到再考虑 `npm run mi:enumerate`。
    """
    idx = {}
    for f in glob.glob(dp('data/_cache/product-*.json')):
        try:
            d = json.load(open(f, encoding='utf-8'))
        except Exception:
            continue
        if d.get('productId') and d.get('name'):
            idx.setdefault(norm(d['name']), str(d['productId']))
    for f in glob.glob(dp('data/_cache/search-*.json')):
        try:
            d = json.load(open(f, encoding='utf-8'))
        except Exception:
            continue
        for it in (d if isinstance(d, list) else []):
            pid = it.get('productId')
            txt = it.get('text') or ''
            if pid and txt:
                idx.setdefault(norm(txt), str(pid))
    return idx


def fetch(pid, retry=2):
    """调官方 API。失败返回 None（调用方按缺失处理，不猜）。"""
    for attempt in range(retry + 1):
        try:
            r = subprocess.run(
                ['curl', '-sS', '-m', '20', '-A', UA,
                 '-H', 'Referer: https://www.mi.com/',
                 '-H', 'Accept-Language: zh-CN,zh;q=0.9',
                 API % pid],
                capture_output=True)
            raw = r.stdout
        except Exception:
            raw = b''
        if len(raw) > 200:
            break
        time.sleep(1.0 * (attempt + 1))
    if len(raw) < 200:
        return None
    try:
        return json.loads(raw.decode('utf-8', 'replace'))
    except Exception:
        return None


def num_of(v):
    m = re.search(r'(-?\d+(?:\.\d+)?)', str(v).replace(',', ''))
    return float(m.group(1)) if m else None


def is_real_value(v):
    """商城把实测值写进括号里。带（实测）的不能写进额定列。"""
    return '实测' in str(v)


def normalize_unit(raw):
    s = str(raw).strip()
    # 商城文本里混着制表符（「43\tdB」「定频电机\t\t\t」，2026-10-04 实测）
    s = re.sub(r'[\t\r\n]+', '', s)
    # 「（实测值）」这类口径标记已经体现在字段名上（cadr_pm_real），
    # 再留在值里就成了「830（实测值）m³/h」这种重复标注
    s = re.sub(r'[（(]\s*(实测值?|实测|额定值?|标称值?)\s*[)）]', '', s)
    s = re.sub(r'\s*(实测值?|实测|额定值?)\s*$', '', s)
    s = re.sub(r'^(实测值?|实测|额定值?|标称值?)\s*', '', s)
    # 商城能效栏会把「一级」录成「一级级」（2026-10-04 米家洗衣机实测 10/11 款如此）
    s = re.sub(r'^([一二三四五])级级$', r'\1级', s)
    # 尺寸常用半角 * 分隔（598*597*850mm），库内口径是 ×（598×597×850mm）
    if re.search(r'\d\s*\*\s*\d', s):
        s = s.replace('*', '×')
    for cn, en in (('立方米', 'm³'), ('毫升', 'ml'), ('升', 'L'), ('分贝', 'dB'),
                   ('瓦特', 'W'), ('瓦', 'W'), ('平方米', '㎡'), ('分钟', 'min')):
        s = s.replace(cn, en)
    return s.strip()


def param_list(params):
    """`class_parameters` 有两种形状：`{'name':'关键参数','list':[…]}` 或直接是 list。

    同一个接口两种商品返回的形状不同（实测：空气净化器 Ultra 是前者，
    部分空调是后者），所以这里两种都接。
    """
    if isinstance(params, dict):
        params = params.get('list') or []
    return [p for p in (params or []) if isinstance(p, dict)]


def pick_from_params(params, schema_keys):
    """把商城的「关键参数」翻译成本站字段。返回 {字段: (值, 来源说明)}。"""
    out = {}
    for it in param_list(params):
        if not it.get('is_page_show'):
            continue
        name = str(it.get('name') or it.get('top_title') or '').strip()
        val = str(it.get('value') or it.get('bottom_title') or '').strip()
        if not name or not val or SKIP_KEYS.search(name):
            continue
        real = is_real_value(val)
        key = KEY_MAP.get(name) or KEY_MAP.get(name.replace(' ', ''))
        if not key:
            continue
        # 带（实测值）的一律转到 _real 列；schema 里没有 _real 列就跳过，不混用
        if real:
            rk = key + '_real'
            if rk not in schema_keys:
                continue
            key = rk
        elif key + '_real' in schema_keys and ('_real' in key or real):
            pass
        if key not in schema_keys:
            continue
        val = normalize_unit(val)
        # 「/」「/级」「无」这类占位值不是数据（迷你洗衣机能效栏是「/级」、洗净比是「/」）
        if re.fullmatch(r'[-/—\s]*[级]?', val) or val in ('无', '不支持', '暂无'):
            continue
        # 复合噪音保留口径前缀（库内风格「洗涤52dB」「洗涤62/甩干72dB」），
        # 商城参数名本身写明口径，拼进值里不引入新信息
        if key == 'noise' and name in ('洗涤噪音值', '洗涤噪音') and not val.startswith('洗涤'):
            val = '洗涤' + val
        # 智能互联「支持/支持智能」→ 库内风格是写明能力（米家APP互联）
        if key == 'smart' and name == '智能互联':
            val = '支持智能互联'
        out[key] = (val, '商城关键参数「%s」' % name)
    return out


def numeric_only(keys):
    """schema 里声明为 number 的字段集合：这些要剥掉单位只留数值。"""
    return keys


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--cat', help='只处理某品类（可逗号分隔）')
    ap.add_argument('--dry', action='store_true')
    ap.add_argument('--report', action='store_true',
                    help='只列出拿不到 product_id 的小米产品，不抓取')
    ap.add_argument('--limit', type=int, default=0)
    args = ap.parse_args()

    cats = args.cat.split(',') if args.cat else None
    nameidx = build_name_index()
    targets = []
    for f in sorted(glob.glob(dp('data/*/schema.json'))):
        cid = os.path.basename(os.path.dirname(f))
        if cats and cid not in cats:
            continue
        pf = dp('data/%s/products.json' % cid)
        if not os.path.exists(pf):
            continue
        s = json.load(open(f, encoding='utf-8'))
        keys = {x['key'] for x in s['fields']}
        types = {x['key']: x['type'] for x in s['fields']}
        for p in json.load(open(pf, encoding='utf-8')):
            if p.get('brand') != '小米':
                continue
            pid = product_id_of(p)
            how = 'verify_url'
            if not pid:
                pid = nameidx.get(norm(p.get('name')))
                how = '本地商城缓存按名反查' if pid else None
            if args.report:
                targets.append((cid, p['id'], pid, how))
                continue
            if not pid:
                continue
            targets.append((cid, p['id'], pid, (keys, types, p.get('name'), how)))
    if args.report:
        miss = [t for t in targets if not t[2]]
        print('小米产品 %d 款，其中 %d 款反查不到 product_id' % (len(targets), len(miss)))
        for cid, prod, _, _ in miss[:60]:
            print('  %-18s %s' % (cid, prod))
        return
    if args.limit:
        targets = targets[:args.limit]

    viaurl = sum(1 for t in targets if t[3][3] == 'verify_url')
    print('待处理 %d 款小米产品（%d 款 product_id 来自 verify_url，'
          '%d 款来自本地商城缓存反查）' % (len(targets), viaurl, len(targets) - viaurl))
    done = [0]
    results = {}

    def job(t):
        cid, prod, pid, extra = t
        keys, types, _name, _how = extra
        d = fetch(pid)
        done[0] += 1
        if done[0] % 25 == 0:
            print('  %d/%d' % (done[0], len(targets)), flush=True)
        if not d or d.get('code') != 200:
            return (cid, prod, None)
        gl = d.get('data', {}).get('goods_list') or []
        if not gl:
            return (cid, prod, None)
        gi = gl[0].get('goods_info') or {}
        # 对不上型号的直接丢 —— 名字反查可能落到同系列另一款，宁可空着
        gname = str(gi.get('name') or '').strip()
        if gname and _name and norm(gname)[:6] != norm(_name)[:6]:
            return (cid, prod, None)
        base = next(x for x in json.load(open(dp('data/%s/products.json' % cid),
                                                 encoding='utf-8')) if x['id'] == prod)
        fills = {}
        # 价格：price 现价 -> official_price，market_price 划线价 -> ref_price
        # 只补空值不覆盖：改价是促销常态，批量订正不该顺手改价
        now = num_of(gi.get('price') or '')
        mkt = num_of(gi.get('market_price') or '')
        if (now and 49 <= now <= 999999 and 'official_price' in keys
                and blank(base.get('official_price'))):
            fills['official_price'] = (int(now), '商城 API price=%s' % gi.get('price'))
        # 划线价与现价相同时不是促销价，写进去只是重复，丢掉
        if (mkt and now and mkt != now and 'ref_price' in keys
                and blank(base.get('ref_price'))):
            fills['ref_price'] = (int(mkt), '商城 API market_price=%s' % gi.get('market_price'))
        for k, v in pick_from_params(gi.get('class_parameters'), keys).items():
            if blank(base.get(k)):
                if types.get(k) == 'number':
                    n = num_of(v[0])
                    if n is None:
                        continue
                    v = (int(n) if n == int(n) else n, v[1])
                fills.setdefault(k, v)
        return (cid, prod, fills or None)

    with ThreadPoolExecutor(max_workers=3) as ex:
        for r in ex.map(job, targets):
            if r and r[2]:
                results[(r[0], r[1])] = r[2]

    nfields = sum(len(v) for v in results.values())
    print('\n可回填：%d 款产品 / %d 个字段' % (len(results), nfields))
    print(Counter(k for v in results.values() for k in v).most_common(20))

    if args.dry:
        print('\n--dry 示例：')
        for (cid, pid), fills in list(results.items())[:10]:
            print('   %s/%s' % (cid, pid))
            for k, (v, why) in fills.items():
                print('       %s = %-18s (%s)' % (k, v, why))
        return

    n = 0
    for (cid, pid), fills in results.items():
        d = dp('data/_draft/%s' % cid)
        os.makedirs(d, exist_ok=True)
        cur = json.load(open(dp('data/%s/products.json' % cid), encoding='utf-8'))
        base = next(x for x in cur if x['id'] == pid)
        item = dict(base)
        for k, (v, _why) in fills.items():
            item[k] = v
        item['verify_date'] = D
        # 核查状态只升不降：已是「已核验（多源）」的不动（AGENTS.md 数据红线）
        if (base.get('verify_status') or '') != '已核验（多源）':
            item['verify_status'] = '已核验（官方商城）'
        item['change_log'] = (base.get('change_log', '') or '') + \
            '；%s 官方商城 API 回填：%s' % (
                D, '，'.join('%s=%s' % (k, v) for k, (v, _) in fills.items()))
        item['updated_at'] = D
        src = base.get('verify_source')
        if isinstance(src, list):
            item['verify_source'] = sorted(set(src) | {'小米商城'})
        with open('%s/%s.json' % (d, pid), 'w', encoding='utf-8', newline='\n') as fh:
            json.dump(item, fh, ensure_ascii=False, indent=2)
            fh.write('\n')
        n += 1
    print('\n已写入 data/_draft/：%d 条' % n)


if __name__ == '__main__':
    main()