# -*- coding: utf-8 -*-
"""人工可复核的「缺点」候选生成 —— 只给线索，不直接写库。

## 为什么还要脚本

246 款产品「缺点」为空。`cons` 是**编辑判断**（「这个值算高还是低」），
规则化会写错（空调 `内16-35-41 / 外51dB` 取第一个数得 16，判成「不吵」，
而真实值是外机 51dB）。所以**脚本不写库**，只做三件机器擅长的事：

1. 把该产品**已有的参数**摊平给人看（按中文标签，不按 key）
2. 按品类的**常识阈值**标出「可能算缺点」的候选（让人确认，不是让人接受）
3. 输出成 Markdown，人逐条改写成一句中文，粘回 JSON

## 用法

    python scripts/cons-candidates.py --cat washing-machine
    python scripts/cons-candidates.py --cat washing-machine,kettle > /tmp/x.md
    python scripts/cons-candidates.py --all        # 全部 246 款

产物是一份 Markdown，每款一段：产品名 / 已有参数 / 候选缺点。
人在 `缺点（改写后）：` 后面填一句，交回后由 apply 步骤写库。
"""
import json, os, re, sys, glob, argparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding='utf-8')

# 字段中文名（站内 schema 的 label 之上再补一层口语化，读起来不费脑）
CN = {
    'name': '产品名', 'brand': '品牌', 'type': '类型', 'series': '系列',
    'official_price': '参考价(元)', 'ref_price': '划线价(元)',
    'model_code': '零售型号', 'miot_model': '米家协议型号',
    'size': '整机尺寸', 'size_indoor': '内机尺寸', 'size_outdoor': '外机尺寸',
    'weight': '整机重量', 'power': '额定功率(W)',
    'noise': '噪音(dB)', 'noise_wash': '洗涤噪音(dB)', 'noise_spin': '脱水噪音(dB)',
    'capacity': '容量(L)', 'tank': '水箱(L)', 'clean_tank': '清水箱(L)',
    'dirty_tank': '污水箱(L)', 'water_tank': '水箱(L)', 'dust_cup': '尘杯(L)',
    'year': '上市年份', 'month': '上市月份', 'energy': '能效等级',
    'runtime': '续航', 'battery': '电池', 'battery_days': '续航天数',
    'heat_power': '取暖功率(W)', 'light_power': '照明功率(W)',
    'fan_power': '风扇功率(W)', 'vent_power': '换气功率(W)',
    'warm_mode': '取暖方式', 'control': '控制方式', 'open_size': '安装开孔(mm)',
    'pishu': '匹数', 'cool_cap': '制冷量(W)', 'heat_cap': '制热量(W)',
    'cool_power': '制冷功率(W)', 'airflow': '循环风量', 'area': '适用面积',
    'wash_cap': '洗涤容量(kg)', 'dry_cap': '烘干容量(kg)', 'spin_rpm': '脱水转速',
    'wash_ratio': '洗净比', 'volume': '餐具套数', 'water_eff': '水效等级',
    'total_vol': '总容积(L)', 'fridge_vol': '冷藏容积(L)', 'freezer_vol': '冷冻容积(L)',
    'cadr_pm': '颗粒物CADR', 'cadr_hcho': '甲醛CADR', 'filter_life': '滤芯寿命',
    'filter_price': '滤芯价格', 'suction_aw': '吸入功率(AW)', 'vacuum': '真空度(kPa)',
    'climb': '越障能力', 'navigation': '导航方式', 'base_func': '基站功能',
    'motor': '电机', 'charge': '充电', 'dehumid': '日除湿量(L)',
    'humid_rate': '加湿量(ml/h)', 'temp_ctrl': '温控', 'inner_pot': '内胆',
    'preset': '预约', 'app': '智能控制', 'appoint': '预约', 'gear': '火力档位',
    'resolution': '分辨率', 'refresh': '刷新率(Hz)', 'mem': '内存',
    'size_inch': '屏幕尺寸(英寸)', 'backlight': '背光', 'brightness': '亮度',
    'throw_ratio': '投射比', 'dmd': '显示芯片', 'pure_flow': '制水速度',
    'ro_life': 'RO滤芯寿命', 'water_rate': '废水比', 'rated_vol': '额定总净水量',
    'cert': '认证', 'sterilize': '除菌方式', 'freq': '震动频率',
    'modes': '清洁模式', 'blades': '刀头', 'waterproof': '防水',
    'fingerprint': '指纹识别', 'cat_eye': '猫眼', 'lock_core': '锁体',
    'unlock': '开锁方式', 'store': '安装方式', 'temp': '温控',
    'material': '材质', 'ipx': '防护等级', 'safety': '安全设计',
    'coverage': '适用面积', 'speeds': '风速档位', 'swing': '摆头',
    'throw_dist': '送风距离', 'speed': '转速档位',
    'pressure': '泵压', 'capsule': '胶囊系统', 'milk': '奶泡系统',
    'input_power': '微波功率(W)', 'grill_power': '烧烤功率(W)',
    'inverter': '变频', 'fresh_air': '新风量', 'constant': '恒温性能',
    'mpower': '功率(W)', 'temp_max': '最高温度(℃)',
}


