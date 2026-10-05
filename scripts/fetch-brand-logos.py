# -*- coding: utf-8 -*-
"""品牌 logo 采集：维基数据 P154（logo image）→ 官网 apple-touch-icon 双路。

产物：public/images/brands/<品牌名>.png（透明背景、最长边 ≤160px），
由 vite.config.ts 的 virtual:brand-logos 构建期扫描，放入即出现在首页品牌导航。

路线（按优先级，来自首轮实踩的教训）：
  A. Wikidata 实体的 P154（logo image）声明 → Special:FilePath?width=480 渲染下载。
     注意 Wikipedia pageimages 不可用（返回总部大楼/歧义词照片，小米会命中谷物）。
  B. 官网 <domain>/apple-touch-icon(-precomposed).png 与首页 <link> 声明的图标。
  C. 都失败 → 留给人工（首页 fallback 品牌首字头像）。

幂等：brands/ 里已有的品牌跳过。用法：
    python scripts/fetch-brand-logos.py            # 只处理缺失的
    python scripts/fetch-brand-logos.py --force    # 全部重取
"""
import json
import re
import subprocess
import sys
import time
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DST = ROOT / 'public' / 'images' / 'brands'
CACHE = ROOT / 'data' / '_cache' / 'logo-raw2'
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36'
MAX = 160

# (品牌, [(wiki站点, 词条名)…], [官网域名…])
TABLE = [
    ('美的', [('zhwiki', '美的集团'), ('enwiki', 'Midea')], ['midea.com', 'midea.cn']),
    ('格力', [('zhwiki', '格力电器'), ('enwiki', 'Gree Electric')], ['gree.com', 'gree.com.cn']),
    ('长虹', [('zhwiki', '四川长虹'), ('enwiki', 'Changhong')], ['changhong.com']),
    ('奥克斯', [('zhwiki', '奥克斯集团'), ('enwiki', 'Aux Group')], ['auxgroup.com', 'aux.com']),
    ('追觅', [('zhwiki', '追觅科技'), ('enwiki', 'Dreame')], ['dreame.com', 'dreame.tech']),
    ('奥普', [('zhwiki', '奥普集团'), ('zhwiki', '奥普')], ['aupu.com']),
    ('雷士', [('zhwiki', '雷士照明'), ('enwiki', 'NVC Lighting')], ['nvc-lighting.com']),
    ('小熊', [('zhwiki', '小熊电器')], ['bear517.com']),
    ('欧井', [('zhwiki', '欧井')], ['eurgeen.com']),
    ('方太', [('zhwiki', '方太集团'), ('zhwiki', '方太')], ['fotile.com']),
    ('添可', [('zhwiki', '添可'), ('enwiki', 'Tineco')], ['tineco.com']),
    ('石头', [('zhwiki', '石头科技'), ('enwiki', 'Roborock')], ['roborock.com']),
    ('云鲸', [('zhwiki', '云鲸智能'), ('enwiki', 'Narwal')], ['narwal.com']),
    ('MOVA', [('enwiki', 'MOVA')], ['movatech.com', 'mova-tech.com']),
    ('澳柯玛', [('zhwiki', '澳柯玛'), ('enwiki', 'Aucma')], ['aucma.com', 'aucma.com.cn']),
    ('德尔玛', [('zhwiki', '德尔玛')], ['deerma.com']),
    ('352', [], ['352life.com', '352.com']),
    ('格兰仕', [('zhwiki', '格兰仕'), ('enwiki', 'Galanz')], ['galanz.com']),
    ('象印', [('zhwiki', '象印'), ('enwiki', 'Zojirushi')], ['zojirushi.com', 'zojirushi.co.jp']),
    ('坚果', [('zhwiki', '坚果投影'), ('enwiki', 'JMGO')], ['jmgo.com']),
    ('当贝', [('zhwiki', '当贝网络'), ('zhwiki', '当贝')], ['dangbei.com']),
    ('容声', [('zhwiki', '容声')], ['ronshen.com']),
    ('科沃斯', [('zhwiki', '科沃斯'), ('enwiki', 'Ecovacs')], ['ecovacs.com']),
    ('大疆', [('zhwiki', '大疆创新'), ('enwiki', 'DJI')], ['dji.com']),
    ('创维', [('zhwiki', '创维集团'), ('enwiki', 'Skyworth')], ['skyworth.com']),
    ('索尼', [('zhwiki', '索尼'), ('enwiki', 'Sony')], ['sony.com.cn', 'sony.com']),
    ('康佳', [('zhwiki', '康佳集团'), ('enwiki', 'Konka Group')], ['konka.com']),
    ('小天鹅', [('zhwiki', '小天鹅')], ['littleswan.com']),
    ('安吉尔', [('zhwiki', '安吉尔')], ['angel.com.cn']),
    ('美菱', [('zhwiki', '长虹美菱'), ('zhwiki', '美菱')], ['meiling.com']),
    ('林内', [('zhwiki', '上海林内'), ('zhwiki', '林内')], ['rinnai.com.cn']),
    ('A.O.史密斯', [('zhwiki', '艾欧史密斯'), ('enwiki', 'A. O. Smith')], ['aosmith.com.cn', 'aosmith.com']),
    ('万家乐', [('zhwiki', '广东万家乐'), ('zhwiki', '万家乐')], ['macro.com.cn']),
    ('能率', [('zhwiki', '能率'), ('enwiki', 'Noritz')], ['noritz.com.cn']),
    ('万和', [('zhwiki', '万和电气'), ('enwiki', 'Vanward')], ['vanward.com']),
    ('沁园', [('zhwiki', '沁园')], ['chinatruliva.com', 'truliva.com']),
    ('3M', [('enwiki', '3M')], ['3m.com.cn', '3m.com']),
]


