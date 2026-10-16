# -*- coding: utf-8 -*-
"""从指令名推断中文释义。

很多 cvar 官方没给说明，但**名字本身就是语义**：
    mp_plant_c4_anywhere        → 是否允许在任意位置安放 C4 炸弹
    sv_infinite_ammo            → 是否无限弹药
    cl_disable_round_end_report → 是否禁用回合结束报告

做法：把名字拆成「前缀框架 + 修饰词 + 对象词」，逐块翻译后拼句，
而不是输出 "默认值：false" 这种没信息量的兜底。

    from name_zh import describe_name
    zh, conf = describe_name("mp_plant_c4_anywhere", "bool", "false")
"""
import re

# --------------------------------------------------------------------------- #
# 1. 前缀 → 中文框架（最长前缀优先）
# --------------------------------------------------------------------------- #
PREFIX_FAMILY = {
    "mp_": "对战规则", "sv_": "服务器设置", "cl_": "客户端设置",
    "r_": "渲染设置", "mat_": "材质设置", "snd_": "声音设置",
    "voice_": "语音设置", "hud_": "HUD 设置", "cl_hud_": "HUD 设置",
    "cl_crosshair": "准星设置", "viewmodel_": "视角模型设置", "fps_": "帧率设置",
    "net_": "网络设置", "mm_": "匹配设置", "tv_": "SourceTV 设置",
    "spec_": "观战设置", "demo_": "录像设置", "bot_": "机器人设置",
    "nav_": "导航网格设置", "phys_": "物理设置", "cloth_": "布料模拟设置",
    "animgraph_": "动画图设置", "panorama_": "UI 框架设置", "sc_": "场景渲染设置",
    "lb_": "光照烘焙设置", "csm_": "级联阴影设置", "inferno_": "燃烧瓶设置",
    "weapon_": "武器设置", "ammo_": "弹药设置", "cash_": "经济设置",
    "host_": "主机设置", "engine_": "引擎设置", "fs_": "文件系统设置",
    "con_": "控制台设置", "input_": "输入设置", "joy_": "手柄设置",
    "m_": "鼠标设置", "ui_": "界面设置", "game_": "游戏设置",
    "rcon": "远程控制", "log": "日志设置", "ban": "封禁设置",
}

