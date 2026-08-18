#!/usr/bin/env python3
"""T18 probe (runs inside a cct session): fire 5 requests, print the status CC actually sees."""
import json
import os
import urllib.error
import urllib.request

B = os.environ["ANTHROPIC_BASE_URL"]
op = urllib.request.build_opener(urllib.request.ProxyHandler({}))

for name in ("normal", "429 rate limit", "500 upstream error", "bad JSON",
             "mid-response disconnect"):
    body = {"model": "deepseek-v4-flash", "max_tokens": 16,
            "messages": [{"role": "user", "content": "hi"}]}
    req = urllib.request.Request(B + "/v1/messages", data=json.dumps(body).encode(),
                                 headers={"content-type": "application/json",
                                          "anthropic-version": "2023-06-01",
                                          "x-api-key": "sk-test"})
    try:
        r = op.open(req, timeout=30)
        print(f"{name} → {r.status} {r.read()[:60].decode(errors='replace')}")
    except urllib.error.HTTPError as e:
        print(f"{name} → {e.code} {e.read()[:60].decode(errors='replace')}")
    except Exception as e:                                         # noqa: BLE001
        print(f"{name} → client exception {type(e).__name__}")
