# -*- coding: utf-8 -*-
"""从产品名回填 model_code（竞品）。

背景：618 款竞品当初导入时名称取自第三方，但 model_code 留成了「查不到」，
而其中多数产品名里**就带着零售型号**（「美的KFR-72LW/N8WF1」「CV-DSH40C 电热水瓶」），
属于导入时的低级遗漏。

## 判定策略

只做**可机械复核**的提取，不猜：

1. `brand ≠ 小米` —— 小米/米家产品名里是系列代号（电视 S Pro Mini LED、除湿机 Max），
   从名字造型号是错的，那些保持「查不到」；
2. 在名称里找**连续的型号串**：以字母或数字开头，由字母数字与 `-` `/` `(`
   `)` `.` `_` 组成，至少 3 个字符、且至少含一个数字；
3. 排除明显不是型号的取值（纯数字如容量、纯字母如 `Skin`/`Steam`/`Pro`）；
4. 命中多个候选时，取**最长**的那个（型号通常比系列代号长）；
   长度相同则放弃，交人工看。

## 可信度

型号原文来自第三方（`verify_url` 指向的 pconline 规格页），与本站产品名同源。
`scripts/fetch-verify-titles.py` 会用规格页标题做交叉校验，两者一致即互证 ——
pconline 恢复后可补跑一次校验。

## 用法

    python scripts/fill-model-codes.py --dry    # 只报告
    python scripts/fill-model-codes.py         # 写入 data/_draft/<品类>/<id>.json
"""
import json, os, re, sys, glob, argparse
from collections import Counter

# 仓库根目录：按脚本自身位置解析，不依赖 cwd（见方案 P0-1）
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def dp(rel):
    """仓库相对路径 → 绝对路径"""
    return os.path.join(ROOT, rel)


sys.stdout.reconfigure(encoding='utf-8')
D = '2026-10-03'
BLANK = {'查不到', '—', '', None, 'None'}

# 这些品类的竞品名不足以可靠推出零售型号，保持「查不到」：
#  - projector：坚果 S1 / 1895 / SC / V8 是系列代号，不是型号
#  - robot-vacuum / floor-washer：石头 G30 与 G30S、G30 Space 是不同机型但名字高度相似，
#    按名称提取会漏掉 Pro 等后缀造成错号/重号，需人工按官方页逐条确认
SKIP_CATS = {'projector', 'robot-vacuum', 'floor-washer'}

# 型号主体：字母数字与型号常用符号，至少 3 字符。
# 括号单独成一组：KFR 型号里常见 -(B0) 这类后缀，必须整体吃进来再判断配平，
# 否则会截成 `...-RS(B0`。
MODEL_CORE = r'[A-Za-z0-9][A-Za-z0-9\-/_.+]'
MODEL_WITH_PAREN = re.compile(MODEL_CORE + r'{2,}(?:\([A-Za-z0-9]+\))?')
HAS_DIGIT = re.compile(r'\d')

# 型号后缀：这些词是型号的一部分，不能当成独立候选丢掉。
# 石头 G30S Pro / 追觅 M13 Pro Plus / 美的 G3E Pro 的零售型号都含它们。
SUFFIX = r'(?:\s*(?:Pro|Plus|Ultra|Steam|Max|Lite|AE|SE|SII|Pro Plus|Pro Max))'

# 明确不是型号的独立词（形态/系列描述）
NOT_MODEL = {
    'Pro', 'Plus', 'Ultra', 'Steam', 'Max', 'Lite', 'Air', 'Water', 'NEW',
    'New', 'SII', 'a', 'b', 'pro',
    # 套装名/配色/版本后缀：戴森 V16 Piston Animal、追觅 V16 Pro Aqua、
    # 安吉尔 Y3316BK-G b 这类，同一型号的不同套装，不是型号的一部分
    'Piston', 'Animal', 'Nautik', 'Aqua', 'Nautik.', 'Absolute',
}