# --------------------------------------------------------------------------- #
# 2. 词表（整词匹配；长词优先）
# --------------------------------------------------------------------------- #
TOKENS = {
    # --- 对象 / 玩法 ---
    "c4": "C4 炸弹", "bomb": "炸弹", "defuse": "拆弹", "defuser": "拆弹器",
    "plant": "安放", "planted": "已安放", "replant": "重新安放",
    "hostage": "人质", "hostages": "人质", "rescue": "营救", "rescued": "已营救",
    "grenade": "投掷物", "grenades": "投掷物", "flashbang": "闪光弹",
    "smoke": "烟雾弹", "molotov": "燃烧瓶", "incgrenade": "燃烧弹",
    "decoy": "诱饵弹", "hegrenade": "高爆手雷", "healthshot": "医疗针",
    "damage": "伤害", "dmgtokick": "伤害踢出", "dmgtowarn": "伤害警告",
    "taser": "电击枪", "zeus": "电击枪", "dogtag": "狗牌", "dogtags": "狗牌",
    "knife": "刀", "knives": "刀", "pistol": "手枪", "pistols": "手枪",
    "rifle": "步枪", "rifles": "步枪", "sniper": "狙击枪", "snipers": "狙击枪",
    "shotgun": "霰弹枪", "shotguns": "霰弹枪", "smg": "冲锋枪", "smgs": "冲锋枪",
    "machinegun": "机枪", "gun": "枪械", "guns": "枪械", "weapon": "武器",
    "weapons": "武器", "ammo": "弹药", "armor": "护甲", "kevlar": "护甲",
    "helmet": "头盔", "money": "金钱", "cash": "金钱", "economy": "经济",
    "buy": "购买", "buymenu": "购买菜单", "sellback": "退款",
    "player": "玩家", "players": "玩家", "team": "队伍", "teams": "队伍",
    "teammate": "队友", "teammates": "队友", "enemy": "敌人", "enemies": "敌人",
    "bot": "机器人", "bots": "机器人", "spectator": "观战者", "spectators": "观战者",
    "round": "回合", "rounds": "回合", "match": "比赛", "matchmaking": "匹配",
    "warmup": "热身", "freezetime": "冻结时间", "halftime": "半场",
    "overtime": "加时", "timeout": "暂停", "timeouts": "暂停",
    "score": "得分", "scoreboard": "计分板", "assist": "助攻", "assists": "助攻",
    "kill": "击杀", "kills": "击杀", "death": "死亡", "deaths": "死亡",
    "respawn": "重生", "spawn": "出生", "bot_kick": "踢出机器人",
    "chat": "文字聊天", "voice": "语音", "radio": "无线电", "ping": "标记",
    "radar": "雷达", "minimap": "小地图", "hud": "HUD", "crosshair": "准星",
    "viewmodel": "视角模型", "fov": "视野范围", "sensitivity": "灵敏度",
    "mouse": "鼠标", "keyboard": "键盘", "joystick": "摇杆", "gamepad": "手柄",
    "volume": "音量", "sound": "声音", "music": "音乐", "audio": "音频",
    "demoui": "录像界面", "demo": "录像", "replay": "回放", "record": "录制",
    "shadow": "阴影", "shadows": "阴影", "light": "光照", "lighting": "光照",
    "texture": "贴图", "textures": "贴图", "particle": "粒子", "particles": "粒子",
    "fog": "雾气", "skybox": "天空盒", "sky": "天空", "decal": "贴花",
    "decals": "贴花", "ragdoll": "布娃娃", "ragdolls": "布娃娃",
    "model": "模型", "models": "模型", "frame": "帧", "fps": "帧率",
    "framerate": "帧率", "frametime": "帧时间", "tick": "tick", "ticks": "tick",
    "tickrate": "tick 速率", "latency": "延迟", "jitter": "抖动", "loss": "丢包",
    "bandwidth": "带宽", "rate": "速率", "buffer": "缓冲", "interp": "插值",
    "packet": "数据包", "packets": "数据包", "connection": "连接",
    "cheat": "作弊", "cheats": "作弊", "debug": "调试", "developer": "开发者模式",
    "log": "日志", "logging": "日志记录", "console": "控制台",
    "map": "地图", "level": "关卡", "explosion": "爆炸", "fire": "火焰",
    "speed": "速度", "velocity": "速度", "gravity": "重力", "friction": "摩擦力",
    "accelerate": "加速度", "acceleration": "加速度", "bunnyhopping": "连跳",
    "bhop": "连跳", "autobunnyhopping": "自动连跳", "jump": "跳跃",
    "walk": "步行", "crouch": "下蹲", "duck": "下蹲", "strafe": "横移",
    "air": "空中", "ground": "地面", "water": "水中", "ladder": "梯子",
    "surf": "滑翔", "aim": "瞄准", "recoil": "后坐力", "spread": "散布",
    "inaccuracy": "散布", "accuracy": "精度", "penetration": "穿透",
    "tracer": "曳光弹", "tracers": "曳光弹", "zoom": "开镜", "scope": "瞄准镜",
    "silencer": "消音器", "outline": "描边", "alpha": "不透明度",
    "opacity": "不透明度", "color": "颜色", "thickness": "粗细",
    "size": "大小", "length": "长度", "width": "宽度", "height": "高度",
    "gap": "间隙", "dot": "中心点", "style": "样式", "scale": "缩放",
    "offset": "偏移", "position": "位置", "rotation": "旋转", "distance": "距离",
    "range": "范围", "radius": "半径", "time": "时间", "duration": "持续时间",
    "delay": "延迟", "interval": "间隔", "period": "周期", "count": "数量",
    "max": "最大", "min": "最小", "limit": "上限", "threshold": "阈值",
    "ratio": "比例", "percent": "百分比", "level": "等级",
    "difficulty": "难度", "mode": "模式", "type": "类型",
    "first": "第一", "second": "第二", "third": "第三", "last": "最后",
    "current": "当前", "default": "默认", "server": "服务器", "client": "客户端",
    "host": "主机", "local": "本地", "online": "在线", "offline": "离线",
    "body": "身体", "head": "头部", "headshot": "爆头", "chest": "胸部",
    "hitbox": "命中判定框", "hitboxes": "命中判定框", "bone": "骨骼",
    "bones": "骨骼", "entity": "实体", "entities": "实体", "prop": "道具",
    "props": "道具", "trigger": "触发器", "button": "按钮", "door": "门",
    "vehicle": "载具", "physics": "物理", "collision": "碰撞",
    "trace": "射线检测", "ray": "射线", "volumetric": "体积", "screen": "屏幕",
    "window": "窗口", "fullscreen": "全屏", "resolution": "分辨率",
    "quality": "画质", "brightness": "亮度", "gamma": "伽马", "contrast": "对比度",
    "bloom": "泛光", "blur": "模糊", "antialias": "抗锯齿", "vsync": "垂直同步",
    "shader": "着色器", "shaders": "着色器", "imgui": "调试界面",
    "overlay": "叠加层", "flashlight": "手电筒", "muzzle": "枪口",
    "muzzleflash": "枪口火光", "stats": "统计", "statistics": "统计",
    "telemetry": "遥测", "profile": "性能分析", "budget": "预算",
    "memory": "内存", "thread": "线程", "threads": "线程", "async": "异步",
    "parallel": "并行", "loading": "加载", "preload": "预加载",
    "avatar": "头像", "avatars": "头像", "name": "名称", "names": "名称",
    "clan": "战队", "clantag": "战队标签", "clantags": "战队标签",
    "invite": "邀请", "invites": "邀请", "lobby": "大厅", "party": "小队",
    "friend": "好友", "friends": "好友", "mute": "屏蔽", "muted": "已屏蔽",
    "ban": "封禁", "bans": "封禁", "kick": "踢出", "vote": "投票",
    "votes": "投票", "password": "密码", "admin": "管理员", "rcon": "远程控制",
    "workshop": "创意工坊", "addon": "附加内容", "addons": "附加内容",
    "annotation": "标注", "annotations": "标注", "marker": "标记",
    "report": "报告", "reports": "报告", "warning": "警告", "warnings": "警告",
    "notification": "通知", "notifications": "通知", "message": "消息",
    "messages": "消息", "issue": "问题", "issues": "问题",
    "preview": "预览", "thumbnail": "缩略图", "icon": "图标", "icons": "图标",
    "mainmenu": "主菜单", "menu": "菜单", "panel": "面板", "widget": "控件",
    "loadout": "装备栏", "inventory": "物品栏", "item": "物品", "items": "物品",
    "skin": "皮肤", "skins": "皮肤", "paintkit": "涂装",
    "music_volume": "音乐音量", "mixahead": "混音提前量", "timer": "计时",
    "multi": "多重", "binds": "按键绑定", "bind": "按键绑定", "binds_": "按键绑定",
    "input": "输入", "vote": "投票", "nextmap": "下一张地图", "keep": "保留",
    "current": "当前", "end": "结束", "match_end": "比赛结束",
    "teamid": "队友标识", "overhead": "头顶", "colors": "颜色",
    "next": "下一个", "prev": "上一个", "previous": "上一个",
    "delay": "延迟", "timing": "时序", "zoom": "开镜", "unscope": "取消开镜",
    # ---- 按未译片段频次补的第二批 ----
    "csgo": "CSGO", "test": "测试", "sos": "声音引擎", "dist": "距离",
    "path": "路径", "override": "覆盖", "playsettings": "对局设置",
    "gen": "生成", "radial": "环形菜单", "text": "文本", "depth": "深度",
    "ent": "实体", "tab": "标签页", "camera": "摄像机", "bias": "偏移",
    "listen": "监听", "spring": "弹簧", "flags": "标记", "split": "分割",
    "area": "区域", "start": "开始", "layer": "层", "npcsolve": "NPC 解算",
    "cache": "缓存", "gpu": "GPU", "filter": "过滤器", "world": "世界",
    "occlusion": "遮挡", "fade": "淡出", "joint": "关节", "dsp": "DSP",
    "adsp": "音频 DSP", "list": "列表", "factor": "系数", "shoot": "射击",
    "step": "步进", "obstacle": "障碍", "session": "会话", "clip": "裁剪",
    "tone": "色调", "pred": "预测", "visualize": "可视化", "event": "事件",
    "material": "材质", "boundary": "边界", "opt": "优化", "yaw": "偏航",
    "anim": "动画", "pitch": "俯仰", "multiplier": "倍率",
    "aspect": "宽高比", "detail": "细节", "task": "任务",
    "absorb": "吸收", "rt": "实时", "playcast": "播送", "rcvage": "接收时效",
    "ledge": "边缘", "airboat": "气垫船", "jeep": "吉普",
    "push": "推力", "stat": "统计", "splitscreen": "分屏", "hltv": "HLTV",
    "poll": "轮询", "network": "网络", "early": "提前", "latch": "锁存",
    "silencer": "消音器", "ironsight": "机瞄", "highlight": "高亮",
}

