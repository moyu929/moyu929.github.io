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
BLANK = ('查不到', '—', '', None, '-')
D = '2026-10-04'
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

# 本站字段 -> 第三方规格表的字段名候选（按优先级）
#
# 2026-10-04 扩表：缓存里实测有 225 个不同的第三方字段名，原先只映射 28 个。
# 扩充时踩到的坑，逐条记在 SHAPE 里做形状守卫：
#   * `产品功率` 在空调下写的是「1.5匹」，不是瓦 —— 不能当功率取
#   * `产品容量` 在空调下写的是「4.5L」（匹数的另一种写法），在破壁机下才是容量
#   * `吸尘能力` 写的是「28000pa」而本站 `suction` 期望 kPa，两者差 1000 倍
#   * `噪音强度` 写的是「84dB」，比任何家用品都高，多半是错误行，别当噪音取
FIELD_MAP = {
    # —— 功率：只认带 W 的来源字段。`产品功率` 不在其中（空调写匹数）——
    'power':       ['额定功率', '额定总功率', '输入功率', '最大额定功率', '功率', '功耗'],
    # 2026-10-04 微波炉批次新增：烤箱/蒸烤箱/微波炉品类下 pconline 的「产品功率」
    # 写的就是额定输入功率（如老板 R026 2600W、格兰仕 DG26T-D20 1600W），
    # 与空调的「1.5匹」不同；NEED_UNIT 的 W 守卫 + 阈值仍然生效。
    'power_input': ['产品功率'],
    'power_heat':  ['加热功率'],
    'power_cool':  ['制冷功率'],
    'power_mix':   ['搅拌功率'],
    'power_wash':  ['洗涤功率'],
    'power_dehy':  ['脱水功率'],
    'power_fan':   ['风扇功率'],
    'power_light': ['灯暖功率', '照明功率'],
    'power_grill': ['烧烤功率'],
    'power_mw':    ['微波功率'],

    # —— 尺寸：注意室内机/室外机要分开，不能合并进 size
    'size':        ['产品尺寸', '机身尺寸', '外形尺寸', '外型尺寸', '扫地机器人', '产品大小', '尺寸'],
    'size_indoor': ['室内机尺寸'],
    'size_outdoor':['室外机尺寸'],
    'open_size':   ['安装开孔尺寸', '开孔尺寸'],

    'weight':      ['产品重量', '主机净重', '重量', '净重', '毛重'],

    # —— 噪音：`噪音强度` 不在其中（实测值 84dB，是错行）
    'noise':       ['室内机噪音', '工作噪音', '运转噪音', '产品噪音', '噪音'],
    'noise_out':   ['室外机噪音'],

    # —— 容量 / 水箱
    'capacity':    ['产品容量', '内胆容量', '容积大小', '餐具容量', '洗涤容量', '容量'],
    'tank':        ['水箱容积', '水箱容量', '集尘箱容量', '清水箱容量', '污水箱容量'],
    'tank_clean':  ['净水箱容量', '清水箱容量'],
    'tank_dirty':  ['污水箱容量'],

    'energy':      ['能效等级', '能耗等级', '能源效率', '能效'],

    'flux':        ['额定通量', '净水流量', '通量', '制水速度'],

    'runtime':     ['续航时间', '连续使用时间', '工作时间'],
    'charge_time': ['充电时间'],
    'battery':     ['电池容量', '电池规格'],

    'coverage':    ['适用面积', '覆盖面积'],
    'voltage':     ['额定电压', '电源电压', '额定输入', '电源性能'],

    'refresh':     ['屏幕刷新频率', '刷新率'],
    'response':    ['屏幕响应速度'],
    'resolution':  ['分辨率', '屏幕分辨率'],
    'screen_size': ['屏幕尺寸'],

    # —— 空调：匹数与能力
    'cool_cap':    ['制冷量'],
    'heat_cap':    ['制热量'],
    'cold_wind':   ['循环风量', '风量', '风量大小'],
    'fresh_air':   ['新风量'],
    'pishu':       ['匹数'],
    'apf':         ['全年能源消耗率(APF)', 'APF'],
    'seer':        ['能效比(SEER)', 'SEER'],
    'refrigerant': ['制冷剂'],
    'inverter':    ['是否变频'],
    'ac_type':     ['空调类型'],
    'cold_heat':   ['冷暖类型'],

    # —— 除湿 / 加湿
    'dehumid':     ['日除湿量'],
    'humid_rate':  ['加湿量'],
    'compressor':  ['压缩机'],

    # —— 清洁电器
    'suction_pa':  ['吸尘能力'],
    'vacuum':      ['真空度'],
    'climb':       ['爬坡能力'],
    'dust_cup':    ['尘杯容量'],
    'dust_way':    ['集尘方式'],
    'filter_kind': ['滤芯种类'],
    'motor':       ['电机类型'],

    # —— 厨房
    'heating':     ['加热方式'],
    'gear':        ['可选档位', '档位', '火力档位', '风力档位'],
    'material':    ['锅体材质', '内胆材质', '内筒材料', '面板材质', '搅拌杯材质', '材质'],
    'speeds':      ['风力档位', '可选档位', '速度调节'],
    'preset':      ['预约定时煮饭', '预约时间'],
    'water_yield': ['出汁率', '出浆率'],
    'net_flow':    ['净水机原理'],
    'install':     ['安装方式'],
    'open_way':    ['开门方式'],
    'water_use':   ['耗水量'],
    'ipx':         ['产品特性'],
    'full_auto':   ['全自动'],
    # 控温方式（电子控温/机械控温）描述的是温控元件，不是操控方式，
    # 映射进 control 会污染「按键式/旋钮式/触控式」口径 —— 2026-10-04 微波炉批次移除
    'control':     ['操控方式', '控制方式', '操作方式'],
    'display':     ['显示屏'],
    'temp_range':  ['温度范围'],

    # —— 净化器
    'cadr_pm':     ['固态污染物CADR', '颗粒物CADR'],
    'cadr_hcho':   ['甲醛CADR'],
    'filter_layers': ['过滤方式'],
    'area':        ['适用面积'],

    # —— 上市时间与价格（不是规格参数，单独解析）
    '_上市时间':   ['上市时间'],
    '_参考价':     ['参考价:', '参考价', '市场价'],
}

