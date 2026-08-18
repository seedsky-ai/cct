#!/usr/bin/env python3
"""T20 probe: send once → idle 3s (upstream has closed) → send twice more, all must be 200."""
import json
import os
import time
import urllib.request

B = os.environ["ANTHROPIC_BASE_URL"]
op = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def one(tag):
    body = {"model": "deepseek-v4-flash", "max_tokens": 8,
            "messages": [{"role": "user", "content": "hi"}]}
    req = urllib.request.Request(B + "/v1/messages", data=json.dumps(body).encode(),
                                 headers={"content-type": "application/json",
                                          "anthropic-version": "2023-06-01", "x-api-key": "sk-t"})
    try:
        print(f"{tag}: {op.open(req, timeout=30).status}")
    except Exception as e:                                         # noqa: BLE001
        print(f"{tag}: FAIL {type(e).__name__} {str(e)[:60]}")


one("first")
time.sleep(3)                                      # past the upstream's 1s idle limit
one("after-idle")
one("third")