# --------------------------------------------------------------------------- #
# 3. 修饰词（英文 → 中文），单独成块
# --------------------------------------------------------------------------- #
MODIFIERS = {
    "anywhere": "在任意位置", "everywhere": "在所有位置", "always": "始终",
    "never": "从不", "only": "仅", "all": "全部", "none": "无",
    "auto": "自动", "automatic": "自动", "manual": "手动",
    "infinite": "无限", "unlimited": "无限", "free": "免费",
    "allow": "允许", "allowed": "允许", "disallow": "禁止", "deny": "拒绝",
    "enable": "启用", "enabled": "启用", "disable": "禁用", "disabled": "禁用",
    "force": "强制", "forced": "强制", "require": "要求", "required": "必需",
    "ignore": "忽略", "block": "屏蔽", "skip": "跳过", "prevent": "阻止",
    "show": "显示", "display": "显示", "hide": "隐藏", "draw": "绘制",
    "render": "渲染", "update": "更新", "reset": "重置", "reload": "重新加载",
    "save": "保存", "load": "加载", "write": "写入", "read": "读取",
    "print": "打印", "toggle": "切换", "random": "随机", "randomize": "随机化",
    "use": "使用", "uses": "使用", "shared": "共享", "private": "私有",
    "public": "公开", "global": "全局", "per": "每", "user": "用户",
    "same": "相同", "different": "不同", "custom": "自定义",
    "silent": "静默", "smooth": "平滑", "dynamic": "动态", "static": "静态",
    "fast": "快速", "slow": "缓慢", "high": "高", "low": "低",
    "near": "近处", "far": "远处", "front": "前方", "back": "后方",
    "left": "左侧", "right": "右侧", "top": "顶部", "bottom": "底部",
    "vertical": "垂直", "horizontal": "水平", "both": "两者",
    "overhead": "头顶", "on": "开启", "off": "关闭",
    "again": "再次", "before": "之前", "after": "之后", "during": "期间",
    "while": "在…时", "when": "当…时", "if": "如果",
    "team": "队伍", "enemy": "敌方", "friendly": "友方",
    "first_person": "第一人称", "third_person": "第三人称",
}

