# -*- coding: utf-8 -*-
"""微波炉补全批次 · 人工把关层（在 fill-mi-official / fill-params 产出的草稿之上）。

2026-10-04 会话用。职责：
  1. 剔除自动回填中的可疑值（阈值拦不住的：命名矛盾、跨源冲突、疑似复制粘贴）；
  2. 写入 ZOL 参考价 / 老板官网参数等脚本覆盖不到的补全；
  3. 为 21 张裸卡写 pros/cons（只引用已入库/本批次入库参数与官方文案，不引入参数表外数字）；
  4. 统一重写 change_log / verify_source / verify_date / updated_at。
每处改动都写明来源与理由；剔除的值记剔除理由，不悄悄丢弃。
"""
import json, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding='utf-8')
D = '2026-10-04'
DRAFT = os.path.join(ROOT, 'data', '_draft', 'microwave')
LIB = json.load(open(os.path.join(ROOT, 'data', 'microwave', 'products.json'), encoding='utf-8'))
BASE = {p['id']: p for p in LIB}

ZOL = json.load(open(os.path.join(ROOT, 'data', '_cache', 'zol-microwave.json'), encoding='utf-8'))


def zol_price(ours):
    return ZOL[ours]['price'], ZOL[ours]['param_url'] or ZOL[ours].get('param_url')


# —— 剔除自动回填的可疑值：{产品id: {字段: 理由}} ——
DROPS = {
    # 格兰仕 KDES/G90 系列命名疑编码容量（KDES85→85L?、KDES50→50L?、Q26→26L?），
    # pconline 容量与命名全部矛盾，且两两互斥，宁缺勿错
    'galanz_1927507': {'capacity': 'pconline 容量 50L 与格兰仕 KDES85 型号命名矛盾，宁缺勿错'},
    'galanz_1927527': {'capacity': 'pconline 容量 20L 与格兰仕 KDES50 型号命名矛盾，宁缺勿错'},
    'galanz_1912287': {'capacity': 'pconline 容量 25L 与格兰仕 Q26 命名（26L）矛盾，宁缺勿错'},
    # pconline 1350W 与 ZOL 1380W 冲突（NN-JK200W），宁缺勿错
    'panasonic_1068527': {'input_power': 'pconline 1350W 与 ZOL 1380W 冲突，宁缺勿错'},
    # 老板 WZKQS-36-CQ9363A：pconline 41L/2950W 与老板官网 CQ38-i7（41L/2950W）完全相同，
    # 且自家命名 WZKQS-36 疑指 36L——疑似把 CQ38-i7 的参数复制到了本条
    'robam_1823487': {
        'capacity': 'pconline 41L 与老板命名 WZKQS-36（疑指 36L）矛盾，且与官网 CQ38-i7 容积完全相同，疑复制粘贴错标',
        'input_power': 'pconline 2950W 与官网 CQ38-i7 额定功率完全相同，疑复制粘贴错标',
    },
    # 老板 CQ928：pconline 73L 实为老板 C92-U2P 的容积（同为 3450W，第三方错配）；
    # 官网与苏宁参数页均为 65L（完整型号 ZKQC-65-CQ928）
    'robam_2779639': {'capacity': 'pconline 73L 与老板官网/苏宁参数页 65L（完整型号 ZKQC-65-CQ928）矛盾，弃 pconline'},
}

