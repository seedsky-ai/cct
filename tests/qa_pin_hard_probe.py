#!/usr/bin/env python3
# NOTE: the prompt strings below (e.g. "1+1=? digits only") are TEST DATA, not prose.
# They determine input_tokens, and the calibration assertions (60/68/89/110) are pinned to
# them. Do NOT translate or reword them -- measured: changing to English shifts inp by 2.
"""Pinned-tier hardening probe (runs inside a cct session): sends adversarial requests and prints
input_tokens for the caller to assert on.
Usage: qa_pin_hard_probe.py pinned|flex"""
import json
import os
import sys
import urllib.error
import urllib.request

MODE = sys.argv[1] if len(sys.argv) > 1 else "pinned"
B = os.environ["ANTHROPIC_BASE_URL"]
K = os.environ.get("ANTHROPIC_AUTH_TOKEN", "")
op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
ADAPTIVE = {"type": "adaptive", "display": "omitted"}      # form observed with CC 2.1.233

CASES = {
    "pinned": [                                            # pinned tier: all 4 variants → Deeper
        ("A_effort_max", {"output_config": {"effort": "max"}}),
        ("B_adaptive", {"output_config": {"effort": "low"}, "thinking": dict(ADAPTIVE)}),
        ("C_disabled", {"thinking": {"type": "disabled"}}),
        ("D_budget", {"thinking": {"type": "enabled", "budget_tokens": 100}}),
        ("E_unknown", {"output_config": {"effort": "low", "mystery_knob": 5},
                       "thinking": {"type": "auto_2027", "new_dial": 1}}),  # drift sentinel
    ],
    "flex": [                                              # Flex: pt untouched, mapped takes over
        ("E_pt_low", {"output_config": {"effort": "low"}, "thinking": dict(ADAPTIVE)}),
        ("F_map_xhigh", {"output_config": {"effort": "xhigh"}, "thinking": dict(ADAPTIVE)}),
    ],
}

for name, extra in CASES[MODE]:
    body = {"model": "deepseek-v4-flash", "max_tokens": 64,
            "messages": [{"role": "user", "content": "1+1=? digits only"}]}
    body.update(extra)
    req = urllib.request.Request(B + "/v1/messages", data=json.dumps(body).encode(),
                                 headers={"content-type": "application/json",
                                          "anthropic-version": "2023-06-01", "x-api-key": K})
    try:
        d = json.load(op.open(req, timeout=300))
        print(name, (d.get("usage") or {}).get("input_tokens", -1))
    except urllib.error.HTTPError as e:
        print(name, "ERR", e.read().decode(errors="ignore")[:120])
