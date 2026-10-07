# -*- coding: utf-8 -*-
"""批 5B 采集脚本：pressure-cooker / refrigerator / humidifier 共 48 款无图产品。

路线（前四批验证）：pconline 产品主页 og:image / alt 含型号的 img → 失败换
g.pconline.com.cn 镜像 → 备用域名跳过。断点续跑：已下载的跳过。
产物：data/_cache/img-src/<品类>/<id>.<ext> + manifest.json
"""
import json
import re
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / 'data' / '_cache' / 'img-src'
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36'
TARGETS = json.loads((ROOT / 'data' / '_cache' / 'img-b5-targets.json').read_text(encoding='utf8'))


def curl(url, out=None, referer=None):
    cmd = ['curl', '-sfL', '--compressed', '--max-time', '30', '-A', UA]
    if referer:
        cmd += ['-e', referer]
    if out:
        cmd += ['-o', str(out)]
    cmd.append(url)
    p = subprocess.run(cmd, capture_output=True)
    return p.stdout if not out else (out.exists() and out.stat().st_size > 1000)


def page_image(home_url, model_token):
    """pconline 主页 → og:image 或 alt 含型号的 img。返回 (url, alt) 或 None。"""
    for host in (None, 'g.pconline.com.cn'):
        u = home_url
        if host:
            u = re.sub(r'product\.pconline\.com\.cn', host, home_url)
        html = curl(u, referer=u)
        time.sleep(0.3)
        if not html:
            continue
        text = html.decode('utf-8', errors='replace')
        # og:image 优先（详情页与主页都可能带）
        m = re.search(r'property="og:image"[^>]+content="([^"]+)"', text)
        if m and m.group(1).startswith('http'):
            return m.group(1), 'og:image'
        # alt 含完整型号的 img
        for tag in re.findall(r'<img[^>]{0,300}?>', text, re.S):
            alt = re.search(r'alt="([^"]{4,60})"', tag)
            src = re.search(r'(?:src|data-src)="([^"]+\.(?:png|jpe?g|webp))"', tag)
            if alt and src and model_token and model_token != '查不到':
                tok = re.sub(r'[^A-Za-z0-9]', '', model_token)[:8]
                if tok and tok in re.sub(r'[^A-Za-z0-9]', '', alt.getgroup(1) if False else alt.group(1)):
                    return src.group(1), alt.group(1)[:30]
        # 兜底：img 路径含 product/大图特征的
        m = re.search(r'<img[^>]+src="(https://img[0-9a-z.]*pconline[^"]*(?:product|big)[^"]*\.(?:png|jpe?g|webp))"', text, re.I)
        if m:
            return m.group(1), 'img-path'
    return None


def main():
    manifest = {}
    for i, t in enumerate(TARGETS, 1):
        key = f"{t['cat']}/{t['id']}"
        out_dir = RAW / t['cat']
        out_dir.mkdir(parents=True, exist_ok=True)
        # 断点：已下载的跳过
        existing = list(out_dir.glob(t['id'] + '.*'))
        if existing:
            manifest[key] = {'url': 'cached', 'file': str(existing[0].name)}
            print(f'{i:2d}/{len(TARGETS)} {key} 已缓存', flush=True)
            continue
        if not t['url'] or 'pconline' not in t['url']:
            manifest[key] = None
            print(f'{i:2d}/{len(TARGETS)} {key} 无 pconline 链接，跳过', flush=True)
            continue
        home = t['url'].replace('_detail.html', '.html')
        model_token = t['model'] or (t['name'].split()[-1] if ' ' in t['name'] else '')
        got = page_image(home, model_token)
        if not got:
            manifest[key] = None
            print(f'{i:2d}/{len(TARGETS)} {key} MISS', flush=True)
            continue
        url, how = got
        ext = url.split('?')[0].rsplit('.', 1)[-1].lower()[:4]
        ext = ext if ext in ('png', 'jpg', 'webp', 'gif') else 'jpg'
        out = out_dir / f"{t['id']}.{ext}"
        ok = curl(url, out=out)
        size = out.stat().st_size if out.exists() else 0
        ok = ok and size > 3000
        manifest[key] = {'url': url[:150], 'how': how, 'file': out.name, 'size': size} if ok else None
        if not ok:
            out.unlink(missing_ok=True)
        print(f'{i:2d}/{len(TARGETS)} {key} {"OK " if ok else "FAIL"} {how} {size}B', flush=True)
        time.sleep(0.35)

    (ROOT / 'data' / '_cache' / 'img-b5-manifest.json').write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1), encoding='utf-8')
    ok = sum(1 for v in manifest.values() if v)
    print(f'\n完成：命中 {ok} / {len(TARGETS)}')


if __name__ == '__main__':
    main()
