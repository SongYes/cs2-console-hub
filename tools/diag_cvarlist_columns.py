# -*- coding: utf-8 -*-
"""确认 cvarlist 输出的列位置是否严格固定（用来区分真记录与日志频道行）。

真 cvarlist 记录的 ' : ' 分隔符落在固定列：79-81 / 98-100 / 133-135（第 4 个在 133 之后）。
日志频道行的冒号位置是随机的，用这个可以几乎无误地区分。
"""
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import import_cvar_dump as I  # noqa: E402

TXT = (ROOT / "_dumps" / "cs2_cvarlist_full.txt").read_text(encoding="utf-8", errors="replace")

sig = Counter()
ok_examples = {}
bad_examples = {}
for raw in TXT.splitlines():
    line = I.LOGPREFIX.sub("", raw).rstrip()
    if not line or I.SUMMARY.match(line):
        continue
    # 只统计"看起来像记录"的行：以合法标识符开头，且含至少两个 ':' 
    if not re.match(r"^[A-Za-z_+][A-Za-z0-9_+]*\s", line):
        continue
    cols = [i for i, c in enumerate(line) if c == ":"]
    if len(cols) < 3:
        continue
    key = (cols[0], cols[1], cols[2])
    sig[key] += 1
    tgt = ok_examples if (cols[0], cols[1]) == (81, 100) else bad_examples
    tgt.setdefault(key, line[:150])

print("分隔符列位置分布（前 12）：")
for k, n in sig.most_common(12):
    print(f"   列{k} 出现 {n} 次")
print()
print("严格列位置(81,100,135) 的行数:", sig.get((81, 100, 135), 0))
print("前两列正确(81,100) 的行数 :", sum(n for k, n in sig.items() if k[:2] == (81, 100)))
print()
print("非标准列位置的样例：")
for k, n in sig.most_common(40):
    if k[:2] != (81, 100):
        print(f"   {k} ×{n}: {bad_examples.get(k, '')[:120]}")
