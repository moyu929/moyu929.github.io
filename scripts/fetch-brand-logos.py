# -*- coding: utf-8 -*-
"""品牌 logo 采集管线：五路来源 → 规范化处理 → public/images/brands/<品牌名>.<ext>

为「源源不断收录新品牌」设计：新品牌进 TABLE（一行）→ 跑本脚本 → 构建期
virtual:brand-logos 自动拾取，首页品牌导航即出 logo。拿不到的自动 fallback
品牌首字头像（前端已支持），后续拿到图放进 brands/ 目录即覆盖。

路线（按可靠性排序，均为 2026-10-05/06 全量 52 品牌实战验证）：
  A. 维基数据 P154（logo image）→ Special:FilePath?width=480 渲染下载。
     ⚠ 不要用 Wikipedia pageimages——返回的是总部大楼/产品照，且「小米」词条
     是谷物（公司词条叫「小米公司」）；zh 维基 HTML 缩略图域名是 thumb.wikimedia.org。
  B. 官网 header <img 含 logo> / apple-touch-icon。⚠ 部分站点 CDN 校验 Referer
     （德尔玛 static.deerma.com 必须带 -e 官网首页），下载 0B 时加 Referer 重试。
  C. iTunes Search API 官方 App 图标（artworkUrl512，实底方图 → 22% 圆角遮罩透明化）。
     ⚠ 错牌甄别是硬要求：sellerName/trackName 必须含品牌 token 或其注册公司 token。
     实战错牌案例：「小熊油耗」「DOUDOUBEAR」「小熊备忘录」（同名不同司）、
     「海信爱家」（集团 App 冒充子品牌）——宁可 fallback 不可错牌。
  D. cn.bing 图片搜索：服务端首屏嵌原图直链（murl），对小品牌最有效
     （容声/美菱第一张即官方方标）。候选混杂，**不自动入位**：跑完生成候选联络表
     （data/_cache/brand-logos/bing-candidates/<品牌>/candidates.png），人工目检后
     `python scripts/fetch-brand-logos.py --pick <品牌>:<序号>` 入位（自动圆角遮罩）。
  E. icon.horse（<domain> 直出 256px）——⚠ 会为无 favicon 的站生成灰色首字母
     占位图，必须经 --allow-icon-horse 显式打开，产物要过占位检测。
  F. 全失败 → fallback 首字头像（前端行为，脚本只记录）。
  实测覆盖：48 → 51/52（D 路线补齐容声/美菱，官网真域名修正后补齐小熊/艾美特；
  仅欧井——站点挂、无 App、搜索引擎无命中）。

规范化处理（入位前统一执行）：
  · SVG 原样入位（浏览器原生渲染，透明由源文件保证）
  · 位图 → RGBA；四角近白实底做容差清除（含白底 JPG logo 与 touchicon）
  · 最长边 ≤160px（22px 显示位 × DPR 3 = 66px，160 留余量）；不放大小图
  · iTunes App 图标额外加 22% 圆角 alpha 遮罩（模拟 App 图标形态，浮在卡片底色上）

幂等：brands/ 已有该品牌（png/svg 任一）即跳过。用法：
    python scripts/fetch-brand-logos.py                  # 只补缺失品牌
    python scripts/fetch-brand-logos.py --only 小熊      # 指定品牌
    python scripts/fetch-brand-logos.py --force          # 全部重取覆盖
"""
import argparse
import json
import re
import subprocess
import sys
import time
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DST = ROOT / 'public' / 'images' / 'brands'
CACHE = ROOT / 'data' / '_cache' / 'brand-logos'
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36'
MAX = 160

