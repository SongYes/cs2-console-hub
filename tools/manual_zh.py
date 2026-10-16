# -*- coding: utf-8 -*-
"""手工精修最后一批「机器翻译覆盖不到」的短条目。

这些条目英文原文本身没有可翻译的实质内容（"Test"、`playsound <soundname>`、本地化键名等），
机器翻译要么照抄原文、要么译错，所以直接给出中文释义。

写入 data/mt_cache.json，src=manual，构建时优先采用。
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "data" / "mt_cache.json"

MANUAL = {
    # 变量名（英文原文就是名字本身）
    "cl_draw_only_deathnotices":
        "只绘制准星与击杀提示，隐藏其余 HUD 元素（录制纯净画面时使用，需 sv_cheats 1）。",
    "cl_hud_radar_scale": "HUD 雷达的缩放比例（0.7~1.3），值越大雷达显示范围越大。",
    "cl_interp": "客户端插值时间（秒）。一般保持默认，由 cl_interp_ratio 与服务器 tick 自动决定。",
    "snd_steamaudio_enable_perspective_correction":
        "Steam Audio 的视角校正：按镜头朝向着色声音方向，让听声辨位更贴近视觉（1=开启）。",
    "bind": "绑定按键到指令：bind <按键> \"<指令>\"。不写指令时查询该键当前绑定。",
    "unbind": "解除按键绑定：unbind <按键>；unbindall 解除全部按键绑定。",
    "unbindall": "解除所有按键绑定（会把移动、开火等默认绑定一起清掉，慎用）。",
    # 极短、无实质内容的说明
    "mp_match_can_clinch":
        "比分领先到无法被追上时是否允许提前结束比赛：1=允许直接锁定胜局，0=必须打完全部回合。",
    "sv_party_mode":
        "派对模式开关（开发用玩笑功能，正式对局中无实际作用）。",
    "net_showmsg":
        "在控制台显示收到的网络消息：<0|1|2|名字>，1=全部消息、2=仅大包，也可指定消息名。",
    "net_showpeaks":
        "只显示超过指定大小的网络消息：net_showpeaks <字节数>（排查大包卡顿用）。",
    "playsound":
        "播放指定音效文件：playsound <音效名>（例如 playsound UI/buttonclick）。",
    "snd_sos_cl_soundevent_pause_last":
        "调试用：暂停最近一次客户端声音事件，用于排查声音事件链。",
    "snd_sos_cl_soundevent_start":
        "调试用：开始记录客户端声音事件，用于排查声音事件链。",
    "snd_sos_cl_soundevent_stop_last":
        "调试用：结束最近一次客户端声音事件记录，用于排查声音事件链。",
    "ShowSteamStatsSessionID":
        "在控制台打印当前的 Steam 统计数据会话 ID（需开发者模式非 0）。",
    "Test_Checkpoint":
        "调试用：向测试脚本标记一个检查点（仅开发环境有效）。",
    "Test_CreateEntity":
        "调试用：创建一个测试实体（仅开发环境有效）。",
    "Test_EHandle":
        "调试用：打印实体句柄信息（仅开发环境有效）。",
    "Test_StartLoop":
        "调试用：标记循环起点，供 Test_Loop 系列指令跳转（仅开发环境有效）。",
    "Test_StartScript":
        "调试用：启动一个测试脚本（仅开发环境有效）。",
    "Test_Loop":
        "调试用：无条件跳回指定的循环起点：Test_Loop <循环名>。",
    "Test_LoopCount":
        "调试用：跳回指定循环起点若干次：Test_LoopCount <循环名> <次数>。",
    "Test_LoopForNumSeconds":
        "调试用：在指定秒数内反复跳回循环起点：Test_LoopForNumSeconds <循环名> <秒数>。",
    "Test_RandomChance":
        "调试用：按百分比概率随机执行后续指令：Test_RandomChance <概率 0-100> <指令…>。",
    "Test_ExitProcess":
        "调试用：立即结束进程：Test_ExitProcess <退出码>。",
    "Test_RandomPlayerPosition":
        "调试用：把玩家随机传送到一个出生点（仅开发环境有效）。",
}


def main():
    cache = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}
    added = updated = 0
    for name, zh in MANUAL.items():
        key = name.lower()
        if key in cache and cache[key].get("zh") == zh:
            continue
        if key in cache:
            updated += 1
        else:
            added += 1
        cache[key] = {"zh": zh, "src": "manual"}
    CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=0), encoding="utf-8")
    print(f"[OK] 手工条目：新增 {added} 条，覆盖 {updated} 条；缓存共 {len(cache)} 条")


if __name__ == "__main__":
    main()
