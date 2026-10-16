# -*- coding: utf-8 -*-
"""等游戏把 cvarlist 写进 console.log，然后自动解析入库。

前置：CS2 启动项里要有 -condebug（本脚本会检查并提示）。
用法：
    python tools/watch_console_log.py            # 等到 console.log 明显变大才解析
    python tools/watch_console_log.py --now      # 立即解析现有 console.log
    python tools/watch_console_log.py --minutes 30

判定「导出完成」：文件里出现 `total convars/concommands` 或解析出的条目数 > 2000。
"""
import argparse
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
LOG = Path(r"C:\Program Files (x86)\Steam\steamapps\common\Counter-Strike Global Offensive"
           r"\game\csgo\console.log")
ALT_LOGS = [
    LOG,
    Path(r"C:\Program Files (x86)\Steam\steamapps\common\Counter-Strike Global Offensive"
         r"\game\csgo_lv\console.log"),
    Path(r"D:\SteamLibrary\steamapps\common\Counter-Strike Global Offensive\game\csgo\console.log"),
]


def find_log():
    for p in ALT_LOGS:
        if p.exists():
            return p
    return LOG


def try_parse(path: Path, apply=True):
    import import_cvar_dump as I
    text = path.read_text(encoding="utf-8", errors="replace")
    cvars, skipped = I.parse_dump(text, is_cmd=False)
    print(f"[i] {path.name}: 解析 {len(cvars)} 条 cvar（跳过 {skipped} 行），"
          f"文件 {path.stat().st_size/1024/1024:.1f} MB")
    if len(cvars) < 200:
        return None
    # 指令行（cmd 段）也一起收
    cmds, _ = I.parse_dump(text, is_cmd=True)
    for k, v in cmds.items():
        cvars.setdefault(k, v)
    db = json.loads((ROOT / "data/commands.json").read_text(encoding="utf-8"))
    db_names = {e["n"] for e in db["entries"]}
    new = sorted(n for n in cvars if n not in db_names)
    print(f"[i] 其中库里没有的 {len(new)} 条")
    out = ROOT / "data" / "game_dump.json"
    out.write_text(json.dumps({
        "source": str(path), "parsed_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "total": len(cvars), "new_count": len(new), "new_names": new,
        "entries": [{"n": n, "en": v.get("desc", ""), "d": v.get("default") or v.get("value"),
                     "s": _scope(v.get("flags") or []), "f": ", ".join(v.get("flags") or []),
                     "k": v.get("kind", "cvar"), "src": "game-dump",
                     "is_new": n not in db_names} for n, v in cvars.items()],
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[OK] 写入 data/game_dump.json")
    print(f"[→] 接下来执行： python tools\\build_db.py   （会自动并入权威导出）")
    return cvars


def _scope(flags):
    f = set(flags)
    cl, sv = "client" in f, "server" in f
    if cl and sv:
        return "both"
    return "client" if cl else ("server" if sv else "unknown")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--now", action="store_true", help="不等，立刻解析现有日志")
    ap.add_argument("--minutes", type=int, default=20, help="最多等多少分钟")
    ap.add_argument("--min-mb", type=float, default=3.0, help="console.log 至少多大才认为导出完成")
    args = ap.parse_args()

    path = find_log()
    print(f"[i] 监视 {path}")
    if not path.exists():
        print("[!] 文件不存在。请确认 CS2 启动项含 -condebug，并且游戏至少启动过一次。")
        print("    当前启动项应为： -insecure -condebug")
        if not args.now:
            return 1

    if args.now:
        got = try_parse(path)
        return 0 if got else 1

    deadline = time.time() + args.minutes * 60
    last = -1
    while time.time() < deadline:
        size = path.stat().st_size if path.exists() else 0
        if size != last:
            print(f"    console.log = {size/1024/1024:.2f} MB"
                  f"（目标 ≥ {args.min_mb} MB）", flush=True)
            last = size
        if size >= args.min_mb * 1024 * 1024:
            print("[i] 日志已足够大，尝试解析…")
            got = try_parse(path)
            if got:
                return 0
        time.sleep(5)
    print("[!] 等待超时。可在游戏里执行 cvarlist 后再跑： --now")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
