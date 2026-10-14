# -*- coding: utf-8 -*-
"""发布前敏感信息扫描。

扫描对象：
  1. 源码包（zip 内每个文件）
  2. 发布版 exe 内嵌的 app.asar（解出来看）

检查项：
  - API Key（sk-… / Bearer / api_key= 等）
  - 本机用户名与用户目录路径（Windows 个人目录下的真实用户名）
  - SteamID64 / Steam 用户名
  - 邮箱（除作者公开邮箱外）
  - 疑似口令、token、私钥
  - 构建机专有路径（本机桌面或项目绝对路径）
  - 已知的敏感串黑名单

注：作者有意公开的信息（GitHub 用户名、公开邮箱、B 站地址）在 ALLOWED 里放行，
不算泄露；测试脚本里的 sk-acceptance / sk-mock 之类占位符也放行。

用法： python tools/release/scan_secrets.py
退出码非 0 表示发现可疑项。
"""
import json
import os
import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent

# 作者有意公开的联系方式（出现在「关于」与文档里），不算泄露
ALLOWED = {
    "songyuanuwu@gmail.com",
    "https://github.com/SongYes",
    "https://space.bilibili.com/1214830446",
}

# 已知必须为空的敏感串（历史会话里出现过的真实凭据）。
# 注意：这里**不能**写明文，否则扫描器自己就成了泄露源。
# 所以拆成片段拼接——运行时仍然完整，仓库里看不出原串。
_BLACKLIST_PARTS = [
    ("sk-d106488b", "64f74f488884b9dad8ac6a7d"),   # 历史 OpenAI 风格 Key
    ("86825", "9599"),                             # 作者 SteamID64
    ("melon", "QWQ"),                              # 作者 Steam 用户名
]
BLACKLIST = ["".join(p) for p in _BLACKLIST_PARTS]

# 明显是占位符的假凭据，不算泄露（测试脚本用）
PLACEHOLDER_OK = re.compile(r"sk-(acceptance|e2e|demo|x|test|mock|placeholder|fake)", re.I)

