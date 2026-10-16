# -*- coding: utf-8 -*-
"""CS2 控制台指令查询中心 —— 本地服务

功能：
  1. 托管前端页面（http://127.0.0.1:8788/）
  2. /api/data       返回指令库（含版本元信息）
  3. /api/update     自动检查更新：比对上游 cvar 仓库与本地库，必要时重新抓取并重建
  4. /api/ai         代理 AI 请求到 DeepSeek / OpenAI 兼容接口（Key 由前端提供，不落盘）
  5. /api/ai/translate  批量把英文释义翻成中文，结果写入 data/zh_cache.json（越用越准）

只用 Python 标准库，无需安装任何依赖。
"""
import json
import gzip
import io
import os
import re
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from datetime import datetime, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
TOOLS = ROOT / "tools"
RAW = ROOT / "_raw"
ZH_CACHE = DATA / "zh_cache.json"
META_PATH = DATA / "db_meta.json"
HOST = "127.0.0.1"
PORT = int(os.environ.get("CS2HUB_PORT", "8788"))
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) CS2ConsoleHub/1.0"

UPSTREAMS = {
    "armync": {
        "name": "ArmynC-CS2-Cvars",
        "file": "armync_cvarlist.md",
        "url": "https://raw.githubusercontent.com/ArmynC/ArminC-CS2-Cvars/main/cvars/cvarlist.md",
        "api": "https://api.github.com/repos/ArmynC/ArminC-CS2-Cvars/commits?path=cvars/cvarlist.md&per_page=1",
        "home": "https://github.com/ArmynC/ArminC-CS2-Cvars",
    },
    "ohlasfar": {
        "name": "OhLasFar CS2 全指令仓库",
        "file": "ohlasfar_release.txt",
        "url": "https://raw.githubusercontent.com/OhLasFar/CS2-ALL-Console-Commands-Repository/main/"
               "Commands%20without%20cheat%20commands/release%20Only%20commands%20without%20cheat/"
               "_release%20Only%20commands%20without%20cheat%20FULL%20LIST.txt",
        "api": "https://api.github.com/repos/OhLasFar/CS2-ALL-Console-Commands-Repository/commits?per_page=1",
        "home": "https://github.com/OhLasFar/CS2-ALL-Console-Commands-Repository",
    },
}

_update_lock = threading.Lock()
_zh_lock = threading.Lock()

# --------------------------------------------------------------------------- #
# 工具
# --------------------------------------------------------------------------- #


def read_json(path: Path, default=None):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def write_json(path: Path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)


def fetch(url: str, timeout=40):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def http_json(url: str, payload=None, headers=None, timeout=120):
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, method="POST" if data else "GET")
    req.add_header("User-Agent", UA)
    req.add_header("Content-Type", "application/json")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


# --------------------------------------------------------------------------- #
# 指令库元信息
# --------------------------------------------------------------------------- #


