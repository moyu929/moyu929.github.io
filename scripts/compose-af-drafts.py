# -*- coding: utf-8 -*-
"""空气炸锅品类订正稿合成（2026-10-04 批次，采集 Agent A）。

在 fill-params.py / fill-mi-official.py 产出的草稿基础上，合并本批人工核验的增量：

1. **字符串带单位数值归一**：竞品 capacity/power 库内是「7.3L」「1250W」字符串，
   schema 声明 number —— 顺手归一，change_log 注明「格式订正」。
2. **可疑值剔除**：海尔 A-M03BG 第三方功率「120W」（空气炸锅功率域 1000-2500W，
   疑脱漏一位），按「宁缺勿错」写回 查不到。
3. **ref_price**：太平洋产品报价参考价（data/_cache/brand-airfryer-*.json 顶层 price），
   按 2026-10-04 分工文档只能进 ref_price，不进 official_price。
4. **official_price**：ZOL 当前零售价（仅 ZOL 收录且名称与库内一致的 5 款），
   注明来源 URL。
5. **temp_max**：ZOL param.shtml「烹饪温度 80-200℃」→ 取上限 200（列语义即最高温）。
6. **pros/cons**：裸卡补卖点，只引用已入库参数与商城在售价，不引入新数字。
7. **审核字段**：verify_date/updated_at=2026-10-04；verify_source 追加；
   verify_status 只升不降 —— 仅当 ZOL 与太平洋在 ≥2 个字段上互证一致时升「已核验（多源）」。

用法：python scripts/compose-af-drafts.py [--dry]
"""
import json, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding='utf-8')
D = '2026-10-04'
CAT = 'air-fryer'
BLANK = ('查不到', '—', '', None, '-')

# ZOL 当前零售价（2026-10-04 逐款核对：ZOL 商品名与库内产品名一致才收录）
ZOL_PRICE = {
    'joyoung_1503867': (999, 'https://detail.zol.com.cn/AirFryer/index1399672.shtml'),
    'joyoung_1504127': (599, 'https://detail.zol.com.cn/AirFryer/index1418981.shtml'),
    'joyoung_1610047': (879, 'https://detail.zol.com.cn/AirFryer/index1399695.shtml'),
    'philips_1330371': (1697, 'https://detail.zol.com.cn/AirFryer/index1353530.shtml'),
    'philips_1506787': (1499, 'https://detail.zol.com.cn/AirFryer/index1400550.shtml'),
}

# ZOL 与太平洋 ≥2 字段互证一致 → 可升「已核验（多源）」
# （philips_1330371 容量冲突：ZOL 3.5L vs 太平洋/官方口径 7.3L —— 不升，冲突已记 change_log）
MULTI_SOURCE = {'joyoung_1503867', 'joyoung_1504127', 'joyoung_1610047', 'philips_1506787'}

# 太平洋参考价里的可疑值（不写入，列汇报）
SUSPECT_DROP = {
    # 空气炸锅额定功率域 1000-2500W，「120W」疑脱漏一位（1200W），宁缺勿错
    ('haier_1907767', 'power'): '120W',
    # 太平洋「产品尺寸 320×312×31 5mm」中间多出空格，段位残缺不可考
    ('midea_1508047', 'size'): '320×312×31 5mm',
}

# 两家权威第三方冲突、无法裁决的字段：宁缺勿错，写回 查不到
# （joyoung_1504127 整机重量两家一致 4.7kg，可证是同一产品，但尺寸互斥：
#   太平洋 275×300×290mm vs ZOL 337×305×287mm，取谁都是猜）
CONFLICTS = {
    ('joyoung_1504127', 'size'): ('太平洋 275×300×290mm', 'ZOL 337×305×287mm'),
}

# ZOL param.shtml 烹饪温度行（80-200℃ → 取上限；列语义 temp_max=最高温度）
ZOL_TEMP = {'joyoung_1504127': 200, 'philips_1330371': 200}

