# -*- coding: utf-8 -*-
"""解析游戏自己导出的 cvarlist / cmdlist 文件，生成权威指令库。

这是整条数据链路里**唯一权威**的来源：游戏运行时会把每个已注册 cvar/命令
连同权限标记、默认值、官方说明一起打印出来。

输入（放到 tools/ 或项目根目录均可，文件名任意，只要含 cvarlist/cmdlist）：
    cs2_cvarlist.txt    由控制台 cvarlist 生成
    cs2_cmdlist.txt     由控制台 cmdlist 生成

典型格式（Source 2）：
    cl_crosshaircolor = "1"  ( def. "0" )  client  -  Crosshair color
    mp_freezetime     = "5"  ( def. "5" )  server, replicated  -  ...
    bot_add           : cmd  -  bot_add <t|ct> ... Adds a bot.

用法：
  python tools/import_cvar_dump.py --cvarlist <路径> [--cmdlist <路径>] [--apply]
"""
import argparse
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
EXTRA = DATA / "game_extra.json"

# cl_xxx = "value" ( def. "value" ) flags - description
CVAR_A = re.compile(
    r"^(?P<name>[A-Za-z_+][A-Za-z0-9_+]*)\s*=\s*\"?(?P<val>[^\"]*?)\"?\s*"
    r"(?:\(\s*def\.\s*\"?(?P<def>[^\"]*?)\"?\s*\))?\s*"
    r"(?P<flags>[a-z_,\s]*?)\s*-\s*(?P<desc>.*)$")
# cl_xxx : cmd - description
CMD_A = re.compile(r"^(?P<name>[A-Za-z_+][A-Za-z0-9_+]*)\s*:\s*(?P<kind>cmd|command)\s*-\s*(?P<desc>.*)$")
# cvarlist 的真实格式： 名称 : 权限标记 : 类型 : 说明
CVAR_C = re.compile(
    r"^(?P<name>[A-Za-z_+][A-Za-z0-9_+]*)\s*:\s*"
    r"(?P<flags>[a-z_,\s]*?)\s*:\s*"
    r"(?P<type>[a-z_]*?)\s*:\s*"
    r"(?P<desc>.*)$")
# 退化格式：name = "value"
CVAR_B = re.compile(r"^(?P<name>[A-Za-z_+][A-Za-z0-9_+]*)\s*=\s*\"?(?P<val>[^\"]*?)\"?\s*$")
# 每行可能带的前缀，来源不同：
#   console.log:  10/14 03:29:59 [Server] xxx
#   vconsole2  :  [Console] xxx / [Client] xxx
#   VConsole2 会话日志: "[   Console               ]: xxx"（方括号内补空格对齐）
LOGPREFIX = re.compile(
    r"^\s*(?:\[\s*(?:Console|Client|Server|Engine|General|InputService|SplitScreen|Host|"
    r"VConComm|VConsole|RenderPipeline\w*|Prediction|Networking|SteamNetSockets|\[I\] VConsole)"
    r"\s*\]\s*:?\s*"
    r"|(?:\d{1,2}[/-]\d{1,2}\s+)?\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:\s*\[[^\]]{0,24}\])?\s*)",
    re.I)
# 报告尾巴：  "1234 total convars/concommands" 之类
# 注意：只认"整行就是表尾"的形式。不要用 `^cvarlist` / `^cmdlist` 来跳过命令回显，
# 否则会把 `cvarlist : cmd : release : Show the list of convars/concommands.`
# 这条**真实命令**一起丢掉（曾经漏掉过它）。
SUMMARY = re.compile(
    r"^\s*-{3,}\s*$"
    r"|^\s*\d+\s+total convars/concommands\s*$"
    r"|^\s*total convars/concommands\s*$")

# cvarlist 的定宽列（对齐时用它切，比按 " : " 切更可靠）：
#   名称(左对齐 74) : 值/cmd(16) : 权限标记(32) : 说明
# 分隔符 ' : ' 分别落在 79-81 / 98-100 / 133-135，所以各列区间是：
COL_NAME = (0, 78)
COL_VALUE = (82, 97)
COL_FLAGS = (101, 133)
COL_DESC = 136

