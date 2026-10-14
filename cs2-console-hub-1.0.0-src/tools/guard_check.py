# -*- coding: utf-8 -*-
"""CS2 实验操作「上锁检查器」——在进联机服务器之前，先确认机器处于干净状态。

背景（先纠正一个常见误解）：
  VAC 主要靠**签名扫描**抓三类东西：
    1. 绕过 / 篡改 Steam 平台完整性（改 steamclient、劫持 Steam API、DLL 注入进游戏进程）
    2. 运行时内存篡改、未经授权的第三方注入
    3. 被 VAC 保护的模块被改动
  **改素材（天空盒 / 模型 / 贴图 / 枪械外观）本身通常不是 VAC 的直接触发点**，
  但它会让你进入"非受信环境"，一旦再叠加注入类工具就很容易踩线。
  所以真正有效的防护是**把实验环境和受保护环境隔开**，而不是"小心一点"。

这个脚本的判据是「相对于干净基线的变化」，不是「最近改动过」——
否则 Steam 每次更新游戏都会误报（本机 vpk 是 Steam 官方更新改的，不是实验改的）。

用法：
  python tools/guard_check.py --baseline      # 确认干净后，记下基线（关键一步）
  python tools/guard_check.py                 # 与基线比对，给出能否进服的结论
  python tools/guard_check.py --modules       # 额外检查游戏进程里的注入模块
  python tools/guard_check.py --json          # 机器可读
"""
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASELINE = ROOT / "data" / "integrity_baseline.json"

STEAM = Path(r"C:\Program Files (x86)\Steam")
GAME_CANDIDATES = [
    STEAM / "steamapps" / "common" / "Counter-Strike Global Offensive",
    Path(r"D:\Steam\steamapps\common\Counter-Strike Global Offensive"),
    Path(r"E:\Steam\steamapps\common\Counter-Strike Global Offensive"),
]
GAME = next((p for p in GAME_CANDIDATES if p.exists()), None)

# 会被"改素材"动到的可执行/完整性文件类型
SENSITIVE_EXT = {".vpk", ".dll", ".exe", ".so", ".dylib", ".asi"}
# Valve 自己的目录：这些位置有 dll/exe 是正常的
VENDOR_DIRS = ("game/bin/win64", "game/csgo/bin/win64", "game/csgo/bin/legacy", "bin/win64")
# 正常动态产物，不入基线（游戏自己会反复写）
NOISE_PATTERNS = (
    r"\\_iconcache\\", r"\\logs?\\", r"\\console\.log$", r"\\core\.vdf$",
    r"\\serverconfig\.vdf$", r"\\installscript\.vdf$", r"\\pwa_", r"\\_dumps\\",
    r"\\steamapps\\downloading\\", r"\.tmp$", r"\\shadercache\\",
    r"\\csgo\\cfg\\", r"\\csgo\\overrides\\", r"\\demoheaders?\\",
)
OUR_ARTIFACT = re.compile(r"\\(cs2hub|dump_commands|verify_gap|condump|cs2_cvarlist)", re.I)
SUSPICIOUS_NAME = re.compile(
    r"(cheat|hack|inject|loader|esp|aimbot|wallhack|triggerbot|bypass|unlock|"
    r"dllinject|hook|trainer|frida)", re.I)


def is_noise(rel: str) -> bool:
    low = rel.lower().replace("/", "\\")
    return any(re.search(p, low, re.I) for p in NOISE_PATTERNS)


def quick_hash(path: Path, size: int) -> str:
    """文件太大就头尾+中间取样哈希（vpk 动辄上百 MB，全量哈希太慢）。"""
    h = hashlib.sha256()
    h.update(str(size).encode())
    try:
        with path.open("rb") as f:
            h.update(f.read(1 << 16))
            if size > (3 << 16):
                for pos in (size // 2, max(0, size - (1 << 16))):
                    f.seek(pos)
                    h.update(f.read(1 << 16))
    except OSError:
        return "unreadable"
    return h.hexdigest()[:20]


def snapshot():
    files = {}
    if not GAME:
        return files
    for root, dirs, names in os.walk(GAME):
        dirs[:] = [d for d in dirs if d.lower() not in ("downloading", "shadercache")]
        for fn in names:
            full = Path(root) / fn
            rel = str(full.relative_to(GAME))
            if is_noise(rel):
                continue
            ext = full.suffix.lower()
            if ext not in SENSITIVE_EXT:
                continue
            try:
                st = full.stat()
            except OSError:
                continue
            files[rel] = {"size": st.st_size, "mtime": int(st.st_mtime),
                          "hash": quick_hash(full, st.st_size)}
    return files


def cmdline_of(name="cs2.exe"):
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             f"(Get-CimInstance Win32_Process -Filter \"Name='{name}'\" | "
             f"Select-Object -First 1 -ExpandProperty CommandLine)"],
            capture_output=True, text=True, timeout=30)
        return (out.stdout or "").strip()
    except Exception as e:
        return f"<读取失败: {e}>"


def injected_modules():
    sysdir = (os.environ.get("SystemRoot") or r"C:\Windows").lower()
    procs, bad = [], []
    for name in ("cs2", "vconsole2"):
        try:
            out = subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 f"Get-Process -Name '{name}' -ErrorAction SilentlyContinue | "
                 f"Select-Object -ExpandProperty Modules | "
                 f"Select-Object -ExpandProperty FileName"],
                capture_output=True, text=True, timeout=60)
        except Exception:
            continue
        mods = [m.strip() for m in (out.stdout or "").splitlines() if m.strip()]
        if mods:
            procs.append({"name": name, "modules": len(mods)})
        for m in mods:
            low = m.lower()
            if sysdir in low or "counter-strike" in low or "steam" in low:
                continue
            if "directx" in low or "vc_redist" in low or "windows" in low:
                continue
            if low.endswith(".dll"):
                bad.append({"process": name, "module": m})
    return {"processes": procs, "suspicious": bad}