# (品牌, [(wiki站点,词条名)…], [官网域名…], [iTunes 搜索词…], iTunes 甄别 token)
# 甄别 token 必须出现在 sellerName/trackName 里才采纳（防错牌）；已在库的品牌也保留行，
# 作为 --force 重取与新品牌参考。
TABLE = [
    ('小米', [('zhwiki', '小米公司'), ('enwiki', 'Xiaomi')], ['mi.com'], ['小米'], '小米'),
    ('美的', [('zhwiki', '美的集团'), ('enwiki', 'Midea')], ['midea.com', 'midea.cn'], ['美的'], '美的'),
    ('格力', [('zhwiki', '格力电器'), ('enwiki', 'Gree Electric')], ['gree.com', 'gree.com.cn'], [], '格力'),
    ('海尔', [('zhwiki', '海尔集团'), ('enwiki', 'Haier')], ['haier.com'], [], '海尔'),
    ('海信', [('zhwiki', '海信集团'), ('enwiki', 'Hisense')], ['hisense.com'], [], '海信'),
    ('长虹', [('zhwiki', '四川长虹'), ('enwiki', 'Changhong')], ['changhong.com'], [], '长虹'),
    ('奥克斯', [('zhwiki', '奥克斯集团'), ('enwiki', 'Aux Group')], ['auxgroup.com', 'aux.com'], [], '奥克斯'),
    ('TCL', [('zhwiki', 'TCL科技'), ('enwiki', 'TCL Technology')], ['tcl.com'], [], 'TCL'),
    ('苏泊尔', [('zhwiki', '苏泊尔'), ('enwiki', 'Supor')], ['supor.com.cn', 'supor.com'], [], '苏泊尔'),
    ('九阳', [('zhwiki', '九阳股份'), ('enwiki', 'Joyoung')], ['joyoung.com'], ['Joyoung', '九阳'], '九阳'),
    ('飞利浦', [('zhwiki', '飞利浦'), ('enwiki', 'Philips')], ['philips.com.cn', 'philips.com'], [], '飞利浦'),
    ('霍尼韦尔', [('zhwiki', '霍尼韦尔'), ('enwiki', 'Honeywell')], ['honeywell.com.cn', 'honeywell.com'], [], '霍尼韦尔'),
    ('追觅', [('zhwiki', '追觅科技'), ('enwiki', 'Dreame')], ['dreame.com', 'dreame.tech'], ['追觅', 'Dreame'], '追觅'),
    ('戴森', [('zhwiki', '戴森'), ('enwiki', 'Dyson (company)')], ['dyson.cn', 'dyson.com'], [], '戴森'),
    ('奥普', [('zhwiki', '奥普集团'), ('zhwiki', '奥普')], ['aupu.com'], ['奥普', 'AUPU'], '奥普'),
    ('欧普', [('zhwiki', '欧普照明'), ('enwiki', 'OPPLE')], ['opple.com.cn', 'opple.com'], [], '欧普'),
    ('松下', [('zhwiki', '松下电器'), ('enwiki', 'Panasonic')], ['panasonic.cn', 'panasonic.com'], [], '松下'),
    ('雷士', [('zhwiki', '雷士照明'), ('enwiki', 'NVC Lighting')], ['nvc-lighting.com.cn', 'nvc-lighting.com'], [], '雷士'),
    ('小熊', [('zhwiki', '小熊电器')], ['bear517.com'], ['小熊电器', 'Bear Electric', '小熊商城'], '小熊'),
    ('欧井', [('zhwiki', '欧井')], ['eurgeen.com', 'eurgeen.cn'], ['欧井', 'Eurgeen'], '欧井'),
    ('西门子', [('zhwiki', '西门子'), ('enwiki', 'Siemens')], ['siemens.com'], [], '西门子'),
    ('老板', [('zhwiki', '老板电器'), ('enwiki', 'Robam')], ['robam.com'], [], '老板'),
    ('方太', [('zhwiki', '方太集团'), ('zhwiki', '方太')], ['fotile.com'], ['方太', 'FOTILE', 'Fotile'], '方太'),
    ('华帝', [('zhwiki', '华帝股份'), ('enwiki', 'Vatti')], ['vatti.com.cn'], ['华帝', 'Vatti'], '华帝'),
    ('艾美特', [('zhwiki', '艾美特')], ['airmate.com.cn', 'airmate.com'], ['艾美特', 'AIRMATE', 'Airmate'], '艾美特'),
    ('添可', [('zhwiki', '添可'), ('enwiki', 'Tineco')], ['tineco.com'], ['Tineco', '添可'], '添可'),
    ('石头', [('zhwiki', '石头科技'), ('enwiki', 'Roborock')], ['roborock.com'], ['Roborock', '石头'], '石头'),
    ('云鲸', [('zhwiki', '云鲸智能'), ('enwiki', 'Narwal')], ['narwal.com', 'narwal.cn'], ['云鲸', 'Narwal'], '云鲸'),
    ('MOVA', [('enwiki', 'MOVA')], ['movatech.com', 'mova-tech.com'], ['MOVA'], 'MOVA'),
    ('澳柯玛', [('zhwiki', '澳柯玛'), ('enwiki', 'Aucma')], ['aucma.com', 'aucma.com.cn'], [], '澳柯玛'),
    ('德尔玛', [('zhwiki', '德尔玛')], ['deerma.com'], ['德尔玛', 'Deerma'], '德尔玛'),
    ('352', [], ['352life.com', '352.com'], ['352', '352Life'], '352'),
    ('格兰仕', [('zhwiki', '格兰仕'), ('enwiki', 'Galanz')], ['galanz.com'], [], '格兰仕'),
    ('象印', [('zhwiki', '象印'), ('enwiki', 'Zojirushi')], ['zojirushi.com', 'zojirushi.co.jp'], [], '象印'),
    ('坚果', [('zhwiki', '坚果投影'), ('enwiki', 'JMGO')], ['jmgo.com'], ['JMGO', '坚果', '火乐', 'Holatech'], '坚果'),
    ('当贝', [('zhwiki', '当贝网络'), ('zhwiki', '当贝')], ['dangbei.com'], ['当贝', 'dangbei'], '当贝'),
    ('容声', [('zhwiki', '容声')], ['ronshen.com', 'ronshen.com.cn'], ['容声', 'Ronshen', '海信容声'], '容声'),
    ('科沃斯', [('zhwiki', '科沃斯'), ('enwiki', 'Ecovacs')], ['ecovacs.com', 'ecovacs.cn'], ['科沃斯', 'Ecovacs'], '科沃斯'),
    ('大疆', [('zhwiki', '大疆创新'), ('enwiki', 'DJI')], ['dji.com'], [], '大疆'),
    ('创维', [('zhwiki', '创维集团'), ('enwiki', 'Skyworth')], ['skyworth.com'], [], '创维'),
    ('索尼', [('zhwiki', '索尼'), ('enwiki', 'Sony')], ['sony.com.cn', 'sony.com'], [], '索尼'),
    ('康佳', [('zhwiki', '康佳集团'), ('enwiki', 'Konka Group')], ['konka.com'], ['康佳', 'Konka'], '康佳'),
    ('小天鹅', [('zhwiki', '小天鹅')], ['littleswan.com'], ['小天鹅', 'Little Swan'], '小天鹅'),
    ('安吉尔', [('zhwiki', '安吉尔')], ['angel.com.cn'], ['安吉尔', 'Angel'], '安吉尔'),
    ('美菱', [('zhwiki', '长虹美菱'), ('zhwiki', '美菱')], ['meiling.com', 'changhongmeiling.cn'], ['美菱', 'Meiling'], '美菱'),
    ('林内', [('zhwiki', '上海林内'), ('zhwiki', '林内')], ['rinnai.com.cn'], [], '林内'),
    ('A.O.史密斯', [('zhwiki', '艾欧史密斯'), ('enwiki', 'A. O. Smith')], ['aosmith.com.cn', 'aosmith.com'], [], 'A.O.史密斯'),
    ('万家乐', [('zhwiki', '广东万家乐'), ('zhwiki', '万家乐')], ['macro.com.cn', 'chinamacro.cn'], ['万家乐', 'Macro'], '万家乐'),
    ('能率', [('zhwiki', '能率'), ('enwiki', 'Noritz')], ['noritz.com.cn'], ['能率', 'NORITZ'], '能率'),
    ('万和', [('zhwiki', '万和电气'), ('enwiki', 'Vanward')], ['vanward.com'], ['万和', 'Vanward'], '万和'),
    ('沁园', [('zhwiki', '沁园')], ['chinatruliva.com', 'truliva.com'], ['沁园', 'Qinyu', 'Truliva'], '沁园'),
    ('3M', [('enwiki', '3M')], ['3m.com.cn', '3m.com'], [], '3M'),
]


