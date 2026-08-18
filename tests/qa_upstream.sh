#!/bin/bash
# T22 — non-official upstream semantics (zero real network, mock upstream).
# Contract: **warn only, never degrade** — tier/preamble/thinking switch are applied as usual
#         and the ledger resolves the tier as usual; the warning shows the host name only
#         (DA_UPSTREAM may carry URL-embedded credentials, so the whole string must never be
#         put on screen).
# Using 0.0.0.0 as the upstream: it is not on the allowlist (api.deepseek.com/loopback), yet it
# still reaches the local mock.
set -u
QD=$(cd "$(dirname "$0")" && pwd)
P=0; F=0
ok()  { echo "  ✓ $1"; P=$((P+1)); }
bad() { echo "  ✗ $1"; F=$((F+1)); }

python3 "$QD/qa_fault_mock.py" 18781 &
MOCK=$!
sleep 1
CAP=$(mktemp -d)
R=$(DA_UPSTREAM=http://user:tok@0.0.0.0:18781 CCT_NO_PICKER=1 DA_CAPTURE="$CAP" \
    cct -e deep python3 "$QD/qa_fault_probe.py" 2>&1)
kill $MOCK 2>/dev/null

case "$R" in *"Non-official upstream (0.0.0.0)"*)
  ok "non-official upstream: warning shows the host name only";;
  *) bad "warning missing/wrong shape: $(echo "$R" | head -1)";; esac
case "$R" in *"user:tok"*) bad "red line: the warning leaked URL-embedded credentials";;
  *) ok "red line: credentials never put on screen (full URL not printed)";; esac
case "$R" in *"◆ Deeper"*) ok "tier banner shown as usual (not degraded to pure passthrough)";;
  *) bad "banner missing: $(echo "$R" | head -3)";; esac

python3 - "$CAP" <<'PY'
import glob, json, os, sys
fs = sorted(glob.glob(os.path.join(sys.argv[1], "*req*")), key=os.path.getmtime)
assert fs, "no captures"
b = json.load(open(fs[0])).get("body") or {}
s = b.get("system")
t = s[0].get("text", "") if isinstance(s, list) and s and isinstance(s[0], dict) else ""
assert (b.get("output_config") or {}).get("effort") == "low", \
    f"base effort should be cleared: {b.get('output_config')}"
assert t.startswith("Reasoning Effort"), f"preamble must still be spliced in: {t[:40]!r}"
PY
if [ $? = 0 ]; then ok "rewrite applied as usual (base effort cleared + preamble at the head)"
else bad "rewrite was degraded"; fi

python3 - <<'PY'
import glob, json, os
p = sorted(glob.glob(os.path.expanduser("~/.cct/sessions/*.jsonl")), key=os.path.getmtime)[-1]
r = [json.loads(x) for x in open(p) if x.strip()][0]
assert r.get("tier") == "deep", f"ledger must resolve the tier normally, got tier={r.get('tier')!r}"
PY
if [ $? = 0 ]; then ok "ledger resolves the tier normally (tier=deep, not None)"
else bad "ledger did not resolve the tier"; fi

rm -rf "$CAP"
echo
echo "upstream acceptance: passed $P / failed $F"
exit $F
