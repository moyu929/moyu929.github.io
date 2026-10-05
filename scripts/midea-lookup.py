# -*- coding: utf-8 -*-
"""按型号从**美的集团官方商城**（www.midea.cn）补规格字段。

## 为什么是美的官方商城

2026-10-05 实测：美的在站内有 **95 款**（`data/*/products.json` 里 `brand == "美的"`），
是单一品牌里最多的。而 `https://www.midea.cn/` 是 **hash 路由 SPA**，
`#/detail?skuId=<数字>` 里**不含任何型号信息**，
`python scripts/probe-specs.py --url "https://www.midea.cn/#/detail?skuId=15454"`
实测「连通但不可用：只抽到 4 个规格字段」——且那 4 个还是
`家电产品` / `首页` / `自营` / `¥999.00` 这类导航噪声，不是规格表。

但把响应监听挂上去（`page.on('response', ...)`）就找到了背后的 BFF 接口：

    POST https://www.midea.cn/api/cms_bff/mtc-bff-app/m2c/querySkuDetail   型号 ← skuId
    POST https://www.midea.cn/api/cms_bff/mtc-bff-app/m2c/productSearch    型号 → skuId

两者都是**纯 HTTP 可调**（见下方「签名不需要」）。

## 签名不需要，curl 直接可调

前端每次请求都在 `headParams` 里带一个 61 字符的 `sign`，看起来像 HMAC。
**实测服务端根本不校验**（`docs/audit/美的商城接入_2026-10-05.md` 有六组对照实验）：

  | 请求体                                      | 结果                                   |
  |---------------------------------------------|----------------------------------------|
  | 原样回放浏览器抓到的 payload                  | `code=000000` ✅                        |
  | 删掉 `sign` 字段                              | `code=000000` ✅                        |
  | `sign` 改成 `"deadbeef"`                      | `code=000000` ✅                        |
  | 换当前时间戳、删掉 `sign`                      | `code=000000` ✅                        |
  | 整个 `headParams` 删掉                        | `code=000000` ✅                        |
  | `{"restParams":{"skuId":"999999999"}}`（不存在）| `mtc-bff-app-COM-100601 查询商品不存在` ✅ |

所以 `querySkuDetail` 的最小请求体就是 `{"restParams":{"skuId":"15454"}}`。

`productSearch` 唯一必须带的是 `sessionId`（任意 32 位 hex，`uuid4().hex` 即可），
少了会回 `mtc-bff-app-COM-999999 用户sessionId不能为空`。
`bizChannel` 也必须带，固定 `"productSearch"`。

## 四条硬纪律（不守会写进错数据）

1. **型号必须逐项核对，不能「搜到了就采」。** 搜索是模糊召回，排名极松：
   搜 `KJ800G-H Pro` 返回的是 `KJ1000G-T1000 Pro` / `KJ400G-RX400 Pro`；
   搜 `MRO805-3000` 返回的是 `MRC828-3000` / `MRC806C-3000`；
   搜 `MY-C5147`（电压力锅）返回的是 `MR-519WUSPZE`（冰箱）。
   本脚本只做**归一后完全相等**判定（照 `suning-lookup.py` 的 `model_matches`）。
2. **⚠️ 型号相符还可能是耗材/配件 —— 必须再加一道品类闸门。**
   这是美的特有的坑，**苏宁没有**：美的给配件沿用**主机型号**作为 `model` 字段，于是

       站内 `MRO805-3000`（净水机）→ 搜到 skuId 15561 = 「RO滤芯-5.5年 适用…」
       站内 `G3E Pro`（微波炉）    → 搜到 skuId 199950 = 「美的微波炉水箱组件…适用于G3E Pro」

   两者的 `model` 字段都与站内 `model_code` **逐字相符**，光靠型号核验会**静默写错货**。
   而且 `lv3CatName` 在这里是**继承自主机**的（滤芯的 `lv3CatName` 就写着「微波炉」），
   所以**不能只看品类字段**，必须匹配**标题**里的耗材词（见 `CONSUMABLE_RE`）。
3. **尺寸只取产品本体，排除包装；轴序 `Length×Width×Height` = 站内 `宽×深×高`。**
   `productPacking` 同时给本体与包装：`indoorBody{Length,Width,Height}` 是本体，
   `indoorPacking{Length,Width,Height}` 是**外箱**（苏宁脚本同款坑）。
   轴序**已用同型号实测钉死**：`MF-KZC6521` 接口给 `390 / 276 / 345`，
   而站内该型号既有值正是 `390×276×345mm`。重量只取 `netWeight`（净重），
   `grossWeight` 是毛重。
4. **`year`（上市时间）本接口给不了，一律不采。** 29 款命中项的
   `attributeList` 里**没有任何**含「上市 / 发布 / 年」的字段；
   只有 `createTime`，但那是**上架时间**不是上市时间 ——
   实测 8 款互不相关的商品（空调 / 饮水机 / 电饭煲 / 管线机…）
   `createTime` **同为 `2024-07-24`**，是批量导入日。
   这与 `suning-lookup.py` 丢弃日精度「上架日期」是同一类错误，故不采。
   `official_price` 同理不采：`salePrice` 是**促销后的实时成交价**，
   与站内「参考价」口径冲突（见 `docs/audit/字段覆盖率与降级清单_2026-10-04.md`）；
   只有 `originPrice`（页面上的**划线价**，页面注明「指商品专柜」）映射到 `ref_price`。

## 实测覆盖率（2026-10-05，`--cand 20`，93 款有效型号）

  精确型号命中 **31 / 93 = 33.3%**；再过耗材闸门剩 **29 / 93 = 31.2%**。
  限流：93 次 search + 1091 次 querySkuDetail，5 线程并发共 87 秒，**零失败零限流**。

命中面高度不均：空调 5/7、冰箱 1/2 尚可；而
洗碗机 0/6、除湿机 0/4、浴霸 0/4、微波炉 1/5、饮水机（管线机）3/5 全军覆没 ——
**官方商城只上架部分型号**，多数型号只在第三方渠道有。
详见 `docs/audit/美的商城接入_2026-10-05.md`。

## 用法

    python scripts/midea-lookup.py --cat washing-machine --dry
    python scripts/midea-lookup.py --cat washing-machine,air-conditioner
    python scripts/midea-lookup.py --cat kettle --limit 5 --cand 20

输出缓存：`data/_cache/midea-<品类>.json`（gitignored，人可复核）
"""
import json, os, re, sys, glob, time, uuid, argparse, subprocess
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding='utf-8')

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
D = '2026-10-05'
BLANK = ('查不到', '—', '', None, '-')

