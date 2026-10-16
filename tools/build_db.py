# -*- coding: utf-8 -*-
"""CS2 控制台指令查询中心 —— 数据构建流水线

输入（_raw/）：
  armync_cvarlist.md   全量 cvar/命令 + 英文描述（ArmynC/ArminC-CS2-Cvars）
  ohlasfar_release.txt 官方 release 标记的命令清单（OhLasFar/CS2-ALL-Console-Commands-Repository）

输出（data/）：
  commands.json  结构化指令库（含中文释义、分类、作用域、默认值、风险标记）
  db_meta.json   版本与统计信息

分级说明：
  scope: client / server / both / unknown
  release: True 表示随正式版客户端下发（竞技可用）
  danger: 打开后可能影响账号安全（如 sv_cheats 类、开发调试类）的提示级别
"""
import json
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "_raw"
DATA = ROOT / "data"
DATA.mkdir(exist_ok=True)

from zh_dict import HAND_ZH, HAND_CLASS, GLOSSARY, PHRASE_RULES  # noqa: E402

MT_CACHE = {}          # 英文原文（小写）-> 中文，main() 里加载

# --------------------------------------------------------------------------- #
# 1. 解析 ArmynC 全量列表
# --------------------------------------------------------------------------- #


def parse_armync(path: Path):
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines()[2:]:
        if not line.strip():
            continue
        parts = line.split("|")
        if len(parts) < 2:
            continue
        name = parts[0].strip()
        flags = parts[1].strip()
        desc = "|".join(parts[2:]).strip() if len(parts) > 2 else ""
        if not name:
            continue
        rows.append({"name": name, "flags": flags, "desc": desc})
    return rows


def parse_release(path: Path):
    """OhLasFar 行格式： name : value/kind : flags : description"""
    out = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        parts = [p.strip() for p in line.split(":")]
        if len(parts) < 3:
            continue
        name, value, flags = parts[0], parts[1], parts[2]
        desc = ":".join(parts[3:]).strip()
        if name:
            out[name] = {"value": value, "flags": flags, "desc": desc}
    return out


# 去重（循环词）与术语纠错复用 fix_mt_cache 里的实现，保证构建与服务端一致
try:
    from fix_mt_cache import dedupe as _dedupe
except Exception:                                    # pragma: no cover
    def _dedupe(x):
        return x


HTML_ENT = {
    "&lt;": "<",
    "&gt;": ">",
    "&amp;": "&",
    "&quot;": '"',
    "&#39;": "'",
    "&nbsp;": " ",
}


def load_game_extra():
    """游戏文件扫描 / cvarlist 导出发现的额外条目。

    合并优先级：game_extra.json（人工核对/扫描） < game_dump.json（游戏 cvarlist 权威导出），
    后者带官方说明与权限标记，应当覆盖前者的推断内容。
    """
    out = {}
    for fname in ("game_extra.json", "game_dump.json"):
        p = DATA / fname
        if not p.exists():
            continue
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        for e in raw.get("entries", []):
            n = (e.get("n") or "").strip()
            if not n:
                continue
            prev = out.get(n)
            if prev is None:
                out[n] = e
            else:                       # 后者信息更全时覆盖
                for k, v in e.items():
                    if v not in (None, "", []):
                        prev[k] = v
    return out


def load_mt_cache():
    """机器翻译缓存（tools/translate_db.py 产出）：英文原文 -> 中文。"""
    p = DATA / "mt_cache.json"
    if not p.exists():
        return {}
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}
    out = {}
    for k, v in raw.items():
        if isinstance(v, dict) and v.get("zh"):
            out[k] = {"zh": v["zh"], "src": v.get("src", "mt"), "fixed": bool(v.get("fixed"))}
    return out


def unescape(text: str) -> str:
    for k, v in HTML_ENT.items():
        text = text.replace(k, v)
    return text


# --------------------------------------------------------------------------- #
# 2. 字段抽取
# --------------------------------------------------------------------------- #

DEFAULT_RE = re.compile(r"^Default:\s*([^<]*?)\s*(?:<br\s*/?>|$)", re.I)


def split_desc(desc: str):
    """拆出 Default: 前缀与真正描述文本。"""
    default = None
    d = desc.strip()
    m = DEFAULT_RE.match(d)
    while m:
        if default is None:
            default = m.group(1).strip()
        d = d[m.end():].strip()
        m = DEFAULT_RE.match(d)
    d = re.sub(r"^<br\s*/?>", "", d).strip()
    return default, d


TYPE_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*([-+]?[\d.]+)\s*$")


def guess_default(desc: str, release_value: str):
    default, _ = split_desc(desc)
    if default:
        return default
    if release_value and release_value != "cmd":
        return release_value
    return None


def infer_type(default, description, name="", release_kind=""):
    if release_kind.lower() == "cmd":
        return "command"
    d = (default or "").strip().strip('"')
    if (default is None or d == "") and not name.startswith(("+", "-")):
        return "command"
    low = d.lower()
    if low in ("true", "false"):
        return "bool"
    if re.fullmatch(r"[-+]?\d+", low):
        return "int"
    if re.fullmatch(r"[-+]?(\d+\.\d*|\.\d+)([eE][-+]?\d+)?", low):
        return "float"
    if re.fullmatch(r"[-+]?\d+(\.\d+)?", low):
        return "number"
    if name.startswith(("+", "-")):
        return "command"
    return "string"


# --------------------------------------------------------------------------- #
# 3. 分类（先人工表，后关键词规则）
# --------------------------------------------------------------------------- #