FLAG_WORDS = {"client", "server", "replicated", "rep", "cheat", "release", "norecord", "archive",
              "notify", "userinfo", "print", "demo", "per_user", "server_can_execute",
              "clientcmd_can_execute", "protected", "prot", "unlogged", "nolog", "devonly",
              "a", "nf", "user", "sv", "cl", "linked", "execute_per_tick", "menubar_item",
              "vconsole_fuzzy", "vconsole_set_focus", "server_cant_query", "client"}
SCOPE_WORDS = {"client", "server", "replicated", "rep", "per_user"}

# 是否强制"定宽列对齐"判据（名字列 74 宽度、第一个冒号在第 81 列）。
# 日志文件（VConsole2 会话日志）必须开，用来挡掉日志频道行；
# 但用户从控制台界面复制的纯文本会丢掉右侧补空格，此时要关掉。
ENFORCE_ALIGN = True


def parse_colon_fields(line):
    """解析 cvarlist 的固定格式：

        名称 : 默认值或 cmd : 权限标记 : 说明

    两种排版都要吃下：
      * VConsole2 会话日志（定宽，74/16/32 列，用位置切最稳）
      * 用户从 VConsole2 复制出来的文本（分隔符变成 " : "，尾巴空格被吃掉）
    """
    s = line.rstrip()
    # 统一分隔符：冒号前后的空格可能被吃掉（说明为空时尾部只剩一个 ':'），
    # 先把所有 "[:]" 规范成 " : "，再按它切分，避免 "cl, release    :" 这种残尾。
    norm = re.sub(r"\s*:\s*", " : ", s)

    def ok(n):
        return bool(re.fullmatch(r"[A-Za-z_+][A-Za-z0-9_+]*", n or ""))

    # ---- 路线一：定宽列 ----
    # 前置条件：行至少要长到"权限列"结束，否则短行会被整段当成名字、
    # 三列全空却"校验通过"（'requires_attr' / 'de_cache' 这类单 token 行就是这样漏进来的）。
    name_w = s[COL_NAME[0]:COL_NAME[1]].strip() if len(s) >= COL_FLAGS[0] else ""
    if ok(name_w):
        val_w = s[COL_VALUE[0]:COL_VALUE[1]].strip() if len(s) >= COL_VALUE[0] + 3 else ""
        flags_w = s[COL_FLAGS[0]:COL_FLAGS[1]].strip().strip(",") if len(s) >= COL_FLAGS[0] else ""
        desc_w = s[COL_DESC:].strip() if len(s) > COL_DESC else ""
        # 三列全空不是记录（挡住单 token 行）
        if not val_w and not flags_w and not desc_w:
            name_w = ""
        val = s[COL_VALUE[0]:COL_VALUE[1]].strip()
        flags = s[COL_FLAGS[0]:COL_FLAGS[1]].strip().strip(",")
        desc = s[COL_DESC:].strip() if len(s) > COL_DESC else ""
        # 权限列必须是权限词，否则说明排版不是定宽的，退回路线二
        if re.fullmatch(r"[a-z_,\s]*", flags) and (
                not flags or all(f in FLAG_WORDS for f in re.split(r"[,\s]+", flags) if f)):
            flag_list = [f.strip() for f in re.split(r"[,\s]+", flags) if f.strip()]
            return {
                "name": name_w,
                "value": "" if val.lower() == "cmd" else val,
                "default": None,
                "flags": flag_list,
                "type": "",
                "desc": desc,
                "kind": "cmd" if val.lower() == "cmd" else "cvar",
            }

    # ---- 路线二：按冒号切分（不依赖冒号两侧空格，最稳） ----
    # 切完并 strip 后：
    #   5 段 → 名称 | 值 | 权限 | 类型 | 说明
    #   4 段 → 名称 | 值 | 权限 | ''        （官方没给说明，尾巴只剩一个 ':'）
    #   3 段 → 名称 | 值 | 权限
    parts = [p.strip() for p in s.strip().split(":", 4)]
    if len(parts) < 3:
        return None
    name = parts[0]
    if not ok(name):
        return None
    val = parts[1]
    flags = parts[2]
    typ = parts[3] if len(parts) > 3 else ""
    desc = parts[4] if len(parts) > 4 else ""

    # 值、权限、说明全空的行不是记录（如 'requires_attr' / 'de_cache' 这类单 token 行）
    if not val.strip() and not flags.strip() and not desc.strip():
        return None
    # ---- 真伪判定：cvarlist 是定宽输出，名字列固定 74 字符宽 ----
    # 实测本机 2802 条导出里，第一个 ' : ' 的冒号**恒定在第 81 列**；
    # 而日志频道行（CL / SV / CEntitySystem…）的冒号位置是随机的。
    # 这是最干净、零误伤的判据，比正则猜"值长什么样"可靠得多。
    colons = [i for i, c in enumerate(s) if c == ":"]
    aligned = bool(colons) and colons[0] == 81
    if not aligned and not ENFORCE_ALIGN:
        # 纯文本粘贴（从控制台界面复制出来的）不再是定宽列，此时只靠值字段形状判定
        aligned = True
    if not aligned:
        # 非对齐行只在"值字段明确无歧义"时才放行（少量旧格式/简化格式）
        v0 = val.strip()
        if not (v0.lower() == "cmd" or re.fullmatch(r"-?\d+(\.\d+)?|true|false", v0)):
            return None

    def is_flags(x):
        x = (x or "").strip()
        if not x:
            return True
        return all(f in FLAG_WORDS for f in re.split(r"[,\s]+", x) if f)

    # ---- 严格校验：把日志行挡在外面 ----
    # VConsole2 的日志频道行长这样： "CL : MaybeSwitchToGameLoop switching to ..."、
    # "CEntitySystem : BuildEntityNetworking (...) took 18.5 msecs ..."，
    # 只靠冒号切分会被误当成 cvar。真正的 cvarlist 行里，第 2 段一定是
    # 空值 / cmd / 数字 / true / false / 短标识（不带空格、不长）。
    def is_value(x):
        x = (x or "").strip()
        if x == "" or x.lower() == "cmd":
            return True
        if len(x) > 40:
            return False
        if re.fullmatch(r'"[^"]*"', x):
            return True
        if re.fullmatch(r"-?\d+(\.\d+)?([eE]-?\d+)?", x):
            return True
        if x.lower() in ("true", "false"):
            return True
        # 单 token（不含空格）：如 fill / normal / any / weapon_knife / 0 0 0
        if " " in x or "\t" in x:
            return False
        return bool(re.fullmatch(r"[\w.,:/#@|%$+\-\[\]]{1,40}", x))

    # ---- 值字段校验（分两档）----
    if not aligned:
        # 非对齐行（日志里的零散命中 / 旧格式）：必须严格像默认值才放行
        if not is_value(val):
            return None
    # 无论是否对齐，都排除"明显是日志句子/调用描述"的值。
    # 注意：列对齐的行是铁证，合法默认值可能很长且带空格/|/#/[]，
    # 例如 "vesthelm vest m4a1 ak47 famas"、"4|2;#GameUI_Retake_Card_..."、
    # "[1:5][2:15][3:15]" —— 这些都不能被误杀。
    v = (val or "").strip()
    if v.lower() != "cmd":
        if re.search(r"[(){}]|->|\btook\b|\bmsecs\b|\bnetframes\b|LoopActivateAllSystems", v) \
                or len(v) > 400:
            return None
    # 名字必须是合法 cvar/命令标识（拒绝含空格的日志频道名）
    if not re.fullmatch(r"[A-Za-z_+][A-Za-z0-9_+]*", name):
        return None

    # 第 3 段不像权限词时，说明这一行的布局与预期不同（旧格式没有类型列）
    if not is_flags(flags):
        if len(parts) == 3:
            desc, typ, flags = flags, "", ""
        elif len(parts) >= 4:
            typ, flags = "", ""
    if len(parts) == 4 and typ and not re.fullmatch(r"[a-z_]{0,12}", typ):
        desc, typ = typ, ""
    flag_list = [f.strip() for f in re.split(r"[,\s]+", flags) if f.strip()]
    return {
        "name": name,
        "value": "" if val.lower() == "cmd" else val,
        "default": None,
        "flags": flag_list,
        "type": typ or None,
        "desc": desc,
        "kind": "cmd" if (val.lower() == "cmd" or typ == "cmd") else "cvar",
    }


