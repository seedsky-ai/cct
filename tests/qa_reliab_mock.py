#!/usr/bin/env python3
"""Mock upstream for T20: HTTP/1.1 keep-alive, but closes the connection after 1s of idle —
forces the connection-reuse self-heal path."""
import json
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer


class H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    timeout = 1                                    # cut as soon as idle for 1s

    def log_message(self, *a):
        pass

    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length") or 0))
        b = json.dumps({"id": "x", "type": "message", "role": "assistant",
                        "content": [{"type": "text", "text": "ok"}],
                        "model": "deepseek-v4-flash",
                        "usage": {"input_tokens": 5, "output_tokens": 2}}).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)


HTTPServer(("127.0.0.1", int(sys.argv[1])), H).serve_forever()