CATEGORY_TREE = [
    ("aim", "准星与瞄准", "🎯", [
        ("crosshair", "准星样式"), ("crosshair_dyn", "动态准星"), ("hit_feedback", "命中反馈"),
        ("aim_assist", "瞄准辅助/后坐力"), ("sniper", "狙击镜与开镜"), ("zoom", "视野缩放"),
    ]),
    ("view", "视角与镜头", "🎥", [
        ("fov", "视野 FOV"), ("viewmodel", "手部/武器模型"), ("camera", "第三人称与观战"),
        ("shake", "画面抖动"), ("spectate", "OB 观战"),
    ]),
    ("hud", "HUD 与界面", "🖥️", [
        ("hud_main", "HUD 主体"), ("radar", "雷达与小地图"), ("hud_team", "队友信息"),
        ("killfeed", "击杀信息"), ("scoreboard", "计分板"), ("menu", "菜单与提示"), ("hud_color", "HUD 颜色"),
    ]),
    ("input", "鼠标键盘与外设", "🖱️", [
        ("mouse_sens", "灵敏度与加速"), ("mouse_raw", "原始输入与轮询"), ("keybind", "按键绑定"),
        ("gamepad", "手柄"), ("scroll", "滚轮与跳投"), ("input_misc", "输入其它"),
    ]),
    ("video", "画面与画质", "🌄", [
        ("resolution", "分辨率与缩放"), ("quality", "画质与特效"), ("lighting", "光影与着色"),
        ("texture", "纹理与模型精度"), ("fog", "雾与阴影"), ("postprocess", "后期处理"),
        ("brightness", "亮度与对比"), ("vsync", "垂直同步与撕裂"),
    ]),
    ("perf", "性能与网络", "⚡", [
        ("fps", "帧率与上限"), ("net", "网络与延迟"), ("lag_comp", "延迟补偿"), ("perf_debug", "性能诊断"),
        ("loading", "加载与预载"), ("threads", "多线程"),
    ]),
    ("audio", "声音", "🔊", [
        ("volume", "音量"), ("audio_spatial", "空间音效与 HRTF"), ("audio_footstep", "脚步与枪声"),
        ("voice", "语音通话"), ("music", "音乐与解说"), ("audio_debug", "音频诊断"),
    ]),
    ("game", "玩法与对局设置", "🎮", [
        ("buy", "购买菜单"), ("grenade", "投掷物"), ("weapon", "武器行为"), ("movement", "移动与跳跃"),
        ("bhop", "连跳与加速"), ("team", "队伍与阵营"), ("warmup", "热身与回合计时"), ("round", "回合规则"),
        ("bot", "电脑玩家 Bot"), ("match", "比赛与匹配"),
    ]),
    ("practice", "练枪与自定义服", "🎯", [
        ("cheats", "作弊开关"), ("noclip", "穿墙与传送"), ("bot_practice", "Bot 练枪"),
        ("infinite", "无限弹药/血量"), ("spawn", "生成与重置"), ("utility_practice", "投掷物练习"),
        ("give", "给予武器与物品"),
    ]),
    ("demo", "录像与回放", "🎬", [
        ("record", "录制"), ("playback", "回放控制"), ("demo_ui", "回放界面"), ("demo_debug", "录像调试"),
    ]),
    ("comm", "通讯与社交", "💬", [
        ("chat", "聊天"), ("ping", "报点与标记"), ("clan", "战队与资料"),
    ]),
    ("account", "账号与平台", "🔐", [
        ("trust", "信任与匹配因子"), ("steam", "Steam 集成"), ("stats", "数据统计"),
    ]),
    ("server", "服务器与联机管理", "🛠️", [
        ("sv_basic", "服务器基础"), ("sv_cheat", "服务器作弊相关"), ("sv_mp", "服务器玩法规则"),
        ("password", "密码与访问"), ("admin", "管理与封禁"), ("rcon", "RCON 与日志"), ("sv_net", "服务器网络"),
    ]),
    ("debug", "调试与开发", "🧪", [
        ("dev", "开发者模式"), ("render_debug", "渲染调试"), ("ent_debug", "实体调试"),
        ("ai_debug", "AI 调试"), ("log_debug", "日志与统计"), ("misc_debug", "其它调试"),
    ]),
    ("engine", "引擎内部", "⚙️", [
        ("nav", "导航与 AI 寻路"), ("panorama", "Panorama UI 框架"), ("phys", "物理引擎"),
        ("cloth", "布料模拟"), ("animgraph", "动画图"), ("ik", "反向动力学 IK"),
        ("render_internal", "渲染内部"), ("sound_internal", "音频内部"), ("steam", "Steam 与平台服务"),
        ("net_internal", "网络内部"), ("engine_misc", "其它引擎变量"),
    ]),
    ("tool", "实用工具指令", "🧰", [
        ("echo", "输出与脚本"), ("alias", "别名与宏"), ("config", "配置文件"), ("exec", "执行与按键配置"),
        ("misc_tool", "其它工具"),
    ]),
]

CAT_NAME = {c[0]: c[1] for c in CATEGORY_TREE}
CAT_ICON = {c[0]: c[2] for c in CATEGORY_TREE}
SUBCAT_NAME = {sub[0]: sub[1] for c in CATEGORY_TREE for sub in c[3]}

# 关键词规则：顺序敏感，先匹配到的生效
KEYWORD_RULES = [
    # (正则, 类别, 子类)
    (r"^cl_crosshair", "aim", "crosshair"),
    (r"^cl_crosshairstyle|^cl_crosshair_dynamic|^cl_crosshairgap|^cl_crosshairsize|^cl_crosshairthickness|^cl_crosshairdot|^cl_crosshair_t\b|^cl_crosshaircolor", "aim", "crosshair_dyn"),
    (r"^cl_crosshair", "aim", "crosshair"),
    (r"^cl_crosshair_recoil|^cl_crosshair_recoil_|^cl_weapon_debug", "aim", "aim_assist"),
    (r"^cl_showhelp|^cl_autohelp", "hud", "menu"),
    (r"^cl_quickinventory|^cl_radial", "hud", "menu"),
]

# 显式分类映射（人工），key 为指令名
def load_hand_class():
    return dict(HAND_CLASS)


# --------------------------------------------------------------------------- #
# 4. 中文释义生成
# --------------------------------------------------------------------------- #

WORD_ZH = {k.lower(): v for k, v in GLOSSARY.items()}

# 预先编译为「一次性交替正则」，避免逐词 N 次 re.sub（性能关键）
_WORD_KEYS = sorted(WORD_ZH, key=len, reverse=True)
_WORD_RE = re.compile(
    r"(?<![A-Za-z])(" + "|".join(re.escape(k) for k in _WORD_KEYS) + r")(?![A-Za-z])",
    re.I)
