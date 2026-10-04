#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""A2 路（环境电器）补数：小米官方来源的 verify_url / 官方价 + pros/cons。

三件事，都写进 data/_draft/<品类>/<id>.json（草稿区，flow:submit 前不入库）：

  ① **补 verify_url**：本路原先有 26 款小米产品 `verify_url` 是「查不到」，
     定位不到商城 product_id 就没法调官方 API。2026-10-04 用
     `python scripts/mi-store-enumerate.py <关键词>`（Playwright，本机装了 Python 版）
     重新枚举商城搜索页，拿到在售商品的 productId，按**商品名逐字对上**后写进
     verify_url。下架型号（商城已无此商品）保持「查不到」，不猜。

  ② **补官方价**：拿到 product_id 后调
     `api2.order.mi.com/product/view?product_id=<id>&version=2`（必须带 Referer），
     `price` → official_price、`market_price` → ref_price（两者相等不写，那不是促销价）。
     仅在字段为空时写入，不覆盖已有值。

  ③ **补 pros/cons**：由「官方卖点文案（`product_info.product_desc`）」+
     「库内已入库参数」推导。文案里的官方数值同时写进对应 schema 字段（如
     2000W → power、17kPa → suction、18小时 → runtime）。
     **不引入参数表里没有的数字**；单位口径与 schema 字段不一致的（商城风量用 m³/h，
     本站 airflow 用 m³/min）不做换算，只在 pros 里照抄官方口径并注明。

用法：
    python scripts/a2-refill-xiaomi.py --dry     # 只看会改什么
    python scripts/a2-refill-xiaomi.py           # 写入 data/_draft/