# 源字段族 -> 本站候选字段。
#
# 只在**语义相同**时才映射：把「是否变频」写进 `energy`（能效等级 1 级）这类
# 看似能填、实则污染数据的做法在这里被刻意排除 —— 宁可少一列。
# 找不到对应 schema 字段的源字段族（如 APF、SEER、制冷剂、开门方式）直接不映射，
# 等对应字段进了 schema 再回来接。
ALIAS = {
    'power_heat':  ['heat_power', 'power'],
    'power_input': ['input_power'],
    'power_cool':  ['cool_power', 'power'],
    'power_mix':   ['power'],
    'power_wash':  ['power'],
    'power_dehy':  ['power'],
    'power_fan':   ['fan_power', 'power'],
    'power_light': ['light_power', 'power'],
    'power_grill': ['grill_power', 'power'],
    'power_mw':    ['mw_power', 'input_power', 'power'],
    'noise_out':   ['noise'],
    'tank_clean':  ['clean_tank', 'water_tank', 'tank'],
    'tank_dirty':  ['dirty_tank', 'water_tank', 'tank'],
    'cold_wind':   ['airflow', 'cold_wind'],
    'suction_pa':  ['suction', 'suction_aw'],
    'filter_kind': ['filter'],
    'speeds':      ['speeds', 'gear'],
    'ipx':         ['ipx'],
}

# 字段级异常阈值：超出即判第三方错标，丢弃
THRESHOLD = {
    'power':     (5, 6000),      # 家电额定功率 5W~6000W
    'power_input': (5, 6000),    # 额定输入功率（产品功率）同域
    'power_heat': (5, 4000),
    'power_cool': (5, 6000),
    'power_mix':  (5, 3000),
    'power_wash': (5, 3000),
    'power_dehy': (5, 2000),
    'power_fan':  (1, 500),
    'power_light': (1, 2000),
    'power_grill': (5, 4000),
    'power_mw':   (5, 3000),
    'weight':    (0.05, 100),    # 净重 50g~100kg
    'noise':     (15, 90),       # 噪音 15~90dB
    'battery':   (500, 20000),   # 电池 500~20000mAh
    'coverage':  (3, 200),       # 适用面积 3~200㎡
    'area':      (3, 200),
    # 2026-10-04 微波炉批次：上限 30 -> 100。本品类含嵌入式蒸烤一体机
    # （美的 BS50D0W 85L、老板 R026 60L、格兰仕 KDES85TMC-A90 50L），
    # 30 的上限把真实容量全拦了；下界 0.2 与 L/ml 单位守卫仍然生效。
    'capacity':  (0.2, 100),     # 通用容量下界
    'tank':      (0.1, 10),
    'tank_clean': (0.1, 10),
    'tank_dirty': (0.1, 10),
    'flux':      (0.05, 10),     # 通量 t/h 或 L/min
    'runtime':   (5, 600),       # 续航 5~600min
    'cool_cap':  (500, 20000),   # 制冷量 W
    'heat_cap':  (500, 25000),
    'cold_wind': (100, 30000),   # 风量 m³/h
    'fresh_air': (30, 1500),
    'dehumid':   (5, 200),       # L/D，家用机极少破 100
    'humid_rate': (50, 1200),    # ml/h
    'dust_cup':  (0.05, 5),      # L
    'climb':     (1, 30),        # mm
    'suction_pa': (500, 60000),  # Pa
    'vacuum':    (1, 40),        # kPa
    'cadr_pm':   (10, 1500),     # m³/h
    'cadr_hcho': (5, 800),
    'pishu':     (0.5, 8),
    'official_price': (49, 999999),
}

