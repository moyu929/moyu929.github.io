# -*- coding: utf-8 -*-
"""按型号从**海尔官方商城**（www.haier.com）补规格字段。

## 为什么是 www.haier.com/cn/

2026-10-05 实测：海尔在站内有 **52 款**（`data/*/products.json` 里 `brand == "海尔"`），
是站内第三多的品牌。任务给的基线「官网稳定 302」**复核结论：302 不是封锁，是 CDN 下发
`C3VK` cookie 的自跳转挑战** —— 先请求一次拿 cookie，第二次同一个 URL 就 `200`：

    $ curl -s -o /dev/null -D - https://www.haier.com/
    HTTP/1.1 302 Moved Temporarily
    Location: https://www.haier.com/          ← 自跳转
    Set-Cookie: C3VK=3a1bb1; Max-Age=300; Path=/
    $ curl -s -b cookiejar https://www.haier.com/   # 200，142KB

**但下面这两个接口根本不需要 cookie**，这是本脚本的关键结论：

    GET  https://www.haier.com/igs/front/search.jhtml     型号 → 商品详情页 URL
    GET  https://www.haier.com/<品类>/<日期>_<metaId>.shtml  详情页（SSR，规格在 HTML 里）

`igs` = 海尔的智能检索网关。参数来自 `www.haier.com/search/` 页内联的 `siteConfig`：
`apiUrl='//www.haier.com'`、`productCode='3e6bff6304c547dba650d9941aa472c0'`、
`siteSmartSearchId='2'`。全部是**明文常量，无签名、无 token、无验证码**。

⚠️ `cn/images/*.js` 这类静态资源**必须**带 cookie + Referer，否则 403（CDN 规则）；
但 `.shtml` 详情页与 `igs` 接口不需要。

## 详情页是 SSR —— 不需要 Playwright

产品详情页是服务端渲染的，规格表直接躺在 HTML 里：

    <div class="tab_content_item ... js_specificationTab">
      <div class="classify_content js_classify_content sd_spec">
        <div class="params js_params">
          <div class="title"><span class="title_text">基本信息</span></div>
          <div class="table js_table">
            <div class="item_tr"><div class="item">
              <div class="name"><span class="name_text">内机尺寸(宽*深*高)mm</span></div>
              <div class="value">351*430*1846</div>
    ...

⚠️ **只解析 `js_specificationTab` 之后的那段**。`js_introduceTab`（产品介绍）里也有一组
`<span class="name">匹数</span><span class="value">3匹</span>` 的「基础属性」，
用同样的正则去扫全页会把卖点文案当规格抽出来。

## ⚠️ 室内机/室外机已经天然分列 —— 不要合并

这是大家电最容易写错的地方。海尔规格表里内外的参数是**分开的独立行**：

    内机尺寸(宽*深*高)mm = 351*430*1846      → size_indoor
    外机尺寸(宽*深*高)mm = 732*553*330       → size_outdoor
    内机噪音dB（A）      = 35               → 写进 noise 的「内」段
    外机噪音dB（A）      = 51               → 写进 noise 的「外」段

站内口径（见 `data/air-conditioner/schema.json`）本来就是 `size_indoor` / `size_outdoor`
两个独立字段，且**尺寸轴序是 `宽*深*高`**（与美的 BFF 的 `Length×Width×Height` 不同，
见 `docs/audit/美的商城接入_2026-10-05.md` 第 4 节 —— 那边要换轴，这边不用换）。

同理冰箱的 `总容积/冷藏室容积/冷冻室容积` 各自成行，直接映射到站内的
`total_vol` / `fridge_vol` / `freezer_vol`，**不做加减、不猜「冷藏冷冻是包含关系」**。

## 四条硬纪律（不守会写进错数据）

1. **型号必须逐项核对。** `igs` 搜索是模糊召回：搜 `EG100HBDC7SU1` 会把
   `EG100HBDC8SU1` / `EG100HBDC179SU1` / `EG100HBDC189SU1` / `EG100HPLUS7SU1`
   一起召回。**只看** `modelno_extra`（干净型号），归一后必须**完全相等**。
   ⚠️ 同一条结果里的 `modelNo` 字段是**高亮过的**，带 `<font color="red">` 标签，
   直接拿它比对必错；`modelno_extra` 才是干净值。
2. **⚠️ 型号相符仍可能是配件/耗材 —— 必须加标题级闸门。**
   美的给配件沿用主机型号（`docs/audit/美的商城接入_2026-10-05.md` 第 3 节），
   海尔同样有独立的配件/耗材分类。这里用**两道**闸门：
   （a）`productClassName` 必须与站内品类一致；
   （b）标题命中 `CONSUMABLE_RE` 即丢。词表取配件目录几乎不会缺席的强信号。
3. **`year`（上市时间）不采。** 搜索结果里的 `bookUpTime` / `docPubtime` 是
   **资料上架/文档发布时间**，不是上市时间（海尔页面通篇写的是「最新价格参考」，
   没有任何字段声称上市日期）。这与 `suning-lookup.py` 丢弃「上架日期」同源，故不采。
4. **`official_price` / `ref_price` 不采。** 搜索结果里那个 `price` 是**当前促销价**，
   天天变，与站内「参考价」口径冲突（同美的 `salePrice` 的坑）。

## 实测覆盖率（2026-10-05）

见 `docs/audit/大家电品牌商城接入_2026-10-05.md`。

## 用法

    python scripts/haier-lookup.py --cat washing-machine --dry
    python scripts/haier-lookup.py --cat air-conditioner,refrigerator
    python scripts/haier-lookup.py --cat dishwasher --limit 3

输出缓存：`data/_cache/haier-<品类>.json`（gitignored，人可复核）
"""
import argparse, html, json, os, re, sys, time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding='utf-8')

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
D = '2026-10-05'
BLANK = ('查不到', '—', '', None, '-')

