# -*- coding: utf-8 -*-
"""电饭煲品类补全订正稿（2026-10-04，采集 Agent A / 分支 collect/yi-rice-cooker）。

一次性策展脚本：把本轮多来源采集结果合并进 data/_draft/rice-cooker/<id>.json。
与通用脚本（fill-params / fill-mi-official）的分工：那两个产出基础草稿；
本脚本**重建**全部 32 份草稿（从库内版本出发），保证 change_log / verify 字段
一致、来源逐条可查。已包含两个通用脚本的全部产出值。

## 来源口径（SKILL.md 优先级）

  * 小米商城 API（api2.order.mi.com/product/view）   → 名称/价格（官方）
  * 小米官网规格页（www.mi.com/dianfanbao2-4l/specs）→ IH 4L 官方参数（Playwright 渲染后抓取）
  * 太平洋产品报价规格页（g.pconline.com.cn，2026-10-04 直连恢复可用）→ 参数/参考价
  * 中关村在线 ZOL（detail.zol.com.cn/rice_cooker/，cookie 过墙见 zol-fetch.py）→ 当前零售价/参数
  * pconline「参考价」只写 ref_price，禁止进 official_price（口径见竞品副分组结项 2026-10-02）；
    ZOL 当前零售价可作竞品 official_price（本轮任务配方 ⑥）。

## 本轮订正（非补全）

  * supor_1928727 额定功率 220W → 剔除（IH 机型物理上不可能，疑 220V 电压串行错标；
    ZOL/官方无该型号数据，无第二来源可定值，宁缺勿错）
  * joyoung_2183719 额定功率 220W → 1200W（ZOL 参数页与库内值冲突，
    pconline 的 220W 判为同上错标；40N1 Pro 为 IH 机型）
  * panasonic_589196 加热方式 底盘加热 → IH电磁（pconline 规格表「IH加热」，
    库内值疑录入错误；SPZ 系列为 IH 产品线）
  * panasonic_2227059 尺寸「314×258×225 mm」→「314×258×225mm」（格式归一，值不变）

用法：python scripts/curate-rice-cooker-2026-10-04.py
"""
import json, os, re, sys

sys.stdout.reconfigure(encoding='utf-8')
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D = '2026-10-04'

ZOL = json.load(open(os.path.join(ROOT, 'data/_cache/zol-rice-cooker.json'), encoding='utf-8'))


def zol_url(ours):
    r = ZOL.get(ours) or {}
    return 'https://detail.zol.com.cn/rice_cooker/index%s.shtml' % r['zol_id'] if r.get('zol_id') else None


PC = 'https://g.pconline.com.cn/product/rice_cooker'
PCX = 'https://g.pconline.com.cn/product/rice_cooker/xiaomi'

# ---- 每款产品的补全（set）/ 订正（fix）/ 卖点（pros/cons）/ 审核字段 ----
# change_log 中逐条写明来源；来源缩写：
#   商城API=小米商城商品接口(price/market_price/商品名)
#   官网规格页=www.mi.com/dianfanbao2-4l/specs（Playwright 渲染）
#   太平洋=<PC>/<品牌>/<pid>_detail.html（2026-10-04 抓取）
#   ZOL=<zol_url>（2026-10-04 抓取）
P = {}

