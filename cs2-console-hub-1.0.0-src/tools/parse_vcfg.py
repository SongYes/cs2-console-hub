# -*- coding: utf-8 -*-
"""解析 CS2 写出的 .vcfg 设置快照，拿到一份「游戏实际认得的 cvar」清单。

这些文件由 host_writeconfig / 退出游戏时刷新，格式是 KeyValues：
    "config" { "convars" { "sv_cheats" "0" ... } }

它只包含「非默认值 + 存档型」的 cvar，所以不是完整清单，
但它是**游戏自己写出来的**，可以当作权威交叉验证：凡是这里出现、
而我们库里没有的，就是确凿的缺失。

位置：
    <Steam>\\userdata\\<id>\\730\\local\\cfg\\cs2_machine_convars.vcfg
    <Steam>\\userdata\\<id>\\730\\local\\cfg\\cs2_user_convars_0_slot0.vcfg

用法： python tools/parse_vcfg.py [--apply]
"""
import argparse
import glob
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

KV = re.compile(r'"([^"]+)"\s+"([^"]*)"')
# per_user 变量在存档里带槽位后缀：hud_scaling$3 —— 变量名本身没有 $n
SLOT_SUFFIX = re.compile(r"\$\d+$")


def strip_slot(name: str) -> str:
    return SLOT_SUFFIX.sub("", name)


def parse_vcfg(path: Path):
    """返回 {cvar: value}；只取 convars 段。"""
    txt = path.read_text(encoding="utf-8", errors="replace")
    out = {}
    depth = 0
    in_convars = False
    for raw in txt.splitlines():
        line = raw.strip()
        if not line:
            continue
        if '"convars"' in line:
            in_convars = True
            continue
        if line == "}" and in_convars:
            in_convars = False
            continue
        if not in_convars:
            continue
        m = KV.match(line)
        if m and m.group(1) not in ("convars", "config"):
            out[strip_slot(m.group(1))] = m.group(2)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true",
                    help="把新发现的 cvar 并入 data/game_extra.json（不带说明）")
    args = ap.parse_args()

    pats = [
        r"C:\Program Files (x86)\Steam\userdata\*\730\local\cfg\cs2_*.vcfg",
        r"D:\SteamLibrary\steamapps\common\Counter-Strike Global Offensive\game\csgo\cfg\*_default.vcfg",
    ]
    files = []
    for p in pats:
        files += [Path(x) for x in glob.glob(p)]

    allcv = {}
    for f in files:
        got = parse_vcfg(f)
        if got:
            print(f"[i] {f.name}: {len(got)} 个 cvar")
            for k, v in got.items():
                allcv.setdefault(k, {"value": v, "files": []})["files"].append(f.name)

    if not allcv:
        print("[!] 没找到可解析的 .vcfg 文件")
        return 1

    db = json.loads((DATA / "commands.json").read_text(encoding="utf-8"))
    db_names = {e["n"] for e in db["entries"]}
    missing = sorted(n for n in allcv if n not in db_names)
    print(f"\n[i] vcfg 快照合计 {len(allcv)} 个 cvar，其中库里没有的 {len(missing)} 个")
    for n in missing:
        print(f"    {n:48s} = {allcv[n]['value'][:24]}   ({','.join(allcv[n]['files'][:2])})")

    if args.apply and missing:
        extra_path = DATA / "game_extra.json"
        raw = json.loads(extra_path.read_text(encoding="utf-8")) if extra_path.exists() else \
            {"note": "游戏文件发现", "entries": []}
        have = {e["n"] for e in raw["entries"]}
        added = 0
        for n in missing:
            if n in have:
                continue
            raw["entries"].append({"n": n, "en": "", "d": allcv[n]["value"], "s": "unknown",
                                   "f": "", "k": "cvar", "src": "game-vcfg",
                                   "files": allcv[n]["files"]})
            added += 1
        extra_path.write_text(json.dumps(raw, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"[OK] 已并入 {added} 条到 data/game_extra.json（记得跑 build_db.py）")
    elif missing:
        print("[i] 加 --apply 可并入 data/game_extra.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
