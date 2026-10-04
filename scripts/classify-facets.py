# -*- coding: utf-8 -*-
"""给非小米品牌产品按 facet 分类。

依据优先级：pconline 缓存的「产品类型/安装方式/加热方式」字段 > 国标型号正则 > 参数阈值 > 价格分档。
每个赋值都写进 change_log 便于复核；没有依据的保持「未归类」，不猜。

用法：python scripts/classify-facets.py           # 只处理尚未归类的非小米品牌产品
"""
import json, glob, os, re, sys, collections

# 仓库根目录：按脚本自身位置解析，不依赖 cwd（见方案 P0-1）
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 库文件的写入统一走 lib/library_io.py：规范序列化 + 写前指纹守卫（方案 P1-1）
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'lib'))
import library_io  # noqa: E402


def dp(rel):
    """仓库相对路径 → 绝对路径"""
    return os.path.join(ROOT, rel)


sys.stdout.reconfigure(encoding='utf-8')
D = '2026-10-01'

# 本站品类 -> pconline 缓存目录名
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

# 第三方「产品类型」取值 -> 本站 facet 值
TYPE_KW = {
    'fan': [('空气循环扇', '循环扇'), ('塔扇', '塔扇'), ('落地扇', '落地扇'),
            ('吊扇', '台扇/桌面'), ('转页扇', '台扇/桌面'), ('壁扇', '台扇/桌面'),
            ('台式', '台扇/桌面'), ('桌面', '台扇/桌面'), ('台扇', '台扇/桌面'),
            ('无叶', '无叶风扇'), ('冷风扇', '冷风扇/两季扇'), ('空调扇', '冷风扇/两季扇'),
            ('风扇灯', '风扇灯')],
    'oven': [('蒸烤一体', '微烤一体'), ('微波烤一体', '微烤一体'), ('微波炉', '微波炉'),
             ('光波炉', '微波炉'), ('电烤箱', '电烤箱'), ('烤箱', '电烤箱')],
    'juicer': [('破壁机', '破壁机'), ('豆浆机', '豆浆机'), ('料理机', '破壁机'),
               ('榨汁杯', '榨汁杯'), ('榨汁机', '榨汁杯'), ('原汁机', '榨汁杯')],
    'xiwanji': [('水槽', '水槽式'), ('洗消', '洗消一体机'), ('独嵌', '独嵌两用'),
                ('嵌入', '嵌入式'), ('台式', '台式')],
    # 第三方写的常���「意大利式」而不是「意式」，两种写法都要匹配，
    # 否则关键词落在字面上却匹配不到（'意式' not in '意大利式'）
    'coffee': [('胶囊', '胶囊'), ('意式', '半自动'), ('意大利式', '半自动'),
               ('半自动', '半自动'), ('全自动', '半自动'), ('美式', '滴滤'),
               ('滴滤', '滴滤'), ('手冲', '滴滤')],
    'water_dispenser': [('管线', '管线'), ('茶吧', '茶吧机'), ('冷热', '冷热'),
                        ('直饮', '即热'), ('智能', '即热'), ('温热', '即热'), ('单热', '即热')],
    # 「欧式快热炉」是第三方对油汀（电热油汀）的常见叫法，与「油汀」同义
    'heater': [('踢脚', '踢脚线'), ('油汀', '油汀'), ('欧式快热炉', '油汀'),
               ('电热毯', '电热毯'), ('暖风机', '暖风机'), ('小太阳', '暖风机'),
               ('取暖器', '暖风机'), ('电暖炉', '暖风机'), ('对流', '暖风机')],
    'washer': [('干衣', '洗烘套装'), ('烘洗', '滚筒洗烘一体'), ('洗烘', '滚筒洗烘一体'),
               ('滚筒', '滚筒洗烘一体'), ('波轮', '波轮')],
}


def load_cache(pc):
    """读该 pconline 目录下的全部品牌缓存（含 fetch-missing-specs.py 补抓的 -extra）。

    同一 id 多次出现时合并字段，不覆盖 —— 先到的是原抓取（字段多），
    后到的是补抓（可能补上原抓没拿到的分类字段）。
    """
    out = {}
    for f in sorted(glob.glob(dp('data/_cache/brand-%s-*.json' % pc))):
        try:
            d = json.load(open(f, encoding='utf-8'))
        except Exception:
            continue
        for it in d:
            k = str(it.get('id') or '')
            if not k:
                continue
            merged = dict(out.get(k) or {})
            for sk, sv in (it.get('specs') or {}).items():
                merged.setdefault(sk, sv)
            out[k] = merged
    return out


