# -*- coding: utf-8 -*-
"""模拟"推理型模型"：思考 token 随问题复杂度增长，输出预算不够就只返回推理、正文为空。

用来验证「预算不够 → 前端自动升档重试」这条链路。
预算足够时返回正文；不够时复刻真实响应（content 空、finish_reason=length、
completion_tokens_details.reasoning_tokens 吃满预算）。
"""
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = 8801
# 模拟这道题的"思考成本"：prompt 越长，需要越多思考 token
BASE_THINK = 700


class H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.path.rstrip("/").endswith("/models"):
            body = json.dumps({"object": "list", "data": [
                {"id": "deepseek-reasoner", "object": "model"},
                {"id": "deepseek-flash", "object": "model"},
            ]}).encode()
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
        body = json.loads(self.rfile.read(n) or b"{}")
        budget = int(body.get("max_tokens") or 0)
        msgs = body.get("messages") or []
        prompt_len = sum(len(str(m.get("content", ""))) for m in msgs)
        think = BASE_THINK + prompt_len // 2          # 思考成本随上下文增长
        if budget <= think:
            data = {
                "id": "mock", "object": "chat.completion", "model": body.get("model"),
                "choices": [{"index": 0, "message": {"role": "assistant", "content": ""},
                             "finish_reason": "length"}],
                "usage": {"prompt_tokens": prompt_len // 4,
                          "completion_tokens": budget, "total_tokens": budget + prompt_len // 4,
                          "completion_tokens_details": {"reasoning_tokens": budget}},
            }
        else:
            text = "## 方案\n\n预算够用，正文正常返回。\n\n```cfg\ncl_crosshaircolor 1\n```\n"
            data = {
                "id": "mock", "object": "chat.completion", "model": body.get("model"),
                "choices": [{"index": 0, "message": {"role": "assistant", "content": text},
                             "finish_reason": "stop"}],
                "usage": {"prompt_tokens": prompt_len // 4,
                          "completion_tokens": think + 60,
                          "total_tokens": think + 60 + prompt_len // 4,
                          "completion_tokens_details": {"reasoning_tokens": think}},
            }
        raw = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


if __name__ == "__main__":
    print(f"[mock-reasoning] http://127.0.0.1:{PORT}/v1  （思考成本随上下文增长）")
    ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