# —— 手工补全：{产品id: (字段, 值, 来源说明)} ——
ADDS = {
    # 老板官网（robam.com/product/detail/746，SSR 标题已直抓核验）+ 苏宁参数页
    'robam_2779639': [
        ('capacity', 65, '老板官网 CQ928 产品页（65L，完整型号 ZKQC-65-CQ928）'),
        ('year', 2023, '老板官网/苏宁参数页「上市时间 2023年7月」'),
        ('control', '触控式', '老板官网 CQ928 产品页「操作方式 触控式」'),
    ],
    # 老板官网 CQ38-i7 产品页（robam.com/product/detail/998）：容积 41L、额定功率 2950W
    'robam_2780059': [
        ('input_power', 2950, '老板官网 CQ38-i7 产品页「额定功率 2950W」'),
    ],
    # ZOL 参考价（detail.zol.com.cn 实抓，价格胶囊）
    'midea_1513087': [('official_price', 7749, '中关村在线参考报价')],
    'midea_1513147': [('official_price', 4599, '中关村在线参考报价')],
    'midea_1512987': [('official_price', 4599, '中关村在线参考报价')],
    'midea_1513027': [('official_price', 3799, '中关村在线参考报价')],
    'galanz_1590687': [
        ('official_price', 3699, '中关村在线参考报价'),
        ('control', '触摸式/旋钮控制', '中关村在线参数页「操控方式」'),
    ],
    'robam_1115201': [('official_price', 7699, '中关村在线参考报价')],
    'robam_1115202': [('official_price', 6299, '中关村在线参考报价')],
    'panasonic_1068716': [('official_price', 6999, '中关村在线参考报价（页面型号 NN-CS1000，与本站 NN-CS1000XPE 同系列）')],
    'panasonic_1068717': [('official_price', 3299, '中关村在线参考报价')],
    'panasonic_1068527': [
        ('official_price', 3499, '中关村在线参考报价'),
        ('size', '494×476×375mm', '中关村在线参数页「产品尺寸 494*476*375mm」（x→× 格式订正）'),
    ],
    # 小米商城商品页链接（product_id 来自本地商城搜索缓存按名反查）
    'mw_p1': [('verify_url', 'https://www.mi.com/shop/buy/detail?product_id=1230802829',
               '小米商城商品页（product_id 来自官方搜索缓存）')],
    'mw_steam_bake': [('verify_url', 'https://www.mi.com/shop/buy/detail?product_id=1230800421',
                       '小米商城商品页（product_id 来自官方搜索缓存）')],
    'mw_steam_bake_p1': [('verify_url', 'https://www.mi.com/shop/buy/detail?product_id=1230803393',
                          '小米商城商品页（product_id 来自官方搜索缓存）')],
}

# —— 裸卡卖点（21 款）：只引用已入库/本批次入库参数与官方页文案 ——
PROSCONS = {
    'mw_bake_1': (
        ['微烤一体，一台两用', '米家智能互联', '入门价位友好'],
        ['容量与功率等参数官方公开有限'],
    ),
    'midea_1513087': (
        ['85L双腔超大容量', '3150W大功率预热快', '嵌入式安装与橱柜融为一体', '支持APP远程操控'],
        ['体积庞大，小厨房难以安置', '售价较高，预算门槛不低'],
    ),
    'midea_1513147': (
        ['72L大容量', '3300W大功率', '嵌入式蒸烤一体', '支持APP远程操控'],
        ['嵌入式安装需预留橱柜空间', '售价较高'],
    ),
    'midea_1512987': (
        ['50L容量满足家庭烘焙需求', '3200W大功率', '嵌入式安装节省台面空间'],
        ['嵌入式安装需预留橱柜空间'],
    ),
    'midea_2478419': (
        ['台式免安装，摆放灵活', '石墨烯热管导热高效', '微蒸烤多功能合一', '23L容量适合小家庭'],
        ['容量较小，不适合大批量烘焙'],
    ),
    'midea_1513027': (
        ['34L容量适中', '3100W大功率', '嵌入式蒸烤一体', '支持APP远程操控'],
        ['嵌入式安装需预留橱柜空间'],
    ),
    'galanz_1927507': (
        ['2600W额定输入功率', '机械控温操作直观', '嵌入式蒸烤一体设计'],
        ['机械控温精度一般'],
    ),
    'galanz_1927527': (
        ['2200W额定输入功率', '电子控温更精准'],
        ['容量与尺寸等关键规格公开有限'],
    ),
    'galanz_1912287': (
        ['2100W额定输入功率', '蒸烤一体多功能', '黑色外观经典耐看'],
        ['容量各渠道口径不一，选购前需核实'],
    ),
    'galanz_1927587': (
        ['20L紧凑机身，小厨房友好', '1400W额定输入功率', '机械控温操作简单'],
        ['机械控温精度一般', '容量较小不适合大家庭'],
    ),
    'galanz_1590687': (
        ['26L容量满足日常烘焙', '1600W额定输入功率', '电子控温更精准', '触摸+旋钮双操控'],
        ['售价较高'],
    ),
    'robam_2779639': (
        ['65L大容量', '3450W大功率', 'AI智瞳识别食材', '蒸烤炸一体'],
        ['售价较高，预算门槛不低', '65L体积庞大需预留充足橱柜空间'],
    ),
    'robam_2780059': (
        ['41L容量', '2950W大功率', '微蒸烤一体多功能料理'],
        ['嵌入式安装需预留橱柜空间'],
    ),
    'robam_1115201': (
        ['60L大容量', '2600W额定输入功率', '内置12个自动菜单', '支持ROKI智能生态'],
        ['售价较高，预算门槛不低'],
    ),
    'robam_1115202': (
        ['60L大容量', '2600W额定输入功率', '嵌入式电烤箱经典配置'],
        ['售价较高'],
    ),
    'robam_1823487': (
        ['蒸烤炸一体多功能', '标配炸烤网架与玻璃烤盘', '嵌入式安装'],
        ['机械控温精度一般'],
    ),
    'panasonic_1068716': (
        ['30L大容量', '彩色触摸屏操控', '平板式底盘易清洁', '微蒸烤一体多能'],
        ['售价较高，预算门槛不低'],
    ),
    'panasonic_2478499': (
        ['28L容量', '上烤下蒸立体料理', '微蒸烤炸炖一体', '变频微波加热更均匀'],
        ['功能丰富，操作逻辑需要适应'],
    ),
    'panasonic_1590787': (
        ['31L容量', '蜂巢循环加热', '双直喷蒸汽', '蒸烤炸一体'],
        ['无微波功能，热饭需改用蒸制'],
    ),
    'panasonic_1068717': (
        ['30L大容量', '蒸烤炸多功能合一', '机械式操控简单直观'],
        ['机械式操控不如触控精准', '售价较高'],
    ),
    'panasonic_1068527': (
        ['30L容量', '台式免安装', '蒸烤炸一体', '494mm宽幅摆放灵活'],
        ['售价较高'],
    ),
}