def load_evidence():
    """读 data/_cache/facet-evidence/evidence.json。

    这是为「仍未归类的非小米品牌产品」补抓的证据：逐条含太平洋规格与 ZOL 参数页。
    与 load_cache 的字段名不同源，这里统一摊平成 {品类: {产品id: {字段: 值}}}，
    字段名加前缀区分来源（p_ = pconline，z_ = zol），供 by_kw 一起匹配。
    """
    out = {}
    path = dp('data/_cache/facet-evidence/evidence.json')
    try:
        items = json.load(open(path, encoding='utf-8'))
    except Exception:
        return out
    for it in items:
        cat, pid = it.get('cat'), it.get('id')
        if not cat or not pid:
            continue
        flat = {}
        for k, v in (it.get('pconline') or {}).items():
            flat['p_' + k] = v
        for k, v in ((it.get('zol') or {}).get('specs') or {}).items():
            flat['z_' + k] = v
        if flat:
            out.setdefault(cat, {})[pid] = flat
    return out


EVIDENCE = load_evidence()


def num(v):
    if v is None:
        return None
    m = re.search(r'(\d+(?:\.\d+)?)', str(v).replace(',', ''))
    return float(m.group(1)) if m else None


def field(sp, *names):
    """从规格 dict 取字段值，兼容 evidence 的来源前缀（p_ 太平洋 / z_ ZOL）。

    所有规则都用它取值，别直接用 dict.get —— evidence 里的键是 p_类别、
    p_产品容量 这样带前缀的，直取会全部落空。
    """
    for n in names:
        if n in sp and sp[n] not in (None, ''):
            return sp[n]
        for pre in ('p_', 'z_'):
            if pre + n in sp and sp[pre + n] not in (None, ''):
                return sp[pre + n]
    return None


def pick_id(url):
    m = re.search(r'/([0-9]+)_detail\.html', url or '')
    return m.group(1) if m else None


def by_kw(pc, sp, fields, why_prefix):
    """按第三方分类字段取值映射到本站 facet 值。

    evidence 里的字段带来源前缀（p_ 太平洋 / z_ ZOL），字段名与原缓存不完全一致，
    所以先按原名取，取不到再回退到前缀名。
    """
    def get(f):
        if f in sp:
            return str(sp[f])
        for pre in ('p_', 'z_'):
            if pre + f in sp:
                return str(sp[pre + f])
        return ''
    blob = ''.join(get(f) for f in fields)
    if not blob.strip():
        return None
    for kw, v in TYPE_KW.get(pc, []):
        if kw in blob:
            return v, '%s=%s' % (why_prefix, blob)
    return None


def by_price(p, tiers, why):
    price = p.get('ref_price')
    if not isinstance(price, (int, float)) or price <= 0:
        return None
    for lo, v in tiers:
        if price >= lo:
            return v, '参考价 %s 元（%s）' % (price, why)
    return None


# ---------------- 各品类判定规则 ----------------

def rule_aircon(p, sp):
    n, t = p['name'], str(field(sp, '空调类型') or '')
    if re.search(r'风管|天花|中央|多联|嵌入', n + t):
        return '中央空调', '名称/空调类型含风管/中央/嵌入'
    if '立式' in t or re.search(r'72\s*L?W', n):
        return '柜机', '空调类型=%s 或型号含 72LW' % t
    if '挂式' in t or re.search(r'(26|35|50|72)\s*G?W', n):
        return '挂机', '空调类型=%s 或型号含 GW' % t
    return None


def rule_fan(p, sp):
    got = by_kw('fan', sp, ['产品类型'], '第三方产品类型')
    if got:
        return got
    t = str(field(sp, '产品类型') or '')
    if 'USB' in t or 'USB' in p['name']:
        return '台扇/桌面', '第三方产品类型=%s（USB 小风扇属桌面类）' % t
    return None