_PHRASE_COMPILED = [(re.compile(p, re.I), r) for p, r in PHRASE_RULES]
_ZH_CACHE = {}


def _word_sub(m):
    return WORD_ZH[m.group(1).lower()]


def preprocess_en(text: str) -> str:
    t = unescape(text)
    t = t.replace("\u2019", "'").replace("\u2018", "'")
    t = t.replace("\u201c", '"').replace("\u201d", '"')
    t = re.sub(r"\s+", " ", t).strip()
    return t


def auto_zh(name: str, en: str, typ: str, scope: str):
    """规则化中文释义。返回 (zh, quality)。quality: 2=人工 1=规则生成 0=无"""
    if name in HAND_ZH:
        return HAND_ZH[name], 2
    if not en:
        return None, 0
    t = preprocess_en(en)
    cache_key = t
    if cache_key in _ZH_CACHE:
        return _ZH_CACHE[cache_key]
    result = _auto_zh_core(t)
    _ZH_CACHE[cache_key] = result
    return result


def _auto_zh_core(t: str):
    # 去掉用法前缀 "name <args> - "，用法单独留作参数说明
    usage = None
    m = re.match(r"^\S+(?:\s+(\<[^>]*\>(?:\s+\<[^>]*\>)*|\"[^\"]*\"(?:\s+\"[^\"]*\")*))+\s*-\s*(.+)$", t)
    if m:
        usage = m.group(1)
        t = m.group(2).strip()

    # 短语规则（整体替换）
    for rx, repl in _PHRASE_COMPILED:
        t = rx.sub(repl, t)

    # 词表替换（单次交替正则）
    hits = [0]
    words = re.findall(r"[A-Za-z]{2,}", t)

    def _sub(mm):
        hits[0] += 1
        return WORD_ZH[mm.group(1).lower()]

    t = _WORD_RE.sub(_sub, t)

    zh = t
    if not re.search(r"[\u4e00-\u9fff]", zh):
        return None, 0
    zh = re.sub(r"\s+", " ", zh).strip(" ,.;")
    if usage:
        usage_txt = re.sub(r"\s+", " ", usage)
        zh = f"{zh}（参数：{usage_txt}）"
    # 覆盖率：命中词数 / 英文词数。过低说明只是零星替换，属于「机翻碎片」，不作为正式释义
    ratio = hits[0] / max(1, len(words))
    return zh, (1 if ratio >= 0.35 else 0)


def _is_weak_zh(zh: str, strict: bool = False) -> bool:
    """判断一条中文释义是不是"没有信息量 / 不合格"。

    典型垃圾：
      · "默认值：false"（早期把上游的 Default: false<br> 机翻过来的）
      · 只有英文/数字，没有汉字
      · 去掉标点后短于 3 个字
    strict=True 时（用于校验"从名字推断"的结果）：只要还残留英文单词就判不合格，
    因为读者不该在中文释义里看到 "半径多重plier" 这种半成品。
    """
    if not zh:
        return True
    s = zh.strip()
    if re.fullmatch(r"默认值[:：].*", s):
        return True
    if not re.search(r"[\u4e00-\u9fff]", s):
        return True
    if strict and re.search(r"[A-Za-z]{2,}", s):
        return True
    hanzi = len(re.findall(r"[\u4e00-\u9fff]", s))
    return hanzi < 3


def _infer_from_name(name: str, typ: str, default):
    """纯名字推断：成功返回 (中文, 置信度)，推不出返回 (None, 0)。"""
    try:
        import name_zh
        zh, conf = name_zh.describe_name(name, typ, default)
        if zh and conf >= 1 and not _is_weak_zh(zh, strict=True):
            return zh, 1
    except Exception:
        pass
    return None, 0


def _name_hint(name: str) -> str:
    try:
        import name_zh
        return name_zh.breakdown(name) or ""
    except Exception:
        return ""


def _fallback_zh(name: str, is_cmd: bool) -> str:
    """实在推不出来时的诚实兜底：明说没有说明，并告诉用户怎么自查。"""
    if is_cmd:
        return f"控制台命令；官方与上游均未提供说明，用 `help {name}` 查看参数用法。"
    return (f"官方与上游均未提供说明；变量名 `{name}` 已表明用途，"
            f"游戏内可用 `help {name}` 自查。")


def scope_infer(name: str, scope: str, flags: str):
    """flags 缺失时按命名约定推断作用域。"""
    if scope != "unknown":
        return scope
    low = name.lower()
    if low.startswith("sv_") or low.startswith("mp_") or low.startswith("host_") \
            or low.startswith("rcon") or low.startswith("log") or low.startswith("ban"):
        return "server"
    if low.startswith("cl_") or low.startswith("mat_") or low.startswith("r_") \
            or low.startswith("snd_") or low.startswith("voice_") or low.startswith("m_") \
            or low.startswith("fps_") or low.startswith("hud_") or low.startswith("viewmodel") \
            or low.startswith("crosshair") or low.startswith("bind") or low == "sensitivity":
        return "client"
    if low.startswith("tv_"):
        return "both"
    if low.startswith("spec_"):
        return "client"
    return scope


# --------------------------------------------------------------------------- #
# 5. 风险/权限判定
# --------------------------------------------------------------------------- #


def scope_of(flags: str):
    f = set(x.strip().lower() for x in flags.split(",") if x.strip())
    cl, sv = "cl" in f, "sv" in f
    if cl and sv:
        return "both"
    if cl:
        return "client"
    if sv:
        return "server"
    return "unknown"


DANGER_PATTERNS = [
    (r"^sv_cheats", "high", "开启后仅限私人/机器人服务器；竞技服会拒绝该指令，误用可能触发 VAC 保护机制。"),
    (r"^sv_lan|^sv_password|^rcon", "medium", "涉及服务器访问控制，公开服请勿随意修改。"),
    (r"^(debug|test|dev|_?dump|ent_|ai_debug|host_)", "low", "开发调试用，正式对局中通常无效。"),
    (r"cheat$|, cheat", "high", "作弊类变量，仅在 sv_cheats 1 的私人服务器/本地生效。"),
]


def danger_of(name: str, flags: str):
    for pat, level, note in DANGER_PATTERNS:
        if re.search(pat, name, re.I) or (pat.startswith("cheat") and re.search(pat, flags, re.I)):
            return level, note
    return None, None