P['rc_p1_4l'] = dict(
    set={'official_price': 999, 'ref_price': 1199,
         'power': 1345, 'size': '330×272×238mm', 'model_code': 'MFB18BM'},
    src=['小米商城API（现价 999 / 划线价 1199）', '太平洋/%s/2860391_detail.html' % PCX],
    status=None, add_src=['小米商城', '太平洋电脑网'],
)
P['rc_p1_3l'] = dict(
    set={'power': 1130, 'size': '302.5×252.5×221mm', 'model_code': 'MFB17AM', 'ref_price': 799},
    src=['太平洋/%s/2605939_detail.html（型号栏为「P1 3L(MFB17AM)」，取括号内型号，商品页标题同证）' % PCX],
    status=None, add_src=['太平洋电脑网'],
)
P['rc_ih_4l'] = dict(
    set={'power': 1430, 'size': '334×282×230mm', 'inner_pot': '合金'},
    src=['小米官网规格页 www.mi.com/dianfanbao2-4l/specs（额定功率 1430w、外形尺寸 334×282×230mm、内胆材质 合金；型号 IHFB02CM 与库内一致互证）'],
    status=None, add_src=['小米官网规格页'],
)
P['rc_n1_4l'] = dict(
    set={'size': '265×319×210mm', 'power': 650, 'model_code': 'MFB13B0', 'ref_price': 179},
    src=['太平洋/%s/2321079_detail.html' % PCX],
    status='已核验（第三方）',
    add_src=['太平洋电脑网'],
    set_url='%s/2321079_detail.html' % PCX,
    extra_log='库内官方价 169 与太平洋参考价 179 存在差异，按「只补空值不覆盖价」保留 169，待审核方复核',
)
P['rc_n1_3l'] = dict(
    set={'size': '243×296×202mm', 'power': 650, 'model_code': 'MFB13A0', 'ref_price': 169},
    src=['太平洋/%s/2290599_detail.html' % PCX, '商城API（market_price=169；现价 159 与太平洋参考价 159 互证）'],
    status='已核验（多源）', add_src=['小米商城', '太平洋电脑网'],
)
P['rc_c1_3l'] = dict(
    set={'size': '325×224×202mm'},
    src=['ZOL %s（库内功率 650W 与 ZOL 参数页一致，互证）' % zol_url('rc_c1_3l')],
    status='已核验（第三方）', add_src=['中关村在线'],
    set_url=zol_url('rc_c1_3l'),
)
P['rc_ih2'] = dict(
    set={},
    pros=['IH电磁加热', '2L/3L/4L/5L 多档容量可选（商城在售档位）', '0氟陶瓷涂层内胆，健康易洁'],
    cons=['同系列跨容量档位配置有差异，选购需逐档确认', '预约/内胆等参数官方未完整标称'],
    src=['小米商城商品页文案（product_id=10050167）'],
    status=None, add_src=[],
    skip_note='系列条目（2/3/4/5L）：尺寸/型号/功率随容量档位不同，不取单档值（太平洋 2862551/2862571/2862591/2862611 四档各异）',
)

P['rc_weiya'] = dict(
    set={'capacity': 4},
    pros=['IH电磁加热+蓄压球技术，微压焖香', '智显小黑屏，状态一目了然', 'NFC 闪连云食谱', '4L 容量'],
    cons=['微压非全压力，口感层次不及压力IH机型', '内胆材质等参数未完整标称'],
    src=['商城API（商品名「米家智能电饭煲 微压版 4L」→ 容量 4）', '小米商城商品页文案（product_id=10000353）'],
    status=None, add_src=['小米商城'],
    extra_log='库内官方价 449 为商城「起价」，锚定商品（product_id=10000353）现价 599，待审核方复核',
)
P['rc_bianya_4l'] = dict(
    set={'ref_price': 2299, 'power': 1390, 'size': '340×278×235mm', 'model_code': 'MFB17BM'},
    src=['商城API（market_price=2299）', '太平洋/%s/2736899_detail.html' % PCX],
    status=None, add_src=['小米商城', '太平洋电脑网'],
)
P['rc_s1_3l'] = dict(
    set={},
    pros=['IH电磁加热', '主打快煮，煮饭省时', '厚质内胆，蓄热均匀'],
    cons=['仅 3L 单容量，多口之家不适用', '功率/尺寸等参数官方未标称'],
    src=['小米商城商品页文案（product_id=1230802702）'],
    status=None, add_src=[],
)
P['rc_fast_5l'] = dict(
    set={'size': '270×330×253mm', 'power': 860, 'model_code': 'MFB06CM'},
    pros=['5L 大容量，适合多人家庭', '860W 大火力快煮', '五层聚能内胆', '支持 WiFi 与 NFC 智能互联', '自调节防溢'],
    cons=['底盘加热，受热均匀性不及 IH 机型'],
    src=['太平洋/%s/1672607_detail.html' % PCX, '小米商城商品页文案（product_id=1230809439；现价 349 与太平洋参考价 349 互证）'],
    status=None, add_src=['太平洋电脑网'],
)
P['rc_fast_34l'] = dict(
    set={'ref_price': 299},
    pros=['主打超快煮，节省时间', '厚质不粘内胆', '玻璃面板设计', '269 元起定价亲民'],
    cons=['底盘加热，非 IH', '3L/4L 双档参数有差异，按需选购'],
    src=['商城API（market_price=299）', '小米商城商品页文案（product_id=1230800191）'],
    status=None, add_src=['小米商城'],
    skip_note='系列条目（3L/4L）：尺寸/型号/功率随档位不同，不取单档值（3L 档太平洋型号 MFB07M 与 4L 档不同）',
)