# 单位守卫：number 字段的值必须自带该单位，否则判第三方错标。
#
# 这条比阈值更早生效、也更准 —— 空调的 `产品功率` 写「1.5匹」、净化器的
# `产品容量` 写「4.5L」（匹数的另一种写法），数值上都能骗过阈值，只有单位能拦住。
NEED_UNIT = {
    'power': r'[Ww]|瓦', 'power_heat': r'[Ww]|瓦', 'power_cool': r'[Ww]|瓦',
    'power_mix': r'[Ww]|瓦', 'power_wash': r'[Ww]|瓦', 'power_dehy': r'[Ww]|瓦',
    'power_fan': r'[Ww]|瓦', 'power_light': r'[Ww]|瓦', 'power_grill': r'[Ww]|瓦',
    'power_mw': r'[Ww]|瓦',
    'weight': r'kg|KG|千克|公斤|g$|克',
    'noise': r'dB|分贝',
    'battery': r'mAh|ah|安时',
    'coverage': r'㎡|m2|平方米|平米|㎡',
    'area': r'㎡|m2|平方米|平米',
    'capacity': r'[Ll]|升|ml',
    'tank': r'[Ll]|升|ml', 'tank_clean': r'[Ll]|升|ml', 'tank_dirty': r'[Ll]|升|ml',
    'flux': r'升|L/|ml|mL|t/h',
    'runtime': r'min|分钟|小时|h$',
    'cool_cap': r'W', 'heat_cap': r'W',
    'cold_wind': r'm3|m³|立方米',
    'fresh_air': r'm3|m³',
    'dehumid': r'[Ll]|升',
    'humid_rate': r'ml|mL|毫升|升',
    'dust_cup': r'[Ll]|升|ml',
    'climb': r'mm|毫米|cm',
    'suction_pa': r'[Pp]a|帕',
    'vacuum': r'[Kk][Pp]a|帕',
    'cadr_pm': r'm3|m³', 'cadr_hcho': r'm3|m³',
    'pishu': r'匹',
}

# text 类字段：值保留原文（尺寸「1084×232×232mm」不能只取第一个数字，
# 那会丢掉尺寸信息），但仍做阈值校验以剔除第三方错标值。
TEXT_FIELDS = {'size', 'size_indoor', 'size_outdoor', 'heating', 'backlight',
               'open_size', 'resolution', 'material', 'energy', 'ipx',
               'display', 'control', 'gear', 'speeds', 'preset', 'motor',
               'compressor', 'filter', 'filter_kind', 'filter_layers'}

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
    """按单位守卫 + 阈值剔除第三方错标值。返回 (是否可用, 说明)。"""
    s = str(raw)
    # 2026-10-04 微波炉批次新增：pconline 的「产品容量 26-35L」「产品功率 1201-1600W」
    # 是**筛选分桶**不是真实参数（NN-SC200W 落在 21-30L 桶，真机 30L；取下界必错）。
    # number 字段一律拒收区间写法；text 字段（温度范围等）不在此列。
    if field not in TEXT_FIELDS and re.match(r'^\s*\d+(?:\.\d+)?\s*[-~—]\s*\d+', s):
        return False, '值「%s」是筛选分桶区间，非具体参数' % s[:20]
    need = NEED_UNIT.get(field)
    if need and not re.search(need, s):
        return False, '值「%s」不含本字段要求的单位（疑串行错标）' % s[:20]
    n = num_of(s)
    if n is None:
        return False, '无法解析数值'
    lo, hi = THRESHOLD.get(field, (None, None))
    if lo is not None and not (lo <= n <= hi):
        return False, '数值 %s 超出合理区间 [%s, %s]（疑单位错标）' % (n, lo, hi)
    return True, str(n)


