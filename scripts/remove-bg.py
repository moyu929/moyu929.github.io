# -*- coding: utf-8 -*-
"""产品图主体提取：去背景 → 透明通道 WebP（原地替换）

为什么需要：官方产品图多带白底/黑底，站点明暗两套主题切换时图片背景会与
主题色冲突。把主体抠出来换成透明背景后，图片浮在卡片底色（--surface-alt）
上，任何主题都协调。

处理对象：public/images/<品类>/<产品id>.webp（≤320px，shrink-images.py 的产物）。
流程：
  1. rembg(U2Net) 抠主体 → RGBA
  2. 按 alpha 包围盒裁出主体，警惕两种失败：主体过小（误抠）/几乎满幅（没抠动）
  3. 主体等比缩放至画布 92%，居中放到 320×320 透明画布上（视觉尺寸归一，
     小缩略图里的产品比原图带大片留白时更大更清晰）
  4. 存回同名 WebP（带 alpha）

幂等：已带有效透明像素的图片跳过，重跑安全。
不可抠的（守卫拦截）保留原图并记录，宁缺勿滥。

用法：
    python scripts/remove-bg.py --dry              # 只统计，不写
    python scripts/remove-bg.py                    # 全量处理
    python scripts/remove-bg.py --only heater      # 只处理某品类
    python scripts/remove-bg.py --model u2net      # 指定模型（默认 u2net）
    python scripts/remove-bg.py --sheet 24         # 处理并输出联络表供目检

模型说明：默认 u2net（约 176MB）。实测 RTX 3080 上 GPU 推理 0.02s/张、
与 1GB 级的 bria-rmbg 在家电产品照上质量无实质差别（A/B 见
data/_cache/ab-test.png 生成脚本思路），而 bria 在 CPU 上 37s/张、GPU 上
4.5s/张——批量场景用 u2net。首次运行会下载模型到 ~/.rembg/models/。
执行 provider 自动探测：CUDA > DirectML > CPU（Windows 无需配 cuDNN，
装 onnxruntime-directml 即可吃 GPU）。
"""
import argparse
import io
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
IMG_ROOT = ROOT / 'public' / 'images'

TARGET = 320        # 画布尺寸，与 shrink-images.py 的上限一致
FILL = 0.92         # 主体长边占画布比例
QUALITY = 85        # 略高于管线的 80：alpha 边缘需要更多比特
MIN_FRAC = 0.04     # 主体面积占画布比下限（低于此判为误抠）
MAX_FRAC = 0.97     # 上限（高于此判为没抠动，常见于背景与主体同色）