def curl(url, out=None, extra=None, tries=2):
    for a in range(tries):
        cmd = ['curl', '-sfL', '--compressed', '-A', UA, '--max-time', '60', '-w', '%{http_code}']
        if extra:
            cmd += extra
        if out:
            cmd += ['-o', str(out)]
        cmd.append(url)
        p = subprocess.run(cmd, capture_output=True)
        data = p.stdout
        code = data[-3:].decode(errors='replace') if len(data) >= 3 else '?'
        if code == '200':
            return data[:-3] if not out else True
        if code in ('404', '403', '410'):
            return None
        time.sleep(3 * (a + 1))
    return None


# ---------------------------------------------------------------- 路线 A：Wikidata P154

def via_p154(brand, titles, work):
    for site, title in titles:
        u = ('https://www.wikidata.org/w/api.php?action=wbgetentities&sites=%s&titles=%s'
             '&props=claims&format=json&formatversion=2') % (site, urllib.parse.quote(title, safe=''))
        d = curl(u)
        time.sleep(0.4)
        if not d:
            continue
        try:
            j = json.loads(d)
        except Exception:
            continue
        for k, v in j.get('entities', {}).items():
            if k == '-1' or not isinstance(v, dict):
                continue
            vals = []
            for c in v.get('claims', {}).get('P154', []):
                sn = c.get('mainsnak', {})
                if sn.get('snaktype') != 'value':
                    continue
                val = sn.get('datavalue', {}).get('value')
                if isinstance(val, str) and val:
                    vals.append((0 if c.get('rank') == 'preferred' else 1, val))
            if not vals:
                continue
            vals.sort()
            fname = vals[0][1].replace('File:', '')
            q = urllib.parse.quote(fname, safe='')
            for host in ('https://commons.wikimedia.org', 'https://zh.wikipedia.org'):
                out = work / f'{brand}.p154.bin'
                if curl(f'{host}/wiki/Special:FilePath/{q}?width=480', out=out):
                    return out, f'wikidata P154「{fname}」'
    return None


