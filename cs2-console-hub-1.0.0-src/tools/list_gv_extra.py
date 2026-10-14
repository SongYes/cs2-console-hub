# -*- coding: utf-8 -*-
"""列出「标记为游戏内确认」但不在本机 cvarlist 完整导出里的条目。

库里的 gv=1 集合 = 用户完整导出（_dumps/cs2_cvarlist_full.txt）∪ 进程内存抓取
（_dumps/cs2_cvarlist_mem.txt）。游戏自己报的总数是 2802，所以多出来的部分应该
正好是"只被内存抓取见到、没出现在完整导出里"的那些名字。
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import import_cvar_dump as I  # noqa: E402


def main():
    db = json.loads((ROOT / "data" / "commands.json").read_text(encoding="utf-8"))
    E = {e["n"]: e for e in db["entries"]}
    gv = {n for n, e in E.items() if e.get("gv")}

    full_txt = (ROOT / "_dumps" / "cs2_cvarlist_full.txt").read_text(encoding="utf-8", errors="replace")
    parsed, _ = I.parse_dump(full_txt)
    exported = set(parsed)
    exported_cmd = {n for n, v in parsed.items() if v.get("kind") == "cmd"}

    mem_names = set()
    mem_path = ROOT / "_dumps" / "cs2_cvarlist_mem.txt"
    if mem_path.exists():
        for raw in mem_path.read_text(encoding="utf-8", errors="replace").splitlines():
            m = re.match(r"^([\x21-\x7e]{2,80}?)\s*:", raw)
            if m:
                mem_names.add(m.group(1).strip())

    print(f"库里 gv=1（游戏内确认）      : {len(gv)}")
    print(f"完整导出解析出的名字          : {len(exported)}（游戏自报 2802）")
    print(f"内存抓取到的名字              : {len(mem_names)}")
    print(f"游戏 / 导出 的差              : {len(exported) - 2802:+d}")
    print()

    only_mem = sorted(gv - exported)
    print(f"= 只在内存抓取里出现、不在完整导出里 : {len(only_mem)} 条")
    for n in only_mem:
        e = E[n]
        src = "cmd" if n in exported_cmd else "cvar"
        print(f"   {n:44s} {src:4s} flags={e.get('f') or '—':34s} en={(e['en'] or '')[:44]!r}")

    missing = sorted(exported - gv)
    print()
    print(f"反向：导出里有、库里却没标 gv 的 : {len(missing)} 条 {missing[:10]}")
    print(f"内存抓取里、完整导出里也没有的  : {len(mem_names - exported)} 条")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