# 来源登记：产品 -> 追加到 verify_source 的来源
SRC_APPEND = {
    'midea_1513087': ['中关村在线'], 'midea_1513147': ['中关村在线'],
    'midea_1512987': ['中关村在线'], 'midea_1513027': ['中关村在线'],
    'galanz_1590687': ['中关村在线'], 'robam_1115201': ['中关村在线'],
    'robam_1115202': ['中关村在线'], 'robam_2779639': ['老板官网', '中关村在线'],
    'robam_2780059': ['老板官网'],
    'panasonic_1068716': ['中关村在线'], 'panasonic_1068717': ['中关村在线'],
    'panasonic_1068527': ['中关村在线'],
}


def fmt(v):
    if isinstance(v, list):
        return '、'.join(v)
    return str(v)


def main():
    os.makedirs(DRAFT, exist_ok=True)
    touched = []
    for pid in sorted(set(list(DROPS) + list(ADDS) + list(PROSCONS))):
        src = os.path.join(DRAFT, pid + '.json')
        item = json.load(open(src, encoding='utf-8')) if os.path.exists(src) else dict(BASE[pid])
        base = BASE[pid]
        entries, drops = [], []

        # 1) 剔除
        for k, why in DROPS.get(pid, {}).items():
            if k in item and item.get(k) not in (None, '查不到', '—', ''):
                cur = item.pop(k)
                drops.append('%s=%s（理由：%s）' % (k, cur, why))

        # 2) 手工补全
        for k, v, why in ADDS.get(pid, []):
            item[k] = v
            entries.append('补全 %s=%s（来源：%s）' % (k, fmt(v), why))

        # 3) 卖点
        if pid in PROSCONS:
            pros, cons = PROSCONS[pid]
            item['pros'], item['cons'] = pros, cons
            entries.append('补写卖点 pros %d 条 / cons %d 条（依据：已入库参数与官方规格页文案，未引入参数表外数值）'
                           % (len(pros), len(cons)))

        # 4) 来源与标注
        extra_src = SRC_APPEND.get(pid, [])
        if extra_src:
            old = base.get('verify_source') or []
            item['verify_source'] = list(dict.fromkeys(list(old) + extra_src))
        item['verify_date'] = D
        item['updated_at'] = D
        # 状态只升不降：本批次不降任何状态（ competitors 已是「已核验（第三方）」，mi 保持原状）
        item['verify_status'] = base.get('verify_status') or item.get('verify_status')

        # 5) change_log 重建（base 原文 + 本批次条目）
        cl = base.get('change_log') or ''
        parts = [cl] if cl else []
        if entries:
            parts.append('%s %s' % (D, '；'.join(entries)))
        for d in drops:
            parts.append('%s 剔除 %s' % (D, d))
        item['change_log'] = '；'.join(p for p in parts if p)

        with open(os.path.join(DRAFT, pid + '.json'), 'w', encoding='utf-8', newline='\n') as fh:
            json.dump(item, fh, ensure_ascii=False, indent=2)
            fh.write('\n')
        touched.append(pid)
        print('%-18s +%d 项补全, %d 项剔除' % (pid, len(entries), len(drops)))
    print('\ntotal drafts:', len(touched))


if __name__ == '__main__':
    main()