DETAIL_API = 'https://www.midea.cn/api/cms_bff/mtc-bff-app/m2c/querySkuDetail'
SEARCH_API = 'https://www.midea.cn/api/cms_bff/mtc-bff-app/m2c/productSearch'

# 纪律 2：标题里出现这些词说明是耗材/配件，型号只是「适配机型」，必须丢弃。
# ⚠️ 只能靠标题，`lv3CatName` 对耗材是继承自主机的（滤芯的品类写着「微波炉」）。
#
# ⚠️ **词表要窄，不能贪多**：`内胆` / `内锅` / `电池` / `排水` / `底座` 这些词
# 会出现在**真机**标题里（实测「美的电热水瓶 5L容量 316母婴级不锈钢内胆 0塑」
# 是一台完整电热水瓶，却因含「内胆」被误判成配件，丢掉 1 款 / 13 字段）。
# 只保留**配件目录里几乎不会缺席**的强信号：
#   「适用 / 专用 / 适配」几乎只出现在配件标题（主机标题不会写「适用于 XXX」），
#   加上零件 nouns（滤芯 / 配件 / 组件 / 说明书 / 线缆类…）。
CONSUMABLE_RE = re.compile(
    r'适用|专用|适配|滤芯|滤网|滤清|配件|耗材|零件|组件|说明书|遥控器|'
    r'排水管|阀门|阀芯|电缆|电源线|连接管|胶泥|密封|扎带|挡板|'
    r'风轮|叶轮|踏板|提篮|水箱组件')

# 包装尺寸键一律排除（纪律 3）
PACK_BODY = ('indoorBodyLength', 'indoorBodyWidth', 'indoorBodyHeight')
PACK_BOX = ('indoorPackingLength', 'indoorPackingWidth', 'indoorPackingHeight')

