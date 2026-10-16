# -*- coding: utf-8 -*-
"""把三份来源的指令名取并集，算出"只有上游 wiki、游戏里没验证过"的缺口。

三份来源：
  1. _dumps/cs2_cvarlist_full.txt  —— 用户提供的 VConsole2 完整导出（可能有断档）
  2. _dumps/cs2_cvarlist_mem.txt   —— 从进程内存抓到的输出（另一批名字，可互补）
  3. data/commands.json            —— 现有指令库（含上游 wiki 的 5145 条）

产出：
  data/gap_names.json   游戏里尚未验证的名字（供游戏内 `find` 批量核对）
  _dumps/verify_gap.cfg 直接丢进 csgo/cfg 执行的核对脚本

用法: python tools/find_gaps.py
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import import_cvar_dump as I  # noqa: E402

DUMP = ROOT / "_dumps" / "cs2_cvarlist_full.txt"
MEM = ROOT / "_dumps" / "cs2_cvarlist_mem.txt"
DATA = ROOT / "data"


def names_from_full(path):
    out = set()
    if not path.exists():
        return out
    txt = path.read_text(encoding="utf-8", errors="replace")
    parsed, _ = I.parse_dump(txt)
    return set(parsed)


def names_from_mem(path):
    out = set()
    if not path.exists():
        return out
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        m = re.match(r"^([\x21-\x7e]{2,80}?)\s*:", raw)
        if m:
            out.add(m.group(1).strip())
    return out


def main():
    db = json.loads((DATA / "commands.json").read_text(encoding="utf-8"))["entries"]
    db_names = {e["n"] for e in db}

    full = names_from_full(DUMP)
    mem = names_from_mem(MEM)
    game_verified = full | mem
    print(f"[i] 用户完整导出解析出   : {len(full)}")
    print(f"[i] 内存抓取补充         : {len(mem - full)} 条新名字")
    print(f"[i] 游戏侧已确认的名字   : {len(game_verified)}")

    gap = sorted(db_names - game_verified)
    print(f"[i] 库里存在但游戏侧未验证: {len(gap)}")
    print(f"    按前缀分布: " + ", ".join(
        f"{p}×{c}" for p, c in _top_prefix(gap, 14)))

    (DATA / "gap_names.json").write_text(
        json.dumps({"count": len(gap), "names": gap}, ensure_ascii=False, indent=1),
        encoding="utf-8")

    # 生成游戏内核对脚本：一次性把缺口名字全部验证
    lines = ["// CS2 指令库缺口核对：由 tools/find_gaps.py 生成",
             "// 放进 .../game/csgo/cfg/ 后执行： exec verify_gap",
             "// 控制台会逐行回报；把输出复制回来即可自动修正指令库",
             "con_enable 1",
             "echo ===== CS2HUB GAP VERIFY START ====="]
    for i, n in enumerate(gap, 1):
        lines.append(f"find {n}")
    lines.append("echo ===== CS2HUB GAP VERIFY END =====")
    cfg = ROOT / "_dumps" / "verify_gap.cfg"
    cfg.write_text("\r\n".join(lines) + "\r\n", encoding="utf-8")
    print(f"[OK] 核对脚本 -> {cfg}（{len(gap)} 行 find）")
    print(guidance(gap))
    return 0


def _top_prefix(names, k):
    from collections import Counter
    return Counter(n.split("_")[0] for n in names).most_common(k)


def guidance(gap):
    return ("\n下一步（二选一，都很快）：\n"
            "  A. 把 _dumps/verify_gap.cfg 复制到 "
            "Steam\\steamapps\\common\\Counter-Strike Global Offensive\\game\\csgo\\cfg\\，\n"
            "     在游戏控制台执行 `exec verify_gap`（必要时先 sv_cheats 1），"
            "把输出贴回来 → 我按结果删除/标记游戏中不存在的条目。\n"
            "  B. 在 VConsole2 里执行 `condump cs2hub_full.txt`（把控制台缓冲整段写盘），"
            "把生成的 cs2hub_full.txt 发我 → 直接得到无断档的完整清单。")


if __name__ == "__main__":
    raise SystemExit(main())
