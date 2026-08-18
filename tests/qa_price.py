#!/usr/bin/env python3
"""qa_price — peak/off-peak time-of-day pricing acceptance (local only, synthetic ledger, no net).
Usage: qa_price.py <directory holding cct.py>
Covers: peak/off-peak on their own · hour boundaries (9:00 peak, 12:00/18:00 off-peak) · mixed
      peak and off-peak + pro triple rate · legacy flat price table (single rate, no time-of-day
      marker). Every amount is hand-computed and nailed down; estimates are forbidden."""
import calendar
import contextlib
import io
import json
import os
import sys
import tempfile

NM = sys.argv[1] if len(sys.argv) > 1 else "."
sys.path.insert(0, NM)
import cct  # noqa: E402

TJ = json.load(open(os.path.join(NM, "tiers.json"), encoding="utf-8"))
P = F = 0


def ok(m):
    global P
    P += 1
    print(f"  ✓ {m}")


def bad(m):
    global F
    F += 1
    print(f"  ✗ {m}")


def has(name, out, want):
    if want in out:
        ok(name)
    else:
        bad(f"{name} | want [{want}] got: {out.strip()[:200]}")


def bj(h):
    """Beijing time 2026-08-17 h:00 sharp → epoch (independent of the host time zone)."""
    return calendar.timegm((2026, 8, 17, h, 0, 0)) - 8 * 3600


M = 1_000_000


def row(h, used="deepseek-v4-flash"):
    return {"ts": bj(h), "status": 200, "asked": used, "used": used,
            "tier": "balance", "inp": M, "cache_r": M, "out": M}


def run(rows, tj=TJ):
    cct._tiers = lambda *a: tj
    fd, path = tempfile.mkstemp(suffix=".jsonl")
    with os.fdopen(fd, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        cct.receipt(path)
    os.unlink(path)
    return buf.getvalue()


# Peak (Beijing 10:00), flash 1M/1M/1M: miss 3.0 + hit 0.10 + out 9.0 = 12.10
R = run([row(10)])
has("single peak row = 12.10 yuan", R, "paid ¥12.10")
has("marked as peak hours", R, "(peak-hour rate)")
# Off-peak (Beijing 3:00): 1.5 + 0.05 + 4.5 = 6.05
R = run([row(3)])
has("single off-peak row = 6.05 yuan", R, "paid ¥6.05")
has("marked as off-peak hours", R, "(off-peak rate)")
# Hour boundaries (half-open interval)
has("9:00 sharp → peak", run([row(9)]), "(peak-hour rate)")
has("12:00 sharp → off-peak", run([row(12)]), "(off-peak rate)")
has("18:00 sharp → off-peak", run([row(18)]), "(off-peak rate)")
# Mixed peak/off-peak + pro 3×: peak flash 12.10 + off-peak pro (4.5+0.15+13.5=18.15) = 30.25
R = run([row(10), row(3, "deepseek-v4-pro")])
has("mixed total = 30.25 yuan", R, "paid ¥30.25")
has("time-of-day breakdown itemized", R, "(peak 12.10 + off-peak 18.15)")
has("pro itemized at the triple rate", R, "incl. pro ¥18.15")
# Legacy flat price table: 1.0 + 0.02 + 2.0 = 3.02, and no time-of-day marker may appear
tj2 = dict(TJ)
tj2["deepseek_price_cny_per_M"] = {"input_miss": 1.0, "cache_hit": 0.02, "output": 2.0}
R = run([row(10)], tj2)
has("legacy flat price = 3.02 yuan", R, "paid ¥3.02")
if "peak" not in R:
    ok("flat price has no time-of-day marker")
else:
    bad(f"flat price shows a time-of-day marker: {R.strip()[:200]}")

print(f"\nprice acceptance: passed {P} / failed {F}")
sys.exit(1 if F else 0)
