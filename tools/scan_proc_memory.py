# -*- coding: utf-8 -*-
"""尝试从 CS2 / VConsole2 进程内存里直接捞 cvarlist 文本。

思路：cvarlist 的输出字符串是格式化后写入控制台缓冲区的，格式固定为
    "%-80s : %-16s : %-32s : %s"
所以内存里会出现大量形如
    "sv_cheats                 : false            : nf, rep, release   : Allow cheats on server"
的连续 ASCII 块。只要能读到进程内存（ReadProcessMemory），就能整段抽出来，
彻底省掉手工粘贴。

只用标准库 + ctypes。需要管理员权限（SeDebugPrivilege）才能读 Steam 启动的游戏进程。
"""
import ctypes
import re
import sys
from ctypes import wintypes
from pathlib import Path

k32 = ctypes.WinDLL("kernel32", use_last_error=True)

PROCESS_QUERY_INFORMATION = 0x0400
PROCESS_VM_READ = 0x0010

MEM_COMMIT = 0x1000
PAGE_READABLE = {0x02, 0x04, 0x20, 0x40}  # RO, RW, EXEC_R, EXEC_RW
PAGE_GUARD = 0x100
PAGE_NOACCESS = 0x01


class MEMORY_BASIC_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("BaseAddress", ctypes.c_void_p),
        ("AllocationBase", ctypes.c_void_p),
        ("AllocationProtect", wintypes.DWORD),
        ("RegionSize", ctypes.c_size_t),
        ("State", wintypes.DWORD),
        ("Protect", wintypes.DWORD),
        ("Type", wintypes.DWORD),
    ]


k32.OpenProcess.restype = wintypes.HANDLE
k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
k32.VirtualQueryEx.restype = ctypes.c_size_t
k32.VirtualQueryEx.argtypes = [wintypes.HANDLE, ctypes.c_void_p,
                               ctypes.POINTER(MEMORY_BASIC_INFORMATION), ctypes.c_size_t]
k32.ReadProcessMemory.restype = wintypes.BOOL
k32.ReadProcessMemory.argtypes = [wintypes.HANDLE, ctypes.c_void_p, ctypes.c_void_p,
                                  ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]

# 一行 cvarlist 记录（必须整行匹配，避免把上一行行尾字母吞进来）：
#   名称 左对齐补空格 : 默认值/cmd : 权限标记 : 说明
LINE_RE = re.compile(
    rb"^([A-Za-z_+][A-Za-z0-9_+]{1,60})[ \t]+"
    rb":[ \t]*([^:\r\n]{0,60}?)[ \t]*"
    rb":[ \t]*([a-z_, \t]{0,60}?)[ \t]*"
    rb":[ \t]?([\x20-\x7e]{0,400})$")
# 允许的最大行宽（cvarlist 单行不会超过这个长度）
MAX_LINE = 512


def enable_debug_privilege():
    adv = ctypes.WinDLL("advapi32", use_last_error=True)
    tok = wintypes.HANDLE()
    if not adv.OpenProcessToken(k32.GetCurrentProcess(), 0x0020 | 0x0008, ctypes.byref(tok)):
        return False
    class LUID(ctypes.Structure):
        _fields_ = [("LowPart", wintypes.DWORD), ("HighPart", wintypes.LONG)]
    class LUID_AND_ATTRIBUTES(ctypes.Structure):
        _fields_ = [("Luid", LUID), ("Attributes", wintypes.DWORD)]
    class TOKEN_PRIVILEGES(ctypes.Structure):
        _fields_ = [("PrivilegeCount", wintypes.DWORD), ("Privileges", LUID_AND_ATTRIBUTES * 1)]
    tp = TOKEN_PRIVILEGES()
    tp.PrivilegeCount = 1
    if not adv.LookupPrivilegeValueW(None, "SeDebugPrivilege", ctypes.byref(tp.Privileges[0].Luid)):
        return False
    tp.Privileges[0].Attributes = 0x00000002  # SE_PRIVILEGE_ENABLED
    return bool(adv.AdjustTokenPrivileges(tok, False, ctypes.byref(tp), 0, None, None))


def pids_of(name):
    import subprocess
    try:
        out = subprocess.run(["tasklist", "/FI", f"IMAGENAME eq {name}", "/FO", "CSV", "/NH"],
                             capture_output=True, text=True, timeout=20).stdout
    except Exception:
        return []
    pids = []
    for line in out.splitlines():
        parts = [p.strip('"') for p in line.split('","')]
        if len(parts) >= 2 and parts[1].isdigit():
            pids.append(int(parts[1]))
    return pids


