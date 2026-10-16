# -*- coding: utf-8 -*-
"""用 OpenAI 兼容大模型批量翻译指令说明（质量优于通用机翻，可指定术语）。

特点：
  - 按英文原文去重，只翻没翻过的（断点续传）
  - 多线程并发 + 失败自动二分重试（一批返回坏 JSON 时拆成两半再试）
  - 术语与格式由 system prompt 约束，翻完再做一次离线术语纠错

用法：
  python tools/translate_db_ai.py --api-key sk-xxx
  python tools/translate_db_ai.py --api-key sk-xxx --only core --workers 10 --batch 50
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
DEFAULT_BASE = "https://api.deepseek.com/v1"
DEFAULT_MODEL = "deepseek-chat"

SYSTEM = (
    "你是 CS2（反恐精英 2）控制台指令的本地化专家，为中文玩家翻译 cvar/命令的官方英文说明。要求：\n"
    "1. 输出简洁、准确、地道的简体中文，一条不超过 60 个汉字；\n"
    "2. 保留技术缩写与专有名词原文：FOV、HUD、UI、HLTV、SourceTV、Steam、SteamID、SDR、UDP、"
    "tick、PVS、LOD、HRTF、RGB、Bot、C4、IP、URL，以及形如 cl_xxx / sv_xxx 的变量名；\n"
    "3. 保留原文里的默认值、取值范围、单位等数值信息，不要自行删改；\n"
    "4. 使用玩家习惯说法：crosshair=准星、radar=雷达、viewmodel=手持模型、ragdoll=尸体模型、"
    "spectator=观战者、freeze cam=冻结镜头、killfeed=击杀提示、scoreboard=计分板、"
    "matchmaking=匹配、friendly fire=队友伤害、grenade=投掷物、armor=护甲、"
    "interpolation=插值、lag compensation=延迟补偿、molotov=燃烧瓶；\n"
    "5. 不要添加原文没有的信息，不要解释、不要客套；\n"
    "6. 严格输出 JSON 对象，键是原文英文（与输入完全一致），值是中文译文。"
)

STRIP_PREFIX = re.compile(r"^(?:译文|中文|翻译)[:：]\s*")


def load_json(path, default):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return default


def save_json(path, obj):
    p = Path(path)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=0), encoding="utf-8")
    tmp.replace(p)


def api_call(base, key, model, payload, timeout=180):
    req = urllib.request.Request(
        base.rstrip("/") + "/chat/completions",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + key},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def parse_json_obj(text):
    t = (text or "").strip()
    t = re.sub(r"^```(?:json)?|```$", "", t, flags=re.M).strip()
    try:
        d = json.loads(t)
        return d if isinstance(d, dict) else None
    except Exception:
        m = re.search(r"\{.*\}", t, re.S)
        if not m:
            return None
        try:
            d = json.loads(m.group(0))
            return d if isinstance(d, dict) else None
        except Exception:
            return None


def translate_batch(items, args, stats, lock):
    """items: [(en, )]，返回 {en: zh}；失败抛异常由上层二分。"""
    listing = "\n".join(f"{i+1}. {en}" for i, en in enumerate(items))
    user = ("请把下面每条英文说明翻译成中文，返回 JSON 对象（键为原始英文，值为中文）：\n" + listing)
    payload = {
        "model": args.model,
        "messages": [{"role": "system", "content": SYSTEM},
                     {"role": "user", "content": user}],
        "temperature": 0.1,
        "max_tokens": min(8000, 120 * len(items) + 400),
        "response_format": {"type": "json_object"},
    }
    last = None
    for attempt in range(args.retries):
        try:
            d = api_call(args.base, args.api_key, args.model, payload)
            content = d["choices"][0]["message"]["content"]
            usage = d.get("usage") or {}
            with lock:
                stats["tokens"] += usage.get("total_tokens", 0)
                stats["calls"] += 1
            obj = parse_json_obj(content)
            if not obj:
                last = "模型未返回 JSON"
                continue
            out = {}
            for en in items:
                v = obj.get(en)
                if v is None:
                    # 模糊匹配：忽略大小写与首尾空白
                    for k2, v2 in obj.items():
                        if k2.strip().lower() == en.strip().lower():
                            v = v2
                            break
                if isinstance(v, str) and v.strip():
                    out[en] = STRIP_PREFIX.sub("", v.strip()).strip()
            if out:
                return out
            last = "返回里没有匹配的键"
        except urllib.error.HTTPError as e:
            last = f"HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:160]}"
            if e.code in (429, 500, 502, 503, 504):
                time.sleep(2 * (attempt + 1))
        except Exception as e:
            last = f"{type(e).__name__}: {str(e)[:140]}"
            time.sleep(1.5)
    raise RuntimeError(last or "unknown")


def translate_split(items, args, stats, lock, depth=0):
    """一批失败就二分重试，最小到单条。"""
    try:
        return translate_batch(items, args, stats, lock)
    except Exception as e:
        if len(items) == 1 or depth >= 3:
            with lock:
                stats["failed"].append((items[0] if items else "", str(e)[:120]))
            return {}
        mid = len(items) // 2
        out = translate_split(items[:mid], args, stats, lock, depth + 1)
        out.update(translate_split(items[mid:], args, stats, lock, depth + 1))
        return out


def targets(db, cache, only):
    seen, todo = set(), []
    for e in db["entries"]:
        en = (e.get("en") or "").strip()
        if not en or len(en) < 4:
            continue
        if only == "core" and not e.get("k"):
            continue
        if only == "game" and e.get("q") != 1:
            continue                      # q==1：官方英文已就位、中文还是规则翻译的那批
        key = en.lower()
        if key in seen or key in cache:
            continue
        seen.add(key)
        todo.append(en)
    return todo


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--api-key", required=True)
    ap.add_argument("--base", default=DEFAULT_BASE)
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--batch", type=int, default=50)
    ap.add_argument("--only", default="all", choices=["all", "core", "game"])
    ap.add_argument("--retries", type=int, default=3)
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    db = load_json(DATA / "commands.json", {})
    cache = load_json(CACHE, {})
    todo = targets(db, cache, args.only)
    if args.limit:
        todo = todo[:args.limit]
    batches = [todo[i:i + args.batch] for i in range(0, len(todo), args.batch)]
    print(f"[i] 待翻译 {len(todo)} 条 -> {len(batches)} 批 × {args.batch} 条/批，"
          f"并发 {args.workers}，模型 {args.model}")

    stats = {"tokens": 0, "calls": 0, "failed": [], "done": 0}
    lock = threading.Lock()
    t0 = time.time()

    def work(batch):
        out = translate_split(batch, args, stats, lock)
        with lock:
            stats["done"] += len(batch)
            cache.update({k.lower(): {"zh": v, "src": "deepseek",
                                      "model": args.model,
                                      "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
                          for k, v in out.items()})
            if stats["done"] % 200 < args.batch:
                save_json(CACHE, cache)
                el = time.time() - t0
                print(f"  {stats['done']}/{len(todo)}  调用 {stats['calls']} 次  "
                      f"tokens {stats['tokens']}  失败 {len(stats['failed'])}  用时 {el/60:.1f} 分")
        return len(out)

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = [ex.submit(work, b) for b in batches]
        for _ in as_completed(futs):
            pass
    save_json(CACHE, cache)
    print(f"[完成] 新增 {len(todo) - len(stats['failed'])} 条；缓存共 "
          f"{sum(1 for v in cache.values() if isinstance(v, dict) and v.get('zh'))} 条；"
          f"调用 {stats['calls']} 次，tokens {stats['tokens']}，"
          f"用时 {(time.time()-t0)/60:.1f} 分")
    if stats["failed"]:
        save_json(DATA / "mt_failed.json", stats["failed"])
        print(f"[!] 失败 {len(stats['failed'])} 条，已记录到 data/mt_failed.json")


if __name__ == "__main__":
    main()