def rule_microwave(p, sp):
    got = by_kw('oven', sp, ['产品类型'], '第三方产品类型')
    if got:
        return got
    if re.search(r'蒸烤|微烤', p['name']):
        return '微烤一体', '名称含蒸烤/微烤'
    return None


def rule_dishwasher(p, sp):
    got = by_kw('xiwanji', sp, ['产品类型', '安装方式'], '第三方类型/安装方式')
    if got:
        return got
    # 西门子/博世洗碗机的型号段位本身就编码了安装方式：
    # SN = 全嵌入式，SJ = 半嵌入（下拉式），SK = 台下式。
    # 型号前面通常带中文品牌名，所以不锚定行首，取型号主体里的段位码。
    m = re.search(r'(SN|SJ|SK)(\d{2})', p['name'])
    if m:
        seg = {'SN': '嵌入式', 'SJ': '嵌入式', 'SK': '台式'}[m.group(1)]
        return seg, '型号段位 %s%s（西门子/博世洗碗机型号编码惯例）' % (m.group(1), m.group(2))
    # 松下 NP-/NW- 系列为嵌入式（窄型）洗碗机
    if re.search(r'\bNP-|\bNW-', p['name']):
        return '嵌入式', '型号段位 NP/NW（松下嵌入式洗碗机系列）'
    return None


def rule_waterheater(p, sp):
    n = p['name']
    if re.search(r'JSQ|燃气|煤气', n):
        return '燃气', '名称含 JSQ 或燃气（JSQ 为燃气热水器国标前缀）'
    if re.search(r'\bES|电热', n):
        return '电热', '名称含 ES 或电热（ES 为电热水器国标前缀）'
    t = str(field(sp, '产品类型') or '')
    if re.search(r'即热|速热|储水', t):
        return '电热', '第三方产品类型=%s' % t
    return None


def rule_pressurecooker(p, sp):
    v = num(field(sp, 'capacity', '产品容量'))
    if v is None:
        return None
    return ('大容量' if v >= 5 else '小容量'), '标称容量 %sL' % v


def rule_dehumid(p, sp):
    v = num(field(sp, 'dehumid', '日除湿量'))
    if v is None:
        return None
    if v >= 40:
        return '大除湿量(40L+)', '日除湿量 %sL/天' % v
    if v >= 20:
        return '中除湿量(20-30L)', '日除湿量 %sL/天' % v
    return '小除湿量(≤20L)', '日除湿量 %sL/天' % v


def rule_induction(p, sp):
    n = p['name'] + str(field(sp, '其它性能') or '') + str(field(sp, '主要特点') or '')
    if re.search(r'超薄|纤薄', n):
        return '超薄', '名称或特点含超薄'
    if re.search(r'青春|学生', n):
        return '青春版', '名称或特点含青春'
    return '常规', '无超薄或青春特征'


def rule_blender(p, sp):
    return by_kw('juicer', sp, ['产品类型'], '第三方产品类型')


def rule_kettle(p, sp):
    n = p['name']
    if '养生' in n:
        return '养生壶', '名称含养生'
    v = num(field(sp, 'capacity', '产品容量'))
    if v is not None:
        if v >= 3:
            return '养生壶', '容量 %sL（≥3L 属养生壶区间）' % v
        if v < 1.2:
            return '电煮壶', '容量 %sL（<1.2L）' % v
        return '电水壶', '容量 %sL' % v
    return None


def rule_coffee(p, sp):
    got = by_kw('coffee', sp, ['类别', '使用方式'], '第三方类别/使用方式')
    if got:
        return got
    if re.search(r'便携', p['name']):
        return '便携', '名称含便携'
    return None


def rule_airfryer(p, sp):
    t = str(field(sp, '加热方式') or '')
    if re.search(r'蒸汽|烤', t + p['name']):
        return '蒸烤一体', '第三方加热方式=%s' % t
    if '可视' in p['name']:
        return '可视炸锅', '名称含可视'
    return '经典炸锅', '无蒸烤或可视特征'


def rule_ricecooker(p, sp):
    n = p['name']
    t = str(field(sp, '加热方式') or '')
    if 'IH' in n or 'IH' in t:
        if re.search(r'压力', n + t):
            return '压力IH', '名称/加热方式含压力+IH'
        return 'IH电磁', '名称/加热方式含 IH'
    return '底盘加热', '第三方加热方式=%s' % t


