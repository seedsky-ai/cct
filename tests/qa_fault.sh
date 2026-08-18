#!/bin/bash
# T18 — upstream fault paths (zero real network, mock upstream).
# Contract: ① upstream errors are relayed verbatim (not reworked, not swallowed) ② every single
#       request must be recorded in the ledger (the audit trail cannot have holes) ③ a mid-response
#       disconnect must hand the client an explainable 502, not a bare disconnect.
# Regression point: when reading the response fails on the non-streaming path, the ledger must
#         still get a row (status=-2) and the client must receive a 502 rather than a bare
#         disconnect.
set -u
QD=$(cd "$(dirname "$0")" && pwd)
P=0; F=0
ok()  { echo "  ✓ $1"; P=$((P+1)); }
bad() { echo "  ✗ $1"; F=$((F+1)); }

python3 "$QD/qa_fault_mock.py" 18777 &
MOCK=$!
sleep 1
RESP=$(DA_UPSTREAM=http://127.0.0.1:18777 CCT_NO_PICKER=1 cct -e deep \
       python3 "$QD/qa_fault_probe.py" 2>&1)
kill $MOCK 2>/dev/null

case "$RESP" in *"429 rate limit → 429"*) ok "429 rate limit relayed verbatim";;
  *) bad "429: $(echo "$RESP" | grep 429)";; esac
case "$RESP" in *"500 upstream error → 500"*) ok "500 upstream error relayed verbatim";;
  *) bad "500: $(echo "$RESP" | grep 500)";; esac
case "$RESP" in *"bad JSON → 200"*)
  ok "200 bad JSON forwarded verbatim (correctness adjudicated by upstream/client)";;
  *) bad "bad JSON: $(echo "$RESP" | grep JSON)";; esac
case "$RESP" in *"mid-response disconnect → 502"*)
  ok "mid-response disconnect → an explainable 502 (not a bare disconnect)";;
  *) bad "disconnect: $(echo "$RESP" | grep disconnect)";; esac

if python3 - <<'PY'
import glob, json, os
p = sorted(glob.glob(os.path.expanduser("~/.cct/sessions/*.jsonl")), key=os.path.getmtime)[-1]
st = [json.loads(l).get("status") for l in open(p) if l.strip()]
print(f"  ledger status sequence: {st}")
assert len(st) == 5, f"5 requests need 5 ledger rows (no holes in the audit trail), got {len(st)}"
assert st[1] == 429 and st[2] == 500, f"error codes must be recorded faithfully: {st}"
assert st[4] == -2, \
    f"mid-response disconnect must record status=-2 (provable after the fact), got {st[4]}"
PY
then ok "five requests → five ledger rows · error codes faithful · disconnect recorded as -2"
else bad "holes in the ledger trail"; fi

echo
echo "fault acceptance: passed $P / failed $F"
exit $F