# ---------------------------------------------------------------- 路线 B：官网

def via_site(brand, domains, work):
    for dom in domains:
        base = f'https://{dom}'
        # B1 apple-touch-icon 约定路径
        for path in ('/apple-touch-icon.png', '/apple-touch-icon-precomposed.png'):
            out = work / f'{brand}.touch.bin'
            if curl(f'{base}{path}', out=out, extra=['-e', base]):
                return out, f'touchicon {dom}{path}'
        # B2 首页解析：touch-icon link 声明 + header <img 含 logo>
        html = curl(base, extra=['-e', base])
        time.sleep(0.3)
        if not html:
            continue
        text = html.decode('utf-8', errors='replace')
        m = re.search(r'<link[^>]+rel="apple-touch-icon[^"]*"[^>]+href="([^"]+)"', text)
        if m:
            out = work / f'{brand}.touch.bin'
            if download_absolute(m.group(1), base, out):
                return out, f'touchicon link {dom}'
        img = None
        for tag in re.findall(r'<img[^>]{0,400}?>', text, re.S):
            low = tag.lower()
            if 'logo' not in low and 'brand' not in low:
                continue
            mm = re.search(r'(?:src|data-src)="([^"]+\.(?:png|svg|webp))"', tag)
            if mm:
                img = mm.group(1)
                break
        if img and download_absolute(img, base, work / f'{brand}.site.{img.rsplit(".", 1)[-1]}'):
            f = next(work.glob(f'{brand}.site.*'))
            return f, f'site header {dom}'
    return None


def download_absolute(href, base, out):
    if href.startswith('//'):
        href = 'https:' + href
    elif href.startswith('/'):
        href = base.rstrip('/') + href
    elif not href.startswith('http'):
        href = base.rstrip('/') + '/' + href
    # 实测教训：站点 CDN 常校验 Referer（德尔玛 static.deerma.com 无 Referer 返回 0B）
    return bool(curl(href, out=out, extra=['-e', base]))


# ---------------------------------------------------------------- 路线 C：iTunes 官方 App 图标