def normalize(raw):
    for cn, en in UNIT_PAIRS:
        raw = raw.replace(cn, en)
    # 尺寸分隔符归一：第三方常写半角 x（595x595x520mm），库内口径是 ×
    raw = re.sub(r'(?<=\d)\s*[xX]\s*(?=\d)', '×', raw)
    return raw.strip()


def pick(field, specs, names=None):
    """按映射表从规格表取值。text 字段保留原文，number 字段取数值。

    2026-10-04 微波炉批次修了一个潜伏 bug：main() 里算好的 plan
    （ALIAS 展开，如 产品功率→input_power）从未传进来，pick 一直按
    FIELD_MAP.get(本站字段名) 字面取源字段族 —— 目标字段名与源字段族名
    不一致的映射（heat_power、input_power 等）全部静默落空。
    现在显式传入展开后的源字段名候选。
    """
    for name in (names or FIELD_MAP.get(field, [])):
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


def pick_year(specs):
    """从「上市时间」解析年份与月份。第三方写法有「2025年,3月」「2025-03」「2025年」几种。"""
    raw = specs.get('上市时间') or ''
    m = re.search(r'(19|20)\d{2}', str(raw))
    if not m:
        return {}
    y = int(m.group(0))
    out = {'year': y}
    mm = re.search(r'(?:年|,|-|/)\s*(\d{1,2})\s*月?', str(raw)[m.end():])
    if mm and 1 <= int(mm.group(1)) <= 12:
        out['month'] = int(mm.group(1))
    return out


def pick_price(specs):
    """从「参考价」取整数价格。第三方写成「￥2499」「¥2,499 元」。"""
    for k in ('参考价:', '参考价', '市场价', '价格'):
        if k in specs:
            m = re.search(r'(\d[\d,]*(?:\.\d+)?)', str(specs[k]).replace(',', ''))
            if m:
                n = float(m.group(1))
                if 49 <= n <= 999999:
                    return int(n), '%s=%s' % (k, specs[k])
    return None, None


def plan_for(schema_keys):
    """把 FIELD_MAP 展开成 {本站字段: [第三方字段名]}，只保留该品类 schema 里存在的 key。"""
    out = {}
    for src, names in FIELD_MAP.items():
        if src.startswith('_'):
            continue
        for cand in ALIAS.get(src, [src]):
            if cand in schema_keys:
                out.setdefault(cand, [])
                out[cand].extend(n for n in names if n not in out[cand])
                break
    return out


def drop_suspicious_duplicates(results):
    """剔除「同品牌同尺寸但型号不同」的存疑值。

    实测发现：松井 CFZ-40S（960L/D）与 CFZ-30S（720L/D）是两台不同除湿量的机器，
    pconline 却给两者同一个「外型尺寸 1567×720×1896mm」——第三方复制粘贴导致的错标。
    这类值写进库会污染横向比较（用户在按尺寸筛选时会把两款不同机型当成同一款）。

    判定不用「区分性字段」（dehumid/power/flux 这些品类各不相同，枚举维护不起）：
    **同品类同品牌下，若两款的型号不同却给出完全相同的尺寸，至少有一方是错的，两方都丢。**
    这是纯结构判定，不依赖任何品类知识，也不会误伤同型号的合法重复收录
    （那类已被 lint 的「型号共用」规则覆盖）。
    """
    by_key = {}
    for (cid, pid), fills in results.items():
        if 'size' not in fills:
            continue
        p = read_lib(cid).get(pid)
        if not p:
            continue
        key = (cid, p.get('brand'), fills['size'][0])
        by_key.setdefault(key, []).append((pid, p, fills))

    dropped = []
    for (cid, brand, size), group in by_key.items():
        if len(group) < 2:
            continue
        for i in range(len(group)):
            for j in range(i + 1, len(group)):
                pid_a, pa, fa = group[i]
                pid_b, pb, fb = group[j]
                ma = str(pa.get('model_code') or '').strip()
                mb = str(pb.get('model_code') or '').strip()
                # 型号相同 -> 可能是同款的合法重复收录，不判；型号为空 -> 无法判，放过
                if not ma or not mb or ma == mb:
                    continue
                for pid, fills in ((pid_a, fa), (pid_b, fb)):
                    if 'size' in fills:
                        dropped.append((cid, pid, 'size',
                                        '与同品牌另一型号「%s」尺寸完全相同，疑第三方错标'
                                        % (mb if pid == pid_a else ma)))
                        del fills['size']
                break
    return dropped


