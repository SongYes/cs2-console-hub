# -*- coding: utf-8 -*-
"""CS2 控制台指令查询中心 —— 图标生成器

设计：
  深色战术底 + 琥珀色终端提示符「>_」+ 圆环准星刻度（CS2 的视觉隐喻）
  配色锚定应用界面本身的色板：#f0a92b 琥珀 / #0d1117 石墨

产出（assets/icons/）：
  icon.svg            主图标矢量版
  icon-flat.svg       备选：无准星环的扁平版
  icon-1024.png       主图 PNG
  icon-256/128/64/48/32/16.png
  cs2-console-hub.ico 多尺寸 Windows 图标（16/20/24/32/40/48/64/128/256）
  sheet.png           尺寸阶梯预览（深色 + 浅色背景）
  sheet-concepts.png  两个方案的对比预览
"""
from io import BytesIO
from pathlib import Path

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets" / "icons"
OUT.mkdir(parents=True, exist_ok=True)

BASE = 1024          # 设计坐标系边长
SS = 4               # 超采样倍数
CANVAS = BASE * SS

AMBER = (240, 169, 43)
AMBER_HI = (255, 199, 92)
AMBER_DK = (196, 128, 18)
GLOW = (255, 176, 48)

FONT = "C:/Windows/Fonts/consolab.ttf"
ICON_SIZES = [256, 128, 64, 48, 40, 32, 24, 20, 16]


def d(v):
    """设计坐标 -> 超采样画布像素（仅供整幅 1024*SS 画布使用）"""
    return v * SS


# --------------------------------------------------------------------------- #
# 底：圆角方块 + 径向渐变 + 暖色氛围
# --------------------------------------------------------------------------- #

def _gradient(size, c_in, c_out, power=1.0):
    y, x = np.mgrid[0:size, 0:size].astype(np.float32)
    cx = cy = (size - 1) / 2.0
    r = np.sqrt((x - cx) ** 2 + (y - cy) ** 2) / (size * 0.62)
    r = np.clip(r, 0, 1) ** power
    a = np.array(c_in, dtype=np.float32)
    b = np.array(c_out, dtype=np.float32)
    rgb = a[None, None, :] * (1 - r)[..., None] + b[None, None, :] * r[..., None]
    return Image.fromarray(rgb.astype(np.uint8), "RGB")


def _mask_rounded(size, radius):
    m = Image.new("L", (size, size), 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, size - 1, size - 1], radius=radius, fill=255)
    return m


def _mask_superellipse(size, n=3.4, inset=0.09):
    """近似超椭圆的平滑光斑，用于中心氛围光。"""
    y, x = np.mgrid[0:size, 0:size].astype(np.float32)
    cx = cy = (size - 1) / 2.0
    half = size / 2.0 * (1 - inset)
    nx = np.abs(x - cx) / half
    ny = np.abs(y - cy) / half
    v = np.clip(1 - (nx ** n + ny ** n), 0, 1) ** 0.55
    return Image.fromarray((v * 255).astype(np.uint8), "L")


def render_base(size):
    """合成图标底板（返回 RGB 图，尺寸 size×size）。"""
    k = size / BASE
    # 渐变底
    base = _gradient(size, (30, 39, 54), (11, 15, 21), power=1.15).convert("RGBA")
    # 中心暖光
    glow = _mask_superellipse(size, n=3.2, inset=0.16).filter(
        ImageFilter.GaussianBlur(size * 0.055))
    warm = Image.new("RGBA", (size, size), GLOW + (0,))
    warm.putalpha(glow.point(lambda v: int(v * 0.30)))
    base = Image.alpha_composite(base, warm)
    # 底部压暗（做出体积感）
    shade = Image.new("L", (size, size), 0)
    sd = ImageDraw.Draw(shade)
    sd.ellipse([-size * 0.25, size * 0.55, size * 1.25, size * 1.6], fill=110)
    shade = shade.filter(ImageFilter.GaussianBlur(size * 0.06))
    dark = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    dark.putalpha(shade)
    base = Image.alpha_composite(base, dark)
    # 顶部高光
    shade2 = Image.new("L", (size, size), 0)
    ImageDraw.Draw(shade2).ellipse(
        [-size * 0.3, -size * 0.75, size * 1.3, size * 0.42], fill=64)
    shade2 = shade2.filter(ImageFilter.GaussianBlur(size * 0.05))
    light = Image.new("RGBA", (size, size), (255, 255, 255, 0))
    light.putalpha(shade2)
    base = Image.alpha_composite(base, light)
    return base


