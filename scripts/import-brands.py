#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""他品牌型号导入引擎（配置驱动，只**追加**新产品，绝不改动既有条目）。

为什么这样设计：
  - 站内既有产品可能正被另一个 Agent 的审核快照冻结，**本脚本只往 products.json 里加新对象**，
    不碰任何已有条目，因此不会与审核冲突（可用 npm run audit:check 验证）。
  - 小米商城只覆盖小米/米家，收录其他品牌改用太平洋产品报价（服务端渲染，可结构化抓取）。
  - 第三方报价不是官方价，所以**不写进 official_price**，而写进新增的 ref_price 字段。

用法：
    python scripts/import-brands.py                 # 按 data/_sources/brand-targets.json 全量跑
    python scripts/import-brands.py robot-vacuum    # 只跑一个品类
    python scripts/import-brands.py --dry robot-vacuum   # 只看会导入什么，不落盘

配置文件：data/_sources/brand-targets.json（每项含义见该文件 _说明）
缓存：   data/_cache/brand-<品类>-<品牌>.json、pconline-<品类>-<id>.json
"""
import json
import pathlib
import re
import sys
import time
import urllib.request

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
CACHE = ROOT / "data" / "_cache"
TARGETS = DATA / "_sources" / "brand-targets.json"

# 库文件的写入统一走 lib/library_io.py：规范序列化 + 写前指纹守卫（方案 P1-1）
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "lib"))
import library_io  # noqa: E402
DESK = "https://product.pconline.com.cn"
MOBILE = "https://g.pconline.com.cn/product"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
TODAY = "2026-10-01"
SOURCE = "太平洋电脑网"

# 审核标注字段（新增产品也要带齐）
AUDIT_KEYS = ["verify_status", "verify_date", "verify_source", "verify_url", "change_log", "updated_at"]


def fetch(url, tries=3):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Referer": DESK + "/"})
            with urllib.request.urlopen(req, timeout=25) as r:
                raw = r.read()
            # 太平洋不同页面编码不一致（详情页多为 UTF-8，部分列表页为 GBK）
            for enc in ("utf-8", "gb18030"):
                try:
                    return raw.decode(enc)
                except UnicodeDecodeError:
                    continue
            return raw.decode("utf-8", "replace")
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(2 + i * 2.5)
    raise last


def load_json(p):
    return json.loads(pathlib.Path(p).read_text(encoding="utf-8"))


def write_products(cat, prods, expect_hash):
    """写库（唯一允许的方式）：规范序列化 + 写前指纹校验。

    expect_hash 是脚本开头载入时的指纹；若中途有别的写入者改过库，library_io 会
    抛 LibraryConflict 拒绝覆盖，而不是静默丢掉对方的改动（方案 P1-1）。
    """
    library_io.save(DATA / cat / "products.json", prods, expect_hash=expect_hash)


# ---------------------------------------------------------------- 抓取

def parse_inline_specs(text):
    """品牌页里内联的参数摘要：'产品分类：家用洗地机；额定功率：68W；...'"""
    specs = {}
    for part in re.split(r"[；;]", text or ""):
        if "：" in part or ":" in part:
            k, v = re.split(r"[：:]", part, 1)
            k = k.strip()
            v = v.strip()
            if k and v and len(k) <= 20:
                specs.setdefault(k, v)
    return specs


def list_models(path, brand):
    """品牌页 -> [{id, 名称, 价格, specs}]（桌面站，服务端渲染）

    价格与参数都从列表页直接抽：列表页的 item-title-des 内联了主要参数，
    比逐款抓详情页快一个量级（1 个品牌 1 次请求 vs 每款 1 次）。
    """
    cf = CACHE / f"brand-{path}-{brand}.json"
    if cf.exists():
        return load_json(cf)
    html = fetch(f"{DESK}/{path}/{brand}/")
    pat = re.compile(rf"/{re.escape(path)}/{re.escape(brand)}/(\d{{5,9}})\.html")
    out = {}
    for m in pat.finditer(html):
        pid = m.group(1)
        # 从链接所在条目块里取名称、价格、内联参数
        start = html.rfind('<div class="item', 0, m.start())
        block = html[start if start > 0 else m.start() : m.start() + 4000]
        name = None
        for key in ("alt", "title"):
            mm = re.search(rf'{key}="([^"]{{4,80}})"', block)
            if mm:
                name = mm.group(1).strip()
                break
        if not name:
            continue
        pm = re.search(r"[¥￥￥]\s*(\d[\d,]*)", block)
        price = int(pm.group(1).replace(",", "")) if pm else None
        des = re.search(r'class="item-title-des"[^>]*>([^<]{10,600})<', block)
        specs = parse_inline_specs(des.group(1)) if des else {}
        if pid not in out:
            out[pid] = {"id": pid, "name": name, "price": price, "specs": specs}
    rows = list(out.values())
    cf.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    time.sleep(1.2)
    return rows


def fetch_specs(path, brand, pid):
    """规格页 -> {参数名: 值}"""
    cf = CACHE / f"pconline-{path}-{brand}-{pid}.json"
    if cf.exists():
        return load_json(cf)
    html = fetch(f"{MOBILE}/{path}/{brand}/{pid}_detail.html")
    specs = {}
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S):
        cells = [re.sub(r"<[^>]+>", "", c) for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, re.S)]
        cells = [re.sub(r"\s+", " ", c).replace("&nbsp;", " ").strip() for c in cells if c.strip()]
        for i in range(0, len(cells) - 1, 2):
            k, v = cells[i], cells[i + 1]
            if k and v and len(k) <= 20 and k not in specs:
                specs[k] = v
    cf.write_text(json.dumps(specs, ensure_ascii=False, indent=1), encoding="utf-8")
    time.sleep(1.2)
    return specs


# ---------------------------------------------------------------- 清洗

def num(text):
    if text is None:
        return None
    m = re.search(r"(\d+(?:\.\d+)?)", str(text).replace(",", ""))
    if not m:
        return None
    v = float(m.group(1))
    return int(v) if v == int(v) else v


def pick_code(name):
    """名称里的括号型号代码，如 添可芙万S20(FW24050ECN) -> FW24050ECN"""
    m = re.search(r"[（(]([A-Za-z0-9][A-Za-z0-9\-_/]{3,30})[)）]", name or "")
    if not m:
        return "查不到"
    code = m.group(1)
    if not re.search(r"\d", code):
        return "查不到"
    return code


CAPACITY_HINT = ("tank", "vol", "capacity", "cap", "cup")


def sane_capacity(field, value):
    """容量类字段的单位错标过滤：第三方常把 L 写成 ml（如净水箱 0.8ml 实为 0.8L）。
    只对 **ml 单位**且数值异常偏小（< 10）的值判错标——L 单位的 0.08L 尘杯是合法的，不能误杀。"""
    if value in (None, "查不到", "", "-", "无"):
        return "查不到"
    if not any(h in field.lower() for h in CAPACITY_HINT):
        return value
    if "ml" not in value.lower() and "毫升" not in value and "毫" not in value:
        return value  # 带 L/Liter 等单位，直接信任
    v = num(value)
    if v is None or v < 10:
        return "查不到"  # 水箱/尘杯不可能是 0.x ml
    return value


def map_specs(specs, mapping):
    """按配置把第三方参数名映射到本站字段；取不到就 查不到。"""
    out = {}
    for field, aliases in (mapping or {}).items():
        val = None
        for a in aliases:
            if a in specs:
                val = specs[a]
                break
        val = val if val not in (None, "", "-", "无") else "查不到"
        out[field] = sane_capacity(field, val)
    return out


def ensure_schema_fields(cat_id, extra_groups):
    """给 schema 补 brand / ref_price 字段，并把新增的分组值追加进 groupBy.order。"""
    sf = DATA / cat_id / "schema.json"
    s = load_json(sf)
    have = {f["key"] for f in s["fields"]}
    changed = False
    if "brand" not in have:
        idx = next((i + 1 for i, f in enumerate(s["fields"]) if f["key"] == "model_code"), 1)
        s["fields"].insert(idx, {"key": "brand", "label": "品牌", "type": "text", "card": "grid", "compare": True})
        changed = True
    if "ref_price" not in have:
        idx = next((i + 1 for i, f in enumerate(s["fields"]) if f["key"] == "official_price"), len(s["fields"]))
        s["fields"].insert(idx, {"key": "ref_price", "label": "参考价", "type": "number", "prefix": "¥", "compare": True, "sortable": True})
        changed = True
    for g in extra_groups or []:
        if g and g not in s["groupBy"]["order"]:
            s["groupBy"]["order"].append(g)
            changed = True
    if changed:
        sf.write_text(json.dumps(s, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return s


def resolve_group(cfg, specs):
    """分组值：优先按 groupMap 从第三方字段映射，取不到用默认 groupValue。"""
    src = cfg.get("groupSource")
    gmap = cfg.get("groupMap") or {}
    if src and gmap:
        raw = str(specs.get(src, "") or "")
        for k, v in gmap.items():
            if k in raw:
                return v
    # 主分组已改为 brand，副分组默认「—」（未归类）；不再使用「竞品」这一分组值
    return cfg.get("groupValue") or "—"


def build_product(cat_id, cfg, slug, brand_cn, m, specs, group_value):
    pid = f"{slug}_{m['id']}"
    mapped = map_specs(specs, cfg.get("map"))
    # 分组字段由 groupValue/groupMap 决定，绝不许被第三方同名参数（如「类别/产品类型」）覆盖
    mapped.pop(cfg.get("groupKey"), None)
    used = len([v for v in mapped.values() if v != "查不到"])
    product = {
        "id": pid,
        "name": m["name"],
        "brand": brand_cn,
        "model_code": pick_code(m["name"]),
        cfg["groupKey"]: group_value,
        "official_price": "查不到",
        "ref_price": m["price"] if m["price"] else "查不到",
        "year": "查不到",
        "pros": [],
        "cons": [],
        "tags": [brand_cn],
    }
    product.update(mapped)
    product["verify_status"] = "已核验（第三方）"
    product["verify_date"] = TODAY
    product["verify_source"] = [SOURCE]
    product["verify_url"] = f"{MOBILE}/{cfg['path']}/{slug}/{m['id']}_detail.html"
    product["change_log"] = (
        f"{TODAY} 建条：品牌型号与参数取自{SOURCE}规格表（{used} 项）；"
        f"第三方报价记入 ref_price，官方价待官方渠道核实"
    )
    product["updated_at"] = TODAY
    return product


def enrich(cat_id, cfg, dry=False):
    """回补已导入条目的参数：抓详情页补全字段，并对容量类做单位错标过滤。

    只作用于**本脚本新增**的产品（带 brand 且 id 形如 <品牌slug>_<id>），
    这些条目不在审核快照范围内，因此可以安全更新（可用 audit:check 验证）。
    """
    lib = library_io.load(DATA / cat_id / "products.json")
    prods = lib["products"]
    slugs = set((cfg.get("brands") or {}).keys())
    by_id = {p["id"]: p for p in prods}
    changed = 0
    for p in prods:
        if not p.get("brand"):
            continue
        slug = p["id"].rsplit("_", 1)[0]
        mid = p["id"].rsplit("_", 1)[1]
        if slug not in slugs or not mid.isdigit():
            continue
        try:
            specs = fetch_specs(cfg["path"], slug, mid)
        except Exception:  # noqa: BLE001
            continue
        mapped = map_specs(specs, cfg.get("map"))
        # 分组字段由导入时的 groupValue/groupMap 决定，绝不许被第三方「产品类型」覆盖
        mapped.pop(cfg.get("groupKey"), None)
        before = {k: p.get(k) for k in mapped}
        p.update({k: v for k, v in mapped.items() if v != "查不到" or p.get(k) in (None, "", "查不到")})
        if before != {k: p.get(k) for k in mapped}:
            changed += 1
    if not dry and changed:
        write_products(cat_id, prods, lib["hash"])
    print(f"  {cat_id}：回补 {changed} 条")
    return changed


def run(cat_id, cfg, dry=False):
    lib = library_io.load(DATA / cat_id / "products.json")
    prods = lib["products"]
    existing = {p["id"] for p in prods}
    # 可能用到的分组值（默认 + groupMap 里的所有映射目标）都要并进 groupBy.order，否则前端不显示
    possible = [cfg.get("groupValue"), *(cfg.get("appendGroups") or [])]
    possible += list((cfg.get("groupMap") or {}).values())
    possible = [g for g in possible if g]
    schema = ensure_schema_fields(cat_id, possible) if not dry else load_json(DATA / cat_id / "schema.json")

    added = 0
    skipped = 0
    for slug, brand_cn in (cfg.get("brands") or {}).items():
        try:
            models = list_models(cfg["path"], slug)
        except Exception as e:  # noqa: BLE001
            print(f"    ! {slug} 列表抓取失败：{str(e)[:50]}")
            continue
        # 优先取有价格的，其次按名称去重
        cands = [m for m in models if m.get("price")]
        cands.sort(key=lambda x: -x["price"])
        cands = cands[: cfg.get("pick", 6)]
        for m in cands:
            pid = f"{slug}_{m['id']}"
            if pid in existing:
                skipped += 1
                continue
            # 优先用列表页内联参数（已在 list_models 里抽好）；命中太少时回退抓详情页补全
            specs = m.get("specs") or {}
            filled = len([v for v in map_specs(specs, cfg.get("map")).values() if v != "查不到"])
            if filled < cfg.get("minFilled", 4):
                try:
                    detail = fetch_specs(cfg["path"], slug, m["id"])
                    for k, v in detail.items():
                        specs.setdefault(k, v)
                except Exception as e:  # noqa: BLE001
                    print(f"    ! {pid} 规格抓取失败：{str(e)[:40]}")
            p = build_product(cat_id, cfg, slug, brand_cn, m, specs, resolve_group(cfg, specs))
            if not dry:
                prods.append(p)
                existing.add(pid)
            added += 1
            print(f"    + {pid}  {m['name'][:40]}  ¥{m['price']}")
    if not dry and added:
        write_products(cat_id, prods, lib["hash"])
    print(f"  {cat_id}：新增 {added}，跳过已存在 {skipped}")


def main(argv):
    cfg_all = {k: v for k, v in load_json(TARGETS).items() if not k.startswith("_")}
    dry = "--dry" in argv
    only = [a for a in argv if not a.startswith("--")]
    for cat_id, cfg in cfg_all.items():
        if only and cat_id not in only:
            continue
        print(f"\n=== {cat_id}（path={cfg['path']}）===")
        try:
            if "--enrich" in argv:
                enrich(cat_id, cfg, dry=dry)
            else:
                run(cat_id, cfg, dry=dry)
        except Exception as e:  # noqa: BLE001
            print(f"  ! {cat_id} 失败：{str(e)[:80]}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