# --------------------------------------------------------------------------- #
# 6. 主流程
# --------------------------------------------------------------------------- #

# 控制台命令（concommand，cvarlist 里值列是 "cmd"）的显式分类。
# 命令和 cvar 的语义完全不同，混用前缀规则会把 getpos/god/give 全塞进"引擎内部"。
CMD_CLASS = {
    # —— 练枪 / 作弊（单机调试最常用）——
    "god": ("practice", "cheats"), "noclip": ("practice", "noclip"), "buddha": ("practice", "cheats"),
    "kill": ("practice", "cheats"), "explode": ("practice", "cheats"),
    "hurtme": ("practice", "cheats"), "healme": ("practice", "cheats"),
    "hurtthem": ("practice", "cheats"), "respawn_player": ("practice", "cheats"),
    "give": ("practice", "give"), "give_oriented": ("practice", "give"),
    "givecurrentammo": ("practice", "give"), "remove_weapon": ("practice", "give"),
    "sv_infinite_ammo": ("practice", "infinite"), "sv_cheats": ("practice", "cheats"),
    "impulse": ("practice", "cheats"), "notarget": ("practice", "cheats"),
    "setpos": ("practice", "utility_practice"), "setpos_exact": ("practice", "utility_practice"),
    "setpos_player": ("practice", "utility_practice"), "setang": ("practice", "utility_practice"),
    "setang_exact": ("practice", "utility_practice"), "getpos": ("practice", "utility_practice"),
    "getpos_exact": ("practice", "utility_practice"), "getposcopy": ("practice", "utility_practice"),
    "getposcopy_exact": ("practice", "utility_practice"), "spec_pos": ("practice", "utility_practice"),
    "noclip_fixup": ("practice", "noclip"), "thirdperson": ("view", "camera"),
    "firstperson": ("view", "camera"), "thirdperson_mayamode": ("view", "camera"),
    "cam_command": ("view", "camera"), "camortho": ("view", "camera"),
    "map": ("tool", "config"), "map_workshop": ("tool", "config"),
    "changelevel": ("tool", "config"), "restart": ("tool", "config"),
    "reloadgame": ("tool", "config"), "exec": ("tool", "exec"), "exec_async": ("tool", "exec"),
    "execifexists": ("tool", "exec"), "host_writeconfig": ("tool", "config"),
    "host_writeconfig_with_prompt": ("tool", "config"), "writekeybindings": ("tool", "config"),
    "quit": ("tool", "misc_tool"), "exit": ("tool", "misc_tool"),
    "disconnect": ("server", "sv_basic"), "connect": ("server", "sv_basic"),
    "connect_hltv": ("server", "sv_basic"), "pause": ("server", "sv_basic"),
    "unpause": ("server", "sv_basic"), "setpause": ("server", "sv_basic"),
    "kick": ("server", "admin"), "kickid": ("server", "admin"), "kickid_hltv": ("server", "admin"),
    "banid": ("server", "admin"), "rcon": ("server", "rcon"), "status": ("server", "sv_basic"),
    "status_json": ("server", "sv_basic"), "sv_shutdown": ("server", "admin"),
    "callvote": ("server", "admin"), "listissues": ("server", "admin"),
    "bind": ("input", "keybind"), "unbind": ("input", "keybind"), "unbindall": ("input", "keybind"),
    "binddefaults": ("input", "keybind"), "bindss": ("input", "keybind"),
    "key_findbinding": ("input", "keybind"), "key_listboundkeys": ("input", "keybind"),
    "button_info": ("input", "keybind"), "slot0": ("input", "keybind"),
    "autobuy": ("game", "buy"), "rebuy": ("game", "buy"), "buyrandom": ("game", "buy"),
    "buymenu": ("game", "buy"), "sellbackall": ("game", "buy"),
    "bot_add": ("game", "bot"), "bot_add_t": ("game", "bot"), "bot_add_ct": ("game", "bot"),
    "bot_kick": ("game", "bot"), "bot_kill": ("game", "bot"), "bot_place": ("game", "bot"),
    "bot_stop": ("game", "bot"), "bot_goto_mark": ("game", "bot"),
    "bot_goto_selected": ("game", "bot"), "bot_path": ("game", "bot"),
    "bot_knives_only": ("game", "bot"), "bot_pistols_only": ("game", "bot"),
    "bot_snipers_only": ("game", "bot"), "bot_all_weapons": ("game", "bot"),
    "say": ("comm", "chat"), "say_team": ("comm", "chat"), "player_ping": ("comm", "ping"),
    "radio": ("comm", "ping"), "radio1": ("comm", "ping"), "radio2": ("comm", "ping"),
    "radio3": ("comm", "ping"), "teammenu": ("game", "team"),
    "demo_goto": ("demo", "playback"), "demo_gototick": ("demo", "playback"),
    "demo_pause": ("demo", "playback"), "demo_resume": ("demo", "playback"),
    "demo_togglepause": ("demo", "playback"), "demo_timescale": ("demo", "playback"),
    "demo_info": ("demo", "playback"), "demo_step_tick": ("demo", "playback"),
    "demoui": ("demo", "demo_ui"), "demolist": ("demo", "playback"),
    "listdemo": ("demo", "playback"), "playdemo": ("demo", "playback"),
    "record": ("demo", "record"), "stop": ("demo", "record"),
    "play": ("audio", "audio_debug"), "soundinfo": ("audio", "audio_debug"),
    "stopsound": ("audio", "audio_debug"), "stopsoundscape": ("audio", "audio_debug"),
    "exec_dump": ("tool", "config"),
    "cvarlist": ("debug", "misc_debug"), "find": ("debug", "misc_debug"),
    "findflags": ("debug", "misc_debug"), "help": ("debug", "misc_debug"),
    "differences": ("debug", "misc_debug"), "print_changed_convars": ("debug", "misc_debug"),
    "toggle": ("tool", "misc_tool"), "toggleconsole": ("tool", "misc_tool"),
    "showconsole": ("tool", "misc_tool"), "hideconsole": ("tool", "misc_tool"),
    "clear": ("tool", "misc_tool"), "clearall": ("tool", "misc_tool"),
    "echo": ("tool", "echo"), "echoln": ("tool", "echo"), "alias": ("tool", "alias"),
    "grep": ("tool", "misc_tool"), "condump": ("tool", "misc_tool"),
    "consoletool": ("tool", "misc_tool"), "sys_info": ("tool", "misc_tool"),
    "repeat_last_console_command": ("tool", "misc_tool"), "cyclevar": ("tool", "misc_tool"),
    "incrementvar": ("tool", "misc_tool"), "multvar": ("tool", "misc_tool"),
    "net_channels": ("perf", "net"), "net_status": ("perf", "net"),
    "net_connections_stats": ("perf", "net"), "net_fakelag": ("perf", "net"),
    "net_fakeloss": ("perf", "net"), "net_fakejitter": ("perf", "net"),
    "net_fakeclear": ("perf", "net"), "net_fakestatus": ("perf", "net"),
    "net_option": ("perf", "net"), "net_showudp": ("perf", "net"),
    "timedemo": ("perf", "perf_debug"), "timedemoquit": ("perf", "perf_debug"),
    "rcon_password": ("server", "rcon"), "log": ("debug", "log_debug"),
    "showents": ("debug", "ent_debug"), "cl_showents": ("debug", "ent_debug"),
    "prop_debug": ("debug", "ent_debug"), "dlight_debug": ("debug", "render_debug"),
    "pixelvis_debug": ("debug", "render_debug"), "mat_wireframe": ("video", "quality"),
    "ent_create": ("debug", "ent_debug"), "ent_text": ("debug", "ent_debug"),
    "ent_fire": ("debug", "ent_debug"), "ent_remove": ("debug", "ent_debug"),
    "ent_kill": ("debug", "ent_debug"), "ent_hitbox": ("debug", "ent_debug"),
    "teleport": ("practice", "utility_practice"), "sv_rethrow_last_grenade": ("practice", "grenade"),
    "sv_smoke_lighting_changed": ("debug", "misc_debug"),
}

