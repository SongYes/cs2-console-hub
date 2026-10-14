# -*- coding: utf-8 -*-
"""后台轮询：持续监视 CS2/VConsole2 内存，一旦出现 cvarlist 输出就立刻抓取并合并。

用法（后台跑）：
  python tools/auto_capture.py --seconds 900 --interval 4

判断"抓到了"的标准：单次扫描 ≥ --min-lines 行（默认 300）。
每抓到一次就合并进 _dumps/cs2_cvarlist_mem.txt，并打印进度。
累积到 2802 条附近就自动停止。
"""
import argparse
import time
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import scrape_cvarlist as SC  # noqa: E402
import scan_proc_memory as S  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=int, default=900, help="最长监视时间")
    ap.add_argument("--interval", type=float, default=4.0, help="轮询间隔秒")
    ap.add_argument("--min-lines", type=int, default=300, help="单次扫描多少行才算有效")
    ap.add_argument("--target", type=int, default=2802, help="游戏报告的总条数")
    ap.add_argument("--best", type=int, default=0, help="只保留行数最多的一次（0=全部累积）")
    args = ap.parse_args()

    S.enable_debug_privilege()
    acc = SC.load_acc()
    print(f"[i] 起始累积 {len(acc)} 条", flush=True)
    deadline = time.time() + args.seconds
    rounds_with_data = 0
    while time.time() < deadline:
        pids = [(e, p) for e in ("cs2.exe", "vconsole2.exe") for p in S.pids_of(e)]
        fresh = {}
        for exe, pid in pids:
            r = SC.scan_lines(pid)
            if r:
                for k, v in r.items():
                    if k not in fresh or len(v[1]) > len(fresh[k][1]):
                        fresh[k] = v
        if len(fresh) >= args.min_lines:
            rounds_with_data += 1
            added = 0
            for k, (flags, line) in fresh.items():
                if k not in acc:
                    acc[k] = line
                    added += 1
            SC.ACC.parent.mkdir(parents=True, exist_ok=True)
            SC.ACC.write_text("\n".join(acc[k] for k in sorted(acc)) + "\n", encoding="utf-8")
            print(f"[+] 第 {rounds_with_data} 次抓到 {len(fresh)} 行，新增 {added}，"
                  f"累计 {len(acc)}/{args.target}", flush=True)
            if len(acc) >= args.target - 5:
                print("[OK] 已凑齐，停止监视", flush=True)
                break
        time.sleep(args.interval)
    print(f"[i] 监视结束，累计 {len(acc)} 条 -> {SC.ACC}", flush=True)
    if len(acc) < args.target:
        print("[i] 还没齐：再在 VConsole2 里敲一遍 cvarlist 并重跑 auto_capture.py 即可继续累积",
              flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