# ---- 竞品 ----
P['midea_1568847'] = dict(
    set={'official_price': 2999, 'appoint': '24小时预约'},
    pros=['IH电磁加热，1300W 大火力', '钛内胆，耐用易洁', '支持 24 小时预约', '4L 容量（4-5人）'],
    cons=['定价较高', '压力参数未公开'],
    src=['ZOL %s（当前零售价 2999）' % zol_url('midea_1568847')],
    status=None, add_src=['中关村在线'],
    extra_log='ZOL 尺寸 368*311*232mm 与库内（太平洋）368×311×248mm 第三位冲突，保留太平洋值待复核',
)
P['midea_1616847'] = dict(
    set={'official_price': 2799, 'appoint': '24小时预约'},
    pros=['IH电磁加热，1300W 大火力', '钛内胆，耐用易洁', '支持 24 小时预约', '4L 容量（4-5人）', '标配金属蒸笼'],
    cons=['定价较高', '压力参数未公开'],
    src=['ZOL %s（当前零售价 2799）' % zol_url('midea_1616847')],
    status=None, add_src=['中关村在线'],
    extra_log='ZOL 尺寸 368*311*232mm 与库内（太平洋）368×311×248mm 第三位冲突，保留太平洋值待复核',
)
P['midea_2072107'] = dict(
    set={},
    pros=['IH电磁加热，1300W 大火力', '钛内胆，耐用易洁', '4L 容量（4-5人）'],
    cons=['预约/压力参数未公开', '无官方直营价，渠道价差较大'],
    src=[], status=None, add_src=[],
)
P['midea_1994707'] = dict(
    set={'size': '368×292×231mm', 'inner_pot': '钛'},
    pros=['IH电磁加热，1300W 大火力', '钛内胆', '4L 容量（4-5人）'],
    cons=['预约/压力参数未公开'],
    src=['太平洋/%s/1994707_detail.html（2026-10-04 直连复抓）' % PC],
    status=None, add_src=['太平洋电脑网'],
    extra_log='尺寸与同系列 MB-EFB4026H 完全一致（疑同模具），单一来源，提请审核方复核',
)
P['midea_1741447'] = dict(
    set={'inner_pot': '备长炭', 'appoint': '支持'},
    fix={'size': '查不到'},
    pros=['IH电磁加热，1300W 大火力', '备长炭内胆，蓄热导磁', '支持预约', '4L 容量（4-5人）'],
    cons=['预约时长未标称', '压力参数未公开'],
    src=['太平洋/%s/1741447_detail.html（2026-10-04 直连复抓）' % PC],
    status=None, add_src=['太平洋电脑网'],
    extra_log='太平洋尺寸栏「38.5×267.2×231mm」明显错标（38.5mm 不可能是整机长度），不采；尺寸保持查不到',
)
P['supor_2606259'] = dict(
    set={},
    pros=['IH电磁加热，1750W 强火力', '4L 容量（4-5人）', '铁铝合金内胆，导热快'],
    cons=['预约/压力参数未公开', '定价较高'],
    src=[], status=None, add_src=[],
)
P['supor_1928727'] = dict(
    set={}, fix={'power': '查不到'},
    pros=['IH电磁加热', '4L 容量（4-5人）', '铜铝合金内胆，导热均匀', '触控操作'],
    cons=['额定功率未公开', '预约参数未公开'],
    src=[],
    status=None, add_src=[],
    extra_log='剔除库内额定功率 220W（太平洋规格表错标：IH 机型物理上不可能 220W，疑 220V 电压串行进功率栏；ZOL/官方无该型号数据可定值，宁缺勿错）',
)
P['supor_1587527'] = dict(
    set={'size': '394×334×265mm', 'inner_pot': '不锈钢内胆'},
    pros=['IH电磁加热', '3L 容量（2-3人），小家庭适用', '不锈钢内胆'],
    cons=['预约/压力参数未公开', '无官方直营价'],
    src=['太平洋/%s/1587527_detail.html（2026-10-04 直连复抓；原文「394mm；宽334mm；高265mm」格式归一为 394×334×265mm，数值不变）' % PC],
    status=None, add_src=['太平洋电脑网'],
)
P['supor_2072247'] = dict(
    set={'size': '260×334×240mm', 'inner_pot': '铜铝合金'},
    pros=['IH电磁加热，1450W 大火力', '4L 容量（4-5人）', '铜铝合金内胆'],
    cons=['预约/压力参数未公开'],
    src=['太平洋/%s/2072247_detail.html（2026-10-04 直连复抓）' % PC],
    status=None, add_src=['太平洋电脑网'],
)
P['supor_1522107'] = dict(
    set={'appoint': '支持'},
    pros=['远红外涂层内胆，不易粘', '支持预约', '4L 容量（4-5人）', '入门定价'],
    cons=['底盘加热，受热均匀性不及 IH', '900W 功率较低，煮饭偏慢'],
    src=['太平洋/%s/1522107_detail.html（预约定时煮饭=支持）' % PC],
    status=None, add_src=[],
)
P['joyoung_2183719'] = dict(
    set={'official_price': 799, 'appoint': '24小时预约'},
    fix={'power': 1200},
    pros=['IH电磁加热，1200W 大火力', '不锈钢球形内胆', '支持 24 小时预约', '4L 容量（4-5人）'],
    cons=['定价在同系列中偏高', '压力参数未公开'],
    src=['ZOL %s（当前零售价 799；参数页功率 1200W、尺寸 344*278*235mm 与库内一致互证）' % zol_url('joyoung_2183719')],
    status=None, add_src=['中关村在线'],
    extra_log='订正额定功率 220W→1200W（ZOL 参数页；pconline 的 220W 判为电压串行错标，与 IH 加热矛盾）',
)
P['joyoung_1900287'] = dict(
    set={'appoint': '支持'},
    pros=['IH电磁加热，1200W 大火力', '土灶铁釜内胆', '支持预约', '4L 容量（4-5人）', '定价亲民'],
    cons=['压力参数未公开'],
    src=['太平洋/%s/1900287_detail.html（预约定时煮饭=支持）' % PC],
    status=None, add_src=[],
)
P['joyoung_2690599'] = dict(
    set={},
    pros=['IH电磁加热', '2L 小容量，1-2 人适用', '不锈钢内胆', '紧凑机身易收纳'],
    cons=['容量小，不适合多口之家', '预约参数未公开'],
    src=[], status=None, add_src=[],
)
P['joyoung_2469659'] = dict(
    set={},
    pros=['4L 容量（4-5人）', '860W 家用足够', '按键式操作简单', '定价亲民'],
    cons=['底盘加热，非 IH', '预约参数未公开'],
    src=[], status=None, add_src=[],
)
P['joyoung_1585667'] = dict(
    set={'official_price': 549, 'appoint': '24小时预约'},
    pros=['支持 24 小时预约', '铁铝合金内胆', '3L 容量（2-3人）', '定价亲民'],
    cons=['底盘加热，非 IH'],
    src=['ZOL %s（当前零售价 549；功率 860W 与库内一致互证）' % zol_url('joyoung_1585667')],
    status=None, add_src=['中关村在线'],
    extra_log='ZOL 尺寸 376*294*263mm 与库内（太平洋）374×294×263mm 首位差 2mm，保留太平洋值待复核',
)
P['panasonic_589196'] = dict(
    set={'official_price': 12999, 'appoint': '支持'},
    fix={'type': 'IH电磁'},
    pros=['IH电磁加热，1400W 高功率', '5L 大容量，多人家庭适用', '钻石黄金内锅', '支持预约'],
    cons=['定价近万元，预算门槛高', '机身较重，挪动不便'],
    src=['ZOL %s（当前零售价 12999；功率 1400W/尺寸 292*365*267mm/重量 8.9kg 与太平洋完全一致，多源互证）' % zol_url('panasonic_589196')],
    status='已核验（多源）', add_src=['中关村在线'],
    extra_log='订正加热方式 底盘加热→IH电磁（太平洋规格表「IH加热」；ZOL 参数页同证 1400W 功率量级）',
)
P['panasonic_589195'] = dict(
    set={'official_price': 10900, 'appoint': '支持'},
    pros=['IH电磁加热，1210W', '3L 容量（2-3人）', '钻石黄金内锅', '支持预约'],
    cons=['定价近万元', '3L 容量对多人家庭偏小'],
    src=['ZOL %s（当前零售价 10900；功率/尺寸/重量与太平洋完全一致，多源互证）' % zol_url('panasonic_589195')],
    status='已核验（多源）', add_src=['中关村在线'],
)
P['panasonic_2657139'] = dict(
    set={},
    pros=['IH电磁加热，1180W', '3L 容量（2-3人）', '铜铝合金内胆'],
    cons=['预约参数未公开', '定价较高'],
    src=[], status=None, add_src=[],
)
P['panasonic_1157036'] = dict(
    set={},
    pros=['1400W 大火力加热', '紧凑机身'],
    cons=['容量/内胆参数未公开', '非 IH 加热'],
    src=[], status=None, add_src=[],
    skip_note='ZOL「松下SR-HCC107」（¥5039，1200W/250*321*201mm）与库内 SR-HCC107-187（1400W/279×348×232mm）功率尺寸均不符，疑为不同型号，ZOL 价格/参数不采',
)
P['panasonic_2227059'] = dict(
    set={},
    fix={'size': '314×258×225mm'},
    pros=['IH电磁加热，1180W', '3L 容量（2-3人）', '钢铝合金内胆', '触控操作'],
    cons=['预约参数未公开', '定价较高'],
    src=[],
    status=None, add_src=[],
    fix_note='尺寸「314×258×225 mm」格式归一为「314×258×225mm」，数值不变',
)

