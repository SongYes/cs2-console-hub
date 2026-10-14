# -*- coding: utf-8 -*-
"""核对 README 里的每条事实性声明与仓库现状是否一致。

README 的过期漂移是反复出现的问题（数字、已删功能、文件路径）。
这个脚本把「README 声称的」与「仓库实际有的」逐条比对，防止再飘。

用法： python tools/verify_readme.py
"""
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
README = ROOT / "README.md"

fails = []
oks = []
EXTS = ("json", "css", "html", "png", "ico", "cfg", "ps1", "cmd", "js", "py", "md", "txt", "dll", "vpk", "asi", "exe")


def check(name, ok, detail=""):
    (oks if ok else fails).append(name)
    line = f"  {'✓' if ok else '✗'} {name}"
    if detail and not ok:
        line += f"   → {detail}"
    print(line)


def resolve(rel):
    """把 README 里可能写成裸文件名的路径解析到实际位置。"""
    rel = rel.replace("\\", "/")
    cands = [rel, "data/" + rel, "assets/" + rel, "docs/" + rel,
             "desktop/" + rel, "tools/" + rel, "tools/dev/" + rel]
    for c in cands:
        if (ROOT / c).exists():
            return c
    return None


def main():
    if not README.exists():
        print("找不到 README.md")
        return 1
    t = README.read_text(encoding="utf-8")
    lines = t.split("\n")

    # ---------------- 数据事实 ----------------
    print("=== 数据事实 ===")
    db = json.loads((ROOT / "data" / "commands.json").read_text(encoding="utf-8"))
    e = db["entries"]
    n_total, n_cmd = len(e), sum(1 for x in e if x.get("t") == "command")
    n_rel = sum(1 for x in e if x.get("r"))
    n_cat = len(db["categories"])
    n_sub = sum(len(c.get("subs") or []) for c in db["categories"])
    q = Counter(x.get("q") for x in e)
    n_nh = sum(1 for x in e if x.get("nh"))
    n_nozh = sum(1 for x in e if not (x.get("z") or "").strip())

    check(f"总条数 {n_total}", f"{n_total} 条" in t)
    check(f"控制台命令 {n_cmd}", f"{n_cmd} 条" in t)
    check(f"正式版下发 {n_rel}", f"{n_rel} 条" in t)
    check(f"分类 {n_cat}", f"{n_cat} 个一级分类" in t)
    check(f"子分类 {n_sub}", f"{n_sub} 个子分类" in t)
    check(f"精校 {q.get(2, 0)}", f"精校 {q.get(2, 0)} 条" in t)
    check(f"AI 译 {q.get(3, 0)}", f"AI 译 {q.get(3, 0)} 条" in t)
    check(f"规则译 {q.get(1, 0)}", f"术语表规则译 {q.get(1, 0)} 条" in t)
    check(f"名字拆解 {n_nh}", f"{n_nh} 条附带" in t)
    check("中文释义覆盖 100%", n_nozh == 0 and "中文释义覆盖 100%" in t)

    # 离线内嵌库必须与主库一致（README 特意强调了这点）
    raw = (ROOT / "assets" / "db.js").read_text(encoding="utf-8")
    m = re.search(r"window\.__CS2_DB__\s*=\s*(\{.*\})\s*;\s*$", raw, re.S)
    emb = json.loads(m.group(1)) if m else {}
    n_emb = len(emb.get("entries") or [])
    check("内嵌库 db.js 与 commands.json 一致", n_emb == n_total,
          f"db.js={n_emb} vs json={n_total}")

    n_base = len(json.loads((ROOT / "data" / "integrity_baseline.json")
                            .read_text(encoding="utf-8"))["files"])
    check(f"上锁基线 {n_base} 个敏感文件",
          n_base == 854 and f"{n_base} 个敏感文件" in t, f"实际 {n_base}")

    # ---------------- 已删功能不得再出现 ----------------
    # 明确说明「该状态已不存在」的句子是合法的，不算漂移
    print("\n=== 已删功能（不得作为现存功能出现）===")
    NEG = re.compile(r"不再有|已剔除|已删除|已移除|不存在|不会再|已改为|已按")
    removed = {
        "自动检查更新 / 检查更新": r"自动检查更新|检查更新",
        "最近跟进": r"最近跟进",
        "账号与平台": r"账号与平台",
        "作用域/类型筛选按钮": r"按作用域（|按类型（指令",
        "中英对照开关（已改三选一）": r"中英对照`?\s*开关",
        "待游戏内确认": r"待游戏内确认|上游收录待确认",
        "mt_cache.json": r"mt_cache\.json",
    }
    for name, pat in removed.items():
        hits = [n for n, l in enumerate(lines, 1)
                if re.search(pat, l) and not NEG.search(l)]
        check(f"不把「{name}」当现存功能", not hits, f"L{hits}")

    # ---------------- 关键文件 ----------------
    print("\n=== README 引用的文件 / 脚本 ===")
    must = [
        "docs/INTRO.md", "docs/packaging.md", "docs/safety-guard.md",
        "docs/repo-description.md", "LICENSE", "NOTICE",
        "index.html", "assets/app.js", "assets/style.css", "assets/theme.css",
        "assets/db.js", "assets/icons/sheet.png", "assets/icons/cs2-console-hub.ico",
        "docs/screenshot-main.png", "docs/screenshot-ai.png",
        "data/commands.json", "data/db_meta.json", "data/zh_cache.json",
        "data/integrity_baseline.json",
        "desktop/main.js", "desktop/server.js", "desktop/afterpack-icon.js",
        "desktop/test_server.js", "desktop/acceptance.js",
        "tools/server.py", "tools/build_db.py", "tools/guard_check.py",
        "tools/import_cvar_dump.py", "tools/scan_game.py", "tools/find_gaps.py",
        "tools/name_zh.py", "tools/translate_db.py", "tools/dump_commands.cfg",
        "tools/release/make_release.py", "tools/dev/e2e.js",
        "start.cmd", "start.ps1", "package.json",
    ]
    for p in must:
        check(f"存在 {p}", (ROOT / p).exists(), "缺失")

    # README 正文里用反引号引到的路径（扩展名按长度排序，避免 json 被 js 截断）
    print("\n=== 正文里提到的相对路径 ===")
    pat = re.compile(r"`([A-Za-z0-9_./\\-]+\.(?:" + "|".join(EXTS) + r"))`")
    seen = set()
    for mm in pat.finditer(t):
        rel = mm.group(1)
        if rel.startswith(("http", "../")) or rel in seen:
            continue
        seen.add(rel)
        check(f"存在 {rel}", resolve(rel) is not None, "缺失")

    # ---------------- npm 脚本 ----------------
    print("\n=== README 提到的 npm 脚本 ===")
    scripts = json.loads((ROOT / "package.json").read_text(encoding="utf-8")).get("scripts", {})
    for mm in re.finditer(r"npm run ([\w:]+)", t):
        name = mm.group(1)
        check(f"script {name}", name in scripts, f"未定义（已有：{sorted(scripts)}）")

    # ---------------- 目录结构图 ----------------
    print("\n=== 目录结构图里的条目 ===")
    i, j = t.find("## 目录结构"), t.find("## 打包")
    tree = t[i:j] if 0 < i < j else ""
    tree_pat = re.compile(r"([A-Za-z0-9_.\-]+\.(?:" + "|".join(EXTS) + r"))")
    for mm in sorted(set(tree_pat.findall(tree))):
        check(f"结构图 {mm}", resolve(mm) is not None, "找不到对应文件")

    # ---------------- 许可证一致性 ----------------
    print("\n=== 许可证（GPL-3.0-only）一致性 ===")
    lic = (ROOT / "LICENSE").read_text(encoding="utf-8")
    check("LICENSE 是 GPLv3 全文",
          "GNU GENERAL PUBLIC LICENSE" in lic
          and "Version 3, 29 June 2007" in lic
          and "END OF TERMS AND CONDITIONS" in lic)
    check("LICENSE 保留了 17 条条款",
          all(f"{n}. " in lic for n in range(0, 18)) or lic.count("\n") > 200)
    pkg_lic = json.loads((ROOT / "package.json").read_text(encoding="utf-8")).get("license")
    check(f"package.json license = GPL-3.0-only（实际 {pkg_lic}）", pkg_lic == "GPL-3.0-only")
    for f in ["README.md", "docs/INTRO.md", "docs/RELEASE_NOTES.md"]:
        ft = (ROOT / f).read_text(encoding="utf-8")
        check(f"{f} 提到 GPL", "GPL" in ft)
        # 本项目文档里不应再把 MIT 当作自己的许可证
        bad = [n for n, l in enumerate(ft.split("\n"), 1)
               if re.search(r"\bMIT\b", l)]
        check(f"{f} 不再自称 MIT", not bad, f"L{bad}")
    # 软件内「关于」也应标注许可证
    idx = (ROOT / "index.html").read_text(encoding="utf-8")
    check("软件内「关于」标注了 GPL", "GPL v3" in idx)

    # ---------------- 收尾 ----------------
    print("\n" + "=" * 56)
    print(f"通过 {len(oks)} / 失败 {len(fails)}")
    if fails:
        print("\n失败项：")
        for f in fails:
            print("  - " + f)
        return 1
    print("README 与仓库现状一致。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