def rule_washer(p, sp):
    got = by_kw('washer', sp, ['产品类型'], '第三方产品类型')
    if got:
        return got
    n = p['name']
    if re.search(r'三筒|双筒|迷你', n):
        return '多筒/迷你', '名称含三筒/双筒/迷你'
    if re.search(r'波轮', n):
        return '波轮', '名称含波轮'
    return None


def rule_robotvac(p, sp):
    n = p['name'] + str(field(sp, '集尘方式') or '')
    if '上下水' in n:
        return '全能上下水', '名称含上下水'
    if re.search(r'基站|自清洁|全能', n) or field(sp, '集尘方式'):
        return '全能基站', '名称或集尘方式含基站'
    return None


def rule_vacuum(p, sp):
    return by_price(p, [(4000, '旗舰'), (1500, '主流'), (1, '入门')], '分档')


def rule_humidifier(p, sp):
    n = p['name']
    if re.search(r'无雾|蒸发', n):
        return '无雾冷蒸发', '名称含无雾或蒸发'
    if re.search(r'超声波|雾化', n):
        return '超声波', '名称含超声波或雾化'
    return None


def rule_waterpur(p, sp):
    t = str(field(sp, '安装方式') or '')
    # 安装方式是非小米品牌唯一稳定给出的分类维度（第三方普遍不标双出水/单出水）
    if '厨下' in t:
        return '厨下式', '第三方安装方式=%s' % t
    if '壁挂' in t:
        return '龙头/前置', '第三方安装方式=%s' % t
    n = p['name']
    if re.search(r'龙头|前置', t + n):
        return '龙头/前置', '名称或安装方式含龙头/前置'
    if re.search(r'全屋|中央', t):
        return '全屋/中央', '第三方安装方式=%s' % t
    if re.search(r'双出水|双水', n):
        return '双出水', '名称含双出水'
    if re.search(r'即热|加热', n):
        return '即热', '名称含即热'
    if re.search(r'单出水|单水', n):
        return '单出水', '名称含单出水'
    if '台式' in t:
        return '单出水', '第三方安装方式=台式'
    return None


def rule_fridge(p, sp):
    n = p['name']
    for pat, v, why in [(r'法式|多门', '法式多门', '法式/多门'), (r'十字', '十字门', '十字'),
                        (r'对开', '对开门', '对开'), (r'三门', '三门', '三门'),
                        (r'两门|单门', '两门', '两门/单门')]:
        if re.search(pat, n):
            return v, '名称含' + why
    return None


def rule_projector(p, sp):
    return by_price(p, [(8000, '旗舰家用'), (3000, '主流家用'), (1, '便携入门')], '分档')


def rule_heater(p, sp):
    n, t = p['name'], str(field(sp, '加热方式') or '')
    if '踢脚' in n:
        return '踢脚线', '名称含踢脚线'
    if re.search(r'油汀|油暖', n + t):
        return '油汀', '名称/加热方式含油汀'
    if '电热毯' in n:
        return '电热毯', '名称含电热毯'
    if re.search(r'暖风机|小太阳|取暖器', n):
        return '暖风机', '名称含暖风机或取暖器'
    return None


def rule_waterdisp(p, sp):
    return by_kw('water_dispenser', sp, ['产品类型'], '第三方产品类型')


def rule_waterheater2(p, sp):
    """补充：林内 RUS 为燃气热水器国标前缀；ES 为电热。"""
    n = p['name']
    if re.search(r'RUS|JSQ', n):
        return '燃气', '型号含 RUS/JSQ（燃气热水器国标前缀）'
    t = str(field(sp, '产品类型') or '')
    if re.search(r'储水|即热|速热', t):
        return '电热', '第三方产品类型=%s' % t
    return rule_waterheater(p, sp)


def rule_heater2(p, sp):
    """补充：第三方「产品类型」优先（踢脚线取暖器/电油汀等），
    再按「加热方式/摆放方式」补——油汀类普遍标「铝片散热式」。"""
    got = by_kw('heater', sp, ['产品类型'], '第三方产品类型')
    if got:
        return got
    how = str(field(sp, '加热方式') or '')
    if '铝片' in how or '导热' in how:
        return '油汀', '第三方加热方式=%s（铝片散热为油汀典型结构）' % how
    place = str(field(sp, '摆放方式') or field(sp, '使用方式') or '')
    if '立式' in place or '落地' in place:
        return '暖风机', '第三方摆放/使用方式=%s' % place
    return rule_heater(p, sp)