def blank(v):
    return v in ('查不到', '—', '', None, '-') or (isinstance(v, (list, dict)) and not v)


def num(v):
    m = re.search(r'(\d+(?:\.\d+)?)', str(v or '').replace(',', ''))
    return float(m.group(1)) if m else None


# 候选缺点规则：(品类或 None, 字段, 判定函数, 中文线索)
# 判定只负责「这可能值得说一句」，**不负责下结论** —— 输出里带原始值，人自己判。
RULES = [
    (None, 'wash_cap', lambda v: num(v) == 1, '洗涤容量仅 {v}kg，小家庭够用、多人局要分批'),
    (None, 'dry_cap', lambda v: num(v) == 0, '无烘干容量，需要单独配干衣机'),
    (None, 'wash_ratio', lambda v: num(v) and num(v) < 1.03, '洗净比 {v} 低于主流 1.05+'),
    (None, 'spin_rpm', lambda v: num(v) and num(v) < 1200, '脱水转速 {v} 偏低，衣物更潮'),
    (None, 'tank', lambda v: num(v) and num(v) < 2, '水箱仅 {v}L，加湿要频繁补水'),
    (None, 'runtime', lambda v: num(v) and num(v) < 30, '续航仅 {v}，大户型一次扫不完'),
    (None, 'battery', lambda v: num(v) and num(v) < 2500, '电池 {v}mAh，续航偏短'),
    (None, 'noise', lambda v: num(v) and num(v) > 55, '噪音 {v}dB 偏高'),
    ('air-conditioner', 'noise', lambda v: num(v) and num(v) > 48, '内机噪音 {v}dB，夜间可能扰人'),
    (None, 'filter_life', lambda v: num(v) and num(v) < 6, '滤芯寿命仅 {v} 个月，长期成本高'),
    (None, 'ro_life', lambda v: num(v) and num(v) < 12, 'RO 滤芯 {v} 个月需更换'),
    (None, 'water_rate', lambda v: '废' in str(v) or (num(v) and num(v) > 2), '废水比 {v}，净水效率一般'),
    (None, 'energy', lambda v: str(v) in ('3', '三级', '3级', '五级', '5级'), '能效仅 {v}，长期电费偏高'),
    (None, 'wash_ratio', lambda v: num(v) and num(v) < 1.05, '洗净比 {v} 不算高'),
    (None, 'volume', lambda v: num(v) and num(v) < 6, '容量 {v} 套偏小'),
    (None, 'inverter', lambda v: str(v) in ('定频', '否', '不支持'), '非变频，温控与噪音表现一般'),
    (None, 'app', lambda v: str(v) in ('查不到', '不支持', '否', '无'), '不支持 App/智能控制'),
    (None, 'weight', lambda v: num(v) and num(v) > 8, '整机 {v}kg，搬动安装费力'),
    ('dishwasher', 'weight', lambda v: num(v) and num(v) > 40, '整机 {v}kg，需预留安装空间'),
    (None, 'sterilize', lambda v: blank(v) or str(v) in ('查不到', '无'), '无除菌能力'),
    (None, 'temp_ctrl', lambda v: blank(v) or str(v) in ('查不到', '机械控温'), '温控方式简单，精度一般'),
    (None, 'preset', lambda v: blank(v) or str(v) in ('查不到', '不支持', '否'), '不支持预约'),
    (None, 'navigation', lambda v: blank(v) or '碰撞' in str(v) or '随机' in str(v), '导航方式 {v}，覆盖率与效率一般'),
    (None, 'climb', lambda v: num(v) and num(v) < 2, '越障能力 {v}cm，过门槛费劲'),
    (None, 'refresh', lambda v: num(v) and num(v) < 120, '刷新率仅 {v}Hz，动态画面流畅度一般'),
    (None, 'mem', lambda v: num(v) and num(v) < 3, '内存 {v}GB，装多应用会紧张'),
    (None, 'throw_ratio', lambda v: num(v) and num(v) > 1.5, '投射比 {v}，需较远摆放距离'),
    (None, 'brightness', lambda v: num(v) and num(v) < 800, '亮度 {v} 流明，白天需遮光'),
    (None, 'cert', lambda v: blank(v) or str(v) in ('查不到', ''), '无水效/卫生认证'),
    (None, 'pure_flow', lambda v: num(v) and num(v) < 1, '制水速度 {v}L/min，接水慢'),
    (None, 'airflow', lambda v: num(v) and num(v) < 400, '循环风量 {v}，制冷/制热偏慢'),
    (None, 'coverage', lambda v: num(v) and num(v) < 12, '适用面积仅 {v}㎡'),
    (None, 'gear', lambda v: num(v) and num(v) < 4, '火力仅 {v} 档，精细控火不足'),
    (None, 'speeds', lambda v: num(v) and num(v) < 3, '风速仅 {v} 档'),
    (None, 'swing', lambda v: str(v) in ('查不到', '不支持', '否', '无'), '不支持摆头，送风范围受限'),
    (None, 'blades', lambda v: blank(v) or str(v) in ('查不到', '单刀头'), '刀头配置简单'),
    (None, 'waterproof', lambda v: str(v) not in ('IPX7', '全身水洗') and blank(v), '防水等级低，不能整机冲洗'),
    (None, 'material', lambda v: '塑料' in str(v), '内胆/材质为 {v}，耐用性一般'),
    (None, 'compressor', lambda v: blank(v) or str(v) in ('查不到', '定频'), '压缩机非常规定频，除湿波动大'),
    (None, 'ipx', lambda v: blank(v) or str(v) in ('查不到', 'IPX0'), '防护等级低，浴室使用需注意'),
    (None, 'safety', lambda v: blank(v) or str(v) in ('查不到', '无'), '安全设计（倾倒断电等）信息不足'),
]