def shape_alpha(size, radius_ratio=0.222):
    """圆角方形裁切蒙版。"""
    return _mask_rounded(size, int(size * radius_ratio))


# --------------------------------------------------------------------------- #
# 笔画工具
# --------------------------------------------------------------------------- #

def _stroke_mask(size, paths, width, size_hint=None):
    """把一组折线路径渲染成描边蒙版（精确圆帽/圆角，无透明度叠加）。"""
    ss = 2
    big = size * ss
    k = big / BASE
    w = max(3, round(width * k))
    mask = Image.new("L", (big, big), 0)
    dr = ImageDraw.Draw(mask)
    for path in paths:
        pts = [(x * k, y * k) for x, y in path]
        dr.line(pts, fill=255, width=w, joint="curve")
        r = w / 2.0
        for px, py in pts:
            dr.ellipse([px - r, py - r, px + r, py + r], fill=255)
    return mask.resize((size, size), Image.LANCZOS)


def _arc_path(cx, cy, r, a0, a1, steps=96):
    import math
    return [(cx + r * math.cos(math.radians(a0 + (a1 - a0) * i / steps)),
             cy + r * math.sin(math.radians(a0 + (a1 - a0) * i / steps)))
            for i in range(steps + 1)]


def ring_paths():
    c = BASE / 2.0
    r = 326
    return [_arc_path(c, c, r, a0, a1) for a0, a1 in
            ((6, 84), (96, 174), (186, 264), (276, 354))]


def tick_paths(length=100, inner=446):
    c = BASE / 2.0
    lo = inner + length
    return [[(c + dx * inner, c + dy * inner), (c + dx * lo, c + dy * lo)]
            for dx, dy in ((-1, -1), (1, -1), (-1, 1), (1, 1))]


def draw_prompt(layer, size, width, color, alpha=255):
    """在 layer 上画「>_」提示符。

    几何以 1024 设计坐标系书写，按 size/1024 统一缩放（坐标与线宽同一比例），
    这样「渲染大图再缩小」与「直接渲染目标尺寸」得到完全一致的构图。
    """
    k = size / BASE
    dr = ImageDraw.Draw(layer)
    fill = color + (alpha,)
    w = max(2, round(width * k))
    # 折角符号 >
    dr.line([(322 * k, 408 * k), (468 * k, 512 * k), (322 * k, 616 * k)],
            fill=fill, width=w, joint="curve")
    # 下划线 _
    y = 648 * k
    dr.line([(556 * k, y), (734 * k, y)], fill=fill, width=w)
    return dr


def colorize(layer, color, alpha=255):
    """把蒙版层染成指定颜色（alpha 作为整体不透明度系数）。"""
    m = layer.getchannel("A")
    if alpha < 255:
        m = m.point(lambda v: int(v * alpha / 255.0))
    out = Image.new("RGBA", layer.size, color + (0,))
    out.putalpha(m)
    return out


def watermark(layer, size, wm, alpha=170, y=892):
    k = size / BASE
    font = ImageFont.truetype(FONT, max(6, round(96 * k)))
    tm = font.getbbox(wm)
    tw, th = tm[2] - tm[0], tm[3] - tm[1]
    x = (size - tw) / 2 - tm[0]
    yy = y * k - th / 2 - tm[1]
    ImageDraw.Draw(layer).text((x, yy), wm, font=font, fill=(255, 255, 255, alpha))


# --------------------------------------------------------------------------- #
# 两个方案
# --------------------------------------------------------------------------- #

