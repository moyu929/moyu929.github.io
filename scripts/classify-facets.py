# -*- coding: utf-8 -*-
"""给竞品按 facet 分类。

依据优先级：pconline 缓存的「产品类型/安装方式/加热方式」字段 > 国标型号正则 > 参数阈值 > 价格分档。
每个赋值都写进 change_log 便于复核；没有依据的保持「未归类」，不猜。

用法：python scripts/classify-facets.py           # 只处理尚未归类的竞品
"""
import json, glob, os, re, sys, collections

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
    'coffee': [('胶囊', '胶囊'), ('意式', '半自动'), ('半自动', '半自动'),
               ('美式', '滴滤'), ('滴滤', '滴滤')],
    'water_dispenser': [('管线', '管线'), ('茶吧', '茶吧机'), ('冷热', '冷热'),
                        ('直饮', '即热'), ('智能', '即热'), ('温热', '即热'), ('单热', '即热')],
    'washer': [('干衣', '洗烘套装'), ('烘洗', '滚筒洗烘一体'), ('洗烘', '滚筒洗烘一体'),
               ('滚筒', '滚筒洗烘一体'), ('波轮', '波轮')],
}


def load_cache(pc):
    out = {}
    for f in glob.glob('data/_cache/brand-%s-*.json' % pc):
        try:
            d = json.load(open(f, encoding='utf-8'))
        except Exception:
            continue
        for it in d:
            if it.get('id'):
                out[str(it['id'])] = it.get('specs') or {}
    return out


def num(v):
    if v is None:
        return None
    m = re.search(r'(\d+(?:\.\d+)?)', str(v).replace(',', ''))
    return float(m.group(1)) if m else None


def pick_id(url):
    m = re.search(r'/([0-9]+)_detail\.html', url or '')
    return m.group(1) if m else None


def by_kw(pc, sp, fields, why_prefix):
    """按第三方分类字段取值映射到本站 facet 值。"""
    blob = ''.join(str(sp.get(f, '')) for f in fields)
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
    n, t = p['name'], str(sp.get('空调类型', ''))
    if re.search(r'风管|天花|中央|多联', n + t):
        return '中央空调', '名称/空调类型含风管或中央'
    if '立式' in t or re.search(r'72\s*L?W', n):
        return '柜机', '空调类型=%s 或型号含 72LW' % t
    if '挂式' in t or re.search(r'(26|35|50|72)\s*G?W', n):
        return '挂机', '空调类型=%s 或型号含 GW' % t
    return None


def rule_fan(p, sp):
    return by_kw('fan', sp, ['产品类型'], '第三方产品类型')


def rule_microwave(p, sp):
    got = by_kw('oven', sp, ['产品类型'], '第三方产品类型')
    if got:
        return got
    if re.search(r'蒸烤|微烤', p['name']):
        return '微烤一体', '名称含蒸烤/微烤'
    return None


def rule_dishwasher(p, sp):
    got = by_kw('xiwanji', sp, ['产品类型', '安装方式'], '第三方类型/安装方式')
    return got


def rule_waterheater(p, sp):
    n = p['name']
    if re.search(r'JSQ|燃气|煤气', n):
        return '燃气', '名称含 JSQ 或燃气（JSQ 为燃气热水器国标前缀）'
    if re.search(r'\bES|电热', n):
        return '电热', '名称含 ES 或电热（ES 为电热水器国标前缀）'
    t = str(sp.get('产品类型', ''))
    if re.search(r'即热|速热|储水', t):
        return '电热', '第三方产品类型=%s' % t
    return None


def rule_pressurecooker(p, sp):
    v = num(p.get('capacity') or sp.get('产品容量'))
    if v is None:
        return None
    return ('大容量' if v >= 5 else '小容量'), '标称容量 %sL' % v


def rule_dehumid(p, sp):
    v = num(p.get('dehumid') or sp.get('日除湿量'))
    if v is None:
        return None
    if v >= 40:
        return '大除湿量(40L+)', '日除湿量 %sL/天' % v
    if v >= 20:
        return '中除湿量(20-30L)', '日除湿量 %sL/天' % v
    return '小除湿量(≤20L)', '日除湿量 %sL/天' % v


def rule_induction(p, sp):
    n = p['name'] + str(sp.get('其它性能', '')) + str(sp.get('主要特点', ''))
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
    v = num(p.get('capacity') or sp.get('产品容量'))
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
    t = str(sp.get('加热方式', ''))
    if re.search(r'蒸汽|烤', t + p['name']):
        return '蒸烤一体', '第三方加热方式=%s' % t
    if '可视' in p['name']:
        return '可视炸锅', '名称含可视'
    return '经典炸锅', '无蒸烤或可视特征'


def rule_ricecooker(p, sp):
    n = p['name']
    t = str(sp.get('加热方式', ''))
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
    n = p['name'] + str(sp.get('集尘方式', ''))
    if '上下水' in n:
        return '全能上下水', '名称含上下水'
    if re.search(r'基站|自清洁|全能', n) or sp.get('集尘方式'):
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
    t = str(sp.get('安装方式', ''))
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
    n, t = p['name'], str(sp.get('加热方式', ''))
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
    'dishwasher': rule_dishwasher, 'fan': rule_fan, 'heater': rule_heater,
    'humidifier': rule_humidifier, 'induction-cooker': rule_induction, 'kettle': rule_kettle,
    'microwave': rule_microwave, 'pressure-cooker': rule_pressurecooker,
    'projector': rule_projector, 'refrigerator': rule_fridge, 'rice-cooker': rule_ricecooker,
    'robot-vacuum': rule_robotvac, 'vacuum': rule_vacuum, 'washing-machine': rule_washer,
    'water-dispenser': rule_waterdisp, 'water-heater': rule_waterheater,
    'water-purifier': rule_waterpur,
}


def main():
    unresolved = collections.defaultdict(list)
    done = 0
    for cid, rule in sorted(RULES.items()):
        sp_path = 'data/%s/schema.json' % cid
        if not os.path.exists(sp_path):
            continue
        s = json.load(open(sp_path, encoding='utf-8'))
        facets = s.get('facets') or []
        if not facets:
            continue
        fk = facets[0]['key']
        valid = set(facets[0]['order'])
        cache = load_cache(CAT2PC.get(cid, cid))
        pp = 'data/%s/products.json' % cid
        ps = json.load(open(pp, encoding='utf-8'))
        changed = 0
        for p in ps:
            if p.get('brand') == '小米':
                continue
            if p.get(fk) not in (None, '未归类', '查不到'):
                continue                      # 已归类，不重复处理
            sp = cache.get(pick_id(p.get('verify_url')), {})
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
            with open(pp, 'w', encoding='utf-8', newline='\n') as f:
                json.dump(ps, f, ensure_ascii=False, separators=(',', ':'))
                f.write('\n')
        done += changed
        print('%-18s 新归类 %3d  仍未解 %3d' % (cid, changed, len(unresolved[cid])))

    print('\n本轮新归类 %d' % done)
    print('\n仍未归类（需人工查证）：')
    for cid, ids in sorted(unresolved.items()):
        print('  %-18s %3d  %s' % (cid, len(ids), ids[:8]))


if __name__ == '__main__':
    main()