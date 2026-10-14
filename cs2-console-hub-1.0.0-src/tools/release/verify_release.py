# -*- coding: utf-8 -*-
"""复核发布包内容：许可文件齐备、无产物混入、源码可构建要素在位。"""
import os
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent


def find_release_root():
    """定位实际输出目录。

    make_release.py 正常写 release/；若该目录被资源管理器占用（删除与改名都被
    拒绝），它会退到 release-<时间戳>/。这里优先用 release/，否则取最新的一份，
    并可用 CS2HUB_RELEASE_DIR 显式指定。
    """
    env = os.environ.get("CS2HUB_RELEASE_DIR")
    if env:
        p = Path(env)
        if (p / "win-x64").is_dir():
            return p
    std = ROOT / "release"
    if (std / "win-x64").is_dir() and any((std / "source").glob("*.zip")):
        return std
    cands = [d for d in ROOT.glob("release-*")
             if (d / "win-x64").is_dir() and any((d / "source").glob("*.zip"))]
    if cands:
        return max(cands, key=lambda d: d.stat().st_mtime)
    return std


REL = find_release_root()
ZIP = next(iter(sorted((REL / "source").glob("*.zip"))), REL / "source" / "none.zip")
WIN = REL / "win-x64"

fails = []


def check(name, ok, detail=""):
    print(f"  {'✓' if ok else '✗'} {name}" + (f"   → {detail}" if detail and not ok else ""))
    if not ok:
        fails.append(name)


print(f"=== 源码包必备文件 ===\n  输出目录：{REL}")
z = zipfile.ZipFile(ZIP)
names = z.namelist()
files = [n for n in names if not n.endswith("/")]

need = {
    "LICENSE": "GPLv3 全文",
    "NOTICE": "版权与附加说明",
    "README.md": "项目说明",
    "package.json": "构建配置",
    ".gitignore": "Git 忽略规则",
    ".gitattributes": "换行与语言统计",
    "index.html": "前端入口",
    "assets/app.js": "前端逻辑",
    "assets/db.js": "离线内嵌库",
    "data/commands.json": "指令库",
    "desktop/main.js": "Electron 主进程",
    "desktop/server.js": "本地服务",
    "desktop/build/icon.ico": "构建图标资源",
    "tools/verify_readme.py": "README 核对脚本",
    "docs/INTRO.md": "中英对照介绍",
    "docs/repo-description.md": "仓库简介",
    "docs/packaging.md": "打包说明",
    "tools/release/make_release.py": "发布分装脚本",
    "tools/build_db.py": "数据库构建",
    "tools/guard_check.py": "上锁检查",
}
for f, desc in need.items():
    hit = [n for n in files if n.endswith("/" + f) or n.endswith(f)]
    check(f"{f}（{desc}）", bool(hit))

print("\n=== LICENSE 内容确认 ===")
lic = z.read([n for n in files if n.endswith("LICENSE")][0]).decode("utf-8")
check("是 GPLv3", "GNU GENERAL PUBLIC LICENSE" in lic and "Version 3, 29 June 2007" in lic)
check("含完整条款至 END OF TERMS", "END OF TERMS AND CONDITIONS" in lic)
check("体积合理（>30KB）", len(lic.encode("utf-8")) > 30000, f"{len(lic.encode('utf-8'))} 字节")

print("\n=== 不应混入源码包的产物 ===")
# 注意：只禁「产物目录在包根」，不能拿 /release/ 这种片段去匹配，
# 否则 tools/release/make_release.py（源码）会被误判。
bad_dirs = ("node_modules/", "dist/", "release/", "_dumps/", "_raw/", "design/",
            "_backup_20261014_110630/", "_backup_commands/")
for bad in bad_dirs:
    hit = [n for n in files if n.replace("cs2-console-hub-1.0.0-src/", "", 1).startswith(bad)]
    check(f"根目录不含 {bad}", not hit, f"{len(hit)} 个：{hit[:2]}")
for bad in ("mt_cache.json", ".bak", "__pycache__", ".pyc"):
    hit = [n for n in files if bad in n]
    check(f"不含 {bad}", not hit, f"{len(hit)} 个：{hit[:2]}")

print("\n=== 发布版目录 ===")
for f in ["CS2控制台指令查询中心-1.0.0-安装包.exe",
          "CS2控制台指令查询中心-1.0.0-便携版.exe",
          "SHA256SUMS.txt", "RELEASE_NOTES.md"]:
    p = WIN / f
    check(f, p.exists(), "缺失")
check("SHA256SUMS 非空", (WIN / "SHA256SUMS.txt").stat().st_size > 60)

print("\n" + "=" * 56)
print(f"文件数：源码 {len(files)} · 发布 {len(list(WIN.iterdir()))}")
if fails:
    print(f"失败 {len(fails)} 项：")
    for f in fails:
        print("  - " + f)
    sys.exit(1)
print("发布包复核通过。")