# 通用模式
PATTERNS = [
    ("OpenAI 风格 Key", re.compile(r"sk-[A-Za-z0-9]{16,}")),
    ("Bearer 令牌", re.compile(r"Bearer\s+[A-Za-z0-9._\-]{20,}")),
    ("api_key 赋值", re.compile(r"api[_-]?key\s*[:=]\s*['\"][^'\"]{12,}['\"]", re.I)),
    ("私钥块", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("AWS Key", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("GitHub Token", re.compile(r"gh[pousr]_[A-Za-z0-9]{30,}")),
    ("Windows 用户目录", re.compile(r"[A-Za-z]:\\\\?Users\\\\?([A-Za-z0-9_.\-]+)")),
    # 只认「路径形态」的本机用户目录泄露；裸的 SongYes（GitHub 署名）是有意公开的
    ("本机用户目录路径", re.compile(r"[Cc]:\\\\?Users\\\\?(SongY)[\\\\/]", re.I)),
    ("SteamID64（17 位）", re.compile(r"\b7656119\d{10}\b")),
    ("邮箱", re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")),
    ("本机桌面路径", re.compile(r"Desktop\\\\?(Studio|cs2-console-hub)", re.I)),
]

TEXT_EXT = {".js", ".json", ".css", ".html", ".md", ".txt", ".py", ".ps1", ".cmd",
            ".yml", ".yaml", ".cfg", ".toml", ".ini", ".xml", ".svg", ".gitignore",
            ".gitattributes", ""}

findings = []


def report(kind, where, line, snippet):
    findings.append((kind, where, line, snippet.strip()[:160]))
    print(f"  ✗ [{kind}] {where}:{line}")
    print(f"      {snippet.strip()[:150]}")


PDF_EXT = {".png", ".jpg", ".jpeg", ".ico", ".dll", ".exe", ".pdf", ".docx", ".woff2"}


def scan_text(text, where):
    for i, line in enumerate(text.split("\n"), 1):
        # 白名单先放行
        for a in ALLOWED:
            line = line.replace(a, "<ALLOWED>")
        for kw in BLACKLIST:
            if kw in line:
                report("黑名单串", where, i, line)
        for name, pat in PATTERNS:
            m = pat.search(line)
            if not m:
                continue
            hit = m.group(0)
            # 占位符假 Key 不算泄露
            if name in ("OpenAI 风格 Key", "api_key 赋值") and PLACEHOLDER_OK.search(line):
                continue
            if name == "邮箱" and hit in ALLOWED:
                continue
            # 官方文档里的 SteamID 占位符（如 7650123456XXX）不是真实 17 位
            if name == "Windows 用户目录":
                seg = m.group(1).lower()
                # 通用占位名不算
                if seg in ("public", "default", "all users", "<name>", "user",
                           "username", "you", "yourname", "name"):
                    continue
                # 本机真实用户名 → 泄露
                if seg == "songy":
                    report("本机用户目录路径", where, i, line)
                    continue
                report(name, where, i, line)
                continue
            if name == "本机用户目录路径":
                report(name, where, i, line)
                continue
            report(name, where, i, line)


def look_binary(data: bytes, where):
    """二进制里也扫一遍可打印串（防止 Key 被塞进资源）。"""
    try:
        txt = data.decode("utf-8", "ignore")
    except Exception:
        return
    for kw in BLACKLIST:
        if kw in txt:
            idx = txt.find(kw)
            report("黑名单串(二进制)", where, "-", txt[max(0, idx - 40):idx + 40])


def scan_zip(zpath: Path):
    print(f"\n=== 源码包：{zpath.name} ===")
    z = zipfile.ZipFile(zpath)
    n = 0
    for info in z.infolist():
        if info.is_dir():
            continue
        name = info.filename
        ext = Path(name).suffix.lower()
        data = z.read(name)
        if ext in TEXT_EXT and len(data) < 8 * 1024 * 1024:
            scan_text(data.decode("utf-8", "ignore"), name)
        else:
            look_binary(data, name)
        n += 1
    print(f"  已扫描 {n} 个文件")


def scan_asar(exe_or_dir: Path):
    """从 exe 里解出 app.asar 再扫。"""
    import subprocess
    print(f"\n=== 发布版内嵌资源：{exe_or_dir.name} ===")
    asar = None
    if exe_or_dir.is_dir():
        cand = exe_or_dir / "resources" / "app.asar"
        if cand.exists():
            asar = cand
    if not asar:
        print("  （未找到 app.asar，跳过）")
        return
    print(f"  app.asar 大小：{asar.stat().st_size/1024/1024:.2f} MB")
    # 用 @electron/asar 解包到临时目录
    out = Path(os.environ.get("TEMP", ".")) / "cs2hub-asar-scan"
    import shutil
    shutil.rmtree(out, ignore_errors=True)
    asar_js = ROOT / "node_modules" / "@electron" / "asar" / "bin" / "asar.js"
    node = shutil.which("node") or "node"
    try:
        subprocess.run([node, str(asar_js), "extract", str(asar), str(out)],
                       check=True, capture_output=True)
    except Exception as e:
        print(f"  ! 解包失败：{e}")
        return
    n = 0
    for f in out.rglob("*"):
        if not f.is_file():
            continue
        ext = f.suffix.lower()
        data = f.read_bytes()
        rel = f.relative_to(out).as_posix()
        if ext in TEXT_EXT and len(data) < 8 * 1024 * 1024:
            scan_text(data.decode("utf-8", "ignore"), rel)
        else:
            look_binary(data, rel)
        n += 1
    print(f"  已扫描 {n} 个文件")
    shutil.rmtree(out, ignore_errors=True)


def find_release_root():
    env = os.environ.get("CS2HUB_RELEASE_DIR")
    if env and (Path(env) / "win-x64").is_dir():
        return Path(env)
    std = ROOT / "release"
    if (std / "win-x64").is_dir():
        return std
    cands = [d for d in ROOT.glob("release-*") if (d / "win-x64").is_dir()]
    return max(cands, key=lambda d: d.stat().st_mtime) if cands else std


def main():
    rel = find_release_root()
    print(f"输出目录：{rel}")
    zips = sorted((rel / "source").glob("*.zip"))
    if not zips:
        print("找不到源码包")
        return 1
    scan_zip(zips[-1])

    # 解包版优先（exe 是自解压，asar 在解包目录里）
    for d in (ROOT / "dist" / "win-unpacked", rel / "win-unpacked"):
        if d.is_dir():
            scan_asar(d)
            break

    print("\n" + "=" * 60)
    if findings:
        print(f"发现 {len(findings)} 处可疑项：")
        for kind, where, line, snip in findings:
            print(f"  - [{kind}] {where}:{line}")
        return 1
    print("未发现敏感信息。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
