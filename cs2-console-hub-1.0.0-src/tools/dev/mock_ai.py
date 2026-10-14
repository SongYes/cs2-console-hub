# -*- coding: utf-8 -*-
"""临时测试用：模拟一个 OpenAI 兼容接口，验证 CS2 Hub 的 AI 转发链路。"""
import json
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def do_GET(self):
        # /v1/models：供 AI 自检的"账户可用模型"一步使用
        if self.path.rstrip("/").endswith("/models"):
            body = json.dumps({"object": "list", "data": [
                {"id": "mock", "object": "model"},
                {"id": "deepseek-chat", "object": "model"},
                {"id": "deepseek-reasoner", "object": "model"},
            ]}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_response(404)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(n).decode("utf-8"))
        auth = self.headers.get("Authorization", "")
        assert auth.startswith("Bearer "), "缺少 Authorization"
        messages = body.get("messages", [])
        sysmsg = messages[0]["content"] if messages else ""
        usermsg = messages[-1]["content"] if messages else ""
        if "翻译" in sysmsg and "JSON" in sysmsg:
            # 翻译接口：回显一个 JSON 映射
            names = re.findall(r'"name":\s*"([^"]+)"', usermsg)
            content = json.dumps({k: f"[AI译] {k} 的中文释义（模拟）" for k in names}, ensure_ascii=False)
        elif "本地指令库摘录" in sysmsg and "[REFLECT]" in usermsg:
            # 检索质量探测：把"检索到的指令名"原样回报，供端到端断言检查
            names = re.findall(r"^([a-zA-Z_][a-zA-Z0-9_+]*)\s*\(", sysmsg, re.M)
            content = (
                "## 检索到的相关指令（回显，模拟回复）\n\n"
                + "\n".join(f"- `{n}`" for n in names[:20])
                + "\n\n```cfg\n" + (names[0] if names else "") + " 1\n```\n"
            )
        else:
            content = (
                "## 方案（模拟回复）\n\n"
                "据你要求，推荐以下指令：\n\n"
                "| 指令 | 推荐值 | 作用 |\n|---|---|---|\n"
                "| `cl_crosshaircolor` | 1 | 绿色准星 |\n"
                "| `cl_crosshairstyle` | 4 | 经典静态带中心点 |\n\n"
                "```cfg\ncl_crosshaircolor 1\ncl_crosshairstyle 4\n```\n\n"
                "注意：`sv_cheats` 类指令官方匹配无效。\n"
            )
        resp = json.dumps({
            "choices": [{"message": {"role": "assistant", "content": content}}],
            "usage": {"prompt_tokens": len(usermsg) // 4, "total_tokens": len(usermsg) // 4 + 42},
        }, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(resp)))
        self.end_headers()
        self.wfile.write(resp)


if __name__ == "__main__":
    print("mock openai-compatible api on http://127.0.0.1:8799/v1")
    ThreadingHTTPServer(("127.0.0.1", 8799), H).serve_forever()