def build_meta():
    """扫描 data/commands.json，生成 db_meta.json（版本、签名、统计、上游指纹）。"""
    db = read_json(DATA / "commands.json", {})
    if not db:
        return {"ok": False, "error": "data/commands.json 不存在，请先运行 tools/build_db.py"}
    entries = db.get("entries", [])
    names = [e["n"] for e in entries]
    version = db.get("version") or datetime.now(timezone.utc).strftime("%Y.%m.%d")
    meta = {
        "ok": True,
        "version": version,
        "built_at": db.get("generated_at"),
        "count": len(entries),
        "core_count": sum(1 for e in entries if e.get("k")),
        "release_count": sum(1 for e in entries if e.get("r")),
        "new_count": db.get("new_count") or sum(1 for e in entries if e.get("st") == "new"),
        "tracked_at": db.get("tracked_at"),
        "hand_zh": sum(1 for e in entries if e.get("q") == 2),
        "auto_zh": sum(1 for e in entries if e.get("q") == 1),
        "game_verified": db.get("game_verified") or sum(1 for e in entries if e.get("gv")),
        "wiki_only": db.get("wiki_only") or sum(1 for e in entries if not e.get("gv")),
        "cmd_count": db.get("cmd_count") or 0,
        "source": db.get("source"),
        "sha256": __import__("hashlib").sha256(
            ",".join(sorted(names)).encode("utf-8")).hexdigest()[:16],
        "fingerprints": {},
    }
    # 上游指纹（GitHub commit 接口 + 本地原始文件内容哈希）
    for key, up in UPSTREAMS.items():
        item = {"name": up["name"]}
        raw_path = RAW / up["file"]
        if raw_path.exists():
            item["sha"] = __import__("hashlib").sha256(raw_path.read_bytes()).hexdigest()[:12]
            item["bytes"] = raw_path.stat().st_size
        try:
            commits = http_json(up["api"], timeout=25)
            if isinstance(commits, list) and commits:
                item["commit"] = commits[0]["sha"][:12]
                item["date"] = commits[0]["commit"]["committer"]["date"]
                item["message"] = commits[0]["commit"]["message"].splitlines()[0][:120]
        except Exception as exc:  # 网络不可用时静默降级
            item["error"] = str(exc)[:160]
        meta["fingerprints"][key] = item
    write_json(META_PATH, meta)
    return meta


def load_meta(rebuild_if_missing=True):
    meta = read_json(META_PATH)
    if not meta or not meta.get("ok"):
        if rebuild_if_missing:
            meta = build_meta()
        else:
            meta = {"ok": False, "error": "缺少 db_meta.json"}
    return meta or {"ok": False, "error": "未知错误"}


# --------------------------------------------------------------------------- #
# 更新流程
# --------------------------------------------------------------------------- #


def check_update(deep=False):
    """检查上游是否有更新。deep=True 时直接比对文件内容（更准但更慢）。"""
    meta = load_meta()
    if not meta.get("ok"):
        return {"ok": False, "error": meta.get("error", "指令库元信息缺失")}

    result = {
        "ok": True,
        "local_version": meta.get("version"),
        "local_count": meta.get("count"),
        "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "upstream": [],
        "update_available": False,
        "reasons": [],
    }
    old = meta.get("fingerprints", {})
    for key, up in UPSTREAMS.items():
        item = {"key": key, "name": up["name"], "home": up["home"]}
        try:
            if deep:
                body = fetch(up["url"], timeout=90)
                new_sha = __import__("hashlib").sha256(body).hexdigest()[:12]
                item["remote_sha"] = new_sha
                item["local_sha"] = old.get(key, {}).get("sha")
                changed = new_sha != item["local_sha"]
                item["content_bytes"] = len(body)
                if changed:
                    (RAW / up["file"]).parent.mkdir(parents=True, exist_ok=True)
                    (RAW / up["file"]).write_bytes(body)
            else:
                commits = http_json(up["api"], timeout=25)
                commit = commits[0]["sha"][:12] if isinstance(commits, list) and commits else None
                cdate = commits[0]["commit"]["committer"]["date"] if commit else None
                item["remote_commit"] = commit
                item["local_commit"] = old.get(key, {}).get("commit")
                item["commit_date"] = cdate
                changed = bool(commit and commit != item["local_commit"])
                # 提交时间晚于本地库生成时间，也认为上游有新内容（即使 commit 已被记录）
                if commit and cdate and meta.get("built_at"):
                    try:
                        _t = datetime.fromisoformat(cdate.replace("Z", "+00:00"))
                        _b = datetime.fromisoformat(str(meta["built_at"]).replace("Z", "+00:00"))
                        if _t > _b:
                            item["newer_than_local"] = True
                    except Exception:
                        pass
            item["changed"] = changed
            if changed:
                result["update_available"] = True
                result["reasons"].append(f"{up['name']} 有更新")
            elif item.get("newer_than_local"):
                result["update_available"] = True
                result["reasons"].append(f"{up['name']} 在本地库生成之后有新提交")
        except Exception as exc:
            item["error"] = str(exc)[:200]
        result["upstream"].append(item)

    # 本地库是否比上游 release 列表少条目（粗略判断指令新增）
    try:
        db = read_json(DATA / "commands.json", {})
        local_names = {e["n"] for e in db.get("entries", [])}
        rel_path = RAW / UPSTREAMS["ohlasfar"]["file"]
        if rel_path.exists():
            remote_names = set()
            for line in rel_path.read_text(encoding="utf-8", errors="replace").splitlines():
                if ":" in line:
                    nm = line.split(":")[0].strip()
                    if nm and " " not in nm:
                        remote_names.add(nm)
            added = sorted(remote_names - local_names)
            if added:
                result["update_available"] = True
                result["new_commands"] = added[:200]
                result["new_command_count"] = len(added)
                result["reasons"].append(f"上游出现 {len(added)} 条本地库没有的指令")
    except Exception:
        pass
    return result


