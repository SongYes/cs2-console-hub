# -*- coding: utf-8 -*-
"""从本地 CS2 安装目录挖控制台指令名。

原理：引擎在启动时把所有已注册的 cvar / 命令名以字符串形式编译进二进制
（cs2.exe、engine2.dll 等）。把这些字符串挖出来，再用命名规则筛选，
就能得到一份「这台机器上这个版本」实际存在的指令清单。

产出：
  data/game_scan.json   扫描结果（候选名 + 出处 + 命中次数）
  data/game_names.txt   纯名字列表，便于 diff

用法：
  python tools/scan_game.py                        # 自动探测游戏目录
  python tools/scan_game.py --dir "D:\\...\\Counter-Strike Global Offensive"
  python tools/scan_game.py --min-len 4 --top 60   # 调整筛选参数
"""
import argparse
import json
import re
import time
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

# 只扫游戏自身的二进制（第三方库如 Qt/ICU/ffmpeg 会带来海量噪声）
GAME_BINARIES = re.compile(
    r"^(cs2|vconsole2|client|server|engine2|materialsystem2|soundsystem|networksystem|"
    r"host|scenesystem|animationsystem|particles|vphysics2|tier0|filesystem_stdio|gameui|"
    r"resourcesystem|composite|matchmaking|steamnetworkingsockets|panorama|panoramauiclient|"
    r"vscript|v8system|navsystem|schemasystem|rendersystemdx11|rendersystemvulkan|"
    r"meshsystem|worldrenderer|soundemittersystem|vpk|dedicated)\.(exe|dll)$", re.I)
# 已知的指令家族前缀（命中这些的候选可信度高）
GOOD_PREFIX = re.compile(
    r"^(cl_|sv_|mp_|r_|snd_|sndev_|host_|net_|ai_|bot_|phys_|mat_|lb_|sc_|ui_|panorama_|"
    r"spec_|tv_|demo_|steam_|gc_|mm_|fps_|func_|ent_|game_|player_|weapon_|ammo_|item_|env_|"
    r"sound_|voice_|vphysics_|ragdoll_|ik_|animgraph|nav_|cs_|cstrike|blur_|sfm_|model_|"
    r"filesystem_|engine_|script_|csgo_|cstrike_|mp_|host_)"
)
# 明显不是 cvar 的名字：着色器内置变量、GLSL/HLSL 扩展、引擎内部符号
NOT_CVAR = re.compile(
    r"^(gl_|GL_|rw_|RW_|s_Linear|s_Point|s_Trilinear|SV_|CC_|C_|I_|CE_|CO_|CH_|CM_|"
    r"EarlyInit|Plat_|BinaryProperties|wasm_|wasm|vload|vstore|pthread_|__|_GLOBAL)", re.I)
# 常见的非指令噪声（CSS 类名、C++ 符号、文件路径等）
BAD_PATTERNS = [
    re.compile(r"^(C|I|S|W|Q)[A-Z][a-zA-Z]{6,}$"),          # CBaseEntity 这类类名
    re.compile(r"^(Set|Get|On|Is|Has|Can|Do|Make|Init|Calc)[A-Z]"),  # 方法名
    re.compile(r"\.(cpp|h|hpp|dll|exe|vtex|vmdl|vmat|vpcf|png|jpg|ttf|txt|cfg|vdf|vpk|so|dylib)$", re.I),
    re.compile(r"^[A-Z0-9_]{8,}$"),                          # 全大写下划线宏
    re.compile(r"(xml|json|svg|http|://|\\\\|/game/|/core/)", re.I),
    re.compile(r"^(std|boost|fmt|spdlog|v8|tbb|protobuf)_"),
    re.compile(r"^_+"),
    re.compile(r"^[a-z]+[A-Z]"),                             # camelCase 多为代码符号
]


def is_candidate(name: str) -> bool:
    if len(name) < 4 or len(name) > 44:
        return False
    if not re.fullmatch(r"[a-z][a-z0-9_]{3,43}", name):   # 引擎 cvar 全是小写+数字+下划线
        return False
    if name.endswith("_") or "__" in name:
        return False
    low = name
    if NOT_CVAR.match(low):
        return False
    for p in BAD_PATTERNS:
        if p.search(name):
            return False
    # 必须命中已知家族前缀（这是最强的可信信号）
    return bool(GOOD_PREFIX.match(low))


ASCII_RE = re.compile(rb"[\x20-\x7e]{4,64}")
UTF16_RE = re.compile(rb"(?:[\x20-\x7e]\x00){4,48}")


