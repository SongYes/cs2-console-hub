# -*- coding: utf-8 -*-
"""把内存里捞到的 cvarlist 原始字节流还原成干净的 cvarlist 文本。

内存里的输出不是干净的换行块：控制台缓冲区是环形写入的，读取时经常出现
"上一行的最后一个字母/一段尾巴" 粘在下一行名字前面的情况，例如

    ... : ID of the sound device to use
    snd_all...          ->  被读成  "Allsound_device_override"

本脚本的做法：
  1. 先把每个行长按 80/16/32/... 的列宽切分，得到候选 (name, value, flags, desc)
  2. 名字若是"干净"的（库里存在 / 明显合法）直接采用
  3. 否则尝试剥掉开头 0~4 个字符，如果剥离后能在已知名字集合里命中就用它
     ——已知名字集合 = 指令库 + 上游权威名单 + 本次同类行里出现过的名字
  4. 仍无法判定的丢弃，并在报告里列出来

用法：
  python tools/clean_mem_dump.py [--in _dumps/cs2_cvarlist_mem.txt] [--out data/game_dump.json]
"""
import argparse
import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

NAME_OK = re.compile(r"^[A-Za-z_+][A-Za-z0-9_+]*$")
# 列宽格式： 名称(80) : 值(16) : 权限(32) : 说明
COLS = re.compile(
    r"^([^\r\n]{1,80}?)\s*:\s*([^\r\n]{0,60}?)\s*:\s*([a-z_,\s]{0,60}?)\s*:\s?([\x20-\x7e]{0,400})\s*$")


def load_known():
    known = set()
    p = DATA / "commands.json"
    if p.exists():
        for e in json.loads(p.read_text(encoding="utf-8"))["entries"]:
            known.add(e["n"])
    for extra in ("game_extra.json", "game_dump.json"):
        q = DATA / extra
        if q.exists():
            try:
                blob = json.loads(q.read_text(encoding="utf-8"))
            except Exception:
                continue
            for e in blob.get("entries", []):
                if e.get("n"):
                    known.add(e["n"])
    return known


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="src", default=str(ROOT / "_dumps" / "cs2_cvarlist_mem.txt"))
    ap.add_argument("--out", dest="dst", default=str(DATA / "game_dump.json"))
    ap.add_argument("--report", default=str(DATA / "game_dump_report.json"))
    args = ap.parse_args()

    known = load_known()
    text = Path(args.src).read_text(encoding="utf-8", errors="replace")

    rows = []          # (name, value, flags, desc) 已确认干净
    rejected = []      # 无法判定的原始行
    recovered = []     # (mangled, fixed)
    for raw in text.splitlines():
        line = raw.rstrip()
        if not line.strip():
            continue
        m = COLS.match(line)
        if not m:
            rejected.append((line, "列宽不符"))
            continue
        name, val, flags, desc = (m.group(i).strip() for i in range(1, 5))
        if not NAME_OK.match(name) or len(name) < 2:
            rejected.append((line, "名字不合法"))
            continue
        if name in known:
            rows.append((name, val, flags, desc))
            continue
        # 尝试剥离被吞进来的前缀（1~5 字符）
        fixed = None
        for cut in range(1, min(6, len(name) - 1)):
            cand = name[cut:]
            if cand in known and NAME_OK.match(cand):
                fixed = cand
                break
        if fixed:
            recovered.append((name, fixed))
            rows.append((fixed, val, flags, desc))
        else:
            rejected.append((line, "未知名字"))

    # 同名去重：保留说明最长的一条
    best = {}
    for name, val, flags, desc in rows:
        cur = best.get(name)
        if cur is None or len(desc) > len(cur["desc"]):
            best[name] = {"name": name, "value": val, "flags": flags, "desc": desc}
    entries = []
    for name in sorted(best):
        r = best[name]
        flags = [f.strip() for f in re.split(r"[,\s]+", r["flags"]) if f.strip()]
        is_cmd = r["value"].lower() == "cmd"
        entries.append({
            "n": name,
            "en": r["desc"],
            "d": None if is_cmd else (r["value"] or None),
            "flags": flags,
            "k": "cmd" if is_cmd else "cvar",
        })

    out = {
        "note": "从 CS2/VConsole2 进程内存直读的 cvarlist 权威输出，经前缀修复后清洗",
        "source_file": str(Path(args.src).name),
        "raw_lines": len(text.splitlines()),
        "kept": len(entries),
        "recovered_from_mangle": len(recovered),
        "rejected": len(rejected),
        "cmds": sum(1 for e in entries if e["k"] == "cmd"),
        "entries": entries,
    }
    Path(args.dst).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    Path(args.report).write_text(json.dumps({
        "recovered": recovered[:200],
        "rejected": [r[0] for r in rejected[:200]],
        "rejected_reasons": Counter(r[1] for r in rejected).most_common(),
    }, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"[i] 原始行 {out['raw_lines']}")
    print(f"[i] 采用   {out['kept']} 条（其中 cmd {out['cmds']} 条）")
    print(f"[i] 前缀修复 {out['recovered_from_mangle']} 条")
    print(f"[i] 丢弃   {out['rejected']} 行 -> 见 {Path(args.report).name}")
    print(f"[OK] -> {args.dst}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
