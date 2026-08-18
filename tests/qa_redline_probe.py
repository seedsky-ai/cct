#!/usr/bin/env python3
# NOTE: the prompt strings below (e.g. "1+1=? digits only") are TEST DATA, not prose.
# They determine input_tokens, and the calibration assertions (60/68/89/110) are pinned to
# them. Do NOT translate or reword them -- measured: changing to English shifts inp by 2.
"""T19 probe (in a pinned-tier session): canary conversation + streaming + large body, one each."""
import json
import os
import urllib.request

B = os.environ["ANTHROPIC_BASE_URL"]
K = os.environ.get("ANTHROPIC_AUTH_TOKEN", "")
op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
MARK = "CANARY-SECRET-PHRASE-9931"


def post(body, stream=False):
    req = urllib.request.Request(B + "/v1/messages", data=json.dumps(body).encode(),
                                 headers={"content-type": "application/json",
                                          "anthropic-version": "2023-06-01", "x-api-key": K})
    raw = op.open(req, timeout=600).read().decode(errors="ignore")
    if not stream:
        return (json.loads(raw).get("usage") or {}).get("input_tokens")
    for line in raw.splitlines():                      # SSE: dig usage out of the stream
        if '"input_tokens"' in line and line.startswith("data: "):
            try:
                d = json.loads(line[6:])
                u = d.get("usage") or (d.get("message") or {}).get("usage") or {}
                if u.get("input_tokens"):
                    return u["input_tokens"]
            except ValueError:
                pass
    return None


base = {"model": "deepseek-v4-flash", "max_tokens": 24,
        "messages": [{"role": "user", "content": f"Remember this word: {MARK}. Reply OK only"}]}
print("CANARY_INP", post(dict(base)))

st = {"model": "deepseek-v4-flash", "max_tokens": 24, "stream": True,
      "messages": [{"role": "user", "content": "1+1=? digits only"}],
      "output_config": {"effort": "max"},
      "thinking": {"type": "adaptive", "display": "omitted"}}
print("STREAM_INP", post(st, stream=True))

big = {"model": "deepseek-v4-flash", "max_tokens": 24,
       "system": [{"type": "text", "text": "Background material. " * 4000}],   # ~40KB
       "messages": [{"role": "user", "content": "1+1=? digits only"}]}
print("BIG_INP", post(big))