def curl(url, out=None, tries=2):
    for a in range(tries):
        cmd = ['curl', '-sfL', '--compressed', '-A', UA, '--max-time', '60', '-w', '%{http_code}', url]
        if out:
            cmd += ['-o', str(out)]
        p = subprocess.run(cmd, capture_output=True)
        data = p.stdout
        code = data[-3:].decode(errors='replace') if len(data) >= 3 else '?'
        if code == '200':
            return data[:-3] if not out else True
        if code in ('404', '403', '410'):
            return None
        time.sleep(3 * (a + 1))
    return None


def p154_file(brand, titles):
    """Wikidata P154 → (文件名, 来源描述)；拿不到返回 None"""
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
            if vals:
                vals.sort()
                return vals[0][1], f'wikidata:{site}:{title}'
    return None


def touchicon(brand, domains):
    """官网 apple-touch-icon / 首页 link 声明 → (字节流, 来源描述)"""
    for dom in domains:
        for path in ('/apple-touch-icon.png', '/apple-touch-icon-precomposed.png'):
            u = f'https://{dom}{path}'
            data = curl(u)
            time.sleep(0.3)
            if data and data[:4] == b'\x89PNG':
                return data, f'touchicon:{dom}{path}'
        # 首页 link 解析
        html = curl(f'https://{dom}/')
        time.sleep(0.3)
        if html:
            try:
                text = html.decode('utf-8', errors='replace')
            except Exception:
                continue
            m = re.search(r'<link[^>]+rel="apple-touch-icon[^"]*"[^>]+href="([^"]+)"', text)
            if not m:
                m = re.search(r'<link[^>]+href="([^"]+)"[^>]+rel="apple-touch-icon[^"]*"', text)
            if m:
                href = m.group(1)
                if href.startswith('//'):
                    href = 'https:' + href
                elif href.startswith('/'):
                    href = f'https://{dom}{href}'
                elif not href.startswith('http'):
                    href = f'https://{dom}/{href}'
                data = curl(href)
                if data and data[:4] == b'\x89PNG':
                    return data, f'link:{href[:80]}'
    return None


def main():
    force = '--force' in sys.argv
    DST.mkdir(parents=True, exist_ok=True)
    CACHE.mkdir(parents=True, exist_ok=True)
    report = {}
    for brand, titles, domains in TABLE:
        dst = DST / f'{brand}.png'
        if dst.exists() and not force:
            report[brand] = 'skip(已有)'
            continue
        got = None
        hit = p154_file(brand, titles)
        if hit:
            fname, src = hit
            q = urllib.parse.quote(fname.replace('File:', ''), safe='')
            data = curl(f'https://commons.wikimedia.org/wiki/Special:FilePath/{q}?width=480',
                        out=CACHE / f'{brand}.bin')
            if data is None:
                data = curl(f'https://zh.wikipedia.org/wiki/Special:FilePath/{q}?width=480',
                            out=CACHE / f'{brand}.bin')
            if data is not None:
                got = CACHE / f'{brand}.bin'
                report[brand] = f'ok(P154) {fname}'
        if got is None:
            hit = touchicon(brand, domains)
            if hit:
                data, src = hit
                (CACHE / f'{brand}.bin').write_bytes(data)
                got = CACHE / f'{brand}.bin'
                report[brand] = f'ok({src})'
        if got is None:
            report[brand] = 'MISS'
        print(brand, '->', report[brand], flush=True)
        time.sleep(0.3)
    (CACHE / 'report.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=1), encoding='utf-8')
    print('下载完成，接下来运行 process-brand-logos 步骤生成 brands/*.png')


if __name__ == '__main__':
    main()
