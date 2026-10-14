# -*- coding: utf-8 -*-
"""核对：游戏 cvarlist 导出的官方说明 vs 指令库里最终的英文说明。

用法: python tools/audit_game_desc.py [--show N]
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import import_cvar_dump as I  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--show", type=int, default=10)
    args = ap.parse_args()

    E = {e["n"]: e for e in json.loads(
        (ROOT / "data" / "commands.json").read_text(encoding="utf-8"))["entries"]}
    txt = (ROOT / "_dumps" / "cs2_cvarlist_full.txt").read_text(encoding="utf-8", errors="replace")
    # 必须走与导入脚本完全相同的解析路径，否则核对的是另一套规则
    parsed, _skipped = I.parse_dump(txt)
    want = {n: {"desc": v.get("desc") or ""} for n, v in parsed.items()}

    same = diff = 0
    shown = 0
    for name, r in want.items():
        e = E.get(name)
        if not e or not r["desc"]:
            continue
        ours = (e["en"] or "").strip()
        theirs = r["desc"].strip()
        # 一致；或一方是另一方的片段（cvarlist 每条只打印一行，说明可能被折行截断）
        if ours == theirs or theirs in ours or ours in theirs:
            same += 1
        else:
            diff += 1
            if shown < args.show:
                shown += 1
                print(f"--- {name}")
                print(f"    游戏官方 : {theirs[:120]}")
                print(f"    库里现有 : {ours[:120]}")
    print(f"\n一致 {same} / 不一致 {diff}（共 {same + diff} 条官方有说明的）")
    # 官方没给说明的条目，库里英文必须是空的
    empty_bad = [n for n, r in want.items() if not r["desc"] and E.get(n, {}).get("en")]
    print(f"官方无说明但库里却有英文的条目（应为 0）: {len(empty_bad)} {empty_bad[:8]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