def rogue_executables(files):
    out = []
    for rel, meta in files.items():
        ext = Path(rel).suffix.lower()
        if ext not in (".dll", ".exe", ".asi"):
            continue
        norm = rel.lower().replace("\\", "/")
        if not any(norm.startswith(v) for v in VENDOR_DIRS):
            out.append({"path": rel, "size": meta["size"],
                        "why": "不在 Valve 目录里的可执行文件"})
        elif SUSPICIOUS_NAME.search(Path(rel).name):
            out.append({"path": rel, "size": meta["size"], "why": "文件名像注入工具"})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--baseline", action="store_true", help="当前状态记为干净基线")
    ap.add_argument("--modules", action="store_true", help="检查进程注入模块（较慢）")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--only-changes", action="store_true", help="只打印有变化的文件")
    args = ap.parse_args()

    if not GAME:
        print("[!] 没找到 CS2 安装目录，请改 GAME_CANDIDATES")
        return 1

    print(f"[i] 扫描 {GAME} …")
    cur = snapshot()
    print(f"[i] 纳入完整性范围的敏感文件: {len(cur)} 个"
          f"（vpk / dll / exe / asi，已排除日志与动态缓存）")

    if args.baseline:
        BASELINE.parent.mkdir(parents=True, exist_ok=True)
        BASELINE.write_text(json.dumps({
            "created_at": datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S"),
            "game_dir": str(GAME),
            "note": "干净基线：只有在确认没有做任何非法改动时才重建它",
            "files": cur,
        }, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        print(f"[OK] 基线已写入 {BASELINE}")
        print("     之后跑 guard_check.py（不带 --baseline）就会与这份基线比对。")
        return 0

    old = {}
    if BASELINE.exists():
        try:
            old = json.loads(BASELINE.read_text(encoding="utf-8")).get("files", {})
        except Exception:
            old = {}
    changed = [rel for rel, m in cur.items() if rel in old and old[rel]["hash"] != m["hash"]]
    added = [rel for rel in cur if rel not in old]
    removed = [rel for rel in old if rel not in cur]
    rogue = rogue_executables(cur)
    mods = injected_modules() if args.modules else {"processes": [], "suspicious": []}
    cmd = cmdline_of()

    report = {
        "time": datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S"),
        "game_dir": str(GAME), "baseline": str(BASELINE) if old else None,
        "scanned": len(cur), "changed": sorted(changed), "added": sorted(added),
        "removed": sorted(removed), "rogue_executables": rogue,
        "injected": mods, "cs2_cmdline": cmd,
    }
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    print()
    print(f"[1] 与基线不一致的敏感文件: {len(changed)}")
    for rel in sorted(changed)[:30]:
        print(f"    ⚠ {rel}")
    if not changed:
        print("    ✅ 没有：素材与二进制与基线一致")
    print(f"[2] 基线里没有、现在多出来的: {len(added)}")
    for rel in sorted(added)[:30]:
        print(f"    ⚠ {rel}")
    if not added:
        print("    ✅ 没有")
    print(f"[3] 基线里有、现在不见了的: {len(removed)}")
    for rel in sorted(removed)[:20]:
        print(f"    ⚠ {rel}")
    if not removed:
        print("    ✅ 没有")

    print(f"\n[4] 可疑可执行文件: {len(rogue)}")
    for r in rogue[:20]:
        print(f"    ⚠ {r['path']}  ({r['size']}B, {r['why']})")
    if not rogue:
        print("    ✅ 干净：所有 dll/exe 都在 Valve 自己的目录里")

    if args.modules:
        print(f"\n[5] 进程模块检查")
        if not mods["processes"]:
            print("    （游戏未运行）")
        else:
            for p in mods["processes"]:
                print(f"    {p['name']}.exe: {p['modules']} 个模块")
            if mods["suspicious"]:
                for s in mods["suspicious"]:
                    print(f"    ⚠ {s['process']} 挂着非系统非 Steam 模块: {s['module']}")
            else:
                print("    ✅ 没有第三方注入模块")

    print(f"\n[6] 当前 CS2 命令行")
    print(f"    {cmd or '（游戏未运行）'}")
    if cmd and "cs2.exe" not in cmd and "读取失败" not in cmd:
        pass
    elif cmd and "-insecure" in cmd.lower():
        print("    ✅ 带 -insecure：不会连接受 VAC 保护的服务器")
    elif cmd:
        print("    ⚠ 没有 -insecure：正常模式，进官方服会走 VAC 校验")

    print("\n" + "=" * 60)
    if not old:
        print("结论：还没有基线。请先确认机器干净，然后执行：")
        print("      python tools\\guard_check.py --baseline")
    else:
        problems = []
        if changed:
            problems.append(f"{len(changed)} 个敏感文件与基线不符")
        if added:
            problems.append(f"{len(added)} 个新增可疑文件")
        if rogue:
            problems.append(f"{len(rogue)} 个可疑可执行文件")
        if mods["suspicious"]:
            problems.append(f"{len(mods['suspicious'])} 个注入模块")
        if problems:
            print("结论：⚠ 当前不适合进受保护服务器")
            print("      问题：" + "、".join(problems))
            print("      修法：Steam → CS2 → 属性 → 已安装文件 → 验证游戏文件完整性")
            print("      或者启动选项加 -insecure（只玩本地 / 社区服 / demo，不进官方竞技）")
        else:
            print("结论：✅ 与基线一致，可以正常进服")
            print("      进官方服时启动选项不要带 -insecure")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