# 命令名族兜底（前缀 → 分类），顺序敏感
CMD_PREFIX_CLASS = [
    ("cl_ent_|ent_|cl_ent", "debug", "ent_debug"),
    ("cl_script_|script_", "debug", "dev"),
    ("cl_debugoverlay_|debugoverlay_", "debug", "misc_debug"),
    ("nav_", "engine", "nav"),
    ("phys_", "engine", "phys"),
    ("snd_sos_|snd_beatpattern_|snd_steamaudio_", "audio", "audio_debug"),
    ("snd_samplers_|snd_cast", "audio", "audio_debug"),
    ("mp_backup_|mp_warmup_|mp_pause_|mp_unpause_|mp_swapteams|mp_scrambleteams|mp_modify_timeouts",
     "server", "admin"),
    ("mp_", "game", "round"),
    ("tv_", "demo", "playback"),
    ("sv_", "server", "sv_basic"),
    ("cl_", "hud", "hud_main"),
    ("r_|sc_|lb_|mat_|csm_", "debug", "render_debug"),
    ("fog_", "debug", "render_debug"),
    ("host_", "perf", "perf_debug"),
    ("itemtest_|particle_test_|cast_|test_|debug_", "debug", "misc_debug"),
    ("annotation_|camera_path_|camera_", "tool", "misc_tool"),
    ("ragdoll_|shatterglass_|retake_", "debug", "misc_debug"),
    ("bot_", "game", "bot"),
    ("navspace_", "engine", "nav"),
]

# 显式排除清单：只在"进程内存抓取"里出现过、但用户那份完整 cvarlist 文本导出里
# 没有对应记录，无法证实当前版本仍存在。用户核对后确认移除，这里硬编码挡住，
# 避免以后重建时又被内存抓取的宽松匹配带回来。
EXCLUDED_NAMES = {
    "ents",                      # 疑似旧版实体列表命令
    "path",                      # 疑似旧版路径显示命令
    "refresh_ui_audio_state",    # 未在官方 cvarlist 导出中出现
}


def classify_cmd(name: str):
    """给 concommand 分类（cvarlist 值列为 cmd 的那些）。"""
    if name in CMD_CLASS:
        return CMD_CLASS[name]
    low = name.lower()
    if re.fullmatch(r"slot\d{1,2}", low):
        return ("input", "keybind")
    if re.fullmatch(r"\+.*", low) or re.fullmatch(r"-.*", low):
        return ("input", "keybind")
    for pat, cat, sub in CMD_PREFIX_CLASS:
        if re.match(pat, low):
            return (cat, sub)
    return ("debug", "misc_debug")


