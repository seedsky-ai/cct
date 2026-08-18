#!/usr/bin/env python3
"""Mock upstream for T18: returns normal/429/500/bad JSON/mid-response disconnect by request index.
(Custom headers are dropped by the relay's header allowlist, so we rotate on the index instead.)"""
import json
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer

N = {"i": 0}


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        i = N["i"]
        N["i"] += 1
        self.rfile.read(int(self.headers.get("Content-Length") or 0))
        if i == 1:                                     # 429 rate limit
            b = json.dumps({"type": "error", "error": {"type": "rate_limit_error",
                                                       "message": "Too many requests"}}).encode()
            self.send_response(429)
        elif i == 2:                                   # 500
            b = b'{"type":"error","error":{"type":"api_error","message":"upstream boom"}}'
            self.send_response(500)
        elif i == 3:                                   # 200 but bad JSON
            b = b'{"broken": '
            self.send_response(200)
        elif i == 4:                                   # send headers, then cut
            self.send_response(200)
            self.send_header("Content-Length", "9999")
            self.end_headers()
            self.wfile.write(b'{"partial"')
            self.wfile.flush()
            self.close_connection = True
            return
        else:
            b = json.dumps({"id": "x", "type": "message", "role": "assistant",
                            "content": [{"type": "text", "text": "ok"}],
                            "model": "deepseek-v4-flash",
                            "usage": {"input_tokens": 7, "output_tokens": 3}}).encode()
            self.send_response(200)
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)


HTTPServer(("127.0.0.1", int(sys.argv[1])), H).serve_forever()
