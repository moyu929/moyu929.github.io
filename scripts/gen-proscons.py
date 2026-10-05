# -*- coding: utf-8 -*-
"""按产品自身的参数值生成 `pros` / `cons` 卖点标签（只补空的那一侧）。

## 为什么用规则而不是逐条手写

330 处 `pros`/`cons` 缺口，246 款产品已有 ≥4 个可用参数。卖点本质是
**把参数翻译成一句人话**：「10kg 大容量」「一级能效」「噪音 45dB 偏高」。
这些**完全可从该产品自身字段推导**，不需要新来源，也不该由模型逐条编 ——
规则生成有两个模型给不了的好处：

1. **不可能编造数字**：标签里的每个数字都从 `product[field]` 取，
   没有「参数表里没有的数字」这种违规
2. **可复现、可审查**：规则表在代码里，改一条规则全体重跑

## 洁净门槛：只生成「干净值」的标签

源值是**异质字符串**，不是干净的「数字 + 单位」。实测踩到的形态：

| 源值 | 直接拼进标签的结果 |
| --- | --- |
| `6.8`（无单位） | `6，搬运无压力` —— 量纲不明，「无压力」是编的 |
| `55`（vent_power 无单位） | `55 换气` —— 读者不知道是瓦还是分钟 |
| `内16-35-41 / 外51dB` | `内16-35-41 / 外51dB 噪音` —— 复合值当卖点等于没写 |
| `1.5匹` | `1.5匹 匹` —— 单位重复 |
| `新一级(APF5.50)` | `新一级(APF5.50) 能效` —— 冗余 |

所以只有满足以下任一条件的值才生成标签：

1. **干净数值**：`^\d+(\.\d+)?\s*(kg|W|dB|L|mAh|㎡|m³|℃|%|Hz|匹|档|级|套|寸|英寸|分钟|小时|ml|Pa|bar)$`
2. **纯中文枚举**：长度 ≤ 6 且不含数字与括号（如「变频」「风暖」「遥控」）

其余一律跳过 —— **宁可少一条标签，不写一句读者看不懂的话**。

`cons` 完全不生成：它要判断「这个值算高还是低」，那是编辑判断，不是规则能替代的。

## 用法

    python scripts/gen-proscons.py --dry
    python scripts/gen-proscons.py --cat washing-machine
    python scripts/gen-proscons.py            # 写入 data/_draft/
"""
import json, os, re, sys, glob, argparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding='utf-8')
D = '2026-10-05'
BLANK = ('查不到', '—', '', None, '-')
MAX_TAGS = 4


def val(p, k):
    """取字段值并去掉占位。空值返回 None。"""
    v = p.get(k)
    return None if blank(v) else v


def dp(rel):
    return os.path.join(ROOT, rel)


def blank(v):
    return v in BLANK or (isinstance(v, (list, dict)) and not v)


def num(v):
    m = re.search(r'(-?\d+(?:\.\d+)?)', str(v or '').replace(',', ''))
    return float(m.group(1)) if m else None


def unit_of(v):
    """从值里抽出单位（'10kg' -> 'kg'）。抽不出返回空串。"""
    m = re.search(r'([a-zA-Z³²%℃/]+)\s*$', str(v or '').strip())
    return m.group(1) if m else ''


CLEAN_NUM = re.compile(
    r'^(\d+(?:\.\d+)?)\s*(kg|KG|Kg|W|w|dB|L|l|mAh|㎡|m³|℃|%|Hz|匹|档|级|套|'
    r'寸|英寸|分钟|小时|ml|ML|Pa|pa|bar|米|mm|cm|个|次|颗|片|块|支|只|条|件)$')
CLEAN_ENUM = re.compile(r'^[一-鿿]{2,6}$')


def clean_value(s):
    """只放行两种形态：干净的「数字+单位」、纯中文枚举。

    复合值（`内16-35-41 / 外51dB`）、无单位数字（`6.8`）、带修饰的长串一律拒 ——
    拼进标签后要么读者看不懂，要么等于把参数原样抄一遍。
    """
    s = str(s or '').strip()
    if not s or len(s) > 12:
        return None
    if CLEAN_NUM.match(s):
        return s
    if CLEAN_ENUM.match(s):
        return s
    return None


# ---------------------------------------------------------------- 通用规则
#
# 每条规则：(字段, 标签模板, 方向)
#   方向 'good' —— 有值就写进 pros
#   方向 'bad'  —— 超过阈值写进 cons
#   方向 'low'  —— 低于阈值写进 cons

COMMON = [
    ('energy',        '{v} 能效',            'good'),
    ('size',          '{v} 尺寸',            'good'),
    ('power',         '额定 {v}',            'good'),
    ('noise',         '{v} 噪音',            'good'),
    ('battery',       '{v} 电池',            'good'),
    ('runtime',       '续航 {v}',            'good'),
    ('capacity',      '{v} 容量',            'good'),
    ('tank',          '{v} 水箱',            'good'),
    ('material',      '{v} 材质',            'good'),
    ('gear',          '{v} 火力调节',        'good'),
    ('preset',        '{v} 预约',            'good'),
    ('app',           '支持 APP 远程',        'good'),
    ('display',       '{v} 显示',            'good'),
    ('wifi',          '支持无线联网',         'good'),
    ('filter',        '{v} 滤芯',            'good'),
    ('sterilize',     '{v} 除菌',            'good'),
    ('heat_power',    '{v} 取暖',            'good'),
    ('light_power',   '{v} 照明',            'good'),
    ('hepa',          '{v} 滤网',            'good'),
]

