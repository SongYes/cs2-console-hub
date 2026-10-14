# -*- coding: utf-8 -*-
"""从 CS2 / VConsole2 进程内存实时抓取 cvarlist 输出，增量合并，永久累积。

为什么需要它：游戏控制台缓冲区是环形的，`cvarlist` 打完一次后前面的行会
被后续输出挤掉，所以"事后一次性读内存"永远读不全。本脚本改成：

    * 每次运行都重新扫描内存
    * 把扫到的名字行**按名字**合并进 _dumps/cs2_cvarlist_mem.txt（已有行不覆盖）
    * 因此反复执行（每次在游戏里敲一遍 cvarlist）就能逐步补齐全部约 2802 条

用法：
  python tools/scrape_cvarlist.py            # 扫一次并合并
  python tools/scrape_cvarlist.py --status   # 只看当前累积了多少条
"""
import argparse
import ctypes
import re
import sys
from ctypes import wintypes
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import scan_proc_memory as S  # noqa: E402

ACC = ROOT / "_dumps" / "cs2_cvarlist_mem.txt"
# 允许行首粘连（上一行尾巴）但必须是 "名字+值+权限" 三段式
LOOSE = re.compile(
    rb"^([\x21-\x7e]{2,80}?)[ \t]+:[ \t]*([^:\r\n]{0,60}?)[ \t]*:[ \t]*([a-z_, \t]{0,60}?)[ \t]*:[ \t]?([\x20-\x7e]{0,400})$")


def scan_lines(pid):
    h = S.k32.OpenProcess(S.PROCESS_QUERY_INFORMATION | S.PROCESS_VM_READ, False, pid)
    if not h:
        return None
    found = {}
    mbi = S.MEMORY_BASIC_INFORMATION()
    addr = 0
    buf = ctypes.create_string_buffer(1 << 20)
    read = ctypes.c_size_t()
    while S.k32.VirtualQueryEx(h, ctypes.c_void_p(addr), ctypes.byref(mbi), ctypes.sizeof(mbi)):
        base, size = mbi.BaseAddress or 0, mbi.RegionSize
        nxt = base + size
        if mbi.State == S.MEM_COMMIT and mbi.Protect in S.PAGE_READABLE and not (mbi.Protect & S.PAGE_GUARD):
            off, carry = 0, b""
            while off < size:
                chunk = min(1 << 20, size - off)
                if S.k32.ReadProcessMemory(h, ctypes.c_void_p(base + off), buf, chunk,
                                           ctypes.byref(read)) and read.value:
                    blob = carry + buf.raw[:read.value]
                    nl = blob.rfind(b"\n")
                    if nl >= 0:
                        for ln in blob[:nl].split(b"\n"):
                            ln = ln.rstrip(b"\r")
                            if len(ln) > 600:
                                continue
                            m = LOOSE.match(ln)
                            if not m:
                                continue
                            name = m.group(1).decode("latin-1").strip()
                            flags = m.group(3).decode("latin-1").strip()
                            val = m.group(2).decode("latin-1").strip()
                            if not flags and val.lower() != "cmd":
                                continue          # 三要素缺一，多半是别的日志行
                            if name not in found or len(ln) > len(found[name][1]):
                                found[name] = (flags, ln.decode("latin-1"))
                        carry = blob[nl + 1:]
                    else:
                        carry = blob
                else:
                    carry = b""
                off += chunk
        if nxt <= addr:
            break
        addr = nxt
    S.k32.CloseHandle(h)
    return found


def load_acc():
    if not ACC.exists():
        return {}
    out = {}
    for raw in ACC.read_text(encoding="utf-8", errors="replace").splitlines():
        if not raw.strip():
            continue
        m = LOOSE.match(raw.encode("latin-1", "replace"))
        if m:
            out[m.group(1).decode("latin-1").strip()] = raw
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--status", action="store_true", help="只显示当前累积量")
    args = ap.parse_args()

    acc = load_acc()
    if args.status:
        print(f"[i] 已累积 {len(acc)} 条 -> {ACC.name}")
        return 0

    S.enable_debug_privilege()
    pids = [(e, p) for e in ("cs2.exe", "vconsole2.exe") for p in S.pids_of(e)]
    if not pids:
        print("[!] 没找到 cs2.exe / vconsole2.exe 进程")
        return 1
    fresh = {}
    for exe, pid in pids:
        r = scan_lines(pid)
        if r is None:
            print(f"[!] {exe} PID {pid} 打不开（可能需要管理员权限）")
            continue
        print(f"[i] {exe} PID {pid}: 扫到 {len(r)} 行")
        for k, (flags, line) in r.items():
            if k not in fresh or len(line) > len(fresh[k][1]):
                fresh[k] = (flags, line)
    if not fresh:
        print("[!] 这次没扫到任何 cvarlist 行（先在游戏里敲一遍 cvarlist 再跑）")
        return 1

    added = 0
    for k, (flags, line) in fresh.items():
        if k not in acc:
            acc[k] = line
            added += 1
    ACC.parent.mkdir(parents=True, exist_ok=True)
    ACC.write_text("\n".join(acc[k] for k in sorted(acc)) + "\n", encoding="utf-8")
    print(f"[i] 本次新增 {added} 条")
    print(f"[i] 累计 {len(acc)} 条 -> {ACC}")
    left = 2802 - len(acc)
    if left > 0:
        print(f"[i] 距离游戏报告的 2802 条还差约 {left} 条：")
        print("    在 VConsole2 里再敲一遍 cvarlist，然后重跑本脚本（可反复累积到齐）")
    else:
        print("[OK] 已凑齐 2802 条，可以跑 tools\\clean_mem_dump.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