# `siteConfig` 内联常量（见 www.haier.com/search/ 页面源码）
SEARCH_API = 'https://www.haier.com/igs/front/search.jhtml'
PRODUCT_CODE = '3e6bff6304c547dba650d9941aa472c0'
SITE_ID = '2'

# 纪律 2 的配件/耗材闸门。词表要窄 —— `内胆` / `内筒` / `门封` 会出现在整机标题里。
CONSUMABLE_RE = re.compile(
    r'专用|适用|适配|配件|耗材|零件|组件|说明书|遥控器|滤芯|滤网|滤清|'
    r'清洗|支架|底座|排水管|连接管|进水阀|电源线|电缆|密封|扎带|'
    r'毛刷|刷头|喷头|挂钩|晾衣|洗衣液|清洁剂|除垢|贴膜|保护膜|脚轮|把手|拉手|'
    r'门封条|铭牌|标签|贴纸|线卡|保险管|温控器|压缩机|电机|风扇|风轮|叶轮|托盘|提篮')

# 接口里的占位值，写进去等于没填还占了坑
GARBAGE_RE = re.compile(
    r'^(其他|其它|/|无|无要求|无数据|待定|未知|暂无|不支持|以实物为准|—|-+|N/?A|none|null)$',
    re.I)


def dp(rel):
    return os.path.join(ROOT, rel)


def curl(url, referer='https://www.haier.com/'):
    """详情页/搜索接口都是纯 HTML/JSON，不需要 cookie，也不需要浏览器。

    刻意**不**用 `-L`：CDN 的 302 自跳转挑战应当被原样暴露出来，
    加了 `-L` 会把挑战吞掉，让人误以为「通了」。
    """
    import subprocess
    r = subprocess.run(
        ['curl', '-s', '-m', '30', url,
         '-H', 'User-Agent: ' + UA,
         '-H', 'Accept: text/html,application/xhtml+xml,application/json,*/*',
         '-H', 'Accept-Language: zh-CN,zh;q=0.9',
         '-H', 'Referer: ' + referer],
        capture_output=True)
    return r.stdout.decode('utf-8', 'replace')


def norm(s):
    """型号归一：去空白与全角/半角差异。

    海尔型号里 `*` `/` `-` `.` 是**型号本体的一部分**（`KFR-72LW/E2-1Pro`），
    只去空白与括号，全角标点转半角。
    """
    s = html.unescape(str(s or '')).strip()
    s = re.sub(r'<[^>]+>', '', s)          # 搜索结果里 modelNo 带 <font> 高亮
    s = s.replace('＊', '*').replace('×', 'x').replace('Ｘ', 'X')
    s = re.sub(r'[（(]([Hh\(].*?)[）)]$', '', s)   # 去掉尾部 (HE)/(内机) 之类后缀噪声
    return re.sub(r'[\s　]', '', s).upper()


