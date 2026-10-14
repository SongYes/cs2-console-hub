# -*- coding: utf-8 -*-
"""核对：导出文件里真正的 cvarlist 输出到底有多少条，多出来的名字是什么。

背景：`cvarlist` 的输出是连续的记录块，块与块之间是别的日志行。
如果按"整份文件逐行匹配"来数，会把日志里其它恰好长得像记录的行也算进来。
本脚本用「连续成段」的方式只认真正的输出块，并与逐行匹配的结果对比，列出差异。
"""
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import import_cvar_dump as I  # noqa: E402

SRC = ROOT / "_dumps" / "cs2_cvarlist_full.txt"


def contiguous_names(lines, min_run=20):
    """只收连续成段的记录（真正的 cvarlist 输出块）。"""
    runs, cur = [], []
    for raw in lines:
        line = I.LOGPREFIX.sub("", raw).rstrip()
        rec = None
        if line and not I.SUMMARY.match(line):
            rec = I.parse_colon_fields(line)
        if rec:
            cur.append(rec)
        else:
            if len(cur) >= min_run:
                runs.append(cur)
            cur = []
    if len(cur) >= min_run:
        runs.append(cur)
    return runs


def main():
    lines = SRC.read_text(encoding="utf-8", errors="replace").splitlines()
    runs = contiguous_names(lines)
    print(f"发现 {len(runs)} 个连续输出块：")
    block_names = set()
    for i, r in enumerate(runs, 1):
        names = {x["name"] for x in r}
        block_names |= names
        print(f"  块 {i}: {len(r)} 行 / {len(names)} 个不同名字  "
              f"[{r[0]['name']} … {r[-1]['name']}]")

    loose, _ = I.parse_dump("\n".join(lines))
    loose_names = set(loose)
    print()
    print(f"连续块并集            : {len(block_names)}")
    print(f"整份文件逐行匹配      : {len(loose_names)}")
    noise = sorted(loose_names - block_names)
    print(f"逐行匹配多出来的      : {len(noise)}  ← 这些多半是日志噪声，不是真指令")
    for n in noise[:40]:
        print(f"    {n:44s} desc={(loose[n].get('desc') or '')[:56]!r}")
    print()
    print(f"连续块里有、逐行匹配却没有的: {len(block_names - loose_names)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