def candidates(name, brand):
    """返回名称里所有型号候选串（已剔除明显的非型号）。"""
    nm = (name or '').strip()
    for b in (brand, '米家', '小米', 'Xiaomi'):
        if b and nm.startswith(b):
            nm = nm[len(b):]
            break
    out = []
    # 先吃掉「型号(可带括号) + 后缀」的组合，避免后缀被当成独立候选
    for m in re.finditer(MODEL_WITH_PAREN.pattern + SUFFIX, nm):
        s = re.sub(r'\s+', ' ', m.group(0).strip())
        if s.count('(') != s.count(')'):     # 括号必须配平
            continue
        s = s.strip('-/_')
        if _plausible(s):
            out.append(s)
    for m in MODEL_WITH_PAREN.finditer(nm):
        s = m.group(0)
        if s.count('(') != s.count(')'):
            continue
        s = s.strip('-/_')
        if _plausible(s):
            out.append(s)
    return out


def _plausible(s):
    if len(s) < 3 or not HAS_DIGIT.search(s):
        return False
    if s in NOT_MODEL:
        return False
    if not re.search(r'[A-Za-z]', s):   # 纯数字是容量不是型号
        return False
    return True


def pick(name, brand):
    """取最长的候选；并列最长则放弃（宁可留空也不猜）。"""
    c = candidates(name, brand)
    if not c:
        return None, '无候选'
    c = sorted(set(c), key=lambda x: -len(x))
    if len(c) > 1 and len(c[0]) == len(c[1]):
        return None, '多个并列候选 %s' % c[:3]
    return c[0], '名称中的型号串'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dry', action='store_true', help='只报告，不写库')
    args = ap.parse_args()

    hits, ambiguous, none = [], [], []
    seen = set()
    for f in sorted(glob.glob(dp('data/*/schema.json'))):
        cid = os.path.basename(os.path.dirname(f))
        s = json.load(open(f, encoding='utf-8'))
        if 'model_code' not in [x['key'] for x in s['fields']]:
            continue
        for p in json.load(open(dp('data/%s/products.json' % cid), encoding='utf-8')):
            if p.get('model_code') not in BLANK:
                seen.add((cid, str(p['model_code'])))    # 已入库的型号参与重号检查
                continue
            if p.get('brand') == '小米':
                continue
            if cid in SKIP_CATS:
                ambiguous.append((cid, p['id'], p['name'], '该品类命名无法从名称可靠判定型号'))
                continue
            m, why = pick(p.get('name', ''), p.get('brand', ''))
            if not m:
                if why.startswith('多个'):
                    ambiguous.append((cid, p['id'], p['name'], why))
                else:
                    none.append((cid, p['id'], p['name']))
                continue
            # 提取值在同品类已存在、或本次提取里已出现过 -> 说明名称里的型号不完整
            # （套装名/配色后缀被吃掉），宁可不填也不制造重号
            key = (cid, m)
            if key in seen:
                ambiguous.append((cid, p['id'], p['name'], '型号 %s 在同品类重复，疑似名称未含完整型号' % m))
                continue
            seen.add(key)
            hits.append((cid, p['id'], p['name'], m))

    print('可从产品名提取型号：%d 条' % len(hits))
    print('候选并列需人工看：%d 条；无可提取：%d 条；小米系系列代号：保持「查不到」'
          % (len(ambiguous), len(none)))
    print()
    for cid, n in Counter(h[0] for h in hits).most_common():
        print('   %-18s %3d' % (cid, n))

    if args.dry:
        print('\n--dry 未写库。示例：')
        for h in hits[:10]:
            print('   %s/%s  %s -> %s' % h)
        print('\n并列候选示例（需人工判断）：')
        for a in ambiguous[:8]:
            print('   %s/%s  %s  %s' % a)
        return

    for cid, pid, name, m in hits:
        d = dp('data/_draft/%s' % cid)
        os.makedirs(d, exist_ok=True)
        cur = json.load(open(dp('data/%s/products.json' % cid), encoding='utf-8'))
        base = next(x for x in cur if x['id'] == pid)
        item = dict(base)
        item['model_code'] = m
        item['verify_date'] = D
        item['change_log'] = (base.get('change_log', '') or '') + \
            '；%s 回填型号：原「%s」，产品名「%s」中的型号串为 %s（来源与产品名同源的第三方规格站）' \
            % (D, base.get('model_code'), name, m)
        item['updated_at'] = D
        with open('%s/%s.json' % (d, pid), 'w', encoding='utf-8', newline='\n') as fh:
            json.dump(item, fh, ensure_ascii=False, indent=2)
            fh.write('\n')
    print('\n已写入 data/_draft/：%d 条（flow:submit 提交待审）' % len(hits))


if __name__ == '__main__':
    main()