def search(model, size=20):
    """型号 → 候选结果列表。纯 GET，无签名无 cookie。"""
    u = '%s?code=%s&siteId=%s&searchWord=%s&pageNumber=1&pageSize=%d' % (
        SEARCH_API, PRODUCT_CODE, SITE_ID, quote(model), size)
    raw = curl(u, 'https://www.haier.com/search/?keyword=' + quote(model))
    try:
        d = json.loads(raw)
    except Exception:
        return [], 'PARSE_FAIL', raw[:160]
    page = (d.get('page') or {})
    out = page.get('content') or []
    if not isinstance(out, list):
        return [], 'BAD_SHAPE', str(out)[:160]
    return out, '000000', ''


def spec_pairs(page_html):
    """SSR 详情页 → [(分组名, 参数名, 值)]。只取 `js_specificationTab` 之后的部分。

    ⚠️ 纪律 2：`js_introduceTab`（产品介绍）里也有 `<span class="name">匹数</span>`，
    扫全页会把卖点文案当规格抽出来，必须从 `js_specificationTab` 截断。
    """
    # ⚠️ 不能从 `js_specificationTab` 截断：那是个 <li> tab 按钮，
    # 真正的规格表在 140KB 开外，而 `js_koubeiTab` 就在 tab 按钮旁边（相距 124 字符），
    # 按旧写法 seg 会被切成 124 字符 → 解析 0 项。
    # 正确锚点是规格表容器 `js_params`（实测位于 143530），规格区没有第二个 tab 结尾，
    # 取到 HTML 末尾即可（后面的用户口碑区不含 name_text）。
    i = page_html.find('js_params')
    if i < 0:
        return []
    seg = page_html[i:]
    out, group = [], ''
    # 顺序扫描：分组标题 与 「名: 值」对
    tok = re.compile(
        r'title_text">\s*([^<]*?)\s*</span>'
        r'|name_text">\s*([^<]*?)\s*</span>(.*?)class="value">\s*(.*?)\s*</div>',
        re.S)
    for m in tok.finditer(seg):
        if m.group(1) is not None:
            group = _clean(m.group(1))
            continue
        k = _clean(m.group(2))
        v = _clean(m.group(4))
        if k:
            out.append((group, k, v))
    return out


def _clean(s):
    s = re.sub(r'<[^>]+>', '', s or '')
    s = html.unescape(s)
    return re.sub(r'\s+', ' ', s).strip()


def model_matches(page_model, want):
    """纪律 1：归一后必须**完全相等**。不做包含/前缀匹配。

    海尔搜索会把 `EG100HBDC7SU1` 的兄弟型号
    `EG100HBDC8SU1` / `EG100HBDC179SU1` / `EG100PLUS7SU1` 一起召回，
    前缀匹配必然错配到整个产品族。
    """
    if not page_model:
        return False
    return norm(page_model) == norm(want)


def is_consumable(row, cat_cn):
    """纪律 2：两道闸门 —— 品类必须对得上，且标题不能是配件/耗材。"""
    pc = (row.get('productClassName') or row.get('bigClass') or '').strip()
    if pc and cat_cn and pc != cat_cn:
        return True, '品类不符（站内 %s vs 官方 %s）' % (cat_cn, pc)
    title = '%s %s' % (row.get('pname') or '', row.get('tag') or '')
    if CONSUMABLE_RE.search(title):
        return True, '标题含配件/耗材词：「%s」' % (row.get('pname') or '')[:30]
    return False, ''


# 站内品类 → 海尔 `productClassName`（实测值，缺省即不做品类闸门）
CAT_CN = {
    'air-conditioner': '空调', 'refrigerator': '冰箱', 'washing-machine': '洗衣机',
    'dishwasher': '洗碗机', 'tv': '电视', 'robot-vacuum': '扫地机器人',
    'air-purifier': '空气净化器', 'water-purifier': '净水器',
    'water-heater': '热水器', 'air-fryer': '电饭煲', 'dehumidifier': '除湿机',
}

