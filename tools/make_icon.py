# -*- coding: utf-8 -*-
"""CS2 控制台指令查询中心 —— 图标生成器

设计（按用户提供稿的实测几何还原）：
  蓝色圆角方块 + 白色终端提示符「>_」
  底色就是应用主题色 --accent #2f6fed，无渐变、无描边，纯扁平。

实测依据（对用户提供的 167×158 png 逐像素取样）：
  蓝块边长       142 px（图内）           → 归一化 1.000
  圆角半径       约 31 px                → 0.218 × 边长
  「>」          x 36..66, y 54..85
  「_」          x 75..101, y 102..105

笔画粗细的定法（重要）：
  原图是带模糊边缘的低分辨率图，几何笔画约 10.1px（0.071 × 边长），
  但它的**白色像素覆盖率**是 10.36%（含模糊外溢）。
  直接按 0.071 画，覆盖率只有 7.78%（比值 0.75），视觉上会显得偏细。
  所以按「感知重量」对齐：取
      笔画宽 0.100 × 边长      「_」厚 0.030 × 边长
  使白字覆盖率落在 10% 左右，与原图观感一致。
  （几何测量值 0.071 记在这里备查，实际采用感知值。）

产出（assets/icons/）：
  icon.svg            主图标矢量（唯一几何源）
  icon-flat.svg       同上的扁平副本（兼容旧引用）
  icon-1024.png       主图 PNG
  icon-16/20/24/32/40/48/64/128/256/512.png
  cs2-console-hub.ico 多尺寸 Windows 图标
  sheet.png           尺寸阶梯预览（README 顶部用）
  sheet-concepts.png  深/浅底对比预览
  desktop-preview.png 桌面/任务栏效果预览

用法： python tools/make_icon.py
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets" / "icons"
BUILD = ROOT / "desktop" / "build"
OUT.mkdir(parents=True, exist_ok=True)

BASE = 1024          # 设计坐标系边长
SS = 4               # 超采样倍数

BLUE = (47, 111, 237)      # #2f6fed —— 应用 --accent
WHITE = (255, 255, 255)

# ---- 归一化几何（由实测值除以 142 得到）----
INSET = 0.07                          # 蓝块四周留白
SIDE = BASE * (1 - 2 * INSET)         # 蓝块边长（设计坐标）
R_RATIO = 0.218                       # 圆角 / 边长
CHEV_W_RATIO = 0.100                  # 「>」笔画宽 / 边长（感知重量对齐原图）
UNDER_H_RATIO = 0.030                 # 「_」粗细 / 边长（同上）

# 「>」两段线（归一化到蓝块内，蓝块左上为原点）
CHEV = [
    (36 / 142, 54 / 142, 66 / 142, 69.5 / 142),   # 上段：左上 → 右尖
    (66 / 142, 69.5 / 142, 36 / 142, 85 / 142),   # 下段：右尖 → 左下
]
# 「_」横条（用上下边归一化，渲染时取中线）
UNDER = (75 / 142, 102 / 142, 101 / 142, 105 / 142)


def design_points():
    """把归一化几何换算到 1024 设计坐标。"""
    ox = (BASE - SIDE) / 2
    chev = [(ox + a * SIDE, ox + b * SIDE, ox + c * SIDE, ox + d * SIDE)
            for (a, b, c, d) in CHEV]
    under = (ox + UNDER[0] * SIDE, ox + UNDER[1] * SIDE,
             ox + UNDER[2] * SIDE, ox + UNDER[3] * SIDE)
    return chev, under, (ox, ox, ox + SIDE, ox + SIDE)


def render(size: int, bg=None) -> Image.Image:
    """渲染图标。bg=None → 透明背景；否则铺一层底色（方形，不切圆角）。"""
    S = size * SS
    k = S / BASE
    im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)

    chev, under, block = design_points()
    bx0, by0, bx1, by1 = [v * k for v in block]
    r = R_RATIO * SIDE * k
    d.rounded_rectangle([bx0, by0, bx1, by1], radius=r, fill=BLUE + (255,))

    stroke_w = max(1, int(round(CHEV_W_RATIO * SIDE * k)))
    half = CHEV_W_RATIO * SIDE * k / 2
    ends = set()
    for (x0, y0, x1, y1) in chev:
        d.line([(x0 * k, y0 * k), (x1 * k, y1 * k)], fill=WHITE + (255,), width=stroke_w)
        ends.add((x0 * k, y0 * k))
        ends.add((x1 * k, y1 * k))
    for (x, y) in ends:
        d.ellipse([x - half, y - half, x + half, y + half], fill=WHITE + (255,))

    ux0, uy0, ux1, uy1 = [v * k for v in under]
    uh = max(UNDER_H_RATIO * SIDE * k / 2, S * 0.0055)   # 小尺寸下不至于消失
    cy = (uy0 + uy1) / 2
    d.rounded_rectangle([ux0, cy - uh, ux1, cy + uh], radius=uh, fill=WHITE + (255,))

    im = im.resize((size, size), Image.LANCZOS)
    if bg is not None:
        flat = Image.new("RGBA", (size, size), bg + (255,))
        flat.alpha_composite(im)
        return flat
    return im


def svg_text() -> str:
    """SVG：同一套几何，圆头折线。"""
    chev, under, block = design_points()
    bx0, by0, bx1, by1 = block
    r = R_RATIO * SIDE
    w = CHEV_W_RATIO * SIDE
    segs = "\n    ".join(
        f'<line x1="{x0:.1f}" y1="{y0:.1f}" x2="{x1:.1f}" y2="{y1:.1f}"/>'
        for (x0, y0, x1, y1) in chev)
    ux0, uy0, ux1, uy1 = under
    cy = (uy0 + uy1) / 2
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1024 1024"
     width="1024" height="1024">
  <title>CS2 控制台指令查询中心</title>
  <!-- 蓝色圆角方块 + 白色终端提示符「&gt;_」；底色 = 应用主题色 #2f6fed -->
  <rect x="{bx0:.1f}" y="{by0:.1f}" width="{bx1 - bx0:.1f}" height="{by1 - by0:.1f}"
        rx="{r:.1f}" ry="{r:.1f}" fill="#2f6fed"/>
  <g stroke="#ffffff" stroke-width="{w:.1f}"
     stroke-linecap="round" stroke-linejoin="round">
    {segs}
    <line x1="{ux0:.1f}" y1="{cy:.1f}" x2="{ux1:.1f}" y2="{cy:.1f}"/>
  </g>
</svg>
'''


PNG_SIZES = [16, 20, 24, 32, 40, 48, 64, 128, 256, 512, 1024]
ICO_SIZES = [16, 20, 24, 32, 40, 48, 64, 128, 256]


def build_sheet(path, sizes=(256, 128, 64, 48, 32, 24, 20, 16),
                dark=(14, 17, 22), light=(233, 236, 241)):
    """尺寸阶梯预览：同一图标在深/浅底、各尺寸下的表现。"""
    pad, gap = 26, 22
    big = max(sizes)
    row_h = big + 34
    W = pad * 2 + sum(s + gap for s in sizes) + gap
    H = pad * 2 + row_h * 2 + 18
    img = Image.new("RGB", (W, H), light)
    dr = ImageDraw.Draw(img)
    dr.rectangle([0, 0, W, pad + row_h], fill=dark)
    try:
        f = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 15)
    except Exception:
        f = ImageFont.load_default()
    for row, (bg, label) in enumerate(((dark, "深色背景（任务栏 / 暗色桌面）"),
                                       (light, "浅色背景（浅色桌面 / 网页）"))):
        top = pad + row * row_h
        dr.text((pad, top - 20 if row == 0 else top + 4), label, font=f,
                fill=(200, 210, 225) if row == 0 else (90, 102, 122))
        x = pad
        base_y = top + (14 if row == 0 else 26)
        for s in sizes:
            ic = render(s, bg=bg)
            img.paste(ic, (x, base_y + (big - s)), ic)
            x += s + gap
    img.save(path)
    return img


def build_concepts(path):
    """深/浅底 + 多档尺寸对比预览。"""
    W, H = 900, 400
    img = Image.new("RGB", (W, H), (233, 236, 241))
    dr = ImageDraw.Draw(img)
    dr.rectangle([0, 0, W // 2, H], fill=(14, 17, 22))
    try:
        fb = ImageFont.truetype("C:/Windows/Fonts/msyhbd.ttc", 18)
        f = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 15)
    except Exception:
        fb = f = ImageFont.load_default()
    for i, (bg, tc, label) in enumerate((
            ((14, 17, 22), (215, 224, 238), "深色底"),
            ((233, 236, 241), (60, 72, 92), "浅色底"))):
        ox = i * (W // 2)
        dr.text((ox + 30, 24), label, font=fb, fill=tc)
        x = ox + 40
        for s in (180, 96, 48, 24, 16):
            ic = render(s, bg=bg)
            img.paste(ic, (x, 120 + (180 - s)), ic)
            dr.text((x, 322), f"{s}px", font=f, fill=tc)
            x += s + 26
    img.save(path)
    return img


def build_desktop_preview(path):
    """模拟桌面：三种壁纸底色 + 深/浅任务栏，检查醒目程度。"""
    W, H = 900, 500
    bgs = [(24, 34, 56), (92, 106, 128), (206, 212, 222)]
    strip = W // len(bgs)
    img = Image.new("RGB", (W, H), (0, 0, 0))
    dr = ImageDraw.Draw(img)
    for i, c in enumerate(bgs):
        dr.rectangle([i * strip, 0, (i + 1) * strip, H], fill=c)
    dr.rectangle([0, 0, W, 46], fill=(18, 22, 30))
    dr.rectangle([0, H - 44, W, H], fill=(22, 26, 34))
    font = ImageFont.truetype("C:/Windows/Fonts/msyhbd.ttc", 20)
    small = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 18)
    for i, label in enumerate(("深色壁纸", "中灰壁纸", "浅色壁纸")):
        dr.text((i * strip + 22, 12), label, font=font, fill=(200, 210, 225))
    for i in range(len(bgs)):
        cx = i * strip + strip // 2
        icon = render(112)
        img.paste(icon, (cx - 56, 120), icon)
        dr.text((cx - 62, 248), "CS2 指令查询中心", font=small, fill=(15, 15, 15))
        dr.text((cx - 60, 246), "CS2 指令查询中心", font=small, fill=(255, 255, 255))
    # 顶部任务栏里排几个小尺寸，检查 16/24/32/48 下的表现
    dr.text((18, 13), "任务栏尺寸：", font=small, fill=(190, 200, 215))
    x = 148
    for s in (16, 24, 32, 48):
        ic = render(s)
        img.paste(ic, (x, (46 - s) // 2), ic)
        dr.text((x + s // 2 - 9, 4), f"{s}", font=ImageFont.truetype(
            "C:/Windows/Fonts/msyh.ttc", 12), fill=(140, 154, 176))
        x += s + 22
    dr.text((18, 58), "↑ 顶部即任务栏 / 开始菜单尺寸（16 / 24 / 32 / 48 px）",
            font=small, fill=(196, 206, 220))
    img.save(path)
    return img


def write_ico(path, sizes):
    """多尺寸 Windows 图标。

    坑（我们踩过）：PIL 的 ICO `_save` 会跳过「比基准图大」的尺寸
    （源码里 `if size[0] > width ... continue`），并且只会用
    `append_images` 里**尺寸精确匹配**的那张作为该档的图。
    所以必须：
      1) 基准图传**最大**那档（否则大尺寸被整档跳过，ICO 里只剩小图）；
      2) append_images 里放齐其余各档，且尺寸与 sizes 一一对应。
    只传 sizes= 而不给 append_images 的话，PIL 会用基准图缩放出各档
    （也够用，但直接从高清渲染缩更好）。
    """
    order = sorted(sizes)
    frames = {s: render(s) for s in order}
    biggest = order[-1]
    frames[biggest].save(
        path, format="ICO",
        sizes=[(s, s) for s in order],
        append_images=[frames[s] for s in order if s != biggest],
    )
    got = sorted({s[0] for s in Image.open(path).ico.sizes()})
    if got != order:
        raise SystemExit(f"ICO 尺寸不符：期望 {order}，实际 {got}")
    return path


def main():
    print("渲染图标…（几何：蓝块 + >_ ，底色 #2f6fed）")

    svg = svg_text()
    (OUT / "icon.svg").write_text(svg, encoding="utf-8")
    (OUT / "icon-flat.svg").write_text(svg, encoding="utf-8")
    print("  ✓ icon.svg / icon-flat.svg")

    for s in PNG_SIZES:
        render(s).save(OUT / f"icon-{s}.png")
    print(f"  ✓ icon-{{{','.join(str(s) for s in PNG_SIZES)}}}.png")

    ico = OUT / "cs2-console-hub.ico"
    write_ico(ico, ICO_SIZES)
    print(f"  ✓ {ico.name}  ({', '.join(str(s) for s in ICO_SIZES)})")

    build_sheet(OUT / "sheet.png")
    print("  ✓ sheet.png（README 顶部用）")
    build_concepts(OUT / "sheet-concepts.png")
    print("  ✓ sheet-concepts.png")
    build_desktop_preview(OUT / "desktop-preview.png")
    print("  ✓ desktop-preview.png")

    BUILD.mkdir(parents=True, exist_ok=True)
    write_ico(BUILD / "icon.ico", ICO_SIZES)
    render(256).save(BUILD / "icon.png")
    print(f"  ✓ 已同步 {BUILD.relative_to(ROOT)}/icon.ico + icon.png")

    print("\n完成。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