def _classify_source(text):
    """判断输入是「定宽日志」还是「界面复制出来的纯文本」。

    定宽日志里第一个冒号恒定在第 81 列（名字列 74 宽 + 两侧空格）；
    纯文本会丢掉右侧补空格，冒号位置参差不齐。判定结果用于决定是否启用
    「列对齐」判据（该判据是挡日志频道行的关键，但不能用在纯文本上）。
    """
    total = hit = 0
    for raw in text.splitlines():
        line = LOGPREFIX.sub("", raw).rstrip()
        if not line or SUMMARY.match(line):
            continue
        if not re.match(r"^[A-Za-z_+][A-Za-z0-9_+]*\s*:", line):
            continue
        total += 1
        if line.find(":") == 81:
            hit += 1
    return total >= 20 and hit / total > 0.6


def parse_dump(text, is_cmd=False):
    """返回 {name: {value, default, flags, desc}}

    兼容三种来源：
      1. 控制台 `cvarlist` 原始输出（带时间戳的 console.log / VConsole2 会话日志）
      2. `cmdlist` 输出（name : cmd : flags : description）
      3. 简化格式 name = "value" ( def. "x" ) flags - description
    """
    global ENFORCE_ALIGN
    saved = ENFORCE_ALIGN
    ENFORCE_ALIGN = _classify_source(text)
    try:
        return _parse_dump_inner(text, is_cmd)
    finally:
        ENFORCE_ALIGN = saved