def via_itunes(brand, terms, token, work):
    for country in ('cn', 'us'):
        for term in terms:
            u = ('https://itunes.apple.com/search?term=%s&country=%s&entity=software&limit=10'
                 % (urllib.parse.quote(term), country))
            d = curl(u)
            time.sleep(0.3)
            if not d:
                continue
            try:
                j = json.loads(d)
            except Exception:
                continue
            for app in j.get('results', []):
                s = (app.get('sellerName', '') or '') + '|' + (app.get('trackName', '') or '')
                if token not in s:
                    continue  # 错牌甄别：同名不同司直接跳过（实战教训见模块 docstring）
                url = app.get('artworkUrl512')
                if not url:
                    continue
                out = work / f'{brand}.app.bin'
                if curl(url, out=out):
                    return out, f'iTunes({country})「{app.get("trackName", "")}」'
    return None


# ---------------------------------------------------------------- 路线 D：icon.horse（默认关）

def via_iconhorse(brand, domains, work):
    for dom in domains:
        out = work / f'{brand}.ih.bin'
        if curl(f'https://icon.horse/icon/{dom}', out=out):
            return out, f'icon.horse {dom}'
    return None


# ---------------------------------------------------------------- 规范化处理

def normalize(brand, src, is_app_icon=False, rounded=False):
    """SVG 原样入位；位图 RGBA + 四角白底清除 + ≤160px；App 图标/实底方标加 22% 圆角遮罩。
    非图片内容（站点返回 HTML 错误页存成 .bin 的情况）抛 ValueError 由上层跳路线。
    返回 (后缀, 说明)。"""
    head = src.read_bytes()[:12]
    if head.startswith(b'<') or head.startswith(b'<?x'):
        return 'svg', 'SVG 原样'
    magic = (b'\x89PNG', b'\xff\xd8\xff', b'GIF8', b'RIFF')
    if not any(head.startswith(m) for m in magic):
        src.unlink(missing_ok=True)
        raise ValueError('响应不是图片（疑似 HTML 错误页）')
    from PIL import Image, ImageDraw
    im = Image.open(src)
    im.load()
    im = im.convert('RGBA')
    px = im.load()
    w, h = im.size
    corners = [px[0, 0], px[w - 1, 0], px[0, h - 1], px[w - 1, h - 1]]
    if all(c[3] > 250 and min(c[:3]) > 240 for c in corners):
        bg = corners[0][:3]
        im.putdata([(r, g, b, 0) if abs(r - bg[0]) < 20 and abs(g - bg[1]) < 20 and abs(b - bg[2]) < 20
                    else (r, g, b, a) for r, g, b, a in im.getdata()])
    if max(im.size) > MAX:
        r = MAX / max(im.size)
        im = im.resize((round(im.width * r), round(im.height * r)), Image.LANCZOS)
    if is_app_icon or rounded:
        mask = Image.new('L', im.size, 0)
        ImageDraw.Draw(mask).rounded_rectangle(
            [0, 0, im.width - 1, im.height - 1], radius=int(min(im.size) * 0.22), fill=255)
        im.putalpha(mask)
    im.save(DST / f'{brand}.png')
    return 'png', f'{im.size}'


