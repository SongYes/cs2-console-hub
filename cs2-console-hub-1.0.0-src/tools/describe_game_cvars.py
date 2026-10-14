# -*- coding: utf-8 -*-
"""为「游戏文件发现的新 cvar」生成中英说明（人可读的双语释义）。

这些 cvar 上游两个数据源都没有说明，只有名字。用大模型按名字推断用途，
同时产出英文说明与中文释义，并明确标注为「按变量名推断」，避免冒充官方文档。
"""
import argparse
import json
import re
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
EXTRA = DATA / "game_extra.json"

SYSTEM = (
    "你是 CS2（反恐精英2）控制台 cvar 专家。用户给出若干 cvar 名字，"
    "请为每一个推断它的用途，输出**英文官方风格说明**与**简洁中文释义**。要求：\n"
    "1. 只根据名字与 CS2 常识推断，不要编造具体数值范围（除非名字里已含语义）；\n"
    "2. 英文说明 8-20 个单词，中文 10-40 字，都要具体、可操作；\n"
    "3. 若名字疑似非玩家可调的内部变量，中文里注明「（内部调试用）」；\n"
    "4. 输出严格 JSON：{\"<cvar名>\": {\"en\": \"...\", \"zh\": \"...\"}}，键必须是原样的 cvar 名。"
)


def call(args, names):
    user = "请为这些 cvar 生成说明：\n" + "\n".join(names)
    payload = {"model": args.model, "messages": [{"role": "system", "content": SYSTEM},
                                                {"role": "user", "content": user}],
               "temperature": 0.2, "max_tokens": 4000,
               "response_format": {"type": "json_object"}}
    req = urllib.request.Request(args.base.rstrip("/") + "/chat/completions",
                                data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                                headers={"Content-Type": "application/json",
                                         "Authorization": "Bearer " + args.api_key})
    with urllib.request.urlopen(req, timeout=180) as r:
        d = json.loads(r.read().decode("utf-8", "replace"))
    txt = d["choices"][0]["message"]["content"]
    txt = re.sub(r"^```(?:json)?|```$", "", txt.strip(), flags=re.M).strip()
    try:
        obj = json.loads(txt)
    except Exception:
        m = re.search(r"\{.*\}", txt, re.S)
        obj = json.loads(m.group(0)) if m else {}
    return obj if isinstance(obj, dict) else {}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--api-key", required=True)
    ap.add_argument("--base", default="https://api.deepseek.com/v1")
    ap.add_argument("--model", default="deepseek-chat")
    ap.add_argument("--batch", type=int, default=20)
    args = ap.parse_args()

    raw = json.loads(EXTRA.read_text(encoding="utf-8"))
    todo = [e["n"] for e in raw["entries"] if not (e.get("en") or "").strip()]
    print(f"[i] 需要生成说明的 cvar：{len(todo)} 条")
    batches = [todo[i:i + args.batch] for i in range(0, len(todo), args.batch)]

    results = {}
    with ThreadPoolExecutor(max_workers=4) as ex:
        for obj in ex.map(lambda b: call(args, b), batches):
            results.update(obj)

    filled = 0
    for e in raw["entries"]:
        r = results.get(e["n"]) or {}
        if isinstance(r, dict):
            if r.get("en"):
                e["en"] = str(r["en"]).strip()
            if r.get("zh"):
                e["zh"] = str(r["zh"]).strip()
                e["zh_src"] = "model-inferred"
            if e.get("en") or e.get("zh"):
                filled += 1
    raw["described_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    EXTRA.write_text(json.dumps(raw, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[OK] 已为 {filled}/{len(todo)} 条生成说明，写回 data/game_extra.json")
    for e in raw["entries"][:8]:
        print(f"   {e['n']}")
        print(f"      EN: {(e.get('en') or '')[:80]}")
        print(f"      ZH: {(e.get('zh') or '')[:80]}")


if __name__ == "__main__":
    main()
