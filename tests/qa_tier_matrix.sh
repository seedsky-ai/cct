#!/bin/bash
# T17 — all tiers × client variants matrix (0.1.6).
#
# Why it is needed: asserting only that "our preamble got spliced in" (input_tokens) is not enough
# — the client can still change model behaviour through fields such as thinking, so the **body
# actually forwarded** has to be checked field by field.
# This test fires several adversarial client variants at **every tier** and asserts:
#   pinned tiers (Value/Classic/Extra/Deeper): whatever the client writes → inp always equals that
#                                     tier's bare baseline, and the forwarded body has effort=low
#                                     + preamble at the front + thinking not weakened;
#   Flex (official): the three official levels go straight through with their original values
#                                     (thinking untouched), medium/xhigh map onto injection tiers.
#
# ⚠ WARNING: needs a real ANTHROPIC_AUTH_TOKEN, burns real API credit (five sessions, several
#   requests per tier).
set -u
QD=$(cd "$(dirname "$0")" && pwd)
CAP=$(mktemp -d); OUT=$(mktemp)

for t in balance medium xhigh deep; do
  echo "### $t" >> "$OUT"
  CCT_NO_PICKER=1 DA_CAPTURE="$CAP/$t" cct -e "$t" \
    python3 "$QD/qa_tier_matrix_probe.py" pinned >> "$OUT" 2>/dev/null
done
echo "### official" >> "$OUT"
CCT_NO_PICKER=1 DA_CAPTURE="$CAP/official" cct -e official \
  python3 "$QD/qa_tier_matrix_probe.py" flex >> "$OUT" 2>/dev/null

python3 - "$CAP" "$OUT" <<'PY'
import glob, json, os, sys
cap, outf = sys.argv[1], sys.argv[2]
P = F = 0
def ok(m):
    global P; P += 1; print(f"  ✓ {m}")
def bad(m):
    global F; F += 1; print(f"  ✗ {m}")

res, cur = {}, None                                  # {tier: {variant: inp}}
for line in open(outf):
    line = line.strip()
    if line.startswith("### "):
        cur = line[4:]; res[cur] = {}
    elif line and cur:
        p = line.split()
        if len(p) >= 2:
            res[cur][p[0]] = p[1]

def bodies(t):
    return [json.load(open(f)).get("body") or {}
            for f in sorted(glob.glob(os.path.join(cap, t, "*req*")), key=os.path.getmtime)]

def head(b):
    s = b.get("system")
    if isinstance(s, list) and s and isinstance(s[0], dict):
        return s[0].get("text") or ""
    return s if isinstance(s, str) else ""

# ── The four pinned tiers: within one tier every variant must be equal ──
# Baseline = the inp of that tier's bare request (taken at runtime); calibrated values are not
# hard-coded — asserting "however the client writes it, it lands on the same construction" is a
# stronger statement, and it keeps each tier's construction fingerprint out of the repo.
PIN_TIERS = ["balance", "medium", "xhigh", "deep"]
VARIANTS = ["bare", "max_adaptive", "low_disabled", "xhigh_budget"]
for t in PIN_TIERS:
    want = res.get(t, {}).get("bare")
    got = [res.get(t, {}).get(v) for v in VARIANTS]
    (ok if want and all(g == want for g in got) else bad)(
        f"{t}: four client variants inp={got} (baseline {want}, must stay constant)")
    bs = bodies(t)
    if len(bs) != 4:
        bad(f"{t}: expected 4 captures, got {len(bs)}"); continue
    effs = [(b.get("output_config") or {}).get("effort") for b in bs]
    ths = [(b.get("thinking") or {}).get("type") if isinstance(b.get("thinking"), dict) else None
           for b in bs]
    pres = [bool(head(b)) for b in bs]
    (ok if all(e == "low" for e in effs) else bad)(f"{t}: forwarded effort always low {effs}")
    (ok if all(x in (None, "enabled") for x in ths) else bad)(
        f"{t}: thinking not weakened {ths} (adaptive/disabled must not appear)")
    (ok if all(pres) else bad)(f"{t}: preamble always at the head of system {pres}")
    # Differential invariant: apart from messages/thinking, all variants' forwarded bodies match
    base = {k: v for k, v in bs[0].items() if k not in ("messages", "thinking")}
    diff = [i for i, b in enumerate(bs[1:], 1)
            if {k: v for k, v in b.items() if k not in ("messages", "thinking")} != base]
    (ok if not diff else bad)(
        f"{t}: differential invariant — forwarded bodies all identical (diff items {diff})")

# ── Flex: official straight through vs injection-tier mapping ──
# Everything is asserted through ordering/equality relations, never absolute token counts:
#   low == low_disabled < high == bare < max      (official bucket monotonicity + default = high)
#   medium / xhigh equal the bare baseline of the matching injection tier (the mapping lands there)
FK = ["bare", "low", "medium", "high", "xhigh", "max", "low_disabled"]
fx = {k: res.get("official", {}).get(k) for k in FK}
def _n(k):
    try:
        return int(fx.get(k) or 0)
    except ValueError:
        return 0
order_ok = (_n("low") > 0 and _n("low") == _n("low_disabled")
            and _n("low") < _n("high") == _n("bare") < _n("max"))
(ok if order_ok else bad)(
    f"Flex official bucket ordering low==low_disabled < high==bare < max (got {fx})")
map_inp_ok = (fx.get("medium") == res.get("medium", {}).get("bare")
              and fx.get("xhigh") == res.get("xhigh", {}).get("bare"))
(ok if map_inp_ok else bad)(
    f"Flex extended tiers: inp equals the matching injection tier's baseline "
    f"(medium {fx.get('medium')} vs {res.get('medium', {}).get('bare')}, "
    f"xhigh {fx.get('xhigh')} vs {res.get('xhigh', {}).get('bare')})")
bs = bodies("official")
names = ["bare", "low", "medium", "high", "xhigh", "max", "low_disabled"]
if len(bs) != 7:
    bad(f"official: expected 7 captures, got {len(bs)}")
else:
    m = dict(zip(names, bs))
    pt_ok = all((m[n].get("output_config") or {}).get("effort") == n and not head(m[n])
                for n in ("low", "high", "max"))
    (ok if pt_ok else bad)(
        "Flex official three levels: effort value straight through + no preamble")
    th_ok = all((m[n].get("thinking") or {}).get("type") == "adaptive"
                for n in ("low", "high", "max"))
    (ok if th_ok else bad)("Flex official three levels: thinking untouched (adaptive survives)")
    dis = (m["low_disabled"].get("thinking") or {}).get("type")
    (ok if dis == "disabled" else bad)(
        f"Flex straight through: client turning thinking off is not touched either (got {dis})")
    map_ok = all((m[n].get("output_config") or {}).get("effort") == "low" and head(m[n])
                 and (m[n].get("thinking") or {}).get("type") == "enabled"
                 for n in ("medium", "xhigh"))
    (ok if map_ok else bad)(
        "Flex extended tiers: base effort cleared + preamble + thinking taken over")

print(f"\ntier_matrix acceptance: passed {P} / failed {F}")
sys.exit(1 if F else 0)
PY
rc=$?
rm -rf "$CAP" "$OUT"
exit $rc