def has_alpha(img):
    """已处理过的图（带有效透明像素）→ 跳过，保证幂等"""
    if img.mode != 'RGBA':
        return False
    alpha = img.getchannel('A')
    lo, hi = alpha.getextrema()
    if lo >= 250:
        return False
    transparent = sum(1 for v in alpha.getdata() if v < 16)
    return transparent / (img.width * img.height) > 0.01


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--only', help='只处理该品类目录')
    ap.add_argument('--dry', action='store_true', help='只统计，不写入')
    ap.add_argument('--renormalize', action='store_true',
                    help='对已透明的图跳过推理，直接按 alpha 重算包围盒并重新居中归一'
                         '（修「主体贴边」：rembg 软雾/离群噪点会把原始 getbbox 撑大）')
    ap.add_argument('--sheet', type=int, default=0, help='输出 N 张样本联络表（目检用）')
    ap.add_argument('--model', default='u2net', help='rembg 模型名（默认 u2net）')
    ap.add_argument('--provider', default='auto', choices=['auto', 'cuda', 'dml', 'cpu'],
                    help='推理后端（默认 auto：CUDA > DirectML > CPU）')
    args = ap.parse_args()

    from rembg import remove, new_session
    from PIL import Image, ImageDraw

    def subject_bbox(im):
        """主体包围盒：alpha 硬阈值化后再取——rembg 输出的主体外围常带半透明软雾，
        原始 getbbox() 会被雾/离群噪点撑大，导致主体在画布上偏离居中。"""
        solid = im.getchannel('A').point(lambda v: 255 if v > 127 else 0)
        return solid.getbbox()

    def recanvas(rgba, bbox):
        subject = rgba.crop(bbox)
        side = max(subject.size)
        pad = int(side * (1 / FILL - 1) / 2)
        square = Image.new('RGBA', (side + pad * 2, side + pad * 2), (0, 0, 0, 0))
        square.paste(subject, (pad, pad), subject)
        return square.resize((TARGET, TARGET), Image.LANCZOS)

    def pick_providers():
        import onnxruntime as ort
        if args.provider != 'auto':
            chosen = {'cuda': 'CUDAExecutionProvider', 'dml': 'DmlExecutionProvider'}.get(args.provider)
            return [chosen, 'CPUExecutionProvider'] if chosen else ['CPUExecutionProvider']
        avail = ort.get_available_providers()
        chosen = [p for p in ('CUDAExecutionProvider', 'DmlExecutionProvider') if p in avail]
        return chosen + ['CPUExecutionProvider']

    providers = pick_providers()
    # session 只建一次：模型加载放循环外，否则每张图都重初始化
    session = new_session(args.model, providers=providers)
    print(f'模型 {args.model}｜provider {providers[0]}')

    files = sorted(IMG_ROOT.glob('*/*.webp'))
    if args.only:
        files = [f for f in files if f.parent.name == args.only]
    if not files:
        print('没有找到图片')
        return

    done, skipped, kept = [], [], []
    sheet_tiles = []
    t0 = time.time()

    for i, f in enumerate(files, 1):
        cat = f.parent.name
        try:
            img = Image.open(f)
            img.load()
        except Exception as e:
            kept.append((f, f'解码失败 {e}'))
            continue

        if has_alpha(img):
            if not args.renormalize:
                skipped.append((f, '已是透明背景'))
                continue
            rgba = img.convert('RGBA')
            bbox = subject_bbox(rgba)
            if not bbox:
                continue
            canvas = recanvas(rgba, bbox)
            if args.dry:
                continue
            buf = io.BytesIO()
            canvas.save(buf, 'WEBP', quality=QUALITY, method=6)
            f.write_bytes(buf.getvalue())
            done.append((f, 'renormalize'))
            continue
        elif args.renormalize:
            # renormalize 的语义是「只重整已透明的图」——保留原图（无 alpha 的满幅/营销图）
            # 严禁在此被 rembg 重抠（2026-10-06 实测：营销图被抠成透明主体）
            kept.append((f, '保留原图（renormalize 不触碰无 alpha 的图）'))
            continue

        rgba = remove(img.convert('RGBA'), session=session)
        bbox = subject_bbox(rgba)
        if not bbox:
            kept.append((f, '未检出主体'))
            continue
        frac = (bbox[2] - bbox[0]) * (bbox[3] - bbox[1]) / (rgba.width * rgba.height)
        if frac < MIN_FRAC:
            kept.append((f, f'主体过小（{frac:.0%}），疑似误抠'))
            continue
        if frac > MAX_FRAC:
            kept.append((f, f'几乎满幅（{frac:.0%}），疑似未抠动'))
            continue

        canvas = recanvas(rgba, bbox)

        if args.dry:
            done.append((f, f'{frac:.0%}'))
        else:
            buf = io.BytesIO()
            canvas.save(buf, 'WEBP', quality=QUALITY, method=6)
            f.write_bytes(buf.getvalue())
            done.append((f, f'{frac:.0%} {len(buf.getvalue()) // 1024}KB'))

        if len(sheet_tiles) < args.sheet:
            tile = Image.new('RGB', (TARGET // 2, TARGET // 2 + 14), (40, 44, 52))
            thumb = canvas.resize((TARGET // 2, TARGET // 2), Image.LANCZOS)
            tile.paste(thumb, (0, 0), thumb)
            ImageDraw.Draw(tile).text((4, TARGET // 2 + 2), f'{cat}/{f.stem[:14]}', fill=(220, 224, 230))
            sheet_tiles.append(tile)

        if i % 40 == 0:
            print(f'  … {i}/{len(files)}（{time.time() - t0:.0f}s）')

    print(f'\n共 {len(files)} 张：处理 {len(done)} / 跳过(已透明) {len(skipped)} / 保留原图 {len(kept)}'
          f'（{time.time() - t0:.0f}s）')
    for f, why in kept:
        print(f'  · 保留原图 {f.relative_to(ROOT)} —— {why}')
    if len(kept) > 20:
        print(f'  …（其余 {len(kept) - 20} 条省略）')

    if sheet_tiles:
        cols = 6
        rows = (len(sheet_tiles) + cols - 1) // cols
        sheet = Image.new('RGB', (cols * TARGET // 2, rows * (TARGET // 2 + 14)), (24, 26, 32))
        for idx, tile in enumerate(sheet_tiles):
            sheet.paste(tile, ((idx % cols) * TARGET // 2, (idx // cols) * (TARGET // 2 + 14)))
        out = ROOT / 'data' / '_cache' / 'remove-bg-sheet.png'
        out.parent.mkdir(parents=True, exist_ok=True)
        sheet.save(out)
        print(f'联络表（深色底目检）：{out}')


if __name__ == '__main__':
    main()
