#!/bin/bash
# T16 — pinned-tier hardening (0.1.6): no client-side "thinking carrier" may weaken an injection
# tier.
# Mechanism: CC 2.1.233 sends thinking={"type":"adaptive"} on every request, and thinking depth
# follows effort; injection tiers always send effort=low (the clear-the-base-effort construction)
# → adaptive would flatten Deeper into shallow thinking.
# All criteria are deterministic: read the **body actually sent upstream** from the DA_CAPTURE
# captures, then assert relatively on input_tokens (all variants of one tier equal each other ·
# passthrough tier < injection tier), depending on no hard-coded calibrated value.
#
# ⚠ Warning: requires a real ANTHROPIC_AUTH_TOKEN, and spends real API credit
#   (two sessions × 5+2 real requests).
set -u
QD=$(cd "$(dirname "$0")" && pwd)
P=0; F=0
ok()  { echo "  ✓ $1"; P=$((P+1)); }
bad() { echo "  ✗ $1"; F=$((F+1)); }

CAP=$(mktemp -d); OUT=$(mktemp)
CCT_NO_PICKER=1 DA_CAPTURE="$CAP/deep" cct -e deep python3 "$QD/qa_pin_hard_probe.py" pinned \
  > "$OUT" 2>/dev/null
CCT_NO_PICKER=1 DA_CAPTURE="$CAP/flex" cct -e official python3 "$QD/qa_pin_hard_probe.py" flex \
  >> "$OUT" 2>/dev/null

python3 - "$CAP" "$OUT" <<'PY'
import glob, json, os, sys
cap, outf = sys.argv[1], sys.argv[2]
inp = {}
for line in open(outf):
    p = line.split()
    if len(p) >= 2:
        inp[p[0]] = p[1]
P = F = 0
def ok(m):
    global P; P += 1; print(f"  ✓ {m}")
def bad(m):
    global F; F += 1; print(f"  ✗ {m}")

def bodies(sub):
    return [json.load(open(f)).get("body") or {}
            for f in sorted(glob.glob(os.path.join(cap, sub, "*req*")), key=os.path.getmtime)]

def head(b):
    s = b.get("system")
    if isinstance(s, list) and s and isinstance(s[0], dict):
        return s[0].get("text") or ""
    return s if isinstance(s, str) else ""

# ── Pinned tier (deep): four client-side variants → always effort=low + preamble, and thinking
#    must never be disabled/adaptive
names = ["A_effort_max", "B_adaptive", "C_disabled", "D_budget", "E_unknown"]
bs = bodies("deep")
if len(bs) != 5:
    bad(f"deep should have 5 captures, got {len(bs)}")
else:
    # Baseline = the inp of the first request (client stuffs in effort=max); every variant of
    # this tier must equal it.
    # Relative assertions rather than hard-coded calibrated values: stronger semantics ("however
    # the client writes it, it lands on the same construction"), and per-tier calibrated token
    # counts are no longer scattered around the repo.
    BASE = inp.get(names[0])
    for n, b in zip(names, bs):
        oc = (b.get("output_config") or {}).get("effort")
        th = b.get("thinking")
        tt = th.get("type") if isinstance(th, dict) else None
        h = head(b)
        okk = (oc == "low" and h.startswith("Reasoning Effort")
               and (tt in (None, "enabled")) and BASE and inp.get(n) == BASE)
        (ok if okk else bad)(f"{n}: effort={oc} thinking={tt} inp={inp.get(n)}"
                             f"(baseline {BASE}) preamble={'yes' if h else 'no'}")
    # Do not add: when the client sends no thinking we do not add one either (this keeps the
    # construction identical to the calibrated one)
    ("thinking" not in bs[0]) and ok("A no thinking key → we add none") or (
        "thinking" in bs[0] and bad("A the client sent no thinking, we must not add one"))
    # Only type is flipped: every other key is preserved verbatim
    d2 = bs[1].get("thinking") or {}
    (d2.get("display") == "omitted") and ok("B adaptive→enabled, display kept verbatim") or (
        d2.get("display") != "omitted" and bad(f"B display was touched: {d2}"))
    d4 = bs[3].get("thinking") or {}
    (d4.get("budget_tokens") == 100) and ok("D budget_tokens kept verbatim") or (
        d4.get("budget_tokens") != 100 and bad(f"D budget_tokens was touched: {d4}"))
    # Drift sentinel: unknown keys / unknown type must leave a trace (visible on the spot when
    # the client changes format)
    # This test starts two sessions (deep + flex) → each has its own ledger, and the unknown
    # fields are in the deep one
    led = sorted(glob.glob(os.path.expanduser("~/.cct/sessions/*.jsonl")), key=os.path.getmtime)
    uf = []
    for p in led[-2:]:
        for line in open(p):
            try:
                uf += json.loads(line).get("unknown_fields") or []
            except ValueError:
                pass
    want = {"output_config.mystery_knob", "thinking.new_dial", "thinking.type=auto_2027"}
    (ok if want <= set(uf) else bad)(f"drift sentinel: unknown fields traced {sorted(set(uf))}")

# ── Flex: the passthrough tier is not touched at all; only the mapped tier takes over
bs = bodies("flex")
if len(bs) != 2:
    bad(f"flex should have 2 captures, got {len(bs)}")
else:
    def _i(k):
        try:
            return int(inp.get(k) or 0)
        except ValueError:
            return 0
    b, t = bs[0], (bs[0].get("thinking") or {})
    # Passthrough tier: nothing touched at all — no preamble, thinking left as adaptive
    okk = ((b.get("output_config") or {}).get("effort") == "low"
           and t.get("type") == "adaptive" and not head(b) and _i("E_pt_low") > 0)
    (ok if okk else bad)(f"E pt low: effort={(b.get('output_config') or {}).get('effort')} "
                         f"thinking={t.get('type')} inp={inp.get('E_pt_low')} (must be untouched)")
    b, t = bs[1], (bs[1].get("thinking") or {})
    # Mapped tier: takes over — preamble present, thinking reclaimed; relative assertion
    # passthrough tier < injection tier
    okk = ((b.get("output_config") or {}).get("effort") == "low"
           and t.get("type") == "enabled" and head(b)
           and _i("F_map_xhigh") > _i("E_pt_low"))
    (ok if okk else bad)(f"F mapped xhigh: effort={(b.get('output_config') or {}).get('effort')} "
                         f"thinking={t.get('type')} inp={inp.get('F_map_xhigh')} "
                         f"> passthrough {inp.get('E_pt_low')} (must take over)")

print(f"\npin_hard acceptance: passed {P} / failed {F}")
sys.exit(1 if F else 0)
PY
rc=$?
rm -rf "$CAP" "$OUT"
exit $rc
