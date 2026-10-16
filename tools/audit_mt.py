# -*- coding: utf-8 -*-
"""用大模型审计机器翻译质量：找出「中文与英文原意不符」的条目并修正。

为什么需要它：
  关键词规则能抓「炸弹网站」这类词，但抓不到「获得的最大距离」（语义反了）这类错误。
  让模型逐条比对英文原文与现有中文，只输出**明确有问题**的那些，并给出改写。

范围默认是 MyMemory / Argos 这两个较弱引擎的产出（数量约 1100 条，成本可控），
也可用 --scope all 覆盖全部机器翻译条目。

用法：
  python tools/audit_mt.py --api-key sk-xxx                # 只预览
  python tools/audit_mt.py --api-key sk-xxx --apply        # 写入缓存
"""
import argparse
import json
import re
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
CACHE = DATA / "mt_cache.json"
REPORT = DATA / "mt_audit.json"

SYSTEM = (
    "你是 CS2 控制台指令的中文本地化审校。用户会给出若干条「英文原文 + 现有中文译文」，"
    "你要找出其中**中文含义与英文不符**的条目。判定标准（从严，宁缺勿滥）：\n"
    "1. 语义错误或说反了（例如把 get away from 译成「获得」、把 disable 译成「启用」）；\n"
    "2. 关键名词译错（bombsite=炸弹安放点/包点、ragdoll=尸体模型、killfeed=击杀提示、"
    "spectator=观战者、grenade=投掷物、armor=护甲、hitbox=命中判定框、freeze cam=冻结镜头）；\n"
    "3. 中文里残留成片的英文单词（专有名词 HLTV/SourceTV/Steam/UDP/SDR/tick/FOV/HUD 等不算）；\n"
    "4. 语句碎裂到读不通。\n"
    "**用词风格差异、语序不同、简繁差异都不算问题**，不要为了改写而改写。\n"
    "输出严格 JSON，**键用条目序号（字符串形式，如 \"3\"）**："
    "{\"修正\": {\"<序号>\": \"<改写后的中文>\"}, \"问题\": {\"<序号>\": \"<一句话说明错在哪>\"}}。"
    "没有问题的条目不要出现在结果里；若全部合格，返回 {\"修正\": {}, \"问题\": {}}。"
)

# 已知错译 → 正确说法（先做确定性修正，减少模型的负担）
PHRASE_FIXES = [
    ("炸弹网站", "炸弹安放点"), ("炸弹站点", "炸弹安放点"), ("包点网站", "炸弹安放点"),
    ("从C4 炸弹安放点获得的最大距离", "允许离开炸弹安放点的最大距离"),
    ("获得的最大距离", "允许离开的最大距离"),
    ("生命射击", "急救针"), ("狗牌", "狗牌"),
    ("死亡对战", "死斗模式"), ("死亡比赛", "死斗模式"),
    ("场景项目", "地图上的物品"), ("波浪", "波次"),
    ("卷曲", "回合"), ("蜱虫", "tick"),
]


def fix_phrases(t):
    for a, b in PHRASE_FIXES:
        t = t.replace(a, b)
    return t


def api_call(args, messages, max_tokens=8000):
    payload = {
        "model": args.model,
        "messages": messages,
        "temperature": 0.1,
        "max_tokens": max_tokens,
        "response_format": {"type": "json_object"},
    }
    req = urllib.request.Request(
        args.base.rstrip("/") + "/chat/completions",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + args.api_key},
    )
    with urllib.request.urlopen(req, timeout=240) as r:
        d = json.loads(r.read().decode("utf-8", "replace"))
    return d["choices"][0]["message"]["content"], (d.get("usage") or {}).get("total_tokens", 0)


def parse_obj(text):
    t = re.sub(r"^```(?:json)?|```$", "", (text or "").strip(), flags=re.M).strip()
    try:
        d = json.loads(t)
        return d if isinstance(d, dict) else {}
    except Exception:
        m = re.search(r"\{.*\}", t, re.S)
        if not m:
            return {}
        try:
            d = json.loads(m.group(0))
            return d if isinstance(d, dict) else {}
        except Exception:
            return {}


