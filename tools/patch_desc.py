# -*- coding: utf-8 -*-
"""贴片：修正 cvarlist 定宽列被截断导致的英文说明残缺。

个别行的权限列写满 32 字符时，列宽切分会把结尾的 ':' 漏进说明里，
于是库里出现 "Set which ent_text filters you want: " 这种尾巴带冒号的说明。
这里按"游戏导出里该条目的真实说明"重新回填（缺失部分从上游文案补全）。

用法: python tools/patch_desc.py [--apply]
"""
import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    E = json.loads((DATA / "commands.json").read_text(encoding="utf-8"))["entries"]
    bad = [e["n"] for e in E if re.search(r":\s*$", (e["en"] or "")) and (e["en"] or "").strip()]
    print(f"[i] 英文说明以冒号结尾（可能被截断）的条目 {len(bad)} 条")
    for n in bad[:20]:
        e = next(x for x in E if x["n"] == n)
        print(f"    {n:40s} en={e['en'][:80]!r}")
    if not bad:
        return 0
    if not args.apply:
        print("[i] 预览模式，加 --apply 才写入")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
