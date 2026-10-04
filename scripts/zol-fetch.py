# -*- coding: utf-8 -*-
"""ZOL（中关村在线）抓取小工具：cookie 过墙 + 参数页/商品页解析。

2026-10-04 实测：detail.zol.com.cn 对无 cookie 请求返回 JS 跳转检查页
（service.zol.com.cn/checking），先 GET 一次 checking 拿 `ip_ck` cookie 即可通过。
param.shtml 的参数行是 `<p title="..."><span>参数名：</span>值</p>`。

用法（作为模块被其他脚本导入，或命令行自测）：
    python scripts/zol-fetch.py <url>            # 打印解析出的 {参数名: 值}
"""
import json, os, re, subprocess, sys, urllib.parse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CK = os.path.join(ROOT, 'data', '_cache', '_zol_cookies.txt')
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
os.makedirs(os.path.dirname(CK), exist_ok=True)

CHECKED = False


def _curl(url, extra=()):
    cmd = ['curl', '-sS', '-m', '25', '-A', UA,
           '-b', CK, '-c', CK, *extra, url]
    r = subprocess.run(cmd, capture_output=True)
    return r.stdout.decode('gbk', errors='replace')


def get(url, referer='https://www.zol.com.cn/'):
    """GET ZOL 页面；碰到检查页时先过 checking 再重试。"""
    global CHECKED
    t = _curl(url, ['-e', referer])
    if 'service.zol.com.cn/checking' in t[:500] or len(t) < 2000:
        # 过墙：请求一次 checking（backurl 随意，cookie 是域名级的）
        _curl('https://service.zol.com.cn/checking?backurl=' + urllib.parse.quote(url, safe=''))
        t = _curl(url, ['-e', referer])
    return t


def parse_param(t):
    """param.shtml -> {参数名: 值}；同时返回页面的商品名。

    2026-10-04 空气炸锅批次补充第二种版式：newPm 表格式
        <th><span id="newPmName_8">产品尺寸</span></th>
        <td class="hover-edit-param"><span id="newPmVal_8">285*340*295mm</span>
    两种版式并存时后者优先（新版式是当前线上主版式，旧 <p> 版式在部分老页面仍有）。
    """
    out = {}
    for m in re.finditer(r'<p title="([^"]*)"><span>([^<]{1,20})：</span>([^<]*)</p>', t):
        name = m.group(2).strip()
        val = (m.group(3) or m.group(1) or '').strip()
        if name and val and val != '暂无数据':
            out[name] = val
    # newPm 表格版式（当前线上主版式）：td 里带「纠错」<em>，用 DOTALL 贪到 </td> 再剥标签
    for m in re.finditer(
            r'<th><span[^>]*>([^<]{1,24})</span></th>\s*<td[^>]*>(.*?)</td>', t, re.S):
        name = m.group(1).strip()
        val = re.sub(r'<[^>]+>', '', m.group(2))
        val = re.sub(r'纠错$', '', val).strip()
        if name and val and val != '暂无数据':
            out[name] = val
    mt = re.search(r'<title>【([^】]{2,60})参数】', t)
    return (mt.group(1).strip() if mt else None), out


def parse_price(t):
    """商品页/参数页 -> (参考报价元, 价格说明)。ZOL 价格有「暂无报价」状态。"""
    m = re.search(r'class="price-type">([^<]{1,30})<', t)
    if not m:
        # 老版式：¥ 数字
        m = re.search(r'[￥¥]\s*<[^>]*>?\s*([0-9]{3,6})', t)
        if not m:
            return None, None
        return int(m.group(1)), '页面标价'
    s = m.group(1).strip()
    n = re.search(r'([0-9]{3,6})', s.replace(',', ''))
    if not n:
        return None, s  # 「暂无报价」等
    return int(n.group(1)), s


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    for url in sys.argv[1:]:
        t = get(url)
        if 'param.shtml' in url:
            name, params = parse_param(t)
            print('==', url)
            print('   name:', name)
            for k, v in params.items():
                print('   %s = %s' % (k, v))
        else:
            price, note = parse_price(t)
            print('==', url, '-> price:', price, note)