# 裸卡卖点：只引用已入库参数（容量/功率/类型/炸篮/在售价），
# 「经典款无可视窗」依据 type=经典炸锅 与 可视炸锅/蒸烤一体的类型划分。
PROS_CONS = {
    'af_p1_65': (['可视窗，烹饪过程一目了然', '6.5L大容量，适合多人家庭', '商城在售¥369'],
                 ['功率等关键参数查不到']),
    'af_s1_6l': (['可视窗设计', '6L容量适合3-5人', '商城在售¥269'],
                 ['功率等关键参数查不到']),
    'midea_1508047': (['7.3L大容量，适合多人家庭', '不粘涂层炸篮，方便清洁'],
                      ['功率1250W在7.3L容量下偏保守']),
    'midea_2009267': (['4.2L容量适合2-4人小家庭', '不粘涂层炸篮，方便清洁'],
                      ['经典款无可视窗', '4.2L容量不适合多人']),
    'midea_2776339': (['6.5L大容量，适合多人家庭', '2000W大火力，升温快', '不粘涂层炸篮，方便清洁'],
                      ['经典款无可视窗']),
    'midea_2529039': (['6.5L大容量，适合多人家庭', '2100W大功率，升温快', '不粘涂层炸篮，方便清洁'],
                      ['经典款无可视窗']),
    'midea_2120627': (['5L容量适中，适合3-4人', '2000W大火力，升温快', '不粘涂层炸篮，方便清洁'],
                      ['经典款无可视窗']),
    'supor_2601899': (['蒸烤一体，一机多用', '6L大容量，适合多人家庭', '2100W大功率，升温快'],
                      ['蒸+烤双功能体积较大']),
    'supor_1926667': (['5L容量适合3-4人', '1200W低功耗', '不粘涂层炸篮，方便清洁'],
                      ['1200W功率偏低，升温较慢', '经典款无可视窗']),
    'supor_2562419': (['6L大容量，适合多人家庭', '1700W功率均衡', '不粘涂层炸篮，方便清洁'],
                      ['经典款无可视窗']),
    'supor_2660919': (['蒸烤一体，一机多用', '6.3L大容量，适合多人家庭', '2100W大功率，升温快',
                       '金属内腔，耐用无涂层异味'],
                      ['蒸+烤双功能体积较大']),
    'supor_2562439': (['蒸烤一体，一机多用', '5L容量适合3-4人', '1200W低功耗'],
                      ['1200W功率偏低，升温较慢']),
    'joyoung_1504007': (['5L容量适合3-4人', '1200W低功耗', '不粘涂层炸篮，方便清洁'],
                        ['1200W功率偏低，升温较慢', '经典款无可视窗']),
    'joyoung_1503867': (['4L紧凑容量，小厨房友好', '2000W大火力，升温快', '不粘涂层炸篮，方便清洁'],
                        ['4L容量较小，不适合多人']),
    'joyoung_1504127': (['6.5L大容量，适合多人家庭', '最高200℃高温烘烤'],
                        ['1400W功率在6.5L容量下偏低']),
    'joyoung_1153848': (['九阳经典炸锅机型'],
                        ['容量、功率等关键参数查不到']),
    'joyoung_1610047': (['蒸烤一体，一机多用', '5.5L容量适合3-5人', '不粘涂层炸篮，方便清洁'],
                        ['1400W功率偏低，升温较慢']),
    'haier_1151007': (['海尔经典炸锅机型'],
                      ['容量、功率等关键参数查不到']),
    'haier_1612567': (['7L大容量，适合多人家庭', '不粘涂层炸篮，方便清洁'],
                      ['1360W功率在7L容量下偏低', '经典款无可视窗']),
    'haier_2693459': (['4.5L容量适合2-4人', '金属内腔，耐用无涂层异味', '1400W功率均衡'],
                      ['经典款无可视窗']),
    'haier_1907767': (['3L紧凑容量，单身/二人食', '不粘涂层炸篮，方便清洁'],
                      ['3L容量较小，不适合多人']),
    'haier_1612527': (['3.5L紧凑容量，小厨房友好', '不粘涂层炸篮，方便清洁'],
                      ['经典款无可视窗', '3.5L容量不适合多人']),
    'philips_1287387': (['高端定位机型（参考价¥2599）'],
                        ['容量、功率等关键参数查不到']),
    'philips_1330371': (['7.3L超大容量，适合多人家庭', '2225W超大功率，升温快', '最高200℃高温烘烤'],
                        ['参考价¥1799，定位高端']),
    'philips_1330393': (['飞利浦核心系列机型'],
                        ['容量、功率等关键参数查不到']),
    'philips_2009287': (['7.2L大容量，适合多人家庭', '2000W大火力，升温快', '不粘涂层炸篮，方便清洁'],
                        ['经典款无可视窗']),
    'philips_1506787': (['6.2L大容量，适合多人家庭', '2000W大火力，升温快', '不粘涂层炸篮，方便清洁'],
                        ['经典款无可视窗']),
}


