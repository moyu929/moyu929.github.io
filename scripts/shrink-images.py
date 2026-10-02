#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""产品图规范化：public/images 下所有图片统一压成 ≤320px WebP，并回写 img 字段。

为什么是 320px：
  全站最大的图片展示位是产品卡片缩略图 96×112 CSS px（桌面端，见 ProductCard.vue），
  按 DPR 3 计需要 288px 宽，320px 足够；时间轴缩略图 56×64、对比抽屉 80×68 更小。
  此前仓库存 640px JPEG，属过采样（面积约 4 倍），且 WebP 比同质量 JPEG 再小 25~35%。

为什么只留一份、不保留大图：
  展示位最大只有 96px 宽，为它存一张 640px 原图不划算；需要大图时按
  data/_sources/images.json 重新从官方商城拉取即可（`npm run mi:images`），
  所以这里直接降采样替换，不做双份存储。

用法：
    python scripts/shrink-images.py            # 转换 public/images 下的 png/jpg
    python scripts/shrink-images.py --dry      # 只报数不落盘
    python scripts/shrink-images.py --raw      # 顺带把 data/_cache/img-raw 下的原图也转进来
"""
import json
import pathlib
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass

from PIL import Image

ROOT = pathlib.Path(__file__).resolve().parent.parent
IMAGES = ROOT / "public" / "images"
RAW = ROOT / "data" / "_cache" / "img-raw"
MAX_EDGE = 320
QUALITY = 80
SRC_EXT = (".png", ".jpg", ".jpeg", ".webp")

# 三个流转分区：产品在哪个区，img 就回写到哪个区的文件（图片本来就不走分区）
ZONES = ("_draft", "_intake", "_review")

# 库文件的写入统一走 lib/library_io.py：规范序列化 + 写前指纹守卫（方案 P1-1）
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "lib"))
import library_io  # noqa: E402


def write_zone(path: pathlib.Path, obj: dict) -> None:
    """分区文件是缩进 2 空格的 JSON（与 flow.mjs 的 writePretty 同款）"""
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def apply_img(p: dict, cat_id: str) -> bool:
    """把 p['img'] 由旧扩展名改成 .webp；改到了就返回 True"""
    img = p.get("img")
    if not img or img.lower().endswith(".webp"):
        return False
    stem = pathlib.Path(img).stem
    if (IMAGES / cat_id / f"{stem}.webp").exists():
        p["img"] = f"{stem}.webp"
        return True
    return False


def iter_zone_products(cat_id: str):
    """产出 (文件路径, 产品对象)；只含实际存在的分区文件"""
    for zone in ZONES:
        zd = ROOT / "data" / zone / cat_id
        if not zd.exists():
            continue
        for f in sorted(zd.glob("*.json")):
            try:
                yield f, json.loads(f.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                continue


def convert(src: pathlib.Path, dest: pathlib.Path, dry: bool) -> tuple[int, int]:
    """返回 (原大小, 新大小)；已存在且更新的 webp 直接复用。"""
    if src.suffix.lower() == ".webp" and src.resolve() == dest.resolve():
        return src.stat().st_size, src.stat().st_size
    if not dry:
        im = Image.open(src).convert("RGB")
        im.thumbnail((MAX_EDGE, MAX_EDGE), Image.LANCZOS)  # 不会放大
        dest.parent.mkdir(parents=True, exist_ok=True)
        im.save(dest, "WEBP", quality=QUALITY, method=6)
    return src.stat().st_size, (dest.stat().st_size if dest.exists() else 0)


def main(argv) -> int:
    dry = "--dry" in argv
    include_raw = "--raw" in argv

    sources = [p for p in IMAGES.rglob("*") if p.suffix.lower() in SRC_EXT and p.suffix.lower() != ".webp"]
    if include_raw and RAW.exists():
        sources += [p for p in RAW.rglob("*") if p.suffix.lower() in SRC_EXT]

    if not sources:
        print("没有需要转换的图片。")
        return 0

    before = after = 0
    for src in sorted(sources):
        if src.is_relative_to(RAW) if hasattr(src, "is_relative_to") else False:
            rel = src.relative_to(RAW)
            dest = IMAGES / rel.with_suffix(".webp")
        else:
            dest = src.with_suffix(".webp")
        try:
            b, a = convert(src, dest, dry)
        except Exception as e:  # noqa: BLE001
            print(f"  ✗ {src.relative_to(ROOT)}: {e}")
            continue
        before += b
        after += a

    print(f"转换 {len(sources)} 张：{before / 1024 / 1024:.2f}MB → {after / 1024 / 1024:.2f}MB"
          f"（省 {100 - after * 100 // max(before, 1)}%）")
    if dry:
        print("（--dry 模式，未落盘）")
        return 0

    # 回写 img 字段：产品在哪个分区就改哪个分区；库内产品经 library_io（带指纹守卫）
    # categories.json 是两层结构（一级品类 -> 小品类），要摊平后再遍历
    groups = json.loads((ROOT / "data" / "categories.json").read_text(encoding="utf-8"))
    cats = [c for g in groups for c in g.get("categories", [])]
    changed = 0
    for c in cats:
        cid = c["id"]
        for f, obj in list(iter_zone_products(cid)):
            if apply_img(obj, cid):
                write_zone(f, obj)
                changed += 1
                print(f"  ↻ 分区 {f.relative_to(ROOT)}")
        pf = ROOT / "data" / cid / "products.json"
        if not pf.exists():
            continue
        lib = library_io.load(pf)
        hit = 0
        for p in lib["products"]:
            if apply_img(p, cid):
                hit += 1
        if hit:
            library_io.save(pf, lib["products"], expect_hash=lib["hash"])
            changed += hit
    print(f"回写 img 字段 {changed} 处")

    # 没有残留旧扩展名引用时，才删除旧图
    leftover = 0
    for c in cats:
        cid = c["id"]
        for _, obj in iter_zone_products(cid):
            if str(obj.get("img") or "").lower().endswith((".png", ".jpg", ".jpeg")):
                leftover += 1
        pf = ROOT / "data" / cid / "products.json"
        if not pf.exists():
            continue
        for p in json.loads(pf.read_text(encoding="utf-8")):
            if str(p.get("img") or "").lower().endswith((".png", ".jpg", ".jpeg")):
                leftover += 1
    if leftover:
        print(f"仍有 {leftover} 处旧扩展名引用未转换，保留原文件不删")
        return 1
    removed = 0
    for src in sources:
        if src.suffix.lower() != ".webp" and src.exists() and not (include_raw and src.is_relative_to(RAW)):
            src.unlink()
            removed += 1
    print(f"已删除旧图 {removed} 个")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
