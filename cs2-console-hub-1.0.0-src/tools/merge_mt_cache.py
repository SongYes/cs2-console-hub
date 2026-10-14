# -*- coding: utf-8 -*-
"""合并并行分片产生的翻译缓存，产出最终的 data/mt_cache.json。

用法： python tools/merge_mt_cache.py [--clean]
  --clean  合并后删除分片文件与日志（保留 mt_cache.json）
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
MAIN = DATA / "mt_cache.json"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--clean", action="store_true")
    args = ap.parse_args()

    merged = {}
    if MAIN.exists():
        try:
            merged = json.loads(MAIN.read_text(encoding="utf-8"))
        except Exception:
            merged = {}
    before = sum(1 for v in merged.values() if isinstance(v, dict) and v.get("zh"))

    parts = sorted(p for p in DATA.glob("mt_*.json") if p.name != MAIN.name)
    added = 0
    for p in parts:
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"  [!] {p.name} 读取失败：{e}")
            continue
        for k, v in data.items():
            if isinstance(v, dict) and v.get("zh"):
                if k not in merged or not merged[k].get("zh"):
                    added += 1
                merged[k] = v
    for k in list(merged.keys()):
        if not (isinstance(merged[k], dict) and merged[k].get("zh")):
            del merged[k]
    MAIN.write_text(json.dumps(merged, ensure_ascii=False, indent=0), encoding="utf-8")
    total = len(merged)
    by_src = {}
    for v in merged.values():
        by_src[v.get("src", "?")] = by_src.get(v.get("src", "?"), 0) + 1
    print(f"[OK] 合并 {len(parts)} 个分片，新增 {added} 条；mt_cache.json 共 {total} 条"
          f"（合并前 {before} 条）")
    print(f"     按引擎统计：{by_src}")

    if args.clean:
        removed = 0
        for p in parts:
            p.unlink()
            removed += 1
        for pat in ("_log_*.txt", "_err_*.txt"):
            for p in DATA.glob(pat):
                p.unlink()
                removed += 1
        print(f"[OK] 已清理 {removed} 个中间文件")


if __name__ == "__main__":
    main()