def _parse_dump_inner(text, is_cmd=False):
    out = {}
    skipped = 0
    for raw in text.splitlines():
        line = LOGPREFIX.sub("", raw).rstrip()          # 去掉 console.log 的时间戳/通道前缀
        line = line.replace("\t", " ")
        if not line or line.lstrip().startswith(("//", "#")):
            continue
        low = line.lower()
        # 只跳"表尾/分隔线"本身。绝不能用 startswith('cvarlist') 跳命令行，
        # 否则会把 `cvarlist : cmd : release : Show the list of convars/concommands.`
        # 这条真实命令丢掉（踩过这个坑）。
        if SUMMARY.match(line) or low.startswith(("total convars", "====", "----")):
            continue
        # 首选：vconsole2 的 " : " 定宽格式（最可靠）
        rec = parse_colon_fields(line)
        if rec:
            if is_cmd:
                rec["kind"] = "cmd"
            out[rec["name"]] = {k: v for k, v in rec.items() if k != "name"}
            continue
        m = (CVAR_A.match(line) or CMD_A.match(line) or CVAR_B.match(line))
        if not m:
            skipped += 1
            continue
        g = m.groupdict()
        name = g.get("name")
        if not name or len(name) < 2:
            skipped += 1
            continue
        flags_raw = (g.get("flags") or "").strip().strip(",")
        flags = [f.strip() for f in re.split(r"[,\s]+", flags_raw) if f.strip()]
        desc = (g.get("desc") or "").strip()
        out[name] = {
            "value": (g.get("val") or "").strip(),
            "default": (g.get("def") or "").strip() or None,
            "flags": flags,
            "type": (g.get("type") or "").strip() or None,
            "desc": desc,
            "kind": "cmd" if (is_cmd or g.get("kind") or re.search(r":\s*cmd\b", line)) else "cvar",
        }
    return out, skipped


def scope_of(flags):
    f = set(flags)
    cl, sv = "client" in f, "server" in f
    if cl and sv:
        return "both"
    if cl:
        return "client"
    if sv:
        return "server"
    return "unknown"