def render_icon(size, variant="crosshair"):
    base = render_base(size)
    # 外描边
    edge = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    ImageDraw.Draw(edge).rounded_rectangle(
        [0, 0, size - 1, size - 1], radius=int(size * 0.222),
        outline=(255, 190, 90, 92), width=max(1, round(size / BASE * 7)))
    base = Image.alpha_composite(base, edge)

    if variant == "crosshair":
        # 准星：一层克制的柔光 + 清晰核心（每层只染一次色，避免叠加发亮）
        sm = ImageChops.lighter(_stroke_mask(size, ring_paths(), 92),
                                _stroke_mask(size, tick_paths(), 76))
        soft = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        soft.putalpha(sm.filter(ImageFilter.GaussianBlur(max(1, size * 0.007))))
        base = Image.alpha_composite(base, colorize(soft, AMBER, 58))

        cm = ImageChops.lighter(_stroke_mask(size, ring_paths(), 46),
                                _stroke_mask(size, tick_paths(), 38))
        ring = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        ring.putalpha(cm)
        base = Image.alpha_composite(base, colorize(ring, AMBER_HI, 246))

    # 提示符：先光晕，再暗描边，最后亮色核心
    def core(w, color, alpha):
        lay = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw_prompt(lay, size, w, color, alpha)
        return lay

    halo = core(150, GLOW, 82).filter(ImageFilter.GaussianBlur(max(1, size * 0.024)))
    base = Image.alpha_composite(base, halo)
    base = Image.alpha_composite(base, core(116, (6, 9, 13), 190))
    base = Image.alpha_composite(base, core(66, AMBER, 255))
    base = Image.alpha_composite(base, core(22, AMBER_HI, 235))

    watermark(base, size, ">_")

    # 裁成圆角方形
    alpha = shape_alpha(size)
    out = base.convert("RGBA")
    out.putalpha(alpha)
    return out


def render_png(size, variant="crosshair"):
    """渲染指定尺寸（超采样后缩放）。"""
    big = render_icon(size * SS, variant=variant)
    return big.resize((size, size), Image.LANCZOS)


# --------------------------------------------------------------------------- #
# 预览图
# --------------------------------------------------------------------------- #