def read_lib(cid):
    return {p['id']: p for p in json.load(open(dp('data/%s/products.json' % cid), encoding='utf-8'))}


# 本地第三方规格缓存：{pconline 商品 id: {字段: 值}}
def load_cache():
    out = {}
    for f in glob.glob(dp('data/_cache/brand-*.json')):
        try:
            d = json.load(open(f, encoding='utf-8'))
        except Exception:
            continue
        for it in (d if isinstance(d, list) else []):
            if it.get('id') and (it.get('specs') or {}):
                # 第三方页面里 m³ 会被转义成 m&#179;，不解转义单位守卫会全部失配
                out.setdefault(str(it['id']), {}).update(
                    {k: html.unescape(str(v)) for k, v in it['specs'].items()})
    # 2026-10-04 微波炉批次新增：单品缓存 pconline-<品类>-<品牌>-<id>.json
    #（此前手工抓取落盘的整页规格，字段比 brand-*.json 全：多「产品尺寸/重量/内腔尺寸」）
    for f in glob.glob(dp('data/_cache/pconline-*-[0-9]*.json')):
        m = re.search(r'pconline-[a-z_]+-[a-z]+-(\d+)\.json$', f)
        if not m:
            continue
        try:
            d = json.load(open(f, encoding='utf-8'))
        except Exception:
            continue
        if isinstance(d, dict) and d:
            out.setdefault(m.group(1), {}).update(
                {k: html.unescape(str(v)) for k, v in d.items()})
    return out


def pid_of(url):
    m = re.search(r'/([0-9]+)_detail\.html', url or '')
    return m.group(1) if m else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dry', action='store_true')
    ap.add_argument('--cat', help='只处理某品类')
    ap.add_argument('--limit', type=int, default=0, help='每品类最多处理多少条（0=不限）')
    args = ap.parse_args()

    targets = []
    for f in sorted(glob.glob(dp('data/*/schema.json'))):
        cid = os.path.basename(os.path.dirname(f))
        if args.cat and cid not in args.cat.split(','):
            continue
        s = json.load(open(f, encoding='utf-8'))
        keys = {x['key'] for x in s['fields']}
        plan = plan_for(keys)
        if 'year' in keys:
            plan['year'] = ['上市时间']
        if 'month' in keys:
            plan['month'] = ['上市时间']
        for p in json.load(open(dp('data/%s/products.json' % cid), encoding='utf-8')):
            holes = sorted(k for k in plan if p.get(k) in BLANK)
            if not holes:
                continue
            u = p.get('verify_url') or ''
            if 'g.pconline.com.cn/product/' not in u:
                continue
            # 把该品类展开后的映射一起带上：job 里按它取源字段（修 ALIAS 落空 bug）
            targets.append((cid, p['id'], u, holes, dict(plan)))
    if args.limit:
        seen = Counter()
        keep = []
        for t in targets:
            if seen[t[0]] < args.limit:
                keep.append(t); seen[t[0]] += 1
        targets = keep

    cache = load_cache()
    hits = sum(1 for t in targets if pid_of(t[2]) in cache)
    print('待处理 %d 条产品（%d 条缓存已命中，走离线解析；%d 条需联网）'
          % (len(targets), hits, len(targets) - hits))
    done = [0]
    results = {}

    def job(t):
        cid, pid, url, holes, plan = t
        specs = cache.get(pid_of(url)) or fetch_specs(url)
        done[0] += 1
        if done[0] % 50 == 0:
            print('  %d/%d' % (done[0], len(targets)), flush=True)
        if not specs:
            return None
        fills = {}
        for k in holes:
            if k in ('year', 'month'):
                ym = pick_year(specs)
                if k in ym:
                    fills[k] = (ym[k], '上市时间=%s' % specs.get('上市时间'))
            elif k == 'official_price':
                v, why = pick_price(specs)
                if v is not None:
                    fills[k] = (v, why)
            else:
                v, why = pick(k, specs, plan.get(k))
                if v is not None:
                    fills[k] = (v, why)
        return (cid, pid, fills) if fills else None

    with ThreadPoolExecutor(max_workers=2) as ex:
        for r in ex.map(job, targets):
            if r:
                results[(r[0], r[1])] = r[2]

    dropped = drop_suspicious_duplicates(results)
    if dropped:
        print('\n⚠ 剔除 %d 处存疑值：' % len(dropped))
        for cid, pid, fieldname, why in dropped[:10]:
            print('   %s/%s 的 %s：%s' % (cid, pid, fieldname, why))

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