# 接口里占位性的枚举值。实测电热水瓶 `加热方式` 会回 `其他/other` ——
# 站内 `temp_ctrl` 的既有值是 `恒温控制` / `多档火力` / `无(仅沸腾)`，
# 把 `其他/other` 写进去等于没填还占了坑，故整类丢弃。
GARBAGE_RE = re.compile(
    r'^(其他|其它|其它/other|其他/other|other|/|无要求|无数据|待定|未知|暂无|'
    r'不支持|无\s*$|N/?A|none|null|-+)$', re.I)


def dp(rel):
    return os.path.join(ROOT, rel)


def post(url, payload, timeout=25):
    """纯 HTTP 调 BFF 接口。

    每线程一个独立临时文件：共用同一个 `--data-binary` 文件会在并发下互相覆盖，
    表现为随机的 `业务渠道bizChannel不能为空,用户sessionId不能为空` ——
    **那不是站点限流，是自造竞态**（2026-10-05 首次跑时误判成限流，
    修掉后 7 次假失败归零，命中数从 20/93 升到 31/93）。
    """
    p = dp('data/_cache/_midea_req_%s.json' % uuid.uuid4().hex[:8])
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, 'w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False)
    try:
        r = subprocess.run(['curl', '-s', '-m', str(timeout), url,
                            '-H', 'Content-Type: application/json',
                            '-H', 'Origin: https://www.midea.cn',
                            '-H', 'Referer: https://www.midea.cn/',
                            '-H', 'User-Agent: ' + UA,
                            '--data-binary', '@' + p], capture_output=True)
    finally:
        try:
            os.remove(p)
        except OSError:
            pass
    try:
        return json.loads(r.stdout.decode('utf-8', 'replace'))
    except Exception:
        return {'code': 'PARSE_FAIL', 'msg': r.stdout[:160].decode('utf-8', 'replace')}


def norm(s):
    """型号归一：去空白与全角/半角括号差异，让 `F60-33UDProS(HE)` 两边能对上。"""
    return re.sub(r'[\s　（）()]', '', str(s or '')).upper()


def search_sku_ids(model):
    """型号 → 候选 (skuId, 标题) 列表。`sessionId` 必填，否则 999999 报错。"""
    r = post(SEARCH_API, {
        'restParams': {'platformType': 1, 'sessionId': uuid.uuid4().hex,
                       'bizId': 'mtc', 'bizChannel': 'productSearch',
                       'searchKeyword': model, 'sortType': 1, 'desc': False,
                       'excludeNoInvItem': 0},
        'pagination': {'pageNo': 1, 'pageSize': 20, 'countFlag': True}})
    if r.get('code') != '000000':
        return [], r.get('code'), r.get('msg')
    out = []
    for row in (r.get('data') or []):
        if row.get('skuId'):
            out.append((str(row['skuId']), row.get('title') or ''))
    return out, '000000', ''


def fetch_detail(sku_id):
    """skuId → 商品节点。最小请求体就是 `{"restParams":{"skuId":"..."}}`。"""
    r = post(DETAIL_API, {'restParams': {'skuId': str(sku_id)}})
    if r.get('code') != '000000':
        return None, r.get('code'), r.get('msg')
    node = ((r.get('data') or {}).get('mapSkuInfo') or {}).get(str(sku_id))
    return node, '000000', ''


def model_matches(page_model, want):
    """型号是否精确匹配（纪律 1）。**不匹配就整条丢弃，不采任何字段。**

    只做归一后完全相等，不做包含、不做前缀 ——
    `KJ1000G-T1000` 是 `KJ1000G-T1000S` 的前缀，包含式匹配会错配到整个产品族；
    `KFR-72LW` 是 `KFR-72LW/N8QM1` 的前缀，同理。
    """
    if not page_model:
        return False
    return norm(page_model) == norm(want)


def is_consumable(node):
    """纪律 2：型号相符也可能是耗材/配件。"""
    title = node.get('title') or ''
    if CONSUMABLE_RE.search(title):
        return True
    cat = node.get('lv3CatName') or ''
    return bool(CONSUMABLE_RE.search(cat))


