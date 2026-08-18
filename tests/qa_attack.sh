#!/bin/bash
# T21 — attack test (0.1.6): exhaust every client-side means of defeating the pinned tier (Deeper).
# Covers 20 variants: six thinking forms (including malformed) · four effort forms (including
# non-dict) · model-name tricks · system-position attacks · sampling/budget bypass · forged
# future fields.
# Contract: ① no variant may change the tier construction (inp is always equal to the bare
#         baseline of the same tier; a client-supplied system only stacks on top, it never
#         pushes the preamble out) ② malformed input (non-dict output_config/thinking, etc.)
#         must not crash the relay ③ forged future fields must be recorded in the ledger by
#         the sentinel.
#
# ⚠ Needs a real ANTHROPIC_AUTH_TOKEN; burns real API credit (20+ shots in one session).
set -u
QD=$(cd "$(dirname "$0")" && pwd)
P=0; F=0
ok()  { echo "  ✓ $1"; P=$((P+1)); }
bad() { echo "  ✗ $1"; F=$((F+1)); }
CAP=$(mktemp -d)
R=$(CCT_NO_PICKER=1 DA_CAPTURE="$CAP" cct -e deep python3 "$QD/qa_attack_probe.py" 2>&1 \
    | grep -E "^[A-F][0-9]")

if echo "$R" | grep -q "EXC"; then bad "relay crashed: $(echo "$R" | grep EXC)"
else ok "20 attack variants, zero crashes"; fi

# Baseline = the inp of the first bare request; every other shot must equal it one by one. The
# calibrated value is deliberately not hard-coded into the test — asserting "all variants of one
# tier equal each other" is the stronger statement, and it keeps per-tier calibrated token counts
# from being scattered across the repo.
BASE=$(echo "$R" | grep -E "^A1_" | awk '{print $2}')
[ -n "$BASE" ] || bad "could not obtain the bare baseline (A1)"
badpin=$(echo "$R" | grep -E "^(A[1-4]|B[1-3]|C[12]|E[1-3]|F1)_" | grep -v " $BASE " || true)
if [ -z "$badpin" ]; then
  ok "thinking/effort/model-name/sampling attacks → pinned inp always equals the baseline"
else bad "pin defeated (baseline $BASE): $badpin"; fi

sysvals=$(echo "$R" | grep -E "^D[123]_" | awk '{print $2}' | tr '\n' ' ')
# system-position attack: a client-supplied system can only push inp up (it stacks); it must never
# push the preamble out and thereby drop inp below the baseline
sysbad=$(for v in $sysvals; do [ "${v:-0}" -ge "${BASE:-0}" ] || echo "$v"; done)
if [ -z "$sysbad" ]; then
  ok "system-position attack: client system only stacks, never displaces the preamble ($sysvals)"
else bad "system attack (below baseline $BASE): $sysbad"; fi

python3 - "$CAP" <<'PY'
import glob, json, os, sys
fs = sorted(glob.glob(os.path.join(sys.argv[1], "*req*")), key=os.path.getmtime)
n = 0
for f in fs:
    b = json.load(open(f)).get("body") or {}
    s = b.get("system")
    t = s[0].get("text", "") if isinstance(s, list) and s and isinstance(s[0], dict) else (
        s if isinstance(s, str) else "")
    if not t.startswith("Reasoning Effort"):
        raise SystemExit(f"preamble is not at the head: {t[:40]!r}")
    th = b.get("thinking")
    if isinstance(th, dict) and th.get("type") not in (None, "enabled"):
        raise SystemExit(f"thinking not reclaimed: {th}")
    n += 1
print(f"  checked {n} captures: preamble always at the head of system · thinking never weakened")
PY
if [ $? = 0 ]; then ok "capture-by-capture check: preamble at the head + thinking reclaimed"
else bad "capture check failed"; fi

led=$(ls -t "$HOME"/.cct/sessions/*.jsonl 2>/dev/null | head -1)
if [ -z "$led" ]; then bad "no ledger found for this session"; led=/dev/null; fi
if grep -q "output_config.depth" "$led" && grep -q "top.reasoning_effort" "$led"; then
  ok "sentinel: forged future fields (output_config.depth / top.reasoning_effort) traced"
else bad "sentinel left no trace: $(grep -o 'unknown_fields[^]]*]' "$led" | tail -1)"; fi

rm -rf "$CAP"
echo
echo "attack acceptance: passed $P / failed $F"
exit $F
