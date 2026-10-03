#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""把草稿区的订正稿与待入库区已有的订正稿合并，避免互相覆盖。

场景：`fill-mi-official.py` 往 `data/_draft/` 写了 17 款产品的官方参数，其中 7 款
在 `data/_intake/` 里**已经有一份订正稿**（批次 1/2 补的卖点与第三方缓存值）。
此时直接 `flow:submit` 会把草稿区文件搬到待入库区并**覆盖**掉那份，等于丢掉已补的
pros/cons 与缓存字段；而先 withdraw 又会用待入库区的文件**覆盖**草稿区，丢掉官方参数。

正确顺序：先把草稿区内容读进内存 → withdraw（把待入库区那份取回草稿区）→
以取回的内容为基底，用内存里的官方参数**只补空值** → 写回草稿区 → 提交。

用法：
    python scripts/merge-draft-intake.py            # 合并 data/_draft/ 下的全部产品
    python scripts/merge-draft-intake.py --dry      # 只看会合并哪些
"""
import argparse
import json
import os
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BLANK = (None, "", "查不到", "—", "-")


def blank(v):
    return v in BLANK or (isinstance(v, list) and not v)


def draft_keys():
    out = []
    root = os.path.join(ROOT, "data", "_draft")
    for cat in sorted(os.listdir(root)):
        d = os.path.join(root, cat)
        if not os.path.isdir(d):
            continue
        for fn in sorted(os.listdir(d)):
            if fn.endswith(".json"):
                out.append((cat, fn[:-5]))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true")
    args = ap.parse_args()

    merged, plain = [], []
    for cat, pid in draft_keys():
        dp = os.path.join(ROOT, "data", "_draft", cat, pid + ".json")
        ip = os.path.join(ROOT, "data", "_intake", cat, pid + ".json")
        draft = json.load(open(dp, encoding="utf-8"))
        if not os.path.exists(ip):
            plain.append(f"{cat}/{pid}")
            continue
        merged.append(f"{cat}/{pid}")
        if args.dry:
            continue
        # 1) 先把草稿区这份挪开：flow 的 withdraw 拒绝覆盖草稿区同名文件
        #    （「草稿区已有同名文件，先处理它再撤回」——这道保护避免了静默丢数据）
        bak = dp + ".bak"
        os.replace(dp, bak)
        r = subprocess.run(["node", "scripts/flow.mjs", "withdraw", f"{cat}/{pid}", "--by", "bing"],
                           cwd=ROOT, capture_output=True)
        if r.returncode != 0:
            os.replace(bak, dp)  # 撤回失败就还原，别把草稿弄丢
            print(f"  ✗ withdraw 失败（草稿已还原）：{cat}/{pid}")
            continue
        os.remove(bak)
        base = json.load(open(dp, encoding="utf-8"))
        n = 0
        for k, v in draft.items():
            if k in ("id", "pros", "cons"):
                continue
            if blank(base.get(k)) and not blank(v):
                base[k] = v
                n += 1
        # change_log 两边都要留
        for src in (draft,):
            cl = (src.get("change_log") or "").strip("；")
            if cl and cl not in (base.get("change_log") or ""):
                base["change_log"] = (base.get("change_log", "") + "；" if base.get("change_log") else "") + cl
        json.dump(base, open(dp, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        print(f"  ✓ {cat}/{pid}：合并 {n} 个字段")

    print(f"\n合并 {len(merged)} 款（待入库区已有订正稿），其余 {len(plain)} 款直接提交")
    if merged:
        print("  合并：", "、".join(merged[:10]), "…" if len(merged) > 10 else "")
    keys = [f"{c}/{p}" for c, p in draft_keys()]
    if keys and not args.dry:
        cmds = ["npm run flow:submit -- " + " ".join(keys) + " --by bing"]
        sh = os.path.join(ROOT, "data", "_cache", "_bing_submit4.ps1")
        open(sh, "w", encoding="utf-8").write("\n".join(cmds) + "\n")
        print(f"\n  提交命令：{os.path.relpath(sh, ROOT)}（{len(keys)} 款）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