# --------------------------------------------------------------------------- #
# 4. 布尔值句式模板（按后缀从长到短匹配）
# --------------------------------------------------------------------------- #
BOOL_SUFFIX = [
    ("_anywhere", "是否允许在任意位置"),
    ("_everywhere", "是否允许在所有位置"),
    ("_always", "是否始终"),
    ("_only", "是否仅限"),
    ("_enabled", "是否启用"),
    ("_disabled", "是否禁用"),
    ("_allowed", "是否允许"),
    ("_enable", "是否启用"),
    ("_disable", "是否禁用"),
    ("_allow", "是否允许"),
    ("_force", "是否强制"),
    ("_ignore", "是否忽略"),
    ("_block", "是否屏蔽"),
    ("_show", "是否显示"),
    ("_hide", "是否隐藏"),
    ("_display", "是否显示"),
    ("_draw", "是否绘制"),
    ("_render", "是否渲染"),
    ("_use", "是否使用"),
    ("_on", "是否开启"),
    ("_off", "是否关闭"),
]

BOOL_PREFIX = [
    ("show_", "是否显示"),    ("hide_", "是否隐藏"),
    ("draw_", "是否绘制"),
    ("render_", "是否渲染"),
    ("enable_", "是否启用"),
    ("disable_", "是否禁用"),
    ("allow_", "是否允许"),
    ("force_", "是否强制"),
    ("ignore_", "是否忽略"),
    ("use_", "是否使用"),
]