def rebuild_db():
    """重新运行构建流水线（在子进程里，避免污染本进程模块状态）。"""
    import subprocess
    py = sys.executable
    script = TOOLS / "build_db.py"
    proc = subprocess.run([py, str(script)], cwd=str(TOOLS),
                          capture_output=True, text=True, encoding="utf-8", errors="replace")
    ok = proc.returncode == 0
    meta = build_meta() if ok else {}
    return {
        "ok": ok,
        "returncode": proc.returncode,
        "stdout": (proc.stdout or "")[-2000:],
        "stderr": (proc.stderr or "")[-2000:],
        "meta": meta,
    }


def run_update():
    """完整更新：抓上游 → 重建库 → 刷新元信息。"""
    if not _update_lock.acquire(blocking=False):
        return {"ok": False, "error": "已有更新任务正在执行"}
    steps = []
    try:
        chk = check_update(deep=True)
        steps.append({"step": "抓取上游数据", "result": {
            k: chk.get(k) for k in ("update_available", "reasons", "new_command_count")}})
        rb = rebuild_db()
        steps.append({"step": "重建指令库", "result": {"ok": rb["ok"], "returncode": rb["returncode"],
                                                     "stderr": rb["stderr"][-400:]}})
        meta = load_meta()
        return {"ok": rb["ok"], "steps": steps, "meta": meta}
    finally:
        _update_lock.release()


# --------------------------------------------------------------------------- #
# AI：批量翻译缓存
# --------------------------------------------------------------------------- #


def dedupe_words(text):
    """数据自愈：清掉机器翻译遗留的循环重复词（如「打印输出输出」）。"""
    if not text:
        return text
    import re as _re
    t = _re.sub(r"(?:机器人\s*)+Bot", "机器人 Bot", text)
    t = _re.sub(r"\bBot(?:\s+Bot)+\b", "Bot", t)
    t = _re.sub(r"打印输出输出", "打印输出", t)
    for _ in range(4):
        before = t
        t = _re.sub(r"([\u4e00-\u9fff]{2,6})\1+", r"\1", t)
        t = _re.sub(r"\b([A-Za-z][A-Za-z0-9_]{1,15})\b(?:\s+\1\b)+", r"\1", t, flags=_re.I)
        if t == before:
            break
    return t


def apply_zh_cache(db):
    """套用构建时确定的机器翻译结果（data/zh_mt.json）。

    规则：只有构建阶段判定「规则翻译不理想」的条目才会出现在这里，
    所以这里直接覆盖即可，不会覆盖人工精校的释义。
    """
    mt = read_json(DATA / "zh_mt.json", {}) or {}
    hits = 0
    for e in db.get("entries", []):
        zh = mt.get(e["n"])
        if zh and e.get("q") != 2:
            e["z"] = zh
            e["q"] = 3
            hits += 1
        # 无论来源，出口前统一自愈一遍
        if e.get("z"):
            e["z"] = dedupe_words(e["z"])
    return hits


# --------------------------------------------------------------------------- #
# HTTP
# --------------------------------------------------------------------------- #

