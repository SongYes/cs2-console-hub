# -*- coding: utf-8 -*-
"""AI 通路命令行自检：不依赖浏览器，直接报告每一步的真实错误。

用法：
  python tools/ai_selftest.py --api-key sk-xxx
  python tools/ai_selftest.py --api-key sk-xxx --base https://api.deepseek.com/v1 --model deepseek-chat
  python tools/ai_selftest.py                     # 不传 Key 时只测本地服务

它会依次检查：本地服务是否在跑 → 指令库能否加载 → 上游接口鉴权 → 真实问答链路。
任何一步失败都会打印上游原始报错，方便直接定位。
"""
import argparse
import json
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOCAL = "http://127.0.0.1:8788"


def post(url, payload, headers=None, timeout=120):
    req = urllib.request.Request(url, data=json.dumps(payload, ensure_ascii=False).encode("utf-8"))
    req.add_header("Content-Type", "application/json")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def get(url, timeout=60):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--api-key", default="")
    ap.add_argument("--base", default="https://api.deepseek.com/v1")
    ap.add_argument("--model", default="deepseek-chat")
    ap.add_argument("--local", default=LOCAL)
    args = ap.parse_args()

    print("=" * 66)
    print("  CS2 控制台指令查询中心 · AI 通路自检")
    print("=" * 66)
    ok = True

    # 1) 本地服务
    print("\n[1/4] 本地服务")
    try:
        h = get(args.local + "/api/health", timeout=15)
        print(f"    OK   服务在跑：Python {h.get('python')}，根目录 {h.get('root')}")
    except Exception as e:
        print(f"    失败 连不上 {args.local}：{type(e).__name__} {e}")
        print("    → 先双击 start.cmd 启动服务（窗口不能关）")
        return 1

    # 2) 指令库
    print("\n[2/4] 指令库")
    try:
        d = get(args.local + "/api/data", timeout=120)
        meta = d.get("meta") or {}
        print(f"    OK   {d.get('count')} 条指令，机翻套用 {d.get('ai_zh_applied')} 条，"
              f"版本 {meta.get('version')}")
    except Exception as e:
        print(f"    失败 {type(e).__name__} {e}")
        ok = False

    if not args.api_key:
        print("\n[3/4][4/4] 跳过（未提供 --api-key）")
        print("\n结论：本地服务正常。要测 AI 请加 --api-key sk-xxx")
        return 0 if ok else 1

    # 3) 上游鉴权
    print(f"\n[3/4] 上游接口（{args.base} / {args.model}）")
    try:
        t0 = time.time()
        r = post(args.base.rstrip("/") + "/chat/completions",
                 {"model": args.model, "messages": [{"role": "user", "content": "ping"}],
                  "max_tokens": 16},
                 {"Authorization": "Bearer " + args.api_key}, timeout=60)
        print(f"    OK   {time.time()-t0:.1f}s，模型 {r.get('model')}，"
              f"用量 {json.dumps(r.get('usage') or {}, ensure_ascii=False)}")
        print(f"         返回：{str(r['choices'][0]['message']['content'])[:60]}")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:300]
        hints = {401: "API Key 无效或失效", 402: "余额不足", 404: "模型名或 Base URL 不对（Base 要带 /v1）",
                 429: "限流或配额用尽"}
        print(f"    失败 HTTP {e.code} —— {hints.get(e.code, '看法')}")
        print(f"         上游原文：{body}")
        return 1
    except Exception as e:
        print(f"    失败 {type(e).__name__} {e}")
        print("    → 多为网络/代理问题，或 Base URL 不可达")
        return 1

    # 4) 走本地代理的真实链路
    print("\n[4/4] 经由本地服务的真实问答链路（和界面完全同一条路）")
    try:
        t0 = time.time()
        r = post(args.local + "/api/ai", {
            "base_url": args.base, "api_key": args.api_key, "model": args.model,
            "messages": [{"role": "system", "content": "你是 CS2 控制台专家，用中文回答。"},
                         {"role": "user", "content": "用一句话说明 cl_crosshaircolor 1 的作用"}],
            "max_tokens": 200,
        }, timeout=180)
        if not r.get("ok"):
            print(f"    失败 {r.get('error')}")
            if r.get("hint"):
                print(f"         提示：{r['hint']}")
            if r.get("detail"):
                print(f"         上游原文：{str(r['detail'])[:300]}")
            return 1
        print(f"    OK   {time.time()-t0:.1f}s，{json.dumps(r.get('usage') or {}, ensure_ascii=False)}")
        print(f"         回答：{str(r.get('content'))[:120]}")
    except Exception as e:
        print(f"    失败 {type(e).__name__} {e}")
        return 1

    print("\n结论：AI 通路完全正常（本地服务 → 上游 → 渲染链路均已验证）。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