def classify(name: str, flags: str, desc: str, is_cmd: bool = False):
    if is_cmd:
        return classify_cmd(name)
    if name in HAND_CLASS:
        c = HAND_CLASS[name]
        return c[0], c[1]
    low = name.lower()
    # 规则表
    for pat, cat, sub in KEYWORD_RULES:
        if re.search(pat, low):
            return cat, sub
    # 前缀族判定（顺序敏感：越具体的规则越靠前）
    prefix_map = [
        # --- 玩家最常查的族 ---
        ("cl_crosshair", "aim", "crosshair"),
        ("cl_crosshair_recoil", "aim", "aim_assist"),
        ("spec_|cl_show_observer_crosshair|tv_", "view", "spectate"),
        ("viewmodel", "view", "viewmodel"),
        ("crosshair", "aim", "crosshair"),
        ("cl_weapon_debug", "aim", "aim_assist"),
        ("sensitivity|m_yaw|m_pitch|m_customaccel|m_rawinput|m_mouseaccel|zoom_sensitivity",
         "input", "mouse_sens"),
        ("bind|unbind|key_", "input", "keybind"),
        ("joystick|joy_|gamepad|in_", "input", "gamepad"),
        ("cl_scrollwheel", "input", "scroll"),
        ("cl_buymenu|cl_buywheel|buymenu", "game", "buy"),
        ("cl_radar|radar_", "hud", "radar"),
        ("cl_teamid|cl_teammate|cl_teamcounter|cl_hud_playercount|hud_playercount", "hud", "hud_team"),
        ("cl_killfeed|cl_deathnotice|cl_hud_deathnotice|cl_draw_only_deathnotices",
         "hud", "killfeed"),
        ("cl_chat|chat_|cl_avatar|cl_playerspray|cl_join_advertise|cl_invites|cl_language",
         "comm", "clan"),
        ("voice_|cl_voice|sv_voice|sv_alltalk|sv_deadtalk|sv_talk_enemy", "audio", "voice"),
        ("cl_dangerzone_.*sound|cl_deathcam_audio|cl_borrow_music|cl_music", "audio", "audio_debug"),
        ("cl_hud|hud_", "hud", "hud_main"),
        ("cl_showfps|cl_showpos|cl_showloadout|cl_showhelp|cl_autohelp|net_graph", "hud", "hud_main"),
        ("cl_interp|cl_predict|cl_lagcompensation|cl_updaterate|cl_cmdrate|cl_clock|cl_connection",
         "perf", "net"),
        ("cl_demo|demo|cl_obs_interp", "demo", "playback"),
        ("cl_", "hud", "hud_main"),

        # --- 画面 ---
        ("mat_", "video", "quality"),
        ("r_", "video", "quality"),
        ("lb_|csm_|cascade|shadow", "video", "lighting"),
        ("fog_|fog", "video", "fog"),
        ("cloth_|ragdoll", "video", "texture"),
        ("panorama", "engine", "panorama"),
        ("particle", "video", "postprocess"),

        # --- 性能 / 网络 ---
        ("fps_max|fps_", "perf", "fps"),
        ("net_|rate|sv_maxrate|sv_maxupdaterate|sv_minrate|sv_minupdaterate|sv_client_",
         "perf", "net"),
        ("budget|perf_|stat_", "perf", "perf_debug"),
        ("thread|async|job_", "perf", "threads"),

        # --- 音频 ---
        ("snd_|sound|audio_|volume", "audio", "volume"),

        # --- 玩法 ---
        ("mp_", "game", "round"),
        ("cash_team|mp_", "game", "round"),
        ("csgo_video_settings|videocfg_", "tool", "config"),
        ("bot_", "game", "bot"),
        ("ammo_|item_|weapon_", "game", "weapon"),
        ("sv_infinite|sv_grenade|sv_showimpacts|sv_showbullethits|host_timescale",
         "practice", "utility_practice"),
        ("sv_", "server", "sv_basic"),

        # --- 引擎内部 ---
        ("nav", "engine", "nav"),
        ("phys", "engine", "phys"),
        ("cloth", "engine", "cloth"),
        ("animgraph|ik_|npcsolve|anim_", "engine", "animgraph"),
        ("mm_|matchmaking|gc_|steam", "engine", "steam"),
        ("s_|snd_", "engine", "sound_internal"),
        ("func_|ent_|entity_|phys_", "debug", "ent_debug"),
        ("ai_", "debug", "ai_debug"),
        ("dev_|developer", "debug", "dev"),
        ("host_|engine_|sys_|sv_", "engine", "engine_misc"),
        ("cc_|convars|config", "engine", "engine_misc"),
    ]
    for pat, cat, sub in prefix_map:
        if re.match(pat, low):
            return cat, sub
    # 兜底：按描述关键词
    d = desc.lower()
    guess = [
        (("crosshair",), "aim", "crosshair"),
        (("hud", "interface"), "hud", "hud_main"),
        (("radar",), "hud", "radar"),
        (("sound", "audio"), "audio", "audio_debug"),
        (("render", "shader", "material"), "video", "quality"),
        (("network", "latency", "packet"), "perf", "net"),
        (("bot",), "game", "bot"),
        (("demo",), "demo", "playback"),
        (("debug", "dump", "log"), "debug", "misc_debug"),
    ]
    for keys, cat, sub in guess:
        if any(k in d for k in keys):
            return cat, sub
    return "engine", "misc_engine"


def looks_bad_zh(zh: str) -> bool:
    """判定「中文翻译不良好」：只要还残留英文单词就算不合格。

    注意英文专有名词（HLTV、SourceTV、SDR 等）在机器翻译里也是英文词，
    但那些是约定俗成的写法，所以这里只用于「是否要用机翻覆盖规则翻译」的判断：
    规则翻译只要还留着任何英文词，就直接让位给整句机翻。
    """
    if not zh:
        return False
    return bool(re.search(r"[A-Za-z]{2,}", zh))


