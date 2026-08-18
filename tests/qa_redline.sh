#!/bin/bash
# T19 — red lines and transport paths.
#
# ⚠ Warning: needs a real ANTHROPIC_AUTH_TOKEN and burns real API credit — proving that the
#   ledger really holds no conversation content and no keys can only be done by actually
#   issuing real requests.
# Red lines: ① the ledger records token accounting only, no conversation content and no
#       key-shaped strings ② captures store only the body (no headers), keys never hit disk.
#       Paths: ③ the pinned tier applies on the streaming path too (the one real CC takes)
#       ④ for a large request body (chunked upload) the preamble is still spliced in front
#       of system.
set -u
QD=$(cd "$(dirname "$0")" && pwd)
P=0; F=0
ok()  { echo "  ✓ $1"; P=$((P+1)); }
bad() { echo "  ✗ $1"; F=$((F+1)); }
CAP=$(mktemp -d)
R=$(CCT_NO_PICKER=1 DA_CAPTURE="$CAP" cct -e deep python3 "$QD/qa_redline_probe.py" 2>&1)

# The canary question is longer than the short question of the same tier, so inp must be larger;
# the exact construction is guarded by the capture assertions below (the calibrated value is not
# hard-coded — that would scatter each tier's construction fingerprint across the repo).
CIN=$(echo "$R" | awk '/CANARY_INP/{print $2}')
SIN=$(echo "$R" | awk '/STREAM_INP/{print $2}')
if [ "${CIN:-0}" -gt "${SIN:-0}" ] 2>/dev/null; then
  ok "canary request carries the preamble (inp=$CIN > short question of same tier $SIN)"
else bad "canary: $(echo "$R" | grep CANARY)"; fi
if [ "${SIN:-0}" -gt 0 ] 2>/dev/null; then
  ok "pinned tier applies on the streaming path too (inp=$SIN; construction guarded by captures)"
else bad "stream: $(echo "$R" | grep STREAM)"; fi
case "$R" in *"BIG_INP"*) ok "large request body (~40KB, chunked) forwarded successfully";;
  *) bad "big: $(echo "$R" | grep BIG)";; esac

LED=$(ls -t "$HOME"/.cct/sessions/*.jsonl 2>/dev/null | head -1)
[ -n "$LED" ] || { bad "no ledger found for this session"; LED=/dev/null; }
if grep -q "CANARY-SECRET-PHRASE-9931" "$LED"; then bad "red line: ledger holds conversation text"
else ok "red line: zero conversation content in the ledger"; fi
if grep -qE 'sk-[A-Za-z0-9]{16,}' "$LED"; then bad "red line: key-shaped string in the ledger"
else ok "red line: zero key-shaped strings in the ledger"; fi
if grep -rqE 'sk-[A-Za-z0-9]{16,}' "$CAP"; then bad "red line: key-shaped string in the captures"
else ok "red line: zero keys in the captures (body only, no headers)"; fi

python3 - "$CAP" <<'PY'
import glob, json, os, sys
fs = sorted(glob.glob(os.path.join(sys.argv[1], "*req*")), key=os.path.getmtime)
assert len(fs) >= 3, f"expected 3 request captures, got {len(fs)}"
for f in fs:
    d = json.load(open(f))
    assert "headers" not in d, "a capture must not contain headers (key leak surface)"
    b = d.get("body") or {}
    s = b.get("system")
    t = s[0].get("text", "") if isinstance(s, list) and s and isinstance(s[0], dict) else str(s)
    assert t.startswith("Reasoning Effort"), f"preamble must be at the head of system: {t[:30]!r}"
    assert (b.get("output_config") or {}).get("effort") == "low", \
        f"effort must clear the base effort: {b.get('output_config')}"
PY
if [ $? = 0 ]; then
  ok "all three requests (plain/stream/large): preamble at the head + base effort cleared"
else bad "capture assertions failed"; fi

rm -rf "$CAP"
echo
echo "redline acceptance: passed $P / failed $F"
exit $F