MIME = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".ico": "image/x-icon",
    ".woff2": "font/woff2",
    ".txt": "text/plain; charset=utf-8",
    ".md": "text/markdown; charset=utf-8",
}


class Handler(SimpleHTTPRequestHandler):
    server_version = "CS2ConsoleHub/1.0"
    protocol_version = "HTTP/1.1"

    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(ROOT), **kw)

    # ---------- 基础 ----------
    def log_message(self, fmt, *args):
        if self.path.startswith("/api/"):
            sys.stderr.write("[%s] %s\n" % (time.strftime("%H:%M:%S"), fmt % args))

    def guess_type(self, path):
        ext = Path(str(path)).suffix.lower()
        return MIME.get(ext) or super().guess_type(path)

    def _send_json(self, obj, code=200, gzip_ok=True):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        ctype = "application/json; charset=utf-8"
        headers = [("Cache-Control", "no-store")]
        if gzip_ok and len(body) > 2048 and "gzip" in self.headers.get("Accept-Encoding", ""):
            buf = io.BytesIO()
            with gzip.GzipFile(fileobj=buf, mode="wb", compresslevel=6) as gz:
                gz.write(body)
            body = buf.getvalue()
            headers.append(("Content-Encoding", "gzip"))
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        for k, v in headers:
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n <= 0:
            return {}
        try:
            return json.loads(self.rfile.read(n).decode("utf-8", "replace"))
        except Exception:
            return {}

    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Content-Length", "0")
        self.end_headers()

    # ---------- 路由 ----------
    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/api/data":
            db = read_json(DATA / "commands.json", {})
            n = apply_zh_cache(db)
            db["ai_zh_applied"] = n
            db["meta"] = load_meta(rebuild_if_missing=False)
            return self._send_json(db)
        if path == "/api/meta":
            return self._send_json(load_meta())
        if path == "/api/update/check":
            deep = "deep=1" in self.path
            return self._send_json(check_update(deep=deep))
        if path == "/api/zh_cache":
            return self._send_json(read_json(ZH_CACHE, {}) or {})
        if path == "/api/health":
            return self._send_json({"ok": True, "root": str(ROOT),
                                    "python": sys.version.split()[0],
                                    "time": datetime.now().isoformat(timespec="seconds")})
        return super().do_GET()

    def do_POST(self):
        path = self.path.split("?")[0]
        body = self._read_body()

        if path == "/api/update/run":
            return self._send_json(run_update())
        if path == "/api/meta/rebuild":
            return self._send_json(build_meta())

        if path == "/api/ai":
            return self._proxy_ai(body)

        if path == "/api/ai/models":
            return self._ai_models(body)

        if path == "/api/ai/translate":
            return self._ai_translate(body)

        return self._send_json({"ok": False, "error": "未知接口 " + path}, 404)

    # ---------- AI 代理 ----------
    def _ai_models(self, body):
        """列出上游账户可用的模型名，用来排除"模型名写错"这一类问题。"""
        base = (body.get("base_url") or "https://api.deepseek.com/v1").rstrip("/")
        key = body.get("api_key") or ""
        if not key:
            return self._send_json({"ok": False, "error": "缺少 API Key（请在界面右上角设置）"}, 400)
        if not re.match(r"^https?://", base):
            return self._send_json({"ok": False, "error": "base_url 必须是 http(s) 地址"}, 400)
        try:
            data = http_json(base + "/models", None, {"Authorization": "Bearer " + key}, timeout=60)
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:400]
            hint = {401: "API Key 无效或已失效", 402: "余额不足", 404: "Base URL 不对（要带 /v1）",
                    429: "限流"}.get(exc.code, "")
            return self._send_json({"ok": False, "error": f"上游返回 {exc.code}", "hint": hint,
                                    "detail": detail}, 502)
        except Exception as exc:
            return self._send_json({"ok": False, "error": "请求失败：" + str(exc)[:200]}, 502)
        items = data.get("data") if isinstance(data, dict) else None
        names = []
        for it in (items or []):
            n = it.get("id") if isinstance(it, dict) else None
            if n:
                names.append(n)
        return self._send_json({"ok": True, "base_url": base, "count": len(names),
                                "models": sorted(names)})

    def _proxy_ai(self, body):
        base = (body.get("base_url") or "https://api.deepseek.com/v1").rstrip("/")
        key = body.get("api_key") or ""
        model = body.get("model") or "deepseek-chat"
        messages = body.get("messages") or []
        temperature = body.get("temperature", 0.2)
        # 默认给足：推理型模型（reasoner / v4-pro 之类）会把一部分预算用于"思考"，
        # 给太小会导致正文为空而误判成 Key 失效。
        max_tokens = int(body.get("max_tokens") or 4096)
        if not key:
            return self._send_json({"ok": False, "error": "缺少 API Key（请在界面右上角设置）"}, 400)
        if not re.match(r"^https?://", base):
            return self._send_json({"ok": False, "error": "base_url 必须是 http(s) 地址"}, 400)
        url = base + "/chat/completions"
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }
        try:
            data = http_json(url, payload, {"Authorization": "Bearer " + key}, timeout=180)
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:500]
            hint = ""
            if exc.code == 401:
                hint = "API Key 无效或已失效，请到「接口设置」重新填写"
            elif exc.code == 402:
                hint = "账户余额不足，请到服务商后台充值"
            elif exc.code == 404:
                hint = "模型名或接口地址不对，检查 Base URL（要带 /v1）与模型名"
            elif exc.code == 429:
                hint = "触发限流或配额用尽，稍后再试或换模型"
            return self._send_json({"ok": False, "error": f"上游返回 {exc.code}",
                                    "hint": hint, "detail": detail,
                                    "request": {"base_url": base, "model": model,
                                                "messages": len(messages)}}, 502)
        except Exception as exc:
            return self._send_json({"ok": False, "error": "请求失败：" + str(exc)[:300],
                                    "hint": "多为中心网络问题或接口地址不可达；可先用「测试连接」确认",
                                    "request": {"base_url": base, "model": model}}, 502)
        try:
            content = data["choices"][0]["message"]["content"]
        except Exception:
            return self._send_json({"ok": False, "error": "上游响应格式异常",
                                    "detail": str(data)[:500]}, 502)
        usage = data.get("usage") or {}
        # 有些是推理型模型（deepseek-reasoner / v4-pro 之类）：输出预算会先被"思考"吃掉，
        # 然后正文为空、finish_reason=length。这时要明确告诉用户是 token 不够，不是 Key 坏了。
        finish = (data["choices"][0].get("finish_reason") or "")
        detail = usage.get("completion_tokens_details") or {}
        reasoning = int(detail.get("reasoning_tokens") or 0)
        completion = int(usage.get("completion_tokens") or 0)
        if (not (content or "").strip()) and (finish == "length"
                                              or (completion and reasoning >= completion)):
            return self._send_json({
                "ok": True, "content": "", "usage": usage, "model": model,
                "truncated_by_reasoning": True,
                "hint": (f"输出预算被推理过程吃光了（推理 {reasoning} / 输出 {completion} token，"
                         f"max_tokens={max_tokens}）。这不是 Key 或余额的问题："
                         "要么把 max_tokens 调大（推理模型建议 ≥ 1024），"
                         "要么换非推理模型（如 deepseek-chat）。"),
            })
        if (not (content or "").strip()):
            return self._send_json({
                "ok": True, "content": "", "usage": usage, "model": model,
                "empty_content": True,
                "hint": ("上游返回 200 但正文为空。常见原因：模型名不存在（网关静默返回空）、"
                         "内容被安全策略拦截、或该模型只产出推理内容。换 deepseek-chat 试一次即可区分。"),
            })
        return self._send_json({"ok": True, "content": content, "usage": usage, "model": model})

    def _ai_translate(self, body):
        """把一批英文释义翻成中文，写入 data/zh_cache.json。"""
        items = body.get("items") or []
        base = (body.get("base_url") or "https://api.deepseek.com/v1").rstrip("/")
        key = body.get("api_key") or ""
        model = body.get("model") or "deepseek-chat"
        if not key:
            return self._send_json({"ok": False, "error": "缺少 API Key"}, 400)
        if not items:
            return self._send_json({"ok": False, "error": "items 为空"}, 400)
        if not re.match(r"^https?://", base):
            return self._send_json({"ok": False, "error": "base_url 必须是 http(s) 地址"}, 400)

        sys_prompt = (
            "你是 CS2（反恐精英2）控制台指令专家。用户给出若干条 cvar/命令的英文官方说明，"
            "请为每一条翻译成简洁、准确、面向中文玩家的释义。要求：\n"
            "1. 保留指令名与技术缩写（如 FOV、HUD、HRTF、tick）；\n"
            "2. 如果说明里有默认值/取值范围，保留其数值含义；\n"
            "3. 每条不超过 60 个汉字，不要添加原文没有的信息；\n"
            "4. 严格输出 JSON 对象，键为指令名，值为中文释义字符串，不要输出多余文字。"
        )
        compact = [{"name": it.get("n"), "desc": (it.get("en") or "")[:400]} for it in items[:40]]
        user_prompt = "请翻译以下指令说明并返回 JSON：\n" + json.dumps(compact, ensure_ascii=False)

        try:
            data = http_json(base + "/chat/completions", {
                "model": model,
                "messages": [{"role": "system", "content": sys_prompt},
                             {"role": "user", "content": user_prompt}],
                "temperature": 0.1,
                "max_tokens": 4096,
                "response_format": {"type": "json_object"},
            }, {"Authorization": "Bearer " + key}, timeout=240)
            content = data["choices"][0]["message"]["content"]
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:400]
            return self._send_json({"ok": False, "error": f"上游返回 {exc.code}", "detail": detail}, 502)
        except Exception as exc:
            return self._send_json({"ok": False, "error": "请求失败：" + str(exc)[:300]}, 502)

        text = content.strip()
        text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.M).strip()
        try:
            mapping = json.loads(text)
        except Exception:
            m = re.search(r"\{.*\}", text, re.S)
            mapping = json.loads(m.group(0)) if m else {}
        if not isinstance(mapping, dict):
            return self._send_json({"ok": False, "error": "模型未返回 JSON 对象", "raw": text[:400]}, 502)

        with _zh_lock:
            cache = read_json(ZH_CACHE, {}) or {}
            saved = 0
            for name, zh in mapping.items():
                if isinstance(zh, str) and zh.strip():
                    cache[name] = {"zh": zh.strip(),
                                   "src": "ai",
                                   "model": model,
                                   "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
                    saved += 1
            write_json(ZH_CACHE, cache)
        return self._send_json({"ok": True, "saved": saved, "total_cached": len(cache)})


def main():
    if not (DATA / "commands.json").exists():
        print("[!] 未找到 data/commands.json，正在首次构建指令库…")
        rb = rebuild_db()
        if not rb["ok"]:
            print("[!] 构建失败：", rb.get("stderr"))
    else:
        # 后台刷新元信息（不阻塞启动）
        threading.Thread(target=build_meta, daemon=True).start()

    srv = ThreadingHTTPServer((HOST, PORT), Handler)
    url = f"http://{HOST}:{PORT}/"
    print("=" * 62)
    print("  CS2 控制台指令查询中心")
    print("  地址： " + url)
    print("  指令库：" + str(DATA / "commands.json"))
    print("  按 Ctrl+C 退出")
    print("=" * 62)
    if "--no-browser" not in sys.argv:
        threading.Thread(target=lambda: (time.sleep(0.8), webbrowser.open(url)), daemon=True).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n已退出。")
    finally:
        srv.server_close()


if __name__ == "__main__":
    main()