def apply_entries(merged, args, label="", source_files=None):
    """把解析结果写成 data/game_extra.json（构建时并入库）。"""
    db = json.loads((DATA / "commands.json").read_text(encoding="utf-8"))
    db_names = {e["n"] for e in db["entries"]}
    new_names = sorted(n for n in merged if n not in db_names)

    print(f"\n[i] 来源 {label or '游戏导出'}：共 {len(merged)} 条")
    print(f"    现有库已收录 {len(merged) - len(new_names)} 条")
    print(f"    库里缺失 {len(new_names)} 条 ← 这些是权威来源里我们缺的")

    entries = []
    for n, v in merged.items():
        # 说明为空时**必须**保持为空：不能拿默认值（"10"/"0"/"false"）冒充英文释义，
        # 否则前端会把数字当成官方说明显示出来。
        entries.append({
            "n": n,
            "en": (v.get("desc") or "").strip(),
            "d": v.get("default") or (v.get("value") or None),
            "s": scope_of(v.get("flags") or []),
            "f": ", ".join(v.get("flags") or []),
            "t": v.get("type") or None,
            "k": "cmd" if v.get("kind") == "cmd" else "cvar",
            "src": "game-dump",
            "is_new": n not in db_names,
        })
    out = {
        "note": "游戏控制台 cvarlist 的权威导出：权限标记、说明来自游戏本身；"
                "d 为运行时的当前值（游戏只打印当前值，默认值以上游为准）",
        "imported_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "source_files": source_files or [],
        "total": len(entries),
        "new_count": len(new_names),
        "new_names": new_names,
        "entries": entries,
    }
    if args.apply:
        EXTRA.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"[OK] 已写入 data/game_extra.json（{len(entries)} 条，其中新增 {len(new_names)} 条）")
        print("     接着运行： python tools\\build_db.py   （会自动并入指令库）")
    else:
        (DATA / "game_extra.preview.json").write_text(
            json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
        print("[i] 预览已写入 data/game_extra.preview.json（加 --apply 才会正式并入）")
        print("\n     新增条目示例：")
        for n in new_names[:25]:
            v = merged[n]
            print(f"       {n:46s} {str(v.get('desc',''))[:58]}")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cvarlist", default="")
    ap.add_argument("--cmdlist", default="")
    ap.add_argument("--stdin", action="store_true",
                    help="从标准输入读粘贴内容（可直接把控制台输出粘贴进来）")
    ap.add_argument("--kind", default="auto", choices=["auto", "cvar", "cmd"],
                    help="stdin 内容的类型：cvarlist / cmdlist 输出")
    ap.add_argument("--apply", action="store_true", help="写入 data/game_extra.json（构建时会并入库）")
    args = ap.parse_args()

    # ---- 模式一：直接吃粘贴文本 ----
    if args.stdin or (not args.cvarlist and not args.cmdlist and not sys.stdin.isatty()):
        text = sys.stdin.read()
        if not text.strip():
            print("[!] 标准输入是空的")
            return 1
        print(f"[i] 从标准输入读到 {len(text.splitlines())} 行、{len(text)/1024:.0f} KB")
        is_cmd = args.kind == "cmd"
        got, skipped = parse_dump(text, is_cmd=is_cmd)
        if not got:
            print("[!] 一行都没解析出来。请确认粘贴的是 cvarlist 的原始输出，")
            print("    形如： cl_showfps    : client    : int    : Show fps")
            return 1
        print(f"[i] 解析出 {len(got)} 条（{skipped} 行无法识别）")
        return apply_entries(got, args, label="stdin")

    # 自动找文件
    def find(kind):
        cands = []
        for d in (ROOT, ROOT / "tools", DATA, Path.home() / "Desktop", Path.home() / "Downloads"):
            if d.exists():
                cands += [p for p in d.glob(f"*{kind}*.txt")]
        return cands

    cvar_path = Path(args.cvarlist) if args.cvarlist else (find("cvar") or [None])[0]
    cmd_path = Path(args.cmdlist) if args.cmdlist else (find("cmd") or [None])[0]
    if not cvar_path and not cmd_path:
        print("[!] 没找到 cvarlist / cmdlist 文件。")
        print("    先在游戏里执行 `exec dump_commands`（tools/dump_commands.cfg），")
        print("    然后把生成的 cs2_cvarlist.txt / cs2_cmdlist.txt 放到项目根目录或桌面，再跑本脚本。")
        return 1

    merged = {}
    for path, is_cmd in ((cvar_path, False), (cmd_path, True)):
        if not path or not Path(path).exists():
            continue
        text = Path(path).read_text(encoding="utf-8", errors="replace")
        got, skipped = parse_dump(text, is_cmd=is_cmd)
        print(f"[i] {Path(path).name}: 解析出 {len(got)} 条（跳过 {skipped} 行）")
        for k, v in got.items():
            if k in merged:
                merged[k].update({kk: vv for kk, vv in v.items() if vv})
            else:
                merged[k] = v

    if not merged:
        print("[!] 解析结果为空，请检查文件格式（应是控制台 cvarlist 的原始输出）")
        return 1

    return apply_entries(merged, args, label=",".join(
        Path(p).name for p in (cvar_path, cmd_path) if p),
        source_files=[str(p) for p in (cvar_path, cmd_path) if p])


if __name__ == "__main__":
    raise SystemExit(main())