def main():
    global MT_CACHE
    MT_CACHE = load_mt_cache()
    print(f"[i] 机器翻译缓存：{len(MT_CACHE)} 条")

    game_extra = load_game_extra()
    arm = parse_armync(RAW / "armync_cvarlist.md")
    rel = parse_release(RAW / "ohlasfar_release.txt")

    # 先按排除清单清一遍（游戏额外条目 + 上游两条来源）
    if EXCLUDED_NAMES:
        before = len(game_extra)
        for n in EXCLUDED_NAMES:
            game_extra.pop(n, None)
        arm = [r for r in arm if r["name"] not in EXCLUDED_NAMES]
        for n in EXCLUDED_NAMES:
            rel.pop(n, None)
        print(f"[i] 排除清单剔除 {len(EXCLUDED_NAMES)} 条"
              f"（游戏额外条目 {before} → {len(game_extra)}）：{sorted(EXCLUDED_NAMES)}")

    # 游戏侧"确认存在"的名字全集 = cvarlist 导出 ∪ 进程内存抓取。
    # 不在这个集合里的条目只出现在上游 wiki 里，可能已随版本移除，UI 需要区分展示。
    verified = set()
    for fname in ("game_extra.json", "game_dump.json"):
        p = DATA / fname
        if p.exists():
            try:
                for e in json.loads(p.read_text(encoding="utf-8")).get("entries", []):
                    if e.get("n"):
                        verified.add(e["n"])
            except Exception:
                pass
    mem = ROOT / "_dumps" / "cs2_cvarlist_mem.txt"
    if mem.exists():
        for raw in mem.read_text(encoding="utf-8", errors="replace").splitlines():
            m = re.match(r"^([\x21-\x7e]{2,80}?)\s*:", raw)
            if m:
                verified.add(m.group(1).strip())
    verified -= EXCLUDED_NAMES
    print(f"[i] 游戏内已确认存在的名字：{len(verified)} 条")

    # 游戏自身 cvarlist 导出的官方说明（权威）：同名条目以此覆盖上游 wiki 文案
    game_desc = {}
    game_flags = {}
    game_default = {}
    game_kind = {}
    for name, e in game_extra.items():
        if e.get("src") != "game-dump":
            continue
        en = (e.get("en") or "").strip()
        if en:
            game_desc[name] = en
        if e.get("f"):
            game_flags[name] = e["f"]
        if e.get("d") not in (None, ""):
            game_default[name] = e["d"]
        if e.get("k"):
            game_kind[name] = e["k"]
    print(f"[i] 游戏权威说明（cvarlist 导出）：{len(game_desc)} 条，"
          f"权限标记 {len(game_flags)} 条，cmd {sum(1 for v in game_kind.values() if v == 'cmd')} 条")

    known = {row["name"] for row in arm}          # 注意：不能预先并入 rel，否则 release 补充条会被跳过
    base_count = len(arm)
    extra = 0
    # 合并上游 release 清单里 ArmynC 全量列表尚未收录的新指令（自动更新靠这里发现新内容）
    for name, r in rel.items():
        if name in known:
            continue
        arm.append({"name": name, "flags": r["flags"], "desc": r["desc"],
                    "extra_default": None if r["value"] == "cmd" else r["value"]})
        known.add(name)
        extra += 1
    print(f"[i] 全量列表 {base_count} 条 + release 清单新增 {extra} 条 = {len(arm)} 条")

    # 并入游戏文件里发现、上游两个源都没收录的 cvar
    game_added = 0
    for name, e in game_extra.items():
        if name in known:
            continue
        arm.append({"name": name, "flags": e.get("f", ""), "desc": e.get("en", ""),
                    "game": True, "game_zh": e.get("zh", ""), "extra_default": e.get("d")})
        known.add(name)
        game_added += 1
    if game_added:
        print(f"[i] 并入游戏文件发现的额外 cvar {game_added} 条 → 合计 {len(arm)} 条")

    entries = []
    prev_zh = {}          # 规则翻译阶段的产物（对照报告里的「修复前」）
    for idx, row in enumerate(arm):
        name, flags, raw_desc = row["name"], row["flags"], row["desc"]
        # 游戏自身 cvarlist 导出的权限标记 / 默认值优先于上游 wiki
        if game_flags.get(name):
            flags = game_flags[name]
        fl = [x.strip().lower() for x in flags.split(",") if x.strip()]
        r = rel.get(name)
        rel_desc = r["desc"] if r else ""
        # 优先用 release 列表的描述（更完整），其描述缺失时用 armync
        best_desc = rel_desc or raw_desc
        default, clean = split_desc(best_desc)
        if not default:
            default, _ = split_desc(raw_desc)
        if not default and row.get("extra_default") not in (None, ""):
            default = row["extra_default"]
        if not default and r and r["value"] and r["value"] != "cmd":
            default = r["value"]
        # 游戏导出的默认值最权威（注意游戏里当前值是玩家自己改的，不能当默认值）
        if game_default.get(name) not in (None, ""):
            default = game_default[name]
        # 游戏官方说明覆盖上游文案；但游戏没给说明时**必须保留上游已有的英文**，
        # 否则会把上游 wiki 的释义一起清空（曾导致 2000+ 条英文丢失）。
        gd_en = (game_desc.get(name) or "").strip()
        if gd_en:
            best_desc = gd_en
            clean = gd_en
        else:
            clean = split_desc(best_desc)[1] if best_desc else ""
        typ = infer_type(default, clean, name, (r["value"] if r and r["value"] == "cmd" else ""))
        is_cmd = (game_kind.get(name) == "cmd") or (r and r.get("value") == "cmd")
        scope = scope_of(flags if flags else (r["flags"] if r else ""))
        scope = scope_infer(name, scope, flags if flags else (r["flags"] if r else ""))
        cat, sub = classify(name, flags, clean, is_cmd=is_cmd)
        zh, quality = auto_zh(name, best_desc, typ, scope)
        danger, danger_note = danger_of(name, flags)
        key = 1 if ("release" in fl or quality == 2 or name in HAND_CLASS) else 0

        # 机器翻译优先补位：人工精校不动，其余若机翻存在且规则翻译不合格/仍是英文则采用机翻
        z_rule = zh                      # 先留档规则翻译结果（= 修复前展示给用户的内容）
        name_hint = ""                   # 名字语义拆解（仅"没有可靠释义"时给出，供参考）
        gzh = row.get("game_zh")
        if gzh:
            zh, quality = gzh, 2          # 游戏文件条目：说明是按变量名推断生成并核对过的
        mtrec = MT_CACHE.get(clean.strip().lower()) if clean else None
        mt = mtrec["zh"] if mtrec else None
        mt_src = mtrec.get("src", "mt") if mtrec else ""
        if quality < 2 and mt:
            # 规则翻译已足够好（无英文残留）时保留规则结果，避免机翻把专有名词译乱
            keep_rule = quality == 1 and not looks_bad_zh(zh)
            if not keep_rule:
                zh, quality = mt, 3
        prev_zh[name] = z_rule

        # 无官方描述的条目给一条可读的中文兜底说明（绝不用英文原文冒充中文）
        if not zh:
            if name.startswith("+") or name.startswith("-"):
                zh = ("按键/开关类指令（按住生效），通常配合 bind 使用；"
                      if name.startswith("+") else "按键/开关类指令（松开生效），通常配合 bind 使用；")
            else:
                nz, nq = _infer_from_name(name, typ, default)
                if nz:
                    zh, quality = nz, nq
                else:
                    zh = _fallback_zh(name, is_cmd)
                    name_hint = _name_hint(name)

        # 释义没有信息量时（典型："默认值：false"），改用「从指令名推断语义」。
        # 很多 cvar 官方就是没写说明，但名字本身已经把用途说清楚了。
        if _is_weak_zh(zh):
            nz, nq = _infer_from_name(name, typ, default)
            if nz:
                zh, quality = nz, nq
            else:
                zh = _fallback_zh(name, is_cmd)
                name_hint = _name_hint(name)

        # ---- 游戏自身 cvarlist 导出：官方英文已就位，但中文还没机翻就标记待补 ----
        if game_desc.get(name) and not MT_CACHE.get(game_desc[name].strip().lower()):
            quality = 1
            mt_src = ""
            key = 1 if ("release" in fl or name in HAND_CLASS) else key
        elif game_desc.get(name):
            quality = max(quality, 3)

        entries.append({
            "n": name,
            "z": _dedupe(zh or ""),
            "en": clean,
            "t": typ,
            "d": default if default not in (None, "") else None,
            "s": scope,
            "c": cat,
            "u": sub if sub in SUBCAT_NAME else "engine_misc",
            "r": 1 if "release" in fl else 0,
            "k": key,
            "st": "new" if idx >= base_count else "",
            "q": quality,
            "ms": mt_src if quality == 3 else "",
            "x": danger or "",
            "xn": danger_note or "",
            "f": flags,
            "gv": 1 if name in verified else 0,     # 1=游戏内确认存在，0=仅上游 wiki 收录
            "nh": name_hint or "",                 # 名字语义拆解（没有可靠释义时的参考）
        })

    # 排序：release 优先 → 类别 → 名称
    order = {c[0]: i for i, c in enumerate(CATEGORY_TREE)}
    entries.sort(key=lambda e: (
        0 if e["q"] == 2 else 1,                       # 人工精校释义的优先
        0 if e["k"] else 1,                            # 再是实用指令
        0 if e["r"] else 1,                            # 再是正式版下发
        order.get(e["c"], 99), e["n"].lower()))

    db = {
        "version": datetime.now(timezone.utc).strftime("%Y.%m.%d"),
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": {
            "game_export": "CS2 游戏自身控制台 `cvarlist` 的完整导出（VConsole2 会话日志，"
                           "2802 条 convars/concommands）——**权威来源**：权限标记、官方英文说明、"
                           "是否命令（cmd）均以它为准，共 2805 条已入库",
            "cvar_list": "ArmynC/ArminC-CS2-Cvars（cvars/cvarlist.md，main 分支 raw）——补全游戏未打印的字段",
            "release_flags": "OhLasFar/CS2-ALL-Console-Commands-Repository（release 全量清单）",
            "glossary_ref": "eLecCap1taL/CS2-CFG-Wiki（中文术语参考）",
            "machine_translation": "DeepSeek（主力，整句翻译）＋ MyMemory 在线引擎 ＋ Argos 离线模型，"
                                   "再经 CS2 术语规范化和 LLM 复审",
            "blocked_source": "developer.valvesoftware.com 官方 Wiki 有 Anubis 反爬，未能抓取",
        },
        "count": len(entries),
        "tracked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "new_count": sum(1 for e in entries if e.get("st") == "new"),
        "game_verified": sum(1 for e in entries if e.get("gv")),
        "wiki_only": sum(1 for e in entries if not e.get("gv")),
        "cmd_count": sum(1 for e in entries
                         if game_kind.get(e["n"]) == "cmd"),
        "categories": [
            {"id": c[0], "name": c[1], "icon": c[2],
             "subs": [{"id": s[0], "name": s[1]} for s in c[3]]}
            for c in CATEGORY_TREE
        ],
        "entries": entries,
    }
    (DATA / "commands.json").write_text(
        json.dumps(db, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    # 记下「规则翻译阶段」的结果，供对照报告当作「修复前」使用
    (DATA / "zh_prev.json").write_text(
        json.dumps(prev_zh, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    # 本次采用了机器翻译的条目（服务端 /api/data 直接按名字套用，避免前端再跑一遍规则引擎）
    mt_applied = {e["n"]: e["z"] for e in entries if e.get("q") == 3}
    (DATA / "zh_mt.json").write_text(
        json.dumps(mt_applied, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    # 生成离线版数据（供直接双击 index.html 时使用）
    assets = ROOT / "assets"
    assets.mkdir(exist_ok=True)
    (assets / "db.js").write_text(
        "/* 自动生成，请勿手改；由 tools/build_db.py 产出 */\n"
        "window.__CS2_DB__ = " + json.dumps(db, ensure_ascii=False, separators=(",", ":")) + ";\n",
        encoding="utf-8")

    # 统计报告
    from collections import Counter
    cat_count = Counter(e["c"] for e in entries)
    q_count = Counter(e["q"] for e in entries)
    release_entries = [e for e in entries if e["r"]]
    report = {
        "total": len(entries),
        "release": len(release_entries),
        "key": sum(1 for e in entries if e["k"]),
        "with_zh": sum(1 for e in entries if e["z"]),
        "hand_zh": q_count[2],
        "auto_zh": q_count[1],
        "no_zh": q_count[0],
        "release_with_zh": sum(1 for e in release_entries if e["z"]),
        "game_verified": sum(1 for e in entries if e.get("gv")),
        "wiki_only": sum(1 for e in entries if not e.get("gv")),
        "by_category": cat_count.most_common(),
        "by_scope": Counter(e["s"] for e in entries).most_common(),
    }
    (DATA / "db_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()


# --- 发布前脱敏：剔除会随数据外泄的本机信息 ---
# cvarlist 导出会把本机用户名写进某些指令的默认值（玩家名 / 服务器名），
# 这些字段会进入 data/commands.json 与 assets/db.js，进而随源码包与安装包发布。
# 这里统一清空：这两条本来就没有有意义的内置默认值（null，由用户或 Steam 决定）。
LOCAL_PII_PATTERNS = [
    re.compile(r"^[A-Za-z0-9_.\-]{3,32}$"),   # 形如玩家名的短标识
]


def sanitize_local_pii(db: dict) -> int:
    """清空可能带出本机信息的「默认值」字段。返回处理条数。"""
    # 这两条在游戏里的内置默认值是 null，出现字符串必然是导出时带上的本机值
    NO_INTRINSIC_DEFAULT = {"name", "hostname"}
    n = 0
    for e in db.get("entries", []):
        if e.get("n") in NO_INTRINSIC_DEFAULT and str(e.get("d") or "").strip():
            e["d"] = ""
            n += 1
    return n
