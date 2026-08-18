#!/usr/bin/env python3
# NOTE: the prompt strings below (e.g. "1+1=? digits only") are TEST DATA, not prose.
# They determine input_tokens, and the calibration assertions (60/68/89/110) are pinned to
# them. Do NOT translate or reword them -- measured: changing to English shifts inp by 2.
"""Tier matrix probe (runs inside a cct session): send several client variants at one tier and
print input_tokens.
Usage: qa_tier_matrix_probe.py <pinned|flex>"""
import json
import os
import sys
import urllib.error
import urllib.request

MODE = sys.argv[1]
B = os.environ["ANTHROPIC_BASE_URL"]
K = os.environ.get("ANTHROPIC_AUTH_TOKEN", "")
op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
AD = {"type": "adaptive", "display": "omitted"}      # form observed with CC 2.1.233

PINNED = [                                           # pinned: all 4 variants land identically
    ("bare", {}),
    ("max_adaptive", {"output_config": {"effort": "max"}, "thinking": dict(AD)}),
    ("low_disabled", {"output_config": {"effort": "low"}, "thinking": {"type": "disabled"}}),
    ("xhigh_budget", {"output_config": {"effort": "xhigh"},
                      "thinking": {"type": "enabled", "budget_tokens": 100}}),
]
FLEX = [                                             # Flex: each effort word has its own channel
    ("bare", {}),
    ("low", {"output_config": {"effort": "low"}, "thinking": dict(AD)}),
    ("medium", {"output_config": {"effort": "medium"}, "thinking": dict(AD)}),
    ("high", {"output_config": {"effort": "high"}, "thinking": dict(AD)}),
    ("xhigh", {"output_config": {"effort": "xhigh"}, "thinking": dict(AD)}),
    ("max", {"output_config": {"effort": "max"}, "thinking": dict(AD)}),
    ("low_disabled", {"output_config": {"effort": "low"}, "thinking": {"type": "disabled"}}),
]

for name, extra in (PINNED if MODE == "pinned" else FLEX):
    body = {"model": "deepseek-v4-flash", "max_tokens": 32,
            "messages": [{"role": "user", "content": "1+1=? digits only"}]}
    body.update(extra)
    req = urllib.request.Request(B + "/v1/messages", data=json.dumps(body).encode(),
                                 headers={"content-type": "application/json",
                                          "anthropic-version": "2023-06-01", "x-api-key": K})
    try:
        d = json.load(op.open(req, timeout=300))
        print(name, (d.get("usage") or {}).get("input_tokens", -1))
    except urllib.error.HTTPError as e:
        print(name, "ERR", e.read().decode(errors="ignore")[:100])
