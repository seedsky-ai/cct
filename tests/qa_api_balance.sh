#!/bin/bash
# NOTE: the prompt strings below (e.g. "1+1=? digits only") are TEST DATA, not prose.
# They determine input_tokens, and the calibration assertions (60/68/89/110) are pinned to
# them. Do NOT translate or reword them -- measured: changing to English shifts inp by 2.
# Inside a balance-tier session: injection interference + two model-channel cases (the tier-name
# channel was cleaned up in 0.1.5; python, because the image has no curl)
python3 - <<'EOF'
import json, os, urllib.request, urllib.error
B = os.environ["ANTHROPIC_BASE_URL"]
K = os.environ.get("ANTHROPIC_AUTH_TOKEN", "")
op = urllib.request.build_opener(urllib.request.ProxyHandler({}))

def call(body):
    h = {"content-type": "application/json", "anthropic-version": "2023-06-01",
         "x-api-key": K}
    req = urllib.request.Request(B + "/v1/messages", data=json.dumps(body).encode(), headers=h)
    try:
        d = json.load(op.open(req, timeout=300))
    except urllib.error.HTTPError as e:
        return "ERR " + e.read().decode(errors="ignore")[:150]
    u = d.get("usage") or {}
    return f"{u.get('input_tokens', -1)} {d.get('model', '')}"

def Q(m="deepseek-v4-flash", e=None, th=None):
    # The prompt stays in Chinese on purpose: the input_tokens baseline asserted in qa_main.sh
    # T6 (62) is calibrated on these exact bytes.
    b = {"model": m, "max_tokens": 2000,
         "messages": [{"role": "user", "content": "1+1=? digits only"}]}
    if e:
        b["output_config"] = {"effort": e}
    if th:
        b["thinking"] = th
    return b

print("BAL_NOEFF", call(Q()))
print("BAL_STOMP", call(Q(e="max")))
# 0.1.6: a client turning thinking off, or to adaptive, must not weaken the pinned tier
# (CC 2.1.233 sends adaptive in practice)
print("BAL_STOMP_THINK", call(Q(e="max", th={"type": "disabled"})))
# the tier name is no longer claimed → pure passthrough, the upstream adjudicates
print("TIERNAME", call(Q(m="best")))
print("PRO_KEEP", call(Q(m="deepseek-v4-pro")))
print("FOREIGN", call(Q(m="gpt-4o")))
EOF