def candidates(cat, p):
    """返回 [(字段中文名, 原始值, 候选句子), ...]"""
    out = []
    for rcat, field, fn, tpl in RULES:
        if rcat and rcat != cat:
            continue
        v = p.get(field)
        if blank(v):
            continue
        try:
            if not fn(v):
                continue
        except Exception:
            continue
        out.append((CN.get(field, field), v, tpl.format(v=v)))
    return out


def params_block(cat, p, schema_keys):
    rows = []
    for k in schema_keys:
        if k in ('cons', 'pros', 'change_log', 'verify_source', 'verify_url',
                 'verify_status', 'verify_date', 'updated_at', 'id', 'img'):
            continue
        v = p.get(k)
        if blank(v):
            continue
        if isinstance(v, list):
            v = '、'.join(str(x) for x in v)
        rows.append('| %s | %s |' % (CN.get(k, k), str(v).replace('|', '/')[:44]))
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--cat')
    ap.add_argument('--all', action='store_true')
    args = ap.parse_args()
    if not args.cat and not args.all:
        ap.error('需要 --cat 或 --all')

    want = None if args.all else set(args.cat.split(','))
    n = 0
    print('# 「缺点」候选清单（人工改写用）\n')
    print('每款下面是**已有参数**与**候选缺点**。`缺点（改写后）：` 留空给人填。\n')
    print('> 候选缺点只是按阈值标出的线索，**不是结论**。'
          '引号里的原始值才是依据，改写时不要引入参数表里没有的数字。\n')

    for f in sorted(glob.glob(os.path.join(ROOT, 'data/*/schema.json'))):
        cat = os.path.basename(os.path.dirname(f))
        if want and cat not in want:
            continue
        pf = os.path.join(ROOT, 'data/%s/products.json' % cat)
        if not os.path.exists(pf):
            continue
        schema = json.load(open(f, encoding='utf-8'))
        keys = [x['key'] for x in schema['fields']]
        prods = json.load(open(pf, encoding='utf-8'))
        hit = [p for p in prods if blank(p.get('cons'))]
        if not hit:
            continue
        print('\n## %s（%d 款缺「缺点」）\n' % (cat, len(hit)))
        for p in hit:
            n += 1
            print('### %s  ·  %s' % (p.get('name', p['id']), p.get('brand', '')))
            print()
            print('| 参数 | 值 |')
            print('| --- | --- |')
            for r in params_block(cat, p, keys):
                print(r)
            print()
            cands = candidates(cat, p)
            if cands:
                print('**候选缺点**：')
                for label, v, sent in cands[:6]:
                    print('- [%s = %s] %s' % (label, v, sent))
            else:
                print('**候选缺点**：（参数不足，无候选）')
            print()
            print('缺点（改写后）：')
            print()
    print('\n---\n共 %d 款。' % n)


if __name__ == '__main__':
    main()