def is_blank(v):
    return v in BLANK or (isinstance(v, (list, dict)) and not v)


def strip_unit(v):
    """「7.3L」「1250W」→ 7.3 / 1250。归一失败返回 None。"""
    s = str(v).strip()
    n = ''
    for ch in s:
        if ch.isdigit() or ch == '.':
            n += ch
        else:
            break
    try:
        f = float(n)
        return int(f) if f == int(f) else f
    except ValueError:
        return None


def load_pconline_prices():
    out = {}
    import glob
    for f in glob.glob(os.path.join(ROOT, 'data', '_cache', 'brand-airfryer-*.json')):
        for it in json.load(open(f, encoding='utf-8')):
            if it.get('id') and it.get('price'):
                out[str(it['id'])] = int(it['price'])
    return out


# 本站产品 id -> 太平洋规格页 id（verify_url 里抠出来的静态映射，与库内 verify_url 一致）
PCONLINE_ID = {
    'midea_1508047': '1508047', 'midea_2009267': '2009267', 'midea_2776339': '2776339',
    'midea_2529039': '2529039', 'midea_2120627': '2120627',
    'supor_2601899': '2601899', 'supor_1926667': '1926667', 'supor_2562419': '2562419',
    'supor_2660919': '2660919', 'supor_2562439': '2562439',
    'joyoung_1504007': '1504007', 'joyoung_1503867': '1503867', 'joyoung_1504127': '1504127',
    'joyoung_1153848': '1153848', 'joyoung_1610047': '1610047',
    'haier_1151007': '1151007', 'haier_1612567': '1612567', 'haier_2693459': '2693459',
    'haier_1907767': '1907767', 'haier_1612527': '1612527',
    'philips_1287387': '1287387', 'philips_1330371': '1330371', 'philips_1330393': '1330393',
    'philips_2009287': '2009287', 'philips_1506787': '1506787',
}