"""
import argparse
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'scripts', 'lib'))
D = '2026-10-04'
CATS = ['fan', 'heater', 'dehumidifier', 'humidifier', 'mite-remover']

# 枚举商城搜索页后按商品名逐字对上的映射。
# 每条都要能在 data/_cache/search-<关键词>.json 里找到同名商品；
# 对不上的（已下架）不在此表，保持「查不到」。
XIAOMI_IDS = {
    # —— heater（商城关键词「暖风机」「踢脚线取暖器」「电暖器」「油汀」）
    'heater/ht_kick_flame': 1224200046,     # 米家石墨烯踢脚线电暖器 仿真火焰版
    'heater/ht_kick_old': 1230800853,       # 米家踢脚线电暖器 2
    'heater/ht_smart_graphene': 1213900034,  # 米家石墨烯智能电暖器
    'heater/ht_fan_c': 1230808966,          # 米家石墨烯暖风机 C
    'heater/ht_fan_g': 1230800847,          # 米家石墨烯暖风机
    'heater/ht_fan_old': 1230800854,        # 米家暖风机
    'heater/ht_fan_desk': 1203800023,       # 米家桌面暖风机
    'heater/ht_oil': 1230802731,            # 米家石墨烯油汀取暖器
    'heater/ht_blanket': 1230805271,        # 米家智能电热毯 单人款 1.8*0.8m
    # —— humidifier（商城关键词「加湿器」「无雾加湿器」）
    'humidifier/hm_fogless_1200': 1230801367,  # 米家无雾加湿器3[1200]
    'humidifier/hm_fogless_800': 1230802701,   # 米家无雾加湿器3[800]
    # —— mite-remover（商城关键词「除螨仪」）
    'mite-remover/mr_3pro': 1230806798,     # 米家除螨仪3 Pro
    'mite-remover/mr_2pro': 1230803825,     # 米家除螨仪2 Pro
    'mite-remover/mr_pro': 1224500319,      # 米家除螨仪 Pro
    'mite-remover/mr_2': 1230801736,        # 米家除螨仪2
    # 商城已下架、反查不到，保持「查不到」：
    #   dehumidifier/dh_max（米家除湿机 Max）、humidifier/hm_pure_pro、hm_pure_2lite、
    #   fan 的 BPLDS04DM/07DM/08DM、JLLDS01DM 与「落地扇 1X」原版、电池版落地扇
}

# pros/cons 文案（官方卖点文案 + 库内参数）由 a2-content-*.json 提供；
# 校验其中出现的数字必须能在该产品的库内参数或官方文案里找到。


def dp(rel):
    return os.path.join(ROOT, rel)


def load(p):
    with open(p, encoding='utf-8') as f:
        return json.load(f)


def dump(p, obj):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, 'w', encoding='utf-8', newline='\n') as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write('\n')


def empty(v):
    return v is None or v == '' or v == '—' or v == '查不到' or (isinstance(v, list) and not v)


def detail(pid):
    """读本地 product-<id>.json 缓存（由 `npm run mi:detail` 生成），没有就返回 None。"""
    p = dp('data/_cache/product-%s.json' % pid)
    return load(p) if os.path.exists(p) else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dry', action='store_true')
    args = ap.parse_args()

    contents = {}
    for c in CATS:
        f = dp('data/_cache/a2-content-%s.json' % c)
        if os.path.exists(f):
            contents[c] = load(f)

    n_files = 0
    n_fields = 0
    for cid in CATS:
        lib = load(dp('data/%s/products.json' % cid))
        draft_dir = dp('data/_draft/%s' % cid)
        cont = contents.get(cid, {})
        for base in lib:
            pid = base['id']
            # 草稿里已有的改动优先（fill-params / fill-mi-official 已写进去的）
            df = os.path.join(draft_dir, '%s.json' % pid)
            item = load(df) if os.path.exists(df) else dict(base)
            fills = {}

            # ① verify_url
            if base.get('brand') == '小米':
                key = '%s/%s' % (cid, pid)
                if empty(item.get('verify_url')) and key in XIAOMI_IDS:
                    fills['verify_url'] = 'https://www.mi.com/shop/buy/detail?product_id=%s' % XIAOMI_IDS[key]

            # ② 官方价
            if base.get('brand') == '小米':
                m = re.search(r'product_id=(\d+)', fills.get('verify_url') or item.get('verify_url') or '')
                if m:
                    d = detail(m.group(1))
                    if d:
                        if empty(item.get('official_price')) and d.get('price'):
                            fills['official_price'] = int(float(d['price']))
                        if empty(item.get('ref_price')) and d.get('marketPrice') and \
                                str(d['marketPrice']) != str(d['price']):
                            fills['ref_price'] = int(float(d['marketPrice']))

            # ③ pros/cons + 官方文案 / ZOL 里的数值
            #    数值字段只要目标字段为空就填（与 pros/cons 是否已写无关），
            #    pros/cons 只在两项同时为空（裸卡）时才写。
            c = cont.get(pid)
            if c:
                for k, v in (c.get('fields') or {}).items():
                    if empty(item.get(k)):
                        fills[k] = v
                if empty(item.get('pros')) and empty(item.get('cons')):
                    fills['pros'] = c['pros']
                    fills['cons'] = c['cons']
                if fills:
                    fills['_source_note'] = c['_src']

            if not fills:
                continue
            n_files += 1
            plain = {k: v for k, v in fills.items() if not k.startswith('_')}
            n_fields += len(plain)
            print('%s/%s: %s' % (cid, pid, '，'.join(
                '%s=%s' % (k, json.dumps(v, ensure_ascii=False) if not isinstance(v, list)
                 else '[' + '；'.join(v) + ']')
                for k, v in plain.items())))
            if args.dry:
                continue
            item.update(plain)
            srcs = item.get('verify_source')
            extra = ['小米商城'] if fills.get('verify_url') or (
                base.get('brand') == '小米' and any(k in fills for k in ('official_price', 'ref_price'))) else []
            if isinstance(srcs, list):
                item['verify_source'] = sorted(set(srcs) | set(extra))
            item['verify_date'] = D
            item['updated_at'] = D
            # 幂等：先剥掉本脚本上次追加的段落，再重新追加
            prev = re.sub(r'；?%s A2 路补录：.*$' % re.escape(D), '',
                          item.get('change_log') or '')
            desc = []
            if 'verify_url' in plain:
                desc.append('补官方商城链接')
            for k in ('official_price', 'ref_price'):
                if k in plain:
                    desc.append('%s=%s' % (k, plain[k]))
            for k in ('pros', 'cons'):
                if k in plain:
                    desc.append('%s（%d 条）' % (k, len(plain[k])))
            for k, v in plain.items():
                if k not in ('verify_url', 'official_price', 'ref_price', 'pros', 'cons'):
                    desc.append('%s=%s' % (k, v))
            note = fills.get('_source_note') or '小米商城 API'
            item['change_log'] = '%s；%s A2 路补录：%s。依据：%s' % (
                prev, D, '，'.join(desc), note)
            dump(df, item)

    print('\n%s：%d 款产品 / %d 个字段' % ('（dry）' if args.dry else '已写入 data/_draft/', n_files, n_fields))
    return 0


if __name__ == '__main__':
    sys.exit(main())