# 通用映射：站内字段 → 参数名正则（**按顺序取第一个命中**）
GENERIC = {
    'energy':      [r'^能效等级$', r'能效等级'],
    'noise':       [r'^噪音', r'噪声'],
    'total_vol':   [r'总容积', r'总容量'],
    'fridge_vol':  [r'冷藏(?:室)?容积', r'冷藏'],
    'freezer_vol': [r'冷冻(?:室)?容积', r'冷冻'],
    'var_vol':     [r'变温(?:室)?容积'],
    'wash_cap':    [r'洗涤容量', r'^洗涤容量\(kg\)'],
    'dry_cap':     [r'烘干容量', r'干衣容量'],
    'wash_ratio':  [r'洗净比'],
    'spin_rpm':    [r'脱水转速'],
    'capacity':    [r'^餐具容量', r'洗涤容量', r'容量'],
    'volume':      [r'容量'],
    'power':       [r'额定功率'],
    'power_use':   [r'耗电量', r'综合耗电量'],
    'area':        [r'适用面积', r'制冷适用面积'],
    'airflow':     [r'循环风量'],
    'cool_cap':    [r'^制冷量'],
    'heat_cap':    [r'^制热量'],
    'cool_power':  [r'^制冷功率'],
    'pishu':       [r'匹数'],
    'door_type':   [r'门(?:款式|型)'],
    'cooling':     [r'制冷方式'],
    'sterilize':   [r'除菌', r'杀菌'],
    'tank':        [r'水箱'],
    'flux':        [r'通量'],
    'suction':     [r'吸力'],
    'size_inch':   [r'屏幕尺寸', r'尺寸'],
    'resolution':  [r'分辨率'],
    'refresh':     [r'刷新'],
}


def _num(s):
    m = re.search(r'-?\d+(?:\.\d+)?', str(s or '').replace(',', ''))
    return m.group(0) if m else None


def _bare(s):
    v = _num(s)
    if v is None:
        return None
    return str(int(float(v))) if float(v) == int(float(v)) else v


def _split3(v):
    """`351*430*1846` / `351×430×1846` → ('351','430','1846')。"""
    parts = [p for p in re.split(r'[*x×X/\s]+', str(v or '')) if p]
    nums = [_bare(p) for p in parts[:3]]
    if len(nums) == 3 and all(nums):
        return nums
    return None


def pick_air_conditioner(specs):
    """空调：室内机/室外机**分列**，一律不合并。"""
    f = {}
    g = specs.get

    def gg(pat):
        for k, v in specs.items():
            if re.search(pat, k):
                return v
        return None

    # ---- 尺寸：轴序就是 宽*深*高，直接映射 ----
    si, so = gg(r'内机尺寸'), gg(r'外机尺寸')
    if si:
        n = _split3(si)
        if n:
            f['size_indoor'] = ('%s×%s×%smm' % tuple(n), '内机尺寸(宽*深*高)=%s' % si)
    if so:
        n = _split3(so)
        if n:
            f['size_outdoor'] = ('%s×%s×%smm' % tuple(n), '外机尺寸(宽*深*高)=%s' % so)

    # ---- 噪音：内/外分列，拼成站内「内… / 外…dB」口径，不合并成一个数 ----
    il, ol = gg(r'内机.*(?:噪音|噪声)|(?:噪音|噪声).*内机'), gg(r'外机.*(?:噪音|噪声)|(?:噪音|噪声).*外机')
    lo, ho = gg(r'内机低(?:风|档)'), gg(r'内机高(?:风|档)')
    seg = []
    if lo or ho:
        seg.append('内%s' % '-'.join([x for x in (lo, ho) if x]))
    elif il:
        seg.append('内%s' % _bare(il))
    if ol:
        seg.append('外%s' % _bare(ol))
    if len(seg) == 2:
        f['noise'] = ('%s / 外%sdB' % (seg[0], _bare(ol)), '内机噪音 %s、外机噪音 %s' % (il, ol))
    elif seg:
        f['noise'] = ('%sdB' % seg[0][1:], '噪音 %s' % seg[0][1:])

    for field, pat in (('pishu', r'^匹数'), ('area', r'适用面积'),
                       ('cool_cap', r'^制冷量'), ('heat_cap', r'^制热量'),
                       ('cool_power', r'^制冷功率'), ('airflow', r'循环风量')):
        v = gg(pat)
        if v:
            f[field] = (v, '%s=%s' % (pat, v))

    lvl = gg(r'^能效等级')
    if lvl:
        s = re.sub(r'^新?([一二三四五])级$', lambda m: '%d级' % ('一二三四五'.index(m.group(1)) + 1), lvl.strip())
        f['energy'] = (s, '能效等级=%s' % lvl)

    # 重量：内/外分列时只写外机（站内 weight 是整机口径，写室内机会与既有值冲突）
    wo = gg(r'外机.*(?:质量|重量)')
    if wo:
        f['weight'] = ('外%skg' % _bare(wo), '外机质量=%s（接口无整机净重，故标「外」）' % wo)
    return f