def main():
    dry = '--dry' in sys.argv
    lib = {p['id']: p for p in json.load(
        open(os.path.join(ROOT, 'data', CAT, 'products.json'), encoding='utf-8'))}
    prices = load_pconline_prices()
    draft_dir = os.path.join(ROOT, 'data', '_draft', CAT)
    report = {'ref_price': 0, 'official_price': 0, 'temp_max': 0, 'norm': 0,
              'suspect': 0, 'pros_cons': 0, 'status_up': 0}
    suspects = []

    for pid, (pros, cons) in PROS_CONS.items():
        base = lib[pid]
        df = os.path.join(draft_dir, pid + '.json')
        item = json.load(open(df, encoding='utf-8')) if os.path.exists(df) else dict(base)
        notes = []

        # 1. 字符串带单位数值归一（容量/功率）+ 可疑值/冲突值剔除（含尺寸）
        for k in ('capacity', 'power', 'size'):
            v = item.get(k)
            if (pid, k) in CONFLICTS and str(v) and str(v) != '查不到' and (pid, k) in CONFLICTS:
                a, b = CONFLICTS[(pid, k)]
                item[k] = '查不到'
                notes.append('剔除%s冲突值「%s」（两家第三方互斥：%s vs %s，宁缺勿错）' % (k, v, a, b))
                suspects.append((pid, k, '%s（冲突）' % v))
                report['suspect'] += 1
                continue
            if (pid, k) in SUSPECT_DROP and str(v) == SUSPECT_DROP[(pid, k)]:
                item[k] = '查不到'
                notes.append('剔除%s可疑值「%s」（%s）' % (
                    k, v, '疑脱漏一位，宁缺勿错' if k == 'power' else '段位残缺不可考'))
                suspects.append((pid, k, v))
                report['suspect'] += 1
                continue
            if k == 'size' or not isinstance(v, str) or is_blank(v):
                continue
            n = strip_unit(v)
            if n is not None:
                item[k] = n
                notes.append('%s格式订正：%s→%s' % (k, v, n))
                report['norm'] += 1

        # 2. ref_price：太平洋参考价（只补空值）
        pcid = PCONLINE_ID.get(pid)
        if pcid and pcid in prices and is_blank(item.get('ref_price')):
            item['ref_price'] = prices[pcid]
            notes.append('ref_price=%s（来源：太平洋产品报价参考价）' % prices[pcid])
            report['ref_price'] += 1

        # 3. official_price：ZOL 当前零售价（只补空值，注明 URL）
        if pid in ZOL_PRICE and is_blank(item.get('official_price')):
            price, url = ZOL_PRICE[pid]
            item['official_price'] = price
            notes.append('official_price=%s（来源：ZOL参考报价 %s）' % (price, url))
            report['official_price'] += 1

        # 4. temp_max：ZOL 烹饪温度上限
        if pid in ZOL_TEMP and is_blank(item.get('temp_max')):
            item['temp_max'] = ZOL_TEMP[pid]
            notes.append('temp_max=%s（来源：ZOL参数页「烹饪温度」上限）' % ZOL_TEMP[pid])
            report['temp_max'] += 1

        # 5. pros/cons（裸卡才写）
        if is_blank(item.get('pros')) and is_blank(item.get('cons')):
            item['pros'] = pros
            item['cons'] = cons
            notes.append('补卖点/缺点（只引用已入库参数与商城在售价）')
            report['pros_cons'] += 1

        # 6. 审核字段
        if notes:
            cl = (item.get('change_log') or '').rstrip()
            sep = '' if not cl or cl.endswith('；') else '；'
            item['change_log'] = cl + sep + '%s 补全：%s' % (D, '；'.join(notes))
            item['updated_at'] = D
            # 核查时间：本次确实重新核了价格/参数
            item['verify_date'] = D
            src = item.get('verify_source')
            add = []
            if pid in ZOL_PRICE:
                add.append('中关村在线')
            if pcid:
                add.append('太平洋电脑网')
            if isinstance(src, list):
                item['verify_source'] = sorted(set(src) | set(add))
            # 状态只升不降：仅互证一致时升「已核验（多源）」
            if pid in MULTI_SOURCE and item.get('verify_status') != '已核验（多源）':
                item['verify_status'] = '已核验（多源）'
                report['status_up'] += 1
            if not dry:
                with open(df, 'w', encoding='utf-8', newline='\n') as fh:
                    json.dump(item, fh, ensure_ascii=False, indent=2)
                    fh.write('\n')
        print(('--dry ' if dry else '') + pid, '->', '; '.join(notes) if notes else '(no change)')

    print('\n统计:', json.dumps(report, ensure_ascii=False))
    if suspects:
        print('可疑值剔除清单:', suspects)


if __name__ == '__main__':
    main()