# 品类专属规则
PER_CATEGORY = {
    'washing-machine': [
        ('wash_cap', '{v} 大容量', 'good'),
        ('dry_cap', '烘干 {v}', 'good'),
        ('wash_ratio', '洗净比 {v}', 'good'),
        ('spin_rpm', '{v} 脱水', 'good'),
    ],
    'dishwasher': [
        ('volume', '{v} 套', 'good'),
        ('store', '{v}', 'good'),
        ('water_eff', '{v}', 'good'),
        ('dry', '{v}', 'good'),
    ],
    'kettle': [
        ('temp_ctrl', '{v}', 'good'),
        ('inner_pot', '{v} 内胆', 'good'),
        ('control', '{v}', 'good'),
    ],
    'bath-heater': [
        ('heat_power', '{v} 取暖', 'good'),
        ('light_power', '{v} 照明', 'good'),
        ('vent_power', '{v} 换气', 'good'),
        ('warm_mode', '{v}', 'good'),
    ],
    'tv': [
        ('size_inch', '{v} 英寸大屏', 'good'),
        ('refresh', '{v} 刷新', 'good'),
        ('mem', '{v} 内存', 'good'),
        ('resolution', '{v} 分辨率', 'good'),
        ('backlight', '{v} 背光', 'good'),
    ],
    'projector': [
        ('brightness', '{v} 流明', 'good'),
        ('throw_ratio', '{v} 投射比', 'good'),
        ('resolution', '{v} 分辨率', 'good'),
        ('dmd', '{v} 芯片', 'good'),
    ],
    'water-purifier': [
        ('rated_vol', '{v} 产水量', 'good'),
        ('pure_flow', '{v} 制水速度', 'good'),
        ('cert', '{v} 认证', 'good'),
        ('water_rate', '废水比 {v}', 'good'),
    ],
    'vacuum': [
        ('suction_aw', '{v} 吸入功率', 'good'),
        ('vacuum', '{v} 真空度', 'good'),
        ('dust_cup', '{v} 尘杯', 'good'),
        ('filter', '{v} 过滤', 'good'),
    ],
    'robot-vacuum': [
        ('climb', '爬坡 {v}', 'good'),
        ('dust_cup', '{v} 集尘', 'good'),
        ('water_tank', '{v} 水箱', 'good'),
        ('navigation', '{v} 导航', 'good'),
        ('base_func', '{v}', 'good'),
    ],
    'floor-washer': [
        ('clean_tank', '清水箱 {v}', 'good'),
        ('dirty_tank', '污水箱 {v}', 'good'),
        ('motor', '{v} 电机', 'good'),
        ('charge', '{v} 充电', 'good'),
    ],
    'smart-lock': [
        ('fingerprint', '{v} 指纹', 'good'),
        ('cat_eye', '{v} 猫眼', 'good'),
        ('lock_core', '{v} 锁体', 'good'),
        ('unlock', '{v} 开锁', 'good'),
    ],
    'hair-dryer': [
        ('temp_ctrl', '{v} 温控', 'good'),
        ('anion', '{v}', 'good'),
        ('power', '{v} 大功率', 'good'),
    ],
    'refrigerator': [
        ('total_vol', '{v} 总容积', 'good'),
        ('fridge_vol', '冷藏 {v}', 'good'),
        ('freezer_vol', '冷冻 {v}', 'good'),
        ('energy', '{v} 能效', 'good'),
    ],
    'coffee-machine': [
        ('pressure', '{v} 泵压', 'good'),
        ('tank', '{v} 水箱', 'good'),
        ('capsule', '{v}', 'good'),
        ('milk', '{v}', 'good'),
    ],
    'air-conditioner': [
        ('pishu', '{v}', 'good'),
        ('cool_cap', '制冷量 {v}', 'good'),
        ('heat_cap', '制热量 {v}', 'good'),
        ('area', '适用 {v}', 'good'),
        ('inverter', '变频', 'good'),
        ('fresh_air', '新风 {v}', 'good'),
    ],
    'air-purifier': [
        ('cadr_pm', '{v} 颗粒物 CADR', 'good'),
        ('area', '适用 {v}', 'good'),
        ('filter_layers', '{v} 过滤', 'good'),
        ('cert', '{v} 认证', 'good'),
    ],
    'dehumidifier': [
        ('dehumid', '日除湿 {v}', 'good'),
        ('tank', '{v} 水箱', 'good'),
        ('compressor', '{v} 压缩机', 'good'),
    ],
    'humidifier': [
        ('humid_rate', '{v} 加湿量', 'good'),
        ('tank', '{v} 水箱', 'good'),
        ('sterilize', '{v}', 'good'),
    ],
    'rice-cooker': [
        ('capacity', '{v} 容量', 'good'),
        ('inner_pot', '{v} 内胆', 'good'),
        ('appoint', '{v} 预约', 'good'),
    ],
    'pressure-cooker': [
        ('pressure', '{v} 压', 'good'),
        ('inner_pot', '{v} 内胆', 'good'),
        ('preset', '{v} 预约', 'good'),
    ],
    'microwave': [
        ('input_power', '{v} 输入功率', 'good'),
        ('grill_power', '{v} 烧烤', 'good'),
        ('volume', '{v} 容量', 'good'),
    ],
    'fan': [
        ('airflow', '风量 {v}', 'good'),
        ('throw_dist', '送风 {v}', 'good'),
        ('speeds', '{v} 档', 'good'),
        ('battery', '续航 {v}', 'good'),
    ],
    'heater': [
        ('coverage', '适用 {v}', 'good'),
        ('gear', '{v}', 'good'),
        ('safety', '{v}', 'good'),
        ('ipx', '{v}', 'good'),
    ],
    'blender': [
        ('power', '{v} 电机', 'good'),
        ('capacity', '{v} 容量', 'good'),
        ('speed', '{v} 档', 'good'),
        ('noise_down', '{v}', 'good'),
    ],
    'induction-cooker': [
        ('power', '{v} 火力', 'good'),
        ('gear', '{v} 火力调节', 'good'),
        ('panel', '{v} 面板', 'good'),
    ],
    'water-dispenser': [
        ('temp', '{v} 温控', 'good'),
        ('filter', '{v} 滤芯', 'good'),
        ('app', '支持 APP', 'good'),
    ],
    'water-heater': [
        ('constant', '{v} 恒温', 'good'),
        ('app', '支持 APP', 'good'),
    ],
    'shaver': [
        ('wet_dry', '{v} 干湿两用', 'good'),
        ('runtime', '续航 {v}', 'good'),
    ],
    'toothbrush': [
        ('modes', '{v} 模式', 'good'),
        ('battery_days', '{v} 天续航', 'good'),
        ('freq', '{v} 频率', 'good'),
    ],
    'hair-clipper': [
        ('blades', '{v}', 'good'),
        ('waterproof', '{v}', 'good'),
        ('runtime', '续航 {v}', 'good'),
    ],
    'dehumidifier-extra': [],
}

