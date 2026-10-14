# -*- coding: utf-8 -*-
"""把 scan_game.py 的原始候选筛成「高置信 cvar 名单」。

关键点：字符串扫描会把类名（weapon_ak47）、实体名（env_fade）、
源文件名（animgraph）一起挖出来，所以需要用**引擎自己的注册特征**来区分：

  1. 家族前缀（cl_ / sv_ / mp_ / r_ / snd_ / ...）——最强信号
  2. 同一二进制里存在 Valve cvar 的标记串（"sv, cl, rep, cheat"、"norecord" 等），
     说明这个二进制确实在注册 cvar
  3. 排除已知的非 cvar 家族（实体/函数/武器/动画图/皮肤/脚本等）

用法：
  python tools/filter_game_names.py            # 输出报告
  python tools/filter_game_names.py --export   # 顺便导出 data/game_cvars.txt
"""
import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

# 引擎 cvar 家族前缀（按其命名习惯，可信度高）
FAMILY = re.compile(
    r"^(cl_|sv_|mp_|r_|snd_|sndev_|host_|net_|ai_|bot_|phys_|mat_|lb_|sc_|ui_|panorama_|"
    r"spec_|tv_|demo_|steam_|gc_|mm_|fps_|func_|ent_|game_|player_|weapon_|ammo_|item_|env_|"
    r"sound_|voice_|vphysics_|ragdoll_|ik_|animgraph|nav_|cs_|csgo_|cstrike|blur_|sfm_|model_|"
    r"filesystem_|engine_|script_|props_|particle_|pixel_|shader_|vfc_|vtex_|vismon_|"
    r"benchmark_|budget_|mem_|net_|prop_|rope_|rt_|rubikon_|sc_|sfm_|spray_|steam_|"
    r"sys_|time_|tool_|ui_|vgui_|viewmodel_|vprof_|vsync|world_|workshop_)"
)

