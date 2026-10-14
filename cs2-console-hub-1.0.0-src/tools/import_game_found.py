# -*- coding: utf-8 -*-
"""把「游戏文件扫描」发现的缺失 cvar 并入库（人工核对过名字，标注来源为 game）。

为什么需要人工核对：
  字符串扫描无法证明某个名字一定是 cvar（可能是类名、着色器变量、源文件名）。
  这里只收「看起来确实是玩家/服务器可调 cvar」的条目，并把它们单独记在
  data/game_extra.json 里、来源标成 game，便于日后被权威导出覆盖或删除。

真实权威来源请用 tools/import_cvar_dump.py（游戏内 cvarlist 导出）。
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

# 从扫描结果里人工核对过、判定为真 cvar 的名字（按家族分组便于回顾）
CONFIRMED = [
    # 准星（CS2 新版准星参数）
    "cl_crosshair_dynamic_spread_limit", "cl_crosshair_gap", "cl_crosshair_length",
    "cl_crosshair_screen_height", "cl_crosshair_thickness", "cl_crosshaircolor_a",
    "cl_crosshairoutline_a", "cl_crosshairoutline_b", "cl_crosshairoutline_g",
    "cl_crosshairoutline_r",
    # HUD / 雷达 / 观战
    "cl_hud_radar_blur_background", "cl_radar_square_always",
    "cl_radar_square_when_spectating", "cl_show_bombs", "cl_sniper_show_inaccuracy",
    "cl_spectator_predict", "cl_obs_interp_speed", "cl_use_prompt_smoke_density",
    "cl_playerslot_in_names", "cl_radar_show_all_players_when_spectating",
    "cl_force_spec_hud_color_to_team", "cl_hud_bomb_under_radar",
    # 网络 / 插值 / 诊断
    "cl_interp_parallel", "net_ping_p5", "net_ping_p50", "net_ping_p95",
    "net_quality_in_graph", "net_quality_in_graph_scale",
    "net_quality_out_graph", "net_quality_out_graph_scale",
    "net_detailed_ping", "net_basic_ping", "net_flow",
    "net_message_size_enforce", "net_permutation_info",
    "net_skip_redundant_change_callbacks",
    # 声音
    "snd_chicken_obscured_fade_time", "snd_surf_volume_inair",
    "snd_surf_volume_map", "snd_surf_volume_slide",
    "snd_min_latency", "snd_music_mode", "snd_report_audio_nan",
    # 玩法 / 服务器
    "mp_solid_enemies", "mp_shoot_dropped_grenades", "mp_team_intro_type",
    "mp_dm_taser_bonus_streak_max", "bot_takeover", "bot_strafe",
    "bot_path_require_reachable_goal", "bot_defense_rush_chance",
    # 画面（玩家可调范围）
    "r_decals_distance_scale", "r_decals_distance_scale_start",
    "r_decals_distance_scale_end", "r_decals_max_triangle_anchored",
    "r_decals_triangle_max_stretch", "r_character_decal_monitor_render_res",
    "r_spectator_flashbang_opacity", "r_dlss_preset",
    "r_allow_low_gpu_memory_mode", "r_animatable_mesh_shaders",
]


def main():
    scan = json.loads((DATA / "game_scan.json").read_text(encoding="utf-8"))
    names = scan["names"]
    db = json.loads((DATA / "commands.json").read_text(encoding="utf-8"))
    db_names = {e["n"] for e in db["entries"]}
    missing = json.loads((DATA / "game_missing.json").read_text(encoding="utf-8"))["missing_names"]
    missing_set = set(missing)

    entries, skipped = [], []
    for n in CONFIRMED:
        if n in db_names:
            skipped.append((n, "库里已有"))
            continue
        if n not in missing_set:
            skipped.append((n, "扫描结果里没有（可能名字写错）"))
            continue
        info = names.get(n, {})
        entries.append({
            "n": n,
            "en": "",
            "d": None,
            "s": "unknown",
            "f": "",
            "k": "cvar",
            "src": "game",
            "hits": info.get("hits", 0),
            "files": info.get("files", []),
        })

    out = {
        "note": "由本地 CS2 游戏文件字符串扫描发现、经人工核对的 cvar；"
                "权威版本请用 tools/import_cvar_dump.py 从游戏内 cvarlist 导出后覆盖",
        "source": "game files (client.dll / server.dll 等) 字符串扫描",
        "entries": entries,
    }
    (DATA / "game_extra.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[OK] game_extra.json 写入 {len(entries)} 条游戏发现的新 cvar")
    if skipped:
        print(f"     跳过 {len(skipped)} 条：")
        for n, why in skipped:
            print(f"       {n:44s} {why}")
    print("\n写入示例：")
    for e in entries[:12]:
        print(f"   {e['n']:44s} hits={e['hits']:<4} {','.join(e['files'][:2])}")


if __name__ == "__main__":
    main()