def via_bing(brand, work):
    """cn.bing 图片搜索：服务端渲染首屏里嵌原图直链（murl 字段）。
    实战对小品牌最有效（容声/美菱第一张即官方方标），但候选混杂（商品图/歧义词图），
    **不自动入位**——下载候选 + 生成联络表，人工目检后用 --pick 入位。
    返回 None（main 据此提示候选表路径）。"""
    q = f'{brand} logo'
    url = f'https://cn.bing.com/images/search?q={urllib.parse.quote(q)}&first=1'
    html = curl(url) or b''
    text = html.decode('utf-8', errors='replace')
    murls = re.findall(r'murl&quot;:&quot;(.*?)&quot;', text) or re.findall(r'murl":"(.*?)"', text)
    cand_dir = work / 'bing-candidates' / brand
    cand_dir.mkdir(parents=True, exist_ok=True)
    for old in cand_dir.glob('*'):
        old.unlink()
    got = 0
    for i, u in enumerate(murls):
        if got >= 6:
            break
        u = u.replace('\\u002f', '/').replace('\\/', '/')
        out = cand_dir / f'{got}.bin'
        if curl(u, out=out):
            try:
                from PIL import Image
                im = Image.open(out)
                im.load()
                if min(im.size) < 40:
                    out.unlink()
                    continue
                got += 1
            except Exception:
                out.unlink(missing_ok=True)
        time.sleep(0.1)
    if not got:
        return None
    # 候选联络表（深色底）
    from PIL import Image, ImageDraw
    files = sorted(cand_dir.glob('*.bin'))[:got]
    tw, th = 150, 130
    sheet = Image.new('RGB', (tw * len(files), th), (245, 245, 245))
    d = ImageDraw.Draw(sheet)
    for c, f in enumerate(files):
        try:
            im = Image.open(f).convert('RGBA')
            im.thumbnail((130, 92), Image.LANCZOS)
            tile = Image.new('RGBA', (136, 96), (200, 203, 210, 255))
            tile.paste(im, ((136 - im.width) // 2, (96 - im.height) // 2), im)
            sheet.paste(tile.convert('RGB'), (c * tw + 7, 22))
        except Exception:
            continue
        d.text((c * tw + 7, 4), f'#{c}', fill=(0, 0, 0))
    sheet.save(cand_dir / 'candidates.png')
    return None, f'候选表 {cand_dir / "candidates.png"}（{got} 张，人工目检后 --pick {brand}:<序号> 入位）'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--only', help='只处理指定品牌（可逗号分隔）')
    ap.add_argument('--force', action='store_true', help='已有 logo 也重取')
    ap.add_argument('--allow-icon-horse', action='store_true',
                    help='启用路线 D（会为无 favicon 站生成首字母占位图，产物必须目检）')
    ap.add_argument('--pick', metavar='品牌:序号',
                    help='人工目检 bing 候选后入位：把 bing-candidates/<品牌>/ 第 N 张（0 基）规范化入位')
    args = ap.parse_args()

    DST.mkdir(parents=True, exist_ok=True)
    CACHE = ROOT / 'data' / '_cache' / 'brand-logos'
    CACHE.mkdir(parents=True, exist_ok=True)

    if args.pick:
        brand, n = args.pick.rsplit(':', 1)
        cand = CACHE / 'bing-candidates' / brand / f'{int(n)}.bin'
        if not cand.exists():
            print(f'✗ 候选不存在：{cand}（先跑一次本脚本生成候选表）')
            sys.exit(1)
        ext, info = normalize(brand, cand, rounded=True)
        print(f'✓ {brand} ← bing 候选 #{n} → {brand}.{ext} {info}')
        return

    only = set(args.only.split(',')) if args.only else None

    report = {}
    for brand, titles, domains, itunes_terms, token in TABLE:
        if only and brand not in only:
            continue
        if (DST / f'{brand}.png').exists() or (DST / f'{brand}.svg').exists():
            if not args.force:
                report[brand] = 'skip(已有)'
                continue
        hit = None
        for name, fn in [
            ('P154', via_p154),
            ('site', via_site),
            ('iTunes', via_itunes),
            ('bing', via_bing),
            ('icon.horse', via_iconhorse),
        ]:
            if name == 'icon.horse' and not args.allow_icon_horse:
                continue
            if name == 'iTunes' and not itunes_terms:
                continue
            got = None
            try:
                if name == 'P154':
                    got = fn(brand, titles, CACHE)
                elif name in ('site', 'icon.horse', 'bing'):
                    got = fn(brand, domains, CACHE)
                else:
                    got = fn(brand, itunes_terms, token, CACHE)
                if got:
                    src, how = got
                    if src is not None:
                        ext, info = normalize(brand, src, is_app_icon=(name == 'iTunes'))
                        hit = f'{name}: {how} → {ext} {info}'
                    else:
                        # bing 路线：只产出候选表，等待人工 --pick
                        hit = f'{how}'
                        break
            except Exception as e:
                # 单路线失败（坏响应/解码失败）继续下一路线
                print(f'  · {brand} {name} 失败: {e}', flush=True)
                got = None
            if hit:
                break
        report[brand] = hit or 'MISS(前端 fallback 首字头像)'
        print(f'{brand:10s} {report[brand]}', flush=True)

    out = CACHE / 'report.json'
    out.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding='utf-8')
    ok = sum(1 for v in report.values() if v and not v.startswith(('skip', 'MISS')))
    print(f'\n完成：新增 {ok} / 处理 {len(report)}；报告 {out}')
    print('构建后 virtual:brand-logos 自动拾取（svg/png 均可）；MISS 者前端显示首字头像。')


if __name__ == '__main__':
    main()
