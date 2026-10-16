# -*- coding: utf-8 -*-
"""从游戏二进制里搞清楚 `cvarlist` / `cmdlist` 到底把结果写到哪个文件。

做法：定位 "cvarlist" 字符串，把它前后各 400 字节里的可打印字符串全列出来，
通常就能看到它拼接的输出文件名（例如 "cvarlist.txt" / "console.log"）。

用法： python tools/find_dump_filename.py
"""
import re
import sys
from pathlib import Path

CS2 = Path(r"C:\Program Files (x86)\Steam\steamapps\common\Counter-Strike Global Offensive")
TARGETS = [
    CS2 / "game/bin/win64/engine2.dll",
    CS2 / "game/bin/win64/tier0.dll",
    CS2 / "game/csgo/bin/win64/client.dll",
    CS2 / "game/csgo/bin/win64/server.dll",
    CS2 / "game/bin/win64/vconsole2.exe",
    CS2 / "game/bin/win64/cs2.exe",
]
KEYWORDS = [b"cvarlist", b"cmdlist", b"dump_cvars", b"writecvars", b"cvarlist.txt"]

ASCII = re.compile(rb"[\x20-\x7e]{3,80}")


def scan(path: Path):
    if not path.exists():
        return []
    raw = path.read_bytes()
    out = []
    for kw in KEYWORDS:
        start = 0
        while True:
            i = raw.find(kw, start)
            if i < 0:
                break
            start = i + 1
            lo, hi = max(0, i - 500), min(len(raw), i + 500)
            window = raw[lo:hi]
            strings = [m.group(0).decode("ascii", "ignore") for m in ASCII.finditer(window)]
            out.append((kw.decode(), i, strings))
    return out


def main():
    for t in TARGETS:
        hits = scan(t)
        if not hits:
            continue
        print("=" * 72)
        print(f"{t.name}  ({t.stat().st_size/1024/1024:.1f} MB)  命中 {len(hits)} 处")
        # 只展示最可能有信息量的：含 .txt / console / write 的窗口
        shown = 0
        for kw, off, strings in hits:
            joined = " | ".join(strings)
            interesting = re.search(r"\.txt|console|write|log|dump", joined, re.I)
            if not interesting and shown >= 3:
                continue
            print(f"\n  [{kw}] @0x{off:x}")
            for s in strings:
                if len(s) >= 3:
                    print(f"      {s}")
            shown += 1
            if shown >= 8:
                break
    return 0


if __name__ == "__main__":
    sys.exit(main())