def extract(cat, specs, holes=(), _cur=None):
    """参数表 → {站内字段: (值, 来源)}。只返回有值且不在垃圾表里的。"""
    cand = {}
    if cat == 'air-conditioner':
        cand = pick_air_conditioner(specs)
    else:
        for field, pats in GENERIC.items():
            for pat in pats:
                for k, v in specs.items():
                    if re.search(pat, k) and v:
                        cand[field] = (v, '%s=%s' % (k, v))
                        break
                if field in cand:
                    break
        # 尺寸：整机的「外形尺寸/产品尺寸/尺寸(宽*深*高)」→ size（排除内外机）
        if 'size' not in cand:
            for k, v in specs.items():
                if re.search(r'(外形尺寸|产品尺寸|整机尺寸|尺寸[（(]宽)', k) and '机尺寸' not in k:
                    n = _split3(v)
                    if n:
                        cand['size'] = ('%s×%s×%smm' % tuple(n), '%s=%s' % (k, v))
                    break

    out = {}
    for field, (v, why) in cand.items():
        s = str(v).strip()
        if not s or s.lower() == 'none' or GARBAGE_RE.match(s):
            continue
        # 只补空字段：库内已有值一律不碰（SKILL.md 第 8 条）
        #
        # ⚠️ 这里**不能**写成 `if field in holes and not blank(...)`：
        # holes 本身就是按 blank() 筛出来的，「field in holes」为真时 blank 必为真，
        # 那个条件恒为假，守卫等于不存在。实测该 bug 让 84 个已有值被覆盖。
        if _cur is not None and not blank(_cur.get(field)):
            continue
        out[field] = (s, why)
    return out


