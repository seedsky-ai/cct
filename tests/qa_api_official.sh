#!/bin/bash
# NOTE: the prompt strings below (e.g. "1+1=? digits only") are TEST DATA, not prose.
# They determine input_tokens, and the calibration assertions (60/68/89/110) are pinned to
# them. Do NOT translate or reword them -- measured: changing to English shifts inp by 2.
# API semantics probe inside an official-tier session (python, because the image has no curl)
python3 - <<'EOF'
import json, os, urllib.request, urllib.error
B = os.environ["ANTHROPIC_BASE_URL"]
K = os.environ.get("ANTHROPIC_AUTH_TOKEN", "")
op = urllib.request.build_opener(urllib.request.ProxyHandler({}))

def call(body, auth=True):
    h = {"content-type": "application/json", "anthropic-version": "2023-06-01"}
    if auth:
        h["x-api-key"] = K
    req = urllib.request.Request(B + "/v1/messages", data=json.dumps(body).encode(), headers=h)
    try:
        d = json.load(op.open(req, timeout=300))
    except urllib.error.HTTPError as e:
        return "ERR " + e.read().decode(errors="ignore")[:150]
    u = d.get("usage") or {}
    return f"{u.get('input_tokens', -1)} {d.get('model', '')}"

def Q(m="deepseek-v4-flash", e=None):
    # The prompt stays in Chinese on purpose: the input_tokens baselines asserted in qa_main.sh
    # T5 (91/12/104/47/70) are calibrated on these exact bytes.
    b = {"model": m, "max_tokens": 2000,
         "messages": [{"role": "user", "content": "1+1=? digits only"}]}
    if e:
        b["output_config"] = {"effort": e}
    return b

print("OFF_NOEFF", call(Q()))
print("OFF_LOW", call(Q(e="low")))
print("OFF_MAX", call(Q(e="max")))
# 0.1.3 CC effort mapping (official session): medium/xhigh → calibrated injection tiers,
# everything else goes straight through with its original value
print("OFF_MED", call(Q(e="medium")))
print("OFF_XH", call(Q(e="xhigh")))
print("NOAUTH", call(Q(), auth=False))
EOF