def spec_dict(node):
    """attributeList → {属性名: 值}，丢掉空值。

    非空率极不稳定（实测 0/106 到 63/106），所以「有 attributeList」不等于「有规格」。
    """
    out = {}
    for a in (node.get('attributeList') or []):
        k = str(a.get('attrName') or '').strip()
        v = str(a.get('attrVal') if a.get('attrVal') is not None else '').strip()
        if k and v and v.lower() != 'none':
            out.setdefault(k, v)
    return out


def _num(s):
    m = re.search(r'-?\d+(?:\.\d+)?', str(s or '').replace(',', ''))
    return m.group(0) if m else None


def _bare_num(s):
    """取数值并去掉尾随单位。"""
    v = _num(s)
    if v is None:
        return None
    return str(int(float(v))) if float(v) == int(float(v)) else v


def pick_size(node):
    """产品本体尺寸 `宽×深×高mm`（纪律 3）。排除包装箱尺寸。"""
    pk = node.get('productPacking') or {}
    if not all(pk.get(k) for k in PACK_BODY):
        return None, None
    w, d, h = (_bare_num(pk[k]) for k in PACK_BODY)
    if not (w and d and h):
        return None, None
    return '%s×%s×%smm' % (w, d, h), \
        'productPacking Length×Width×Height=%s/%s/%s（已排除 indoorPacking 包装尺寸）' % (w, d, h)


def pick_weight(node, cat):
    """净重。`grossWeight` 是毛重，一律不用。"""
    pk = node.get('productPacking') or {}
    v = _num(pk.get('netWeight'))
    if v is None:
        return None, None
    return '%skg' % v, 'productPacking.netWeight=%s（已排除 grossWeight 毛重）' % v