def blank(v):
    return v in BLANK or (isinstance(v, (list, dict)) and not v)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--cat', required=True, help='品类，可逗号分隔')
    ap.add_argument('--dry', action='store_true')
    ap.add_argument('--limit', type=int, default=0)
    ap.add_argument('--cand', type=int, default=20, help='每个型号最多核验多少个搜索候选')
    ap.add_argument('--workers', type=int, default=4)
    ap.add_argument('--brand', default='海尔')
    args = ap.parse_args()

    cats = args.cat.split(',')
    targets = []
    for cid in cats:
        pf, sf = dp('data/%s/products.json' % cid), dp('data/%s/schema.json' % cid)
        if not os.path.exists(pf):
            print('跳过不存在的品类 %s' % cid)
            continue
        keys = {x['key'] for x in json.load(open(sf, encoding='utf-8'))['fields']}
        keys.discard('year')          # 纪律 3
        keys.discard('official_price')  # 纪律 4
        keys.discard('ref_price')       # 纪律 4
        for p in json.load(open(pf, encoding='utf-8')):
            if args.brand and (p.get('brand') or '').strip() != args.brand:
                continue
            mc = p.get('model_code')
            if blank(mc) or mc.strip() == '查不到':
                continue
            holes = [k for k in keys if blank(p.get(k))]
            if holes:
                targets.append((cid, p['id'], mc.strip(), holes))
    if args.limit:
        targets = targets[:args.limit]

    print('待处理 %d 款（%s；已排除 year / official_price / ref_price）' % (len(targets), args.brand))
    t0 = time.time()
    done = [0]
    results, misses = {}, []
    _cur_holder = {pid: next(x for x in json.load(open(dp('data/%s/products.json' % cid), encoding='utf-8')) if x['id'] == pid) for cid, pid, _, _ in targets}

    def job(t):
        cid, pid, model, holes = t
        cands, code, msg = search(model, args.cand)
        rec = {'id': pid, 'cat': cid, 'model_code': model,
               'candidates': len(cands), 'notes': [], 'fills': None}
        if code != '000000':
            rec['notes'].append('搜索接口异常 %s %s' % (code, msg))
        checked, rejected = 0, []
        for row in cands[:args.cand]:
            pm = row.get('modelno_extra')       # ⚠️ 不是 modelNo（那个带 <font> 高亮）
            checked += 1
            if not model_matches(pm, model):
                rejected.append('%s' % (pm or row.get('pname') or '未标注'))
                continue
            bad, why = is_consumable(row, CAT_CN.get(cid))
            if bad:
                rec['notes'].append('型号相符但被配件/品类闸门拦下：%s' % why)
                continue
            url = row.get('url') or row.get('docPuburl') or row.get('docPubtime')
            if not url:
                rec['notes'].append('%s 型号相符但搜索结果没给详情页 URL' % pm)
                continue
            page = curl(('https:' + url) if url.startswith('//') else url)
            pairs = spec_pairs(page)
            specs = {k: v for _, k, v in pairs if v}
            fills = extract(cid, specs, holes, _cur_holder.get(pid))
            if not fills:
                rec['notes'].append('%s 型号相符但规格表抽不出字段（共解析 %d 项）' % (pm, len(specs)))
                continue
            rec['url'] = ('https:' + url) if url.startswith('//') else url
            rec['model_checked'] = '%s == %s' % (pm, model)
            rec['n_attrs'] = len(specs)
            rec['groups'] = sorted({g for g, _, _ in pairs if g})
            rec['all_specs'] = specs        # 留档，便于人工复核分列是否用对
            rec['fills'] = {k: v[0] for k, v in fills.items()}
            rec['notes'] += ['%s=%s（%s）' % (k, v[0], v[1]) for k, v in fills.items()]
            break
        if not rec['fills']:
            rec['notes'].append('前 %d 个候选无精确型号命中（核验 %d 个）'
                                % (min(args.cand, len(cands)), checked))
            rec['rejected_sample'] = rejected[:5]
        done[0] += 1
        if done[0] % 5 == 0:
            print('  %d/%d  %.0fs' % (done[0], len(targets), time.time() - t0), flush=True)
        return (cid, pid, rec)

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        for _cid, _pid, rec in ex.map(job, targets):
            if rec['fills']:
                results[(_cid, _pid)] = rec
            else:
                misses.append(rec)

    hits = list(results.values())
    n = sum(len(r['fills']) for r in hits)
    print('\n可回填 %d 款 / %d 字段；未命中 %d 款（总耗时 %.0fs）'
          % (len(hits), n, len(misses), time.time() - t0))
    for rec in hits[:12]:
        print('  %s/%s  %s' % (rec['cat'], rec['id'], '，'.join(rec['notes'][:4])))

    for cid in cats:
        items = [r for r in hits + misses if r['cat'] == cid]
        if not items:
            continue
        path = dp('data/_cache/haier-%s.json' % cid)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        json.dump(items, open(path, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print('原始结果：data/_cache/haier-<品类>.json')
    if args.dry:
        return

    cnt = 0
    for rec in hits:
        cid, pid = rec['cat'], rec['id']
        d = dp('data/_draft/%s' % cid)
        os.makedirs(d, exist_ok=True)
        base = next(x for x in json.load(open(dp('data/%s/products.json' % cid), encoding='utf-8'))
                    if x['id'] == pid)
        item = dict(base)
        item.update(rec['fills'])
        item['verify_date'] = D
        vs = base.get('verify_source')
        item['verify_source'] = (sorted(set(vs) | {'海尔官方商城'})
                                 if isinstance(vs, list) and vs else ['海尔官方商城'])
        item['verify_url'] = rec['url']
        item['change_log'] = (base.get('change_log', '') or '') + \
            '；%s 海尔官网补参（型号已逐字核对 %s）：%s' \
            % (D, rec.get('model_checked', ''), '，'.join(rec['notes']))
        item['updated_at'] = D
        with open('%s/%s.json' % (d, pid), 'w', encoding='utf-8', newline='\n') as fh:
            json.dump(item, fh, ensure_ascii=False, indent=2)
            fh.write('\n')
        cnt += 1
    print('\n已写入 data/_draft/：%d 条' % cnt)


if __name__ == '__main__':
    main()