def build_sheet(path, sizes, dark=(14, 17, 22), light=(233, 236, 241)):
    pad, gap = 26, 22
    widths = [s for s in sizes]
    w = pad * 2 + sum(widths) + gap * (len(sizes) - 1)
    h = int(max(sizes) * 1.55 + pad * 2)
    sheet = Image.new("RGB", (w, h), dark)
    dhalf = Image.new("RGB", (w, h // 2), dark)
    lhalf = Image.new("RGB", (w, h - h // 2), light)
    sheet.paste(dhalf, (0, 0))
    sheet.paste(lhalf, (0, h // 2))
    x = pad
    for s in sizes:
        img = render_png(s)
        y = (h // 2 - s) // 2
        sheet.paste(img, (x, y), img)
        y2 = h // 2 + (h - h // 2 - s) // 2
        sheet.paste(img, (x, y2), img)
        x += s + gap
    sheet.save(path)
    return sheet


def build_concepts(path):
    big = 384
    a = render_png(big, "crosshair")
    b = render_png(big, "flat")
    pad = 30
    W = pad * 3 + big * 2
    H = pad * 2 + big + 46
    sheet = Image.new("RGB", (W, H), (14, 17, 22))
    sheet.paste(a, (pad, pad), a)
    sheet.paste(b, (pad * 2 + big, pad), b)
    dr = ImageDraw.Draw(sheet)
    font = ImageFont.truetype("C:/Windows/Fonts/msyhbd.ttc", 26)
    dr.text((pad + big / 2 - 62, pad + big + 12), "方案 A · 准星环", font=font, fill=(240, 169, 43))
    dr.text((pad * 2 + big + big / 2 - 62, pad + big + 12), "方案 B · 扁平版", font=font,
            fill=(154, 167, 187))
    sheet.save(path)
    return sheet


# --------------------------------------------------------------------------- #
# SVG（矢量版，与 PNG 同源设计）
# --------------------------------------------------------------------------- #

SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1024 1024" width="1024" height="1024">
  <defs>
    <radialGradient id="bg" cx="50%" cy="42%" r="72%">
      <stop offset="0%" stop-color="#26313f"/>
      <stop offset="55%" stop-color="#151b24"/>
      <stop offset="100%" stop-color="#0b0e12"/>
    </radialGradient>
    <radialGradient id="glow" cx="50%" cy="50%" r="50%">
      <stop offset="0%" stop-color="#ffb030" stop-opacity=".38"/>
      <stop offset="70%" stop-color="#ffb030" stop-opacity=".08"/>
      <stop offset="100%" stop-color="#ffb030" stop-opacity="0"/>
    </radialGradient>
    <linearGradient id="amber" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#ffc75c"/>
      <stop offset="100%" stop-color="#e09a1c"/>
    </linearGradient>
    <filter id="soft" x="-30%" y="-30%" width="160%" height="160%">
      <feGaussianBlur stdDeviation="10"/>
    </filter>
    <clipPath id="round"><rect x="0" y="0" width="1024" height="1024" rx="227"/></clipPath>
  </defs>

  <g clip-path="url(#round)">
    <rect width="1024" height="1024" fill="url(#bg)"/>
    <ellipse cx="512" cy="470" rx="430" ry="400" fill="url(#glow)"/>

    <!-- 准星环 -->
    <g fill="none" stroke="#f0a92b" stroke-opacity=".78" stroke-width="30" stroke-linecap="round" filter="url(#soft)">
      <path d="M512 186 A326 326 0 0 1 836 512"/>
      <path d="M836 512 A326 326 0 0 1 512 838"/>
      <path d="M512 838 A326 326 0 0 1 188 512"/>
      <path d="M188 512 A326 326 0 0 1 512 186"/>
    </g>
    <g fill="none" stroke="#f0a92b" stroke-opacity=".92" stroke-width="18" stroke-linecap="round">
      <path d="M512 186 A326 326 0 0 1 836 512"/>
      <path d="M836 512 A326 326 0 0 1 512 838"/>
      <path d="M512 838 A326 326 0 0 1 188 512"/>
      <path d="M188 512 A326 326 0 0 1 512 186"/>
    </g>
    <!-- 四角刻度 -->
    <g stroke="#f0a92b" stroke-opacity=".92" stroke-width="18" stroke-linecap="round">
      <path d="M206 206 L280 280"/><path d="M818 206 L744 280"/>
      <path d="M206 818 L280 744"/><path d="M818 818 L744 744"/>
    </g>

    <!-- 终端提示符 >_ -->
    <g filter="url(#soft)" stroke="#ffb030" stroke-opacity=".55" stroke-width="112"
       stroke-linecap="round" stroke-linejoin="round" fill="none">
      <path d="M322 408 L468 512 L322 616"/><path d="M548 648 L742 648"/>
    </g>
    <g stroke="#0a0d12" stroke-opacity=".92" stroke-width="112"
       stroke-linecap="round" stroke-linejoin="round" fill="none">
      <path d="M322 408 L468 512 L322 616"/><path d="M548 648 L742 648"/>
    </g>
    <g stroke="url(#amber)" stroke-width="64"
       stroke-linecap="round" stroke-linejoin="round" fill="none">
      <path d="M322 408 L468 512 L322 616"/><path d="M548 648 L742 648"/>
    </g>

    <text x="512" y="892" text-anchor="middle" font-family="Consolas, monospace"
          font-size="96" font-weight="700" fill="#ffffff" fill-opacity=".66">&gt;_</text>
  </g>
  <rect x="3" y="3" width="1018" height="1018" rx="225" fill="none"
        stroke="#ffbe5a" stroke-opacity=".36" stroke-width="7"/>
</svg>
"""

SVG_FLAT = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1024 1024" width="1024" height="1024">
  <defs>
    <radialGradient id="bg2" cx="50%" cy="38%" r="74%">
      <stop offset="0%" stop-color="#2a3646"/>
      <stop offset="58%" stop-color="#161c26"/>
      <stop offset="100%" stop-color="#0b0e12"/>
    </radialGradient>
    <linearGradient id="amber2" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#ffc75c"/>
      <stop offset="100%" stop-color="#dd961a"/>
    </linearGradient>
    <filter id="soft2" x="-30%" y="-30%" width="160%" height="160%">
      <feGaussianBlur stdDeviation="12"/>
    </filter>
    <clipPath id="round2"><rect width="1024" height="1024" rx="227"/></clipPath>
  </defs>
  <g clip-path="url(#round2)">
    <rect width="1024" height="1024" fill="url(#bg2)"/>
    <g filter="url(#soft2)" stroke="#ffb030" stroke-opacity=".5" stroke-width="150"
       stroke-linecap="round" stroke-linejoin="round" fill="none">
      <path d="M292 372 L474 500 L292 628"/><path d="M566 668 L762 668"/>
    </g>
    <g stroke="#0a0d12" stroke-opacity=".9" stroke-width="150"
       stroke-linecap="round" stroke-linejoin="round" fill="none">
      <path d="M292 372 L474 500 L292 628"/><path d="M566 668 L762 668"/>
    </g>
    <g stroke="url(#amber2)" stroke-width="92"
       stroke-linecap="round" stroke-linejoin="round" fill="none">
      <path d="M292 372 L474 500 L292 628"/><path d="M566 668 L762 668"/>
    </g>
    <text x="512" y="886" text-anchor="middle" font-family="Consolas, monospace"
          font-size="104" font-weight="700" fill="#ffffff" fill-opacity=".6">&gt;_</text>
  </g>
  <rect x="3" y="3" width="1018" height="1018" rx="225" fill="none"
        stroke="#ffbe5a" stroke-opacity=".3" stroke-width="7"/>
</svg>
"""


def write_ico(path, sizes):
    """手写 ICO 文件：PNG 压缩帧，按「大图在前」排列。

    Pillow 的 ICO 写入器只会按升序落帧（256 跑到最后一帧），部分 Windows 视图
    （尤其是快捷方式/大图标）会优先取第一帧，于是会显得糊。这里按规范自己写。
    """
    import struct

    frames = []
    for s in sizes:
        img = render_png(s)
        buf = BytesIO()
        img.save(buf, format="PNG", optimize=True)
        frames.append((s, buf.getvalue()))

    header = struct.pack("<HHH", 0, 1, len(frames))
    offset = 6 + 16 * len(frames)
    entries, blobs = b"", b""
    for s, data in frames:
        dim = 0 if s >= 256 else s          # 256 在 ICO 目录里记作 0
        entries += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(data), offset)
        blobs += data
        offset += len(data)
    path.write_bytes(header + entries + blobs)
    return path


def build_desktop_preview(path):
    """模拟桌面：三种常见壁纸底色 + 深/浅任务栏，检查图标醒目程度。"""
    W, H = 900, 500
    bgs = [(24, 34, 56), (92, 106, 128), (206, 212, 222)]   # 深海蓝 / 中灰蓝 / 浅灰
    strip = W // len(bgs)
    img = Image.new("RGB", (W, H), (0, 0, 0))
    dr = ImageDraw.Draw(img)
    for i, c in enumerate(bgs):
        dr.rectangle([i * strip, 0, (i + 1) * strip, H], fill=c)
    # 顶/底两条"任务栏"
    dr.rectangle([0, 0, W, 46], fill=(18, 22, 30))
    dr.rectangle([0, H - 44, W, H], fill=(22, 26, 34))
    font = ImageFont.truetype("C:/Windows/Fonts/msyhbd.ttc", 20)
    small = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 18)
    for i, label in enumerate(("深色壁纸", "中灰壁纸", "浅色壁纸")):
        dr.text((i * strip + 22, 12), label, font=font, fill=(200, 210, 225))

    # 三种壁纸上各放一个桌面快捷方式（图标 + 两行标签）
    for i in range(len(bgs)):
        cx = i * strip + strip // 2
        icon = render_png(112)
        img.paste(icon, (cx - 56, 120), icon)
        dr.text((cx - 62, 248), "CS2 指令查询中心", font=small, fill=(15, 15, 15))
        dr.text((cx - 60, 246), "CS2 指令查询中心", font=small, fill=(255, 255, 255))
    # 任务栏上的小尺寸表现
    x = 24
    for s in (16, 24, 32, 48):
        ic = render_png(s)
        img.paste(ic, (x, 46 - s // 2), ic)
        x += s + 14
    dr.text((x + 12, 60), "↑ 任务栏 / 开始菜单尺寸下的表现（16 / 24 / 32 / 48 px）",
            font=font, fill=(190, 200, 215))
    img.save(path)
    return img


def main():
    (OUT / "icon.svg").write_text(SVG, encoding="utf-8")
    (OUT / "icon-flat.svg").write_text(SVG_FLAT, encoding="utf-8")

    master = render_png(1024)
    master.save(OUT / "icon-1024.png")
    master.resize((512, 512), Image.LANCZOS).save(OUT / "icon-512.png")

    for s in ICON_SIZES:
        render_png(s).save(OUT / f"icon-{s}.png")

    # 多尺寸 ICO（Windows 图标）：256 放第一帧
    ico_sizes = [256, 128, 64, 48, 40, 32, 24, 20, 16]
    write_ico(OUT / "cs2-console-hub.ico", ico_sizes)

    build_sheet(OUT / "sheet.png", [256, 128, 64, 48, 32, 16])
    build_concepts(OUT / "sheet-concepts.png")
    build_desktop_preview(OUT / "desktop-preview.png")

    print("生成完毕：")
    for f in sorted(OUT.iterdir()):
        print(f"  {f.name:24s} {f.stat().st_size/1024:8.1f} KB")


if __name__ == "__main__":
    main()