def rule_fridge2(p, sp):
    """补充：海尔 LC 系列（单冷藏室占比高、按容积判门型）。"""
    got = rule_fridge(p, sp)
    if got:
        return got
    n = p['name']
    total = num(p.get('total_vol'))
    fridge = num(p.get('fridge_vol'))
    if 'LC-' in n and total:
        if fridge and fridge / total >= 0.75:
            return '两门', '型号 LC 系列且冷藏占比 %.0f%%（≥75%%，冷冻室小）' % (fridge / total * 100)
        return '三门', '型号 LC 系列且总容积 %sL' % total
    return None


def rule_humidifier2(p, sp):
    """补充：按尺寸与加湿量区分——超声波机型普遍带独立水箱且功率低。"""
    got = rule_humidifier(p, sp)
    if got:
        return got
    rate = num(p.get('humid_rate'))
    power = num(p.get('power'))
    size = str(p.get('size') or '')
    if rate and size and power:
        if rate >= 600:
            return '无雾冷蒸发', '加湿量 %s ml/h（≥600 且带水箱，属蒸发式）' % rate
        return '超声波', '加湿量 %s ml/h、功率 %sW、带水箱（超声波机型特征）' % (rate, power)
    return None


def rule_kettle2(p, sp):
    """补充：无名称特征时按容量分档。"""
    v = num(field(sp, 'capacity', '产品容量'))
    if v is None:
        return None
    if v >= 3:
        return '养生壶', '容量 %sL（≥3L 属养生壶区间）' % v
    if v < 1.2:
        return '电煮壶', '容量 %sL（<1.2L）' % v
    return '电水壶', '容量 %sL' % v


def rule_microwave2(p, sp):
    """补充：无分类字段时按容量与形态推断（≥40L 多为嵌入式蒸烤一体）。"""
    got = rule_microwave(p, sp)
    if got:
        return got
    size = str(p.get('size') or '')
    n = p['name']
    if '嵌入' in n or re.search(r'59\d\s*x\s*59\d', size):
        return '微烤一体', '尺寸 %s 或名称含嵌入（嵌入式一体机）' % (size or '查不到')
    if re.search(r'烤', n):
        return '电烤箱', '名称含烤'
    return None


def rule_bathheater(p, sp):
    """浴霸副分组：按取暖功率档位。非小米品牌的第三方规格普遍不给控制方式，
    但灯暖/风暖/额定功率是稳定字段，也是浴霸的核心选购维度。"""
    for f in ('heat_power', '额定功率', '灯暖功率', '风暖功率', '取暖功率', '总功率'):
        v = num(field(p, f))
        if v is None:
            v = num(field(sp, f))
        if v is None:
            continue
        if v >= 2800:
            return '高功率(≥2800W)', '%s=%s' % (f, v)
        if v >= 2400:
            return '中功率(2400-2799W)', '%s=%s' % (f, v)
        return '低功率(<2400W)', '%s=%s' % (f, v)
    c = str(p.get('control') or '')
    if '触摸智能' in c or '智能控制' in c:
        return '触摸智能控制', '控制方式=%s' % c
    if re.search(r'APP|语音|遥控.*触控|多功能', c):
        return 'APP/语音/遥控多模', '控制方式=%s' % c
    if '触控' in c:
        return '触控式', '控制方式=%s' % c
    if '遥控' in c:
        return '遥控式', '控制方式=%s' % c
    return None


def rule_tv(p, sp):
    """电视副分组改为「尺寸段」——原 series 是小米 S 系列命名，其他品牌无法归入。"""
    v = num(p.get('size_inch'))
    if v is None:
        return None
    if v >= 98:
        return '百吋巨幕(≥98")', '尺寸 %s 英寸' % v
    if v >= 85:
        return '超大(85-97")', '尺寸 %s 英寸' % v
    if v >= 75:
        return '大(75-84")', '尺寸 %s 英寸' % v
    if v >= 65:
        return '主流(65-74")', '尺寸 %s 英寸' % v
    return '小(≤64")', '尺寸 %s 英寸' % v