def _tokens_of(stem: str):
    """把名字主体按"从左到右贪心最长匹配"切成中文块。

    先整词（按 _ 切开）匹配，再对切不开的粘连词做贪心最长匹配，
    这样 muzzleflash / freezetime / autobunnyhopping 这类都不会重复或乱序。
    """
    out, hits, missed = [], 0, 0
    keys = sorted(set(TOKENS) | set(MODIFIERS), key=len, reverse=True)
    # 两字母的词（c4 / ui / smg…）也是有效语义，但太短的通用词会误伤，所以只放行白名单
    SHORT_OK = {"c4", "ui", "smg", "fov", "hud", "ct", "ak", "awp", "de", "hp"}

    def emit(word: str, table):
        nonlocal hits
        out.append(("tok" if table is TOKENS else "mod", table[word]))
        hits += 1

    def matchable(k: str) -> bool:
        return len(k) >= 3 or k in SHORT_OK

    for raw in re.split(r"[_\.]", stem):
        p = raw.lower()
        if not p:
            continue
        if p in MODIFIERS:
            emit(p, MODIFIERS)
            continue
        if p in TOKENS:
            emit(p, TOKENS)
            continue
        # 粘连词：贪心最长匹配，每次至少前进一个字符
        i, buf = 0, ""
        while i < len(p):
            matched = None
            for k in keys:
                if matchable(k) and p.startswith(k, i):
                    matched = k
                    break
            if matched:
                if buf:
                    out.append(("raw", buf))
                    missed += 1
                    buf = ""
                emit(matched, MODIFIERS if matched in MODIFIERS else TOKENS)
                i += len(matched)
            else:
                buf += p[i]
                i += 1
        if buf:
            out.append(("raw", buf))
            missed += 1
    return out, hits, missed


def _core_tokens(text: str, table):
    """某个中文词条对应哪些英文词（用于把重复的未译片段去掉）。"""
    text = text.strip()
    hits = [k for k in table if table[k].strip() == text]
    for c in hits:
        yield c
    # 也拆出中文词条里含英文的部分（如 "HUD 设置"）
    for piece in re.findall(r"[A-Za-z]{2,}", text):
        yield piece


def _drop_dupes(blocks):
    """去掉"和相邻中文块指向同一个英文词"的 raw 片段。

    例：mp_damage_headshot_only → 词表里 damage→"伤害"、headshot→"爆头"，
    残留的 raw 'damage' 应丢掉，而不是拼成"仅限damage爆头damage"。
    """
    table = dict(TOKENS)
    table.update(MODIFIERS)
    covered = set()
    for kind, text in blocks:
        if kind == "raw":
            continue
        for key, val in table.items():
            if val.strip() == text.strip():
                covered.add(key)
        for piece in re.findall(r"[A-Za-z]{2,}", text):
            covered.add(piece.lower())
    out = []
    for kind, text in blocks:
        if kind == "raw" and text.lower() in covered:
            continue
        out.append((kind, text))
    return out


def _norm_terms(text: str) -> str:
    """中文短语里的规范写法：C4 / HUD 这类拉丁词前后留空格。"""
    text = re.sub(r"(?<=[\u4e00-\u9fff])(C4|HUD|UI|tick|SourceTV)(?=[\u4e00-\u9fff])",
                  r" \1 ", text)
    text = re.sub(r"\s{2,}", " ", text)
    return text.strip()


def _join(blocks):
    """把词块拼成中文短语。"""
    blocks = _drop_dupes(blocks)
    # 复数尾巴与粘连残留：紧跟在中文块后面的单字母（s / z / c / g / f…）丢掉
    cleaned = []
    for kind, text in blocks:
        if kind == "raw" and len(text) == 1 and text.isalpha() \
                and cleaned and cleaned[-1][0] != "raw":
            continue
        cleaned.append((kind, text))
    blocks = cleaned
    s = "".join(text for _kind, text in blocks)
    return _norm_terms(s)


