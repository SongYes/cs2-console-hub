# -*- coding: utf-8 -*-
"""诊断：内存里到底有多少 cvarlist 行、缺的都是哪些。

不做"连续成段"要求，只统计整行匹配的行数与名字集合，
再和用户在会话里给出的权威总表（_dumps/cs2_cvarlist_ref_names.txt，可选）对比。
"""
import ctypes
import json
import re
import sys
from ctypes import wintypes
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import scan_proc_memory as S  # noqa: E402

# 宽鬆：行首到第一个 ' : ' 之间的全部当名字（允许大写/粘连），
# 但后面必须还有第二个 ' : '（值 : 权限），这样才像一行 cvarlist。
LOOSE = re.compile(rb"^([\x21-\x7e]{2,70}?)[ \t]*:[ \t]*([^:\r\n]{0,60}?)[ \t]*:[ \t]*([^\r\n]{0,400})$")


def collect(pid):
    h = S.k32.OpenProcess(S.PROCESS_QUERY_INFORMATION | S.PROCESS_VM_READ, False, pid)
    if not h:
        return None
    names, lines = set(), 0
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
                if S.k32.ReadProcessMemory(h, ctypes.c_void_p(base + off), buf, chunk, ctypes.byref(read)) and read.value:
                    blob = carry + buf.raw[:read.value]
                    nl = blob.rfind(b"\n")
                    if nl >= 0:
                        for ln in blob[:nl].split(b"\n"):
                            ln = ln.rstrip(b"\r")
                            if len(ln) > S.MAX_LINE:
                                continue
                            m = LOOSE.match(ln)
                            if m:
                                names.add(m.group(1).decode("ascii"))
                                lines += 1
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
    return names, lines


def main():
    S.enable_debug_privilege()
    allnames = set()
    total = 0
    for exe in ("cs2.exe", "vconsole2.exe"):
        for pid in S.pids_of(exe):
            r = collect(pid)
            if not r:
                print(f"[!] {exe} PID {pid} 打不开")
                continue
            names, lines = r
            print(f"[i] {exe} PID {pid}: 宽松匹配 {lines} 行 / {len(names)} 个名字")
            allnames |= names
            total += lines
    print(f"[i] 合计不同名字 {len(allnames)}")
    ref = ROOT / "_dumps" / "cs2_cvarlist_ref_names.txt"
    if ref.exists():
        want = set(x.strip() for x in ref.read_text(encoding="utf-8").splitlines() if x.strip())
        miss = sorted(want - allnames)
        print(f"[i] 参考表 {len(want)} 个名字，内存里没有 {len(miss)} 个")
        print("    缺失示例:", miss[:30])
        (ROOT / "_dumps" / "cs2_missing_from_mem.txt").write_text("\n".join(miss) + "\n", encoding="utf-8")
    out = ROOT / "_dumps" / "cs2_mem_names.txt"
    out.write_text("\n".join(sorted(allnames)) + "\n", encoding="utf-8")
    print(f"[OK] 名字全集 -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