def parse_blob(blob, hits, min_run=6):
    """按行严格解析：只有整行符合 cvarlist 格式的才收，且要求连续成段。

    直接对每行做 fullmatch 可以彻底避免"上一行行尾字母被吞进下一行名字"的污染。
    """
    run = 0
    for raw in blob.split(b"\n"):
        line = raw.rstrip(b"\r")
        if len(line) > MAX_LINE:
            run = 0
            continue
        m = LINE_RE.match(line)
        if not m:
            run = 0
            continue
        name = m.group(1).decode("ascii")
        val = m.group(2).strip()
        flags = m.group(3).strip()
        desc = m.group(4).strip()
        # 至少要像一条真实记录：有权限标记，或者有说明
        if not flags and not desc and val.lower() != b"cmd":
            run = 0
            continue
        run += 1
        if run < min_run:
            continue
        if name not in hits:
            hits[name] = line.decode("latin-1")
    return hits


def scan_pid(pid, min_run=6):
    h = k32.OpenProcess(PROCESS_QUERY_INFORMATION | PROCESS_VM_READ, False, pid)
    if not h:
        return None, f"OpenProcess 失败 (err={ctypes.get_last_error()})"
    hits = {}
    mbi = MEMORY_BASIC_INFORMATION()
    addr = 0
    buf = ctypes.create_string_buffer(1 << 20)
    read = ctypes.c_size_t()
    while k32.VirtualQueryEx(h, ctypes.c_void_p(addr), ctypes.byref(mbi), ctypes.sizeof(mbi)):
        base = mbi.BaseAddress or 0
        size = mbi.RegionSize
        nxt = base + size
        if (mbi.State == MEM_COMMIT and mbi.Protect in PAGE_READABLE
                and not (mbi.Protect & PAGE_GUARD)):
            off = 0
            carry = b""
            while off < size:
                chunk = min(1 << 20, size - off)
                ok = k32.ReadProcessMemory(h, ctypes.c_void_p(base + off), buf, chunk,
                                           ctypes.byref(read))
                if ok and read.value:
                    blob = carry + buf.raw[:read.value]
                    # 最后一行可能被截断，留到下一段拼接
                    nl = blob.rfind(b"\n")
                    if nl >= 0:
                        parse_blob(blob[:nl], hits, min_run)
                        carry = blob[nl + 1:]
                    else:
                        carry = blob
                else:
                    carry = b""
                off += chunk
            if carry:
                parse_blob(carry, hits, min_run)
        if nxt <= addr:
            break
        addr = nxt
    k32.CloseHandle(h)
    return hits, None


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-run", type=int, default=6,
                    help="要求多少行连续成段才算真实输出块（默认 6）")
    args = ap.parse_args()
    ok = enable_debug_privilege()
    print(f"[i] SeDebugPrivilege: {'已启用' if ok else '未启用（可能读不了游戏进程）'}")
    targets = []
    for exe in ("cs2.exe", "vconsole2.exe"):
        for pid in pids_of(exe):
            targets.append((exe, pid))
    if not targets:
        print("[!] 没找到 cs2.exe / vconsole2.exe 进程")
        return 1
    best = {}
    for exe, pid in targets:
        print(f"[i] 扫描 {exe} PID {pid} ...")
        hits, err = scan_pid(pid, min_run=args.min_run)
        if err:
            print(f"    {err}")
            continue
        print(f"    命中 {len(hits)} 行 cvarlist 记录")
        if len(hits) > len(best):
            best = hits
    if not best:
        print("[!] 内存里没找到 cvarlist 输出块（可能还没执行过 cvarlist）")
        return 1
    out = Path(__file__).resolve().parent.parent / "_dumps" / "cs2_cvarlist_mem.txt"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(best[k] for k in sorted(best)) + "\n", encoding="utf-8")
    # 自检：名字里出现大写（除 CS_/Test_ 等已知）通常说明有污染
    bad = [n for n in best if any(c.isupper() for c in n) and not n.startswith(("CS_", "Test_"))]
    print(f"[OK] {len(best)} 条 -> {out}")
    print(f"[i] 可疑名字 {len(bad)} 条" + (f"：{bad[:12]}" if bad else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