def breakdown(name: str):
    """给出"名字语义拆解"：已知含义照译，未识别词如实列出。

    例：tv_playcast_max_rtdelay → "可识别含义：实时 / 播送 / 最大 / 延迟"
    """
    if not name:
        return ""
    low = name.lower()
    pre = max((p for p in PREFIX_FAMILY if low.startswith(p)), key=len, default=None)
    frame = PREFIX_FAMILY.get(pre) if pre else None
    stem = low[len(pre):] if pre else low
    if not stem:
        return ""
    blocks, _h, _m = _tokens_of(stem)
    known, unknown = [], []
    for kind, text in blocks:
        if kind == "raw":
            if len(text) > 1 and text not in unknown:
                unknown.append(text)
        elif text not in known:
            known.append(text)
    if not known:
        return ""
    parts = list(known)
    if frame and frame not in parts:
        parts.insert(0, frame)
    s = "可识别含义：" + " / ".join(parts)
    if unknown:
        s += "；未识别：" + "、".join(unknown)
    return s


def describe_name(name: str, typ: str = "", default=None):
    """从名字推断中文释义。返回 (中文, 置信度)；置信度 0 = 推不出来。"""
    if not name or len(name) < 3:
        return None, 0
    low = name.lower()
    # 前缀框架
    pre = max((p for p in PREFIX_FAMILY if low.startswith(p)), key=len, default=None)
    frame = PREFIX_FAMILY.get(pre) if pre else None
    stem = low[len(pre):] if pre else low
    if not stem:
        return None, 0

    is_bool = (typ == "bool") or str(default).lower() in ("true", "false")
    body = None

    if is_bool:
        for suf, lead in BOOL_SUFFIX:
            if stem.endswith(suf) and len(stem) > len(suf):
                base = stem[:len(stem) - len(suf)]
                blocks, _h, _m = _tokens_of(base)
                body = lead + _join(blocks)
                break
        if not body:
            for pfx, lead in BOOL_PREFIX:
                if stem.startswith(pfx) and len(stem) > len(pfx):
                    blocks, _h, _m = _tokens_of(stem[len(pfx):])
                    body = lead + _join(blocks)
                    break

    blocks, hits, missed = _tokens_of(stem)
    if not body:
        if not any(k != "raw" for k, _ in blocks):
            return None, 0
        body = _join(blocks)
    elif missed:
        # 句式已给出主语，把没翻出来的词补在后面
        extra = _join([b for b in blocks if b[0] == "raw"])
        if extra:
            body += extra

    lead = f"{frame}：" if frame else ""
    sentence = f"{lead}{body}"
    if not sentence.endswith(("。", "！", "？")):
        sentence += "。"
    if is_bool and default is not None and str(default).lower() in ("true", "false"):
        sentence += f"默认 {'开' if str(default).lower() == 'true' else '关'}。"

    if not re.search(r"[\u4e00-\u9fff]", sentence):
        return None, 0
    # 置信度：只看"残留的是不是真英文词"。单字母（复数尾巴 s、粘贴残留 f 之类）
    # 不算未译词，否则 frames→"帧"+s 这种好结果会被误杀。
    missed_words = sum(1 for k, t in blocks if k == "raw" and len(t) > 1)
    conf = 2 if missed_words == 0 else (1 if missed_words <= 1 else 0)
    return sentence, conf


if __name__ == "__main__":
    tests = [
        ("mp_plant_c4_anywhere", "bool", "false"),
        ("sv_infinite_ammo", "bool", "true"),
        ("cl_disable_round_end_report", "bool", "false"),
        ("mp_damage_headshot_only", "bool", "false"),
        ("sv_autobunnyhopping", "bool", "false"),
        ("cl_teamid_overhead_colors_show", "bool", "true"),
        ("snd_mixahead", "float", "0.025"),
        ("mp_c4timer", "int", "40"),
        ("sv_gravity", "float", "800"),
        ("r_drawtracers", "bool", "true"),
        ("cl_radar_scale", "float", "0.7"),
        ("mp_freezetime", "float", "15"),
        ("cl_crosshairstyle", "int", "4"),
        ("voice_threshold", "float", "-100"),
        ("con_enable", "bool", "true"),
        ("cl_allow_multi_input_binds", "bool", "false"),
        ("mp_endmatch_votenextmap_keepcurrent", "bool", "true"),
    ]
    for n, t, d in tests:
        zh, conf = describe_name(n, t, d)
        print(f"{n:36s} conf={conf}  {zh}")