def audit_batch(items, args, stats, lock):
    """items: [(en, zh)]；返回 {'修正': {序号: 中文}, '问题': {序号: 说明}}"""
    lines = []
    for i, (en, zh) in enumerate(items, 1):
        lines.append(f'[{i}]\n英文: {en[:600]}\n现有中文: {zh[:400]}')
    user = "请审校下面这些条目，按 system 要求返回 JSON（键为条目序号）：\n\n" + "\n\n".join(lines)
    last = None
    for attempt in range(args.retries):
        try:
            content, tokens = api_call(args, [{"role": "system", "content": SYSTEM},
                                              {"role": "user", "content": user}])
            with lock:
                stats["tokens"] += tokens
                stats["calls"] += 1
            obj = parse_obj(content)
            if obj is not None:
                return obj
            last = "返回不是 JSON"
        except urllib.error.HTTPError as e:
            last = f"HTTP {e.code}"
            time.sleep(2 * (attempt + 1))
        except Exception as e:
            last = f"{type(e).__name__}: {str(e)[:100]}"
            time.sleep(2)
    raise RuntimeError(last or "unknown")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--api-key", required=True)
    ap.add_argument("--base", default="https://api.deepseek.com/v1")
    ap.add_argument("--model", default="deepseek-chat")
    ap.add_argument("--scope", default="weak", choices=["weak", "all"])
    ap.add_argument("--batch", type=int, default=25)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--retries", type=int, default=3)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    db = json.loads((DATA / "commands.json").read_text(encoding="utf-8"))
    cache = json.loads(CACHE.read_text(encoding="utf-8"))

    # 待审计：同一英文原文只审一次
    todo, seen = [], set()
    for e in db["entries"]:
        en = (e.get("en") or "").strip()
        if not en:
            continue
        rec = cache.get(en.lower())
        if not rec or not rec.get("zh"):
            continue
        if args.scope == "weak" and rec.get("src") not in ("mymemory", "argos"):
            continue
        if en.lower() in seen:
            continue
        seen.add(en.lower())
        zh = fix_phrases(rec["zh"])
        if zh != rec["zh"]:
            rec["zh"] = zh
            rec["fixed"] = True
        todo.append((en, rec["zh"]))
    if args.limit:
        todo = todo[:args.limit]
    print(f"[i] 待审 {len(todo)} 条（范围 {args.scope}），{args.batch} 条/批，并发 {args.workers}")

    batches = [todo[i:i + args.batch] for i in range(0, len(todo), args.batch)]
    stats = {"tokens": 0, "calls": 0, "err": []}
    lock = threading.Lock()
    fixes, problems = {}, {}
    t0 = time.time()

    def work(b):
        try:
            obj = audit_batch(b, args, stats, lock)
        except Exception as e:
            with lock:
                stats["err"].append(str(e)[:120])
            return None
        # 序号 -> 英文原文，避免模型改动原文导致键对不上
        out = {"fixed": {}, "probs": {}}
        idx_map = {str(i + 1): en for i, (en, _zh) in enumerate(b)}
        for k, v in (obj.get("修正") or {}).items():
            k = str(k).strip().strip("[]")
            if k.isdigit() and k in idx_map and isinstance(v, str) and v.strip():
                out["fixed"][idx_map[k]] = v.strip()
        for k, v in (obj.get("问题") or {}).items():
            k = str(k).strip().strip("[]")
            if k.isdigit() and k in idx_map:
                out["probs"][idx_map[k]] = str(v)[:160]
        return out

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        for fut in as_completed([ex.submit(work, b) for b in batches]):
            obj = fut.result()
            if not obj:
                continue
            fixes.update(obj["fixed"])
            problems.update(obj["probs"])
            with lock:
                if (len(fixes) + len(problems)) % 30 < 4:
                    print(f"  已发现可疑 {len(problems)} 条，拟修正 {len(fixes)} 条"
                          f"（{time.time()-t0:.0f}s，tokens {stats['tokens']}）")

    print(f"[完成] 审计 {len(todo)} 条：可疑 {len(problems)}，拟修正 {len(fixes)}；"
          f"调用 {stats['calls']} 次，tokens {stats['tokens']}，用时 {(time.time()-t0)/60:.1f} 分")

    REPORT.write_text(json.dumps({"problems": problems, "fixes": fixes},
                                 ensure_ascii=False, indent=1), encoding="utf-8")
    print("  明细写入 data/mt_audit.json")

    if args.apply and fixes:
        n = 0
        for en, zh in fixes.items():
            key = en.lower()
            rec = cache.get(key)
            if rec:
                rec["zh"] = fix_phrases(zh)
                rec["src"] = "deepseek"
                rec["audited"] = True
                rec["at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
                n += 1
        CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=0), encoding="utf-8")
        print(f"[已应用] 覆盖 {n} 条译文")


if __name__ == "__main__":
    main()