def build_tags(cat, p):
    """按规则生成 (pros, cons)。返回两个列表。"""
    pros, cons = [], []
    rules = list(COMMON) + PER_CATEGORY.get(cat, [])
    for key, tpl, direction in rules:
        if len(pros) >= MAX_TAGS:
            break
        v = val(p, key)
        if v is None:
            continue
        s = clean_value(v)
        if s is None:
            continue
        # 标签里嵌数字的字段，必须是这个产品自己填了值（由 val() 保证）
        text = tpl.format(v=s)
        if direction == 'good' and text not in pros:
            pros.append(text)
    return pros[:MAX_TAGS], cons


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--cat', help='只处理某品类')
    ap.add_argument('--dry', action='store_true')
    args = ap.parse_args()

    total_p = total_c = 0
    written = 0
    for f in sorted(glob.glob(dp('data/*/schema.json'))):
        cid = os.path.basename(os.path.dirname(f))
        if args.cat and cid != args.cat:
            continue
        pf = dp('data/%s/products.json' % cid)
        if not os.path.exists(pf):
            continue
        schema = json.load(open(f, encoding='utf-8'))
        if not any(x['key'] == 'pros' for x in schema['fields']):
            continue
        prods = json.load(open(pf, encoding='utf-8'))
        d = dp('data/_draft/%s' % cid)
        got = 0
        for p in prods:
            if not blank(p.get('pros')) and not blank(p.get('cons')):
                continue
            pros, cons = build_tags(cid, p)
            if not pros and not cons:
                continue
            item = dict(p)
            if not blank(p.get('pros')) and pros:
                item['pros'] = pros
            if not blank(p.get('cons')) and cons:
                item['cons'] = cons
            item['change_log'] = (p.get('change_log', '') or '') + \
                '；%s 按本产品已入库参数生成卖点/缺点标签（规则见 scripts/gen-proscons.py，无外部数值）' % D
            item['updated_at'] = D
            total_p += len(item.get('pros') or [])
            total_c += len(item.get('cons') or [])
            got += 1
            if not args.dry:
                os.makedirs(d, exist_ok=True)
                with open('%s/%s.json' % (d, p['id']), 'w', encoding='utf-8', newline='\n') as fh:
                    json.dump(item, fh, ensure_ascii=False, indent=2)
                    fh.write('\n')
        if got:
            print('  %-18s %2d 款' % (cid, got))
        written += got
    print('\n共 %d 款；生成 pros %d 条 / cons %d 条标签' % (written, total_p, total_c))
    if args.dry:
        return
    print('已写入 data/_draft/')


if __name__ == '__main__':
    main()