def scan_file(path: Path, min_len=4, max_hits=None):
    """扫一个文件，返回 Counter{候选名: 出现次数}"""
    found = Counter()
    try:
        raw = path.read_bytes()
    except Exception as e:
        return found, str(e)
    # ASCII 字符串
    for m in ASCII_RE.finditer(raw):
        s = m.group(0).decode("ascii", "ignore")
        if is_candidate(s):
            found[s] += 1
    # UTF-16LE 字符串（引擎里配置/命令表常用宽字符）
    for m in UTF16_RE.finditer(raw):
        s = m.group(0).decode("utf-16-le", "ignore")
        if is_candidate(s):
            found[s] += 1
    return found, None


def detect_game_dir():
    cands = [
        Path(r"C:\Program Files (x86)\Steam\steamapps\common\Counter-Strike Global Offensive"),
        Path(r"D:\SteamLibrary\steamapps\common\Counter-Strike Global Offensive"),
        Path(r"C:\SteamLibrary\steamapps\common\Counter-Strike Global Offensive"),
        Path(r"E:\SteamLibrary\steamapps\common\Counter-Strike Global Offensive"),
    ]
    for c in cands:
        if (c / "game" / "bin" / "win64").exists():
            return c
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="")
    ap.add_argument("--min-hits", type=int, default=1)
    ap.add_argument("--workers", type=int, default=6)
    args = ap.parse_args()

    game = Path(args.dir) if args.dir else detect_game_dir()
    if not game or not game.exists():
        print("[!] 没找到 CS2 安装目录，请用 --dir 指定")
        return 1
    print(f"[i] 游戏目录：{game}")

    # 扫描目标：只扫游戏自身二进制（engine2/client/server 等）
    targets = []
    for sub in ("game/bin/win64", "game/csgo/bin/win64", "bin/win64"):
        d = game / sub
        if d.exists():
            for p in d.iterdir():
                if p.is_file() and GAME_BINARIES.match(p.name):
                    targets.append(p)
    targets = sorted(set(targets), key=lambda p: -p.stat().st_size)
    print(f"[i] 扫描目标 {len(targets)} 个游戏二进制，合计 "
          f"{sum(p.stat().st_size for p in targets)/1024/1024:.0f} MB")
    for p in targets:
        print(f"      {p.name:32s} {p.stat().st_size/1024/1024:6.1f} MB")

    all_hits = Counter()
    origins = defaultdict(set)
    t0 = time.time()
    from concurrent.futures import ThreadPoolExecutor, as_completed

    def work(p):
        hits, err = scan_file(p)
        return p, hits, err

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = [ex.submit(work, p) for p in targets]
        done = 0
        for fut in as_completed(futs):
            p, hits, err = fut.result()
            done += 1
            for k, v in hits.items():
                all_hits[k] += v
                origins[k].add(p.name)
            if done % 20 == 0 or done == len(targets):
                print(f"    {done}/{len(targets)} 文件，累计候选 {len(all_hits)} 个"
                      f"（{time.time()-t0:.0f}s）")

    # 按命中次数过滤
    names = {k: v for k, v in all_hits.items() if v >= args.min_hits}
    print(f"[i] 共挖出候选 {len(names)} 个（>= {args.min_hits} 次命中）")

    # 与现有指令库对比
    db_path = DATA / "commands.json"
    db_names = set()
    if db_path.exists():
        db = json.loads(db_path.read_text(encoding="utf-8"))
        db_names = {e["n"] for e in db["entries"]}
    new_names = sorted(n for n in names if n not in db_names)

    out = {
        "scanned_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "game_dir": str(game),
        "files_scanned": len(targets),
        "candidates": len(names),
        "in_db": len([n for n in names if n in db_names]),
        "not_in_db": len(new_names),
        "names": {n: {"hits": names[n], "files": sorted(origins[n])[:4],
                      "in_db": n in db_names}
                  for n in sorted(names, key=lambda x: -names[x])},
        "not_in_db": new_names,
    }
    (DATA / "game_scan.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    (DATA / "game_names.txt").write_text("\n".join(sorted(names)), encoding="utf-8")

    print(f"[OK] 写入 data/game_scan.json")
    print(f"     现有库已收录 {out['in_db']} 个；库里没有的 {out['not_in_db']} 个")
    print("\n     库里没有的候选（前 40，按命中次数排序）：")
    for n in sorted(new_names, key=lambda x: -names[x])[:40]:
        print(f"       {n:44s} hits={names[n]:<4} {','.join(sorted(origins[n])[:2])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