# 明确不是 cvar 的家族：实体类名、武器名、动画图资源、UI 面板、脚本实体等
NOT_CVAR_FAMILY = re.compile(
    r"^(weapon_[a-z0-9_]+|item_[a-z0-9_]+|env_[a-z0-9_]+|func_[a-z0-9_]+|phys_[a-z0-9_]+|"
    r"prop_[a-z0-9_]+|player_[0-9]+|player_attachment_[0-9]+|animgraph[0-9]+|animgraph_[a-z0-9_]+|"
    r"ragdoll_[a-z0-9_]+|sound_area_[a-z0-9_]+|snd_event_[a-z0-9_]+|snd_opvar_[a-z0-9_]+|"
    r"cs_[a-z]+$|csgo_[a-z0-9_]+|go_[a-z0-9_]+|item_[0-9]+_item_id|"
    r"player_([a-z0-9_]+)$|model_[a-z0-9_]+|particle_[a-z0-9_]+|vertex_[a-z0-9_]+|"
    r"volume_[a-z0-9_]+|vote_[a-z0-9_]+|visual_[a-z0-9_]+|vdata_[a-z0-9_]+|vtex_[a-z0-9_]+|"
    r"vmdl_[a-z0-9_]+|vmat_[a-z0-9_]+|vsnd_[a-z0-9_]+|webm_[a-z0-9_]+|wasm_[a-z0-9_]+|"
    r"xp_[a-z0-9_]+|steam_player_[a-z0-9_]+|week[a-z_]*|year[a-z_]*|word_[a-z0-9_]+|"
    r"window_[a-z0-9_]+|zone_[a-z0-9_]+|zrule_[a-z0-9_]+|ztrans_[a-z0-9_]+|"
    r"weight[a-z0-9_]*|water_[a-z0-9_]+|wind_[a-z0-9_]+|waypoint_[a-z0-9_]+|"
    r"vzone_[a-z0-9_]+|vertex[a-z0-9_]*|version_[a-z0-9_]+|velocity_[a-z0-9_]+|"
    r"vector[a-z0-9_]*|vec[a-z0-9_]*|vload[a-z0-9_]*|vstore[a-z0-9_]*|"
    r"unknow[a-z0-9_]*|un[a-z]{3,}[a-z0-9_]+|up[a-z0-9_]*|ur[a-z0-9_]*|ui_[a-z0-9_]+|"
    r"uidna[a-z0-9_]*|ul[a-z]{4,}[a-z0-9_]*|um[a-z]{4,}[a-z0-9_]*|unorm[a-z0-9_]*|"
    r"unum[a-z0-9_]*|uprv_[a-z0-9_]+|upvec_[a-z0-9_]+|uregex_[a-z0-9_]+|uset_[a-z0-9_]+|"
    r"ustr_[a-z0-9_]+|utext_[a-z0-9_]+|utf[a-z0-9_]*|utrie[a-z0-9_]*|uts_[a-z0-9_]+|"
    r"ubrk_[a-z0-9_]+|ucal_[a-z0-9_]+|ucasemap_[a-z0-9_]+|ucnv[a-z0-9_]*|ucol[a-z0-9_]*|"
    r"ucsdet_[a-z0-9_]+|ucurr_[a-z0-9_]+|udat[a-z0-9_]*|udata_[a-z0-9_]+|udtitvfmt_[a-z0-9_]+|"
    r"uenum_[a-z0-9_]+|ufieldpositer_[a-z0-9_]+|ufmt[a-z0-9_]*|ugender_[a-z0-9_]+|"
    r"uhash_[a-z0-9_]+|uiter_[a-z0-9_]+|uldn_[a-z0-9_]+|ulist[a-z0-9_]*|uloc[a-z0-9_]*|"
    r"ulocdata_[a-z0-9_]+|ulocimp_[a-z0-9_]+|ultag_[a-z0-9_]+|umeas_[a-z0-9_]+|"
    r"umsg_[a-z0-9_]+|umtx_[a-z0-9_]+|umutablecptrie_[a-z0-9_]+|unorm2_[a-z0-9_]+|"
    r"unumf[a-z0-9_]*|unumrf_[a-z0-9_]+|unumsys_[a-z0-9_]+|uplrules_[a-z0-9_]+|"
    r"u_[a-z0-9]+|[a-z]{1,2}_[a-z0-9]+$)"
)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--export", action="store_true")
    ap.add_argument("--min-hits", type=int, default=1)
    args = ap.parse_args()

    scan = json.loads((DATA / "game_scan.json").read_text(encoding="utf-8"))
    names = scan["names"]
    db = json.loads((DATA / "commands.json").read_text(encoding="utf-8"))
    db_names = {e["n"] for e in db["entries"]}

    keep, drop = {}, Counter()
    for n, info in names.items():
        if info["hits"] < args.min_hits:
            continue
        if not FAMILY.match(n):
            drop["无家族前缀"] += 1
            continue
        if NOT_CVAR_FAMILY.match(n):
            drop["已知非 cvar 家族"] += 1
            continue
        if len(n) > 40 or n.count("_") > 5:
            drop["名字过长/下划线过多"] += 1
            continue
        keep[n] = info

    new = {n: i for n, i in keep.items() if n not in db_names}
    print(f"原始候选        : {len(names)}")
    print(f"过滤后高置信度  : {len(keep)}")
    print(f"  其中库里已有  : {len(keep) - len(new)}")
    print(f"  库里缺失      : {len(new)}")
    print(f"过滤掉的原因    : {dict(drop)}")

    fam = Counter(n.split("_")[0] + "_" for n in new)
    print("\n缺失项按家族分布（前 20）:")
    for f, c in fam.most_common(20):
        print(f"   {f:14s} {c:>4}")

    print("\n缺失项里命中次数最高 / 最像玩家可调的前 60 条:")
    def score(item):
        n, i = item
        s = i["hits"]
        if n.startswith(("cl_", "sv_", "mp_", "r_", "snd_")):
            s += 50
        if any(k in n for k in ("crosshair", "hud", "radar", "volume", "fps", "sensitivity",
                                "viewmodel", "interp", "rate", "voice", "shadow", "particle",
                                "texture", "shadow", "vsync", "gamma", "color")):
            s += 30
        return -s
    for n, i in sorted(new.items(), key=score)[:60]:
        files = ",".join(i["files"][:2])
        print(f"   {n:44s} hits={i['hits']:<5} {files}")

    out = {
        "high_confidence_total": len(keep),
        "in_db": len(keep) - len(new),
        "missing": len(new),
        "dropped_reasons": dict(drop),
        "missing_names": sorted(new),
        "family_histogram": fam.most_common(30),
    }
    (DATA / "game_missing.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    if args.export:
        (DATA / "game_cvars.txt").write_text("\n".join(sorted(keep)), encoding="utf-8")
        print(f"\n[OK] 已导出 data/game_cvars.txt（{len(keep)} 条高置信名单）")
    print("[OK] 报告写入 data/game_missing.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
