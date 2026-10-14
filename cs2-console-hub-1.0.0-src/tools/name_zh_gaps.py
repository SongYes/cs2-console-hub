# -*- coding: utf-8 -*-
"""统计"名字推断"卡在哪些英文词上，用于按频次补词表。

用法: python tools/name_zh_gaps.py [--top 80]
"""
import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import name_zh as N  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=60)
    args = ap.parse_args()

    db = json.loads((ROOT / "data" / "commands.json").read_text(encoding="utf-8"))
    entries = db["entries"]
    # 只看"没有官方英文说明"的条目——这些才是需要名字推断的
    need = [e for e in entries if not (e.get("en") or "").strip()]
    print(f"[i] 没有官方英文说明的条目: {len(need)}")

    gap = []
    for e in need:
        low = e["n"].lower()
        pre = max((p for p in N.PREFIX_FAMILY if low.startswith(p)), key=len, default=None)
        stem = low[len(pre):] if pre else low
        blocks, _h, missed = N._tokens_of(stem)
        for kind, text in blocks:
            if kind == "raw":
                gap.append(text)
    c = Counter(gap)
    print(f"[i] 未译片段（去重后 {len(c)} 种），按出现次数排前 {args.top}：")
    for w, n in c.most_common(args.top):
        print(f"    {n:4d}  {w}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