def pick_ref_price(node):
    """划线价（分 → 元）。页面注明「划线价格：指商品专柜」。

    **不采 `salePrice`**：那是促销后的实时成交价，与站内「参考价」口径冲突。
    """
    v = _num(node.get('originPrice'))
    if not v or float(v) < 100:
        return None, None
    return str(int(float(v) // 100)), 'originPrice=%s 分 → 划线价' % v


def _ac(specs):
    """空调：`attributeList` 是 57 项的完整规格表，比苏宁详情页还全。"""
    f = {}

    def g(pat):
        """返回 (属性名, 值)，取第一个命中的属性。"""
        for k, v in specs.items():
            if re.search(pat, k):
                return k, v
        return None, None

    w = _bare_num(g(r'室外机外形尺寸\(宽\)')[1])
    d = _bare_num(g(r'室外机外形尺寸\(深\)')[1])
    h = _bare_num(g(r'室外机外形尺寸\(高\)')[1])
    if w and d and h:
        f['size_outdoor'] = ('%s×%s×%smm' % (w, d, h),
                             '室外机外形尺寸 宽%s 深%s 高%s' % (w, d, h))
    _, pishu = g(r'^空调匹数$')
    if pishu:
        f['pishu'] = (pishu, '空调匹数=%s' % pishu)
    karea, area = g(r'制冷适用面积')
    if area:
        rng = re.findall(r'\d+', area)
        if len(rng) >= 2:
            f['area'] = ('%s-%s㎡' % (rng[0], rng[1]), '%s=%s' % (karea, area))
        elif len(rng) == 1:
            f['area'] = ('%s㎡' % rng[0], '%s=%s' % (karea, area))
    for field, pat in (('airflow', r'循环风量'), ('cool_power', r'额定制冷功率'),
                       ('heat_cap', r'额定制热功率')):
        k, v = g(pat)
        n = _bare_num(v)
        if n:
            f[field] = (n, '%s=%s' % (k, v))
    # 噪音：站内口径是「内34-40 / 外49dB」
    il = _bare_num(g(r'室内机低风挡噪音')[1])
    ih = _bare_num(g(r'室内机高风挡噪音')[1])
    ol = _bare_num(g(r'室外机低风挡噪音')[1])
    oh = _bare_num(g(r'室外机高风挡噪音')[1])
    seg = []
    if il and ih:
        seg.append('内%s-%s' % (il, ih))
    elif ih:
        seg.append('内%s' % ih)
    if ol and oh:
        seg.append('外%s-%s' % (ol, oh))
    elif oh:
        seg.append('外%s' % oh)
    if len(seg) == 2:
        f['noise'] = ('%s / 外%sdB' % (seg[0], oh or ol), '室内机 %s、室外机 %s'
                      % ('/'.join([x for x in (il, ih) if x]),
                         '/'.join([x for x in (ol, oh) if x])))
    elif seg:
        f['noise'] = ('%sdB' % seg[0][1:], '噪音 %s' % seg[0][1:])
    # 能效：站内口径是「一级(APF5.1)」「超一级(APF5.65)」
    _, lvl = g(r'^能效等级$')
    _, apfv = g(r'变频机能效比（APF）|能效比')
    apf = _num(apfv)
    if lvl:
        s = re.sub(r'[（(]?(19|20)\d{2}版?[）)]?', '', lvl).strip()
        if apf:
            f['energy'] = ('%s(APF%s)' % (s, apf), '能效等级=%s + APF=%s' % (lvl, apfv))
        else:
            f['energy'] = (s, '能效等级=%s' % lvl)
    _, nwv = g(r'净重量\(室外机\)')
    nw = _num(nwv)
    if nw:
        f['weight'] = ('外%skg' % nw, '净重量(室外机)=%s（接口无室内机净重）' % nwv)
    return f


# 通用映射：schema 字段 → attributeList 属性名正则（按顺序取第一个命中）
GENERIC = {
    'energy':        [r'^能效等级$'],
    'noise':         [r'^噪音值', r'^噪音\(dB\)', r'^噪音'],
    'total_vol':     [r'^总容积（L）$', r'^总容积'],
    'fridge_vol':    [r'^冷藏室容积（L）$', r'^冷藏室容积'],
    'freezer_vol':   [r'^冷冻室容积（L）$', r'^冷冻室容积'],
    'var_vol':       [r'^变温容积（L）$', r'^变温容积'],
    'power_use':     [r'^耗电量（度/天）$', r'^耗电量'],
    'cooling':       [r'^制冷方式$'],
    'door_type':     [r'^门款式$', r'^开门方式$'],
    'wash_cap':      [r'^容量（kg）$'],
    'dry_cap':       [r'^烘干容量（kg）$'],
    'wash_ratio':    [r'^洗净比$'],
    'capacity':      [r'^容积（L）$', r'^搅拌杯容积', r'^容量（L）$'],
    'power':         [r'^额定功率', r'^加热功率', r'^洗涤功率（W）$', r'^制冷功率'],
    'flux':          [r'^额定总净水量', r'^通量'],
    'sterilize':     [r'^清洁杀菌方式$'],
    'cadr_hcho':     [r'^甲醛CADR值$'],
    'cadr_pm':       [r'^颗粒物CADR值$', r'^颗粒物CADR'],
    'filter_life':   [r'^滤芯寿命（月）$'],
    'ro_life':       [r'^滤芯寿命（月）$'],
    'pure_flow':     [r'^净水流速'],
    'inner_pot':     [r'^内胆材质$'],
    'material':      [r'^内胆材质$', r'^搅拌杯材质$', r'^面板材质$', r'^侧板材质$'],
    'tank':          [r'^净水箱容量', r'^水箱容量'],
    'temp_ctrl':     [r'^控温方式$'],
}

# 站内该字段的既有值形态（`bare`=纯数字，`unit`=带单位），决定输出要不要补单位
UNIT_STYLE = {
    'air-purifier': {'power': 'unit', 'weight': 'unit'},
    'water-heater': {'capacity': 'unit', 'power': 'unit', 'energy': 'unit'},
    'water-dispenser': {'power': 'unit'},
    'kettle': {'power': 'bare'},
    'rice-cooker': {'power': 'bare'},
    'blender': {'power': 'bare'},
    'pressure-cooker': {'power': 'bare'},
    'induction-cooker': {'power': 'bare'},
    'air-fryer': {'power': 'bare'},
    'microwave': {'power': 'bare', 'energy': 'bare'},
}
POWER_UNIT = {'air-purifier': 'W', 'water-heater': 'W', 'water-dispenser': 'W'}


def extract(cat, node, keys):
    """从商品节点抽 {站内字段: 值}，并记录每个值的来源。"""
    specs = spec_dict(node)
    cand = {}
    if cat == 'air-conditioner':
        cand = _ac(specs)

    # productPacking 是全场最稳的一块（非空率远高于 attributeList）。
    # 空调的 `indoorBody*` 就是室内机，映射到 size_indoor；其余品类映射到 size。
    size_field = 'size_indoor' if cat == 'air-conditioner' else 'size'
    if size_field in keys:
        s, why = pick_size(node)
        if s:
            cand[size_field] = (s, why)
    if 'weight' in keys and 'weight' not in cand:
        w, why = pick_weight(node, cat)
        if w:
            cand['weight'] = (w, why)
    if 'ref_price' in keys:
        rp, why = pick_ref_price(node)
        if rp:
            cand['ref_price'] = (rp, why)

    for field, pats in GENERIC.items():
        if field in cand or field not in keys:
            continue
        for pat in pats:
            for k, v in specs.items():
                if re.search(pat, k):
                    cand[field] = (v, '%s=%s' % (k, v))
                    break
            if field in cand:
                break

    out = {}
    for field, (v, why) in cand.items():
        if field not in keys:
            continue
        s = str(v).strip()
        if not s or s.lower() == 'none' or GARBAGE_RE.match(s):
            continue
        if field == 'energy':
            # 站内主流写法是「1级」，接口给「一级」/「一级(2019版)」
            s = re.sub(r'^新?([一二三四五])级$', lambda m: '%d级' % '一二三四五'.index(m.group(1)) + 1, s)
        elif field == 'power':
            n = _bare_num(s)
            if n:
                style = UNIT_STYLE.get(cat, {}).get('power', 'bare')
                unit = POWER_UNIT.get(cat, 'W')
                s = '%s%s' % (n, unit) if style == 'unit' else n
        elif field in ('capacity', 'noise', 'power_use', 'wash_cap', 'dry_cap',
                       'wash_ratio', 'total_vol', 'fridge_vol', 'freezer_vol',
                       'var_vol', 'cadr_pm', 'cadr_hcho', 'flux', 'pure_flow', 'tank'):
            n = _bare_num(s)
            if n:
                s = n
        out[field] = (s, why)
    return out


def blank(v):
    return v in BLANK or (isinstance(v, (list, dict)) and not v)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--cat', required=True, help='品类，可逗号分隔')
    ap.add_argument('--dry', action='store_true')
    ap.add_argument('--limit', type=int, default=0)
    ap.add_argument('--cand', type=int, default=20,
                    help='每个型号最多核验多少个搜索候选（实测 8→20 使命中 20→31）')
    ap.add_argument('--workers', type=int, default=5)
    ap.add_argument('--brand', default='美的',
                    help='只处理该品牌（美的商城只卖自家货，查别家没有意义）')
    args = ap.parse_args()

    cats = args.cat.split(',')
    targets = []
    for cid in cats:
        pf = dp('data/%s/products.json' % cid)
        sf = dp('data/%s/schema.json' % cid)
        if not os.path.exists(pf):
            print('跳过不存在的品类 %s' % cid)
            continue
        keys = {x['key'] for x in json.load(open(sf, encoding='utf-8'))['fields']}
        # `year` / `official_price` 不在本脚本职责内（纪律 4），排除以免误判成空洞
        for k in ('year', 'official_price'):
            keys.discard(k)
        for p in json.load(open(pf, encoding='utf-8')):
            if args.brand and (p.get('brand') or '').strip() != args.brand:
                continue
            mc = p.get('model_code')
            if blank(mc):
                continue
            holes = [k for k in keys if blank(p.get(k))]
            if holes:
                targets.append((cid, p['id'], mc.strip(), holes, p))
    if args.limit:
        targets = targets[:args.limit]

    print('待处理 %d 款（%s，需 model_code 非空且目标字段为空；已排除 year / official_price）'
          % (len(targets), args.brand or '不限品牌'))
    t0 = time.time()
    done = [0]
    results, misses = {}, []

    def job(t):
        cid, pid, model, holes, p = t
        cands, code, msg = search_sku_ids(model)
        rec = {'id': pid, 'cat': cid, 'model_code': model,
               'candidates': [c[0] for c in cands], 'notes': [], 'fills': None}
        if code != '000000':
            rec['notes'].append('搜索接口报错 %s %s' % (code, msg))
        checked, rejected = 0, []
        for sku, _t in cands[:args.cand]:
            node, code, msg = fetch_detail(sku)
            if node is None:
                continue
            checked += 1
            pm = node.get('model')
            if not model_matches(pm, model):
                rejected.append('%s→%s' % (sku, pm or '未标注'))
                continue
            if is_consumable(node):
                rec['notes'].append('型号相符但是耗材/配件（%s「%s」），按纪律 2 丢弃'
                                    % (sku, (node.get('title') or '')[:26]))
                continue
            fills = extract(cid, node, set(holes))
            if not fills:
                rec['notes'].append('%s 型号相符但抽到的字段全空' % sku)
                continue
            # ⚠️ 元信息（skuId / url / 型号核对）必须与 fills 分开放 ——
            # 早先版本把 `_url` 塞进同一个 dict 再统一 `v[0]` 取值，
            # 结果字符串被当成 (值, 来源) 元组，`v[0]` 取到的是**首字符**：
            # `verify_url` 写成 "h"、`change_log` 里 skuId 写成 "5"。
            rec['sku_id'] = sku
            rec['url'] = 'https://www.midea.cn/#/detail?skuId=%s' % sku
            rec['model_checked'] = '%s == %s' % (pm, model)
            rec['fills'] = {k: v[0] for k, v in fills.items()}
            rec['notes'] += ['%s=%s（%s）' % (k, v[0], v[1]) for k, v in fills.items()]
            rec['n_attrs'] = len(spec_dict(node))
            break
        if not rec['fills']:
            rec['notes'].append('前 %d 个候选无精确型号命中（核验 %d 个）'
                                % (min(args.cand, len(cands)), checked))
            rec['rejected_sample'] = rejected[:5]
        done[0] += 1
        if done[0] % 10 == 0:
            print('  %d/%d  %.0fs' % (done[0], len(targets), time.time() - t0), flush=True)
        return (cid, pid, rec)

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        for cid, pid, rec in ex.map(job, targets):
            if rec['fills']:
                results[(cid, pid)] = rec
            else:
                misses.append(rec)

    n = sum(len(r['fills']) for r in results.values())
    print('\n可回填 %d 款 / %d 字段；未命中 %d 款（总耗时 %.0fs）'
          % (len(results), n, len(misses), time.time() - t0))
    for rec in list(results.values())[:12]:
        print('  %s/%s  %s' % (rec['cat'], rec['id'], '，'.join(rec['notes'][:4])))

    for cid in cats:
        path = dp('data/_cache/midea-%s.json' % cid)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        items = [r for r in list(results.values()) + misses if r['cat'] == cid]
        json.dump(items, open(path, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print('原始结果：data/_cache/midea-<品类>.json')

    if args.dry:
        return

    cnt = 0
    for (cid, pid), rec in results.items():
        d = dp('data/_draft/%s' % cid)
        os.makedirs(d, exist_ok=True)
        cur = json.load(open(dp('data/%s/products.json' % cid), encoding='utf-8'))
        base = next(x for x in cur if x['id'] == pid)
        item = dict(base)
        for k, v in rec['fills'].items():
            item[k] = v
        url, sku = rec['url'], rec['sku_id']
        item['verify_date'] = D
        vs = base.get('verify_source')
        item['verify_source'] = (sorted(set(vs) | {'美的官方商城'})
                                 if isinstance(vs, list) and vs else ['美的官方商城'])
        item['verify_url'] = url
        item['change_log'] = (base.get('change_log', '') or '') + \
            '；%s 美的官方商城补参（skuId=%s，型号已逐字核对）：%s' \
            % (D, sku, '，'.join(rec['notes']))
        item['updated_at'] = D
        with open('%s/%s.json' % (d, pid), 'w', encoding='utf-8', newline='\n') as fh:
            json.dump(item, fh, ensure_ascii=False, indent=2)
            fh.write('\n')
        cnt += 1
    print('\n已写入 data/_draft/：%d 条' % cnt)


if __name__ == '__main__':
    main()
