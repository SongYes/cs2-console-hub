# -*- coding: utf-8 -*-
"""从 exe 里提取图标，核对嵌入的是不是新图标。

只做一件事：读 PE 资源段里的 RT_GROUP_ICON / RT_ICON，导出最大那档 PNG，
再统计蓝底与白字占比，判断是不是「蓝底 + 白色 >_」的新图标。

用法： python tools/read_exe_icon.py "<exe 路径>" [输出 png]
"""
import io
import struct
import sys
from pathlib import Path

from PIL import Image


def parse_pe_resources(data: bytes):
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    if data[pe:pe + 4] != b"PE\0\0":
        raise ValueError("不是 PE 文件")
    nsec = struct.unpack_from("<H", data, pe + 6)[0]
    optsz = struct.unpack_from("<H", data, pe + 20)[0]
    magic = struct.unpack_from("<H", data, pe + 24)[0]
    pe32p = magic == 0x20B
    ddoff = pe + 24 + (112 if pe32p else 96)
    rva_rsrc, _ = struct.unpack_from("<II", data, ddoff + 2 * 8)

    secs = []
    sso = pe + 24 + optsz
    for i in range(nsec):
        o = sso + i * 40
        vsz, va, rsz, ra = struct.unpack_from("<IIII", data, o + 8)
        secs.append((va, max(vsz, rsz), ra))

    def r2o(rva: int) -> int:
        """RVA → 文件偏移。"""
        for va, span, ra in secs:
            if va <= rva < va + span:
                return ra + (rva - va)
        raise ValueError(f"RVA 0x{rva:x} 不在任何段内")

    # 资源目录树：第 1 层=类型，第 2 层=资源 ID，第 3 层=语言 → 数据入口。
    # 每个 IMAGE_RESOURCE_DIRECTORY_ENTRY 的 OffsetToDirectory/OffsetToData
    # 都是「相对资源目录起点」的偏移，需加 rva_rsrc。
    # 注意：判断「是不是子目录」要看**该条目自己**的最高位（0x80000000），
    # 不能拿高位被 ID 占用的值去判断（我们踩过这个坑：0x128 被误判成目录）。
    def dirents(dir_rva: int):
        off = r2o(dir_rva)
        nn, ni = struct.unpack_from("<HH", data, off + 12)
        out = []
        for i in range(nn + ni):
            eo = off + 16 + i * 8
            nid, ofs = struct.unpack_from("<II", data, eo)
            is_dir = bool(ofs & 0x80000000)
            out.append((nid & 0xFFFF, rva_rsrc + (ofs & 0x7FFFFFFF), is_dir))
        return out

    def load_icon(data_entry_rva: int) -> bytes:
        off = r2o(data_entry_rva)
        otd, dsz = struct.unpack_from("<II", data, off)   # OffsetToData(RVA), Size
        do = r2o(otd)
        return data[do:do + dsz]

    def leaf_entries(dir_rva: int):
        """取某类型目录下每个资源 ID 的**唯一**数据入口。

        结构：类型目录 → [资源 ID 子目录] → [语言 数据入口]。
        只能往下钻一层并取第一个语言项，否则会把同一条资源重复计很多次。
        """
        out = []
        for rid, child_rva, is_dir in dirents(dir_rva):
            if is_dir:
                sub = dirents(child_rva)
                if sub:
                    _lid, data_rva, ldir = sub[0]
                    if not ldir:
                        out.append((rid, data_rva))
            else:
                out.append((rid, child_rva))
        return out

    groups, icon_ids = [], []
    for tid, child_rva, is_dir in dirents(rva_rsrc):
        if not is_dir:
            continue
        if tid == 14:                       # RT_GROUP_ICON
            groups.append(child_rva)
        elif tid == 3:                      # RT_ICON
            icon_ids.extend(leaf_entries(child_rva))

    frames = {rid: load_icon(rva) for rid, rva in icon_ids}

    out = []
    for g_rva in groups:
        for _rid, goff_rva in leaf_entries(g_rva):
            o = r2o(goff_rva)
            cnt = struct.unpack_from("<H", data, o + 4)[0]
            for i in range(cnt):
                eo = o + 6 + i * 14
                w, h, _cc, _r, _p, bits, sz, iid = struct.unpack_from("<BBBBHHIH", data, eo)
                out.append({"dim": w if w else 256, "bits": bits, "size": sz,
                            "id": iid, "blob": frames.get(iid)})
    return out


def main():
    exe = Path(sys.argv[1])
    out_png = Path(sys.argv[2]) if len(sys.argv) > 2 else None
    data = exe.read_bytes()
    items = parse_pe_resources(data)
    print(f"  {exe.name}")
    print(f"  RT_GROUP_ICON 共 {len(items)} 档：")
    for it in sorted(items, key=lambda x: x["dim"]):
        print(f"    {it['dim']:>3}x{it['dim']:<3} {it['bits']:>2}bpp  {it['size']:>7} B  id={it['id']}")

    # 取中等偏大的一档来看清字形
    cand = [it for it in items if it["blob"] and it["dim"] >= 64]
    if not cand:
        print("  ! 没有 ≥64px 的帧可检查")
        return 1
    pick = min(cand, key=lambda x: x["dim"])
    im = Image.open(io.BytesIO(pick["blob"])).convert("RGBA")
    w, h = im.size
    px = im.load()
    white = sum(1 for y in range(h) for x in range(w)
                if px[x, y][3] > 160 and min(px[x, y][:3]) > 190)
    blue = sum(1 for y in range(h) for x in range(w)
               if px[x, y][3] > 160 and px[x, y][2] > px[x, y][0] + 60)
    tot = w * h
    print(f"\n  取 {w}px 档分析：")
    print(f"    蓝底 {blue / tot * 100:5.1f}%    白字 {white / tot * 100:5.2f}%")
    core = px[w // 2, h // 2 - int(h * 0.28)]     # 蓝底处（中心偏上）
    print(f"    采样底色 rgba{core}")
    ok = (blue / tot) > 0.55 and 0.03 < (white / tot) < 0.20 \
        and abs(core[0] - 47) < 16 and abs(core[1] - 111) < 16 and abs(core[2] - 237) < 16
    print("    " + ("✓ exe 内嵌的就是新图标（#2f6fed 蓝底 + 白色 >_）"
                    if ok else "✗ 与预期不符"))
    if out_png:
        out_png.parent.mkdir(parents=True, exist_ok=True)
        im.save(out_png)
        print(f"    已导出 {out_png.name}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