def rule_floorwasher(p, sp):
    """洗地机副分组改为「清水箱容量」——原 series 是米家代际，其他品牌无法归入。"""
    v = num(field(sp, 'clean_tank', '净水箱容量'))
    if v is None:
        return None
    if v >= 1000:
        return '大容量(≥1000ml)', '清水箱 %sml' % v
    if v >= 800:
        return '中容量(800-999ml)', '清水箱 %sml' % v
    return '小容量(<800ml)', '清水箱 %sml' % v


def rule_airpur(p, sp):
    cadr = num(p.get('cadr_pm'))
    if cadr is not None:
        for lo, v in [(800, '旗舰'), (500, '高端'), (300, '中端'), (1, '入门')]:
            if cadr >= lo:
                return v, '颗粒物 CADR %s m³/h' % cadr
    return by_price(p, [(5000, '旗舰'), (2500, '高端'), (1200, '中端'), (1, '入门')], '分档')


RULES = {
    'air-conditioner': rule_aircon, 'air-fryer': rule_airfryer, 'air-purifier': rule_airpur,
    'blender': rule_blender, 'coffee-machine': rule_coffee, 'dehumidifier': rule_dehumid,
    'dishwasher': rule_dishwasher, 'fan': rule_fan, 'heater': rule_heater2,
    'humidifier': rule_humidifier2, 'induction-cooker': rule_induction, 'kettle': rule_kettle,
    'microwave': rule_microwave2, 'pressure-cooker': rule_pressurecooker,
    'projector': rule_projector, 'refrigerator': rule_fridge2, 'rice-cooker': rule_ricecooker,
    'robot-vacuum': rule_robotvac, 'vacuum': rule_vacuum, 'washing-machine': rule_washer,
    'water-dispenser': rule_waterdisp, 'water-heater': rule_waterheater2,
    'water-purifier': rule_waterpur,
    'bath-heater': rule_bathheater, 'tv': rule_tv, 'floor-washer': rule_floorwasher,
}


def main():
    unresolved = collections.defaultdict(list)
    done = 0
    for cid, rule in sorted(RULES.items()):
        sp_path = dp('data/%s/schema.json' % cid)
        if not os.path.exists(sp_path):
            continue
        s = json.load(open(sp_path, encoding='utf-8'))
        facets = s.get('facets') or []
        if not facets:
            continue
        fk = facets[0]['key']
        valid = set(facets[0]['order'])
        cache = load_cache(CAT2PC.get(cid, cid))
        pp = dp('data/%s/products.json' % cid)
        lib = library_io.load(pp)
        ps = lib['products']
        changed = 0
        for p in ps:
            if p.get('brand') == '小米':
                continue
            if p.get(fk) not in (None, '未归类', '查不到'):
                continue                      # 已归类，不重复处理
            sp = cache.get(pick_id(p.get('verify_url')), {})
            # 补抓的 evidence 覆盖同名缓存字段（来源更新、字段更准）
            ev = EVIDENCE.get(cid, {}).get(p.get('id'), {})
            if ev:
                merged = dict(sp)
                merged.update({k: v for k, v in ev.items() if v not in (None, '')})
                sp = merged
            got = rule(p, sp)
            if got and got[0] in valid:
                val, why = got
                p[fk] = val
                p['change_log'] = (p.get('change_log', '') or '') + \
                    '；%s 副分组归类：%s（依据：%s）' % (D, val, why)
                p['updated_at'] = D
                changed += 1
            else:
                unresolved[cid].append(p['id'])
        if changed:
            # 写前指纹守卫：期间若有别的写入者改过库，会抛 LibraryConflict 而不是静默覆盖
            library_io.save(pp, ps, expect_hash=lib['hash'], actor=library_io.script_actor())
        done += changed
        print('%-18s 新归类 %3d  仍未解 %3d' % (cid, changed, len(unresolved[cid])))

    print('\n本轮新归类 %d' % done)
    print('\n仍未归类（需人工查证）：')
    for cid, ids in sorted(unresolved.items()):
        print('  %-18s %3d  %s' % (cid, len(ids), ids[:8]))


if __name__ == '__main__':
    main()