# 卖点仅引用库内参数与官方/规格页文案，不改数值 —— 上面 pros/cons 已逐条核对


def guard(ours, key, val):
    """写入前的守卫：型号串干净、功率在合理区间、尺寸带 mm。"""
    if key == 'model_code' and val not in ('查不到', '—'):
        assert re.fullmatch(r'[A-Za-z0-9()（）.\-/]+', val), '%s model_code 不干净: %r' % (ours, val)
    if key == 'power' and isinstance(val, (int, float)) and val not in ('查不到',):
        assert 200 <= val <= 3000, '%s power 越界: %r' % (ours, val)
    if key == 'size' and val not in ('查不到', '—'):
        assert re.fullmatch(r'\d{2,4}(\.\d)?×\d{2,4}(\.\d)?×\d{2,4}(\.\d)?mm', val), '%s size 格式: %r' % (ours, val)
    if key == 'official_price' and isinstance(val, (int, float)):
        assert 49 <= val <= 99999, '%s price 越界: %r' % (ours, val)


def main():
    lib = json.load(open(os.path.join(ROOT, 'data/rice-cooker/products.json'), encoding='utf-8'))
    assert len(lib) == 32
    os.makedirs(os.path.join(ROOT, 'data/_draft/rice-cooker'), exist_ok=True)
    n = 0
    for p in lib:
        ours = p['id']
        cfg = P[ours]
        item = dict(p)
        logs = []
        setd = dict(cfg.get('set') or {})
        # 草稿若已由通用脚本产出，先撤掉其对 fix 字段的写入（以本脚本为准）
        fixd = dict(cfg.get('fix') or {})
        for k, v in setd.items():
            guard(ours, k, v)
            cur = item.get(k)
            assert cur in ('查不到', '—', '', None) or (isinstance(cur, list) and not cur), \
                '%s %s 已有值 %r，只补空值' % (ours, k, cur)
            item[k] = v
            logs.append('%s=%s' % (k, v))
        for k, v in fixd.items():
            guard(ours, k, v)
            item[k] = v
            logs.append('订正 %s=%s' % (k, v))
        if cfg.get('set_url'):
            item['verify_url'] = cfg['set_url']
        # 卖点：只写给裸卡
        if cfg.get('pros') or cfg.get('cons'):
            assert not p.get('pros') and not p.get('cons'), '%s 非裸卡' % ours
            if cfg.get('pros'):
                item['pros'] = cfg['pros']
            if cfg.get('cons'):
                item['cons'] = cfg['cons']
            logs.append('补写卖点 %d 条 pros / %d 条 cons' % (len(cfg.get('pros') or []), len(cfg.get('cons') or [])))
        # change_log
        entry = ''
        if logs:
            entry = '；%s 补全：' % D + '，'.join(logs)
        if cfg.get('src'):
            entry += '（来源：%s）' % '；'.join(cfg['src'])
        elif cfg.get('pros'):
            entry += '（来源：库内已入库参数与商品页文案推导，未引入新数值）'
        if cfg.get('extra_log'):
            entry += '；%s ' % D + cfg['extra_log']
        if cfg.get('skip_note'):
            entry += '；%s 跳过说明：%s' % (D, cfg['skip_note'])
        if cfg.get('fix_note'):
            entry += '；%s ' % D + cfg['fix_note']
        if not logs and not entry:
            continue  # 无实质改进不产草稿
        item['change_log'] = (p.get('change_log') or '') + entry
        item['updated_at'] = D
        item['verify_date'] = D
        # 核查状态只升不降
        rank = ['待核验', '已核验（第三方）', '已核验（官方商城）', '已核验（多源）']
        old = p.get('verify_status') or '待核验'
        new = cfg.get('status')
        if new:
            assert rank.index(new) >= rank.index(old), '%s 状态降级 %s -> %s' % (ours, old, new)
            item['verify_status'] = new
        else:
            item['verify_status'] = old
        src = set(p.get('verify_source') or [])
        item['verify_source'] = sorted(src | set(cfg.get('add_src') or []))
        out = os.path.join(ROOT, 'data/_draft/rice-cooker', ours + '.json')
        with open(out, 'w', encoding='utf-8', newline='\n') as fh:
            json.dump(item, fh, ensure_ascii=False, indent=2)
            fh.write('\n')
        n += 1
        print('%-18s %+d 字段/订正 %s' % (ours, len(setd), ('fix:' + ','.join(fixd)) if fixd else ''))
    print('共重建草稿 %d 份 -> data/_draft/rice-cooker/' % n)


if __name__ == '__main__':
    main()
