#!/bin/bash
# T20 — reliability paths (zero real network, mock upstream).
# ① two concurrent sessions: port isolation · no stray relay after exit (a stray relay holds a
#   port and can be reached by other processes on the same box)
# ② connection reuse self-heals after idling: the upstream drops idle connections after 1s, so a
#   request sent 3s later must rebuild automatically (select liveness pre-check +
#   RemoteDisconnected retry), otherwise users randomly eat 502s.
set -u
QD=$(cd "$(dirname "$0")" && pwd)
P=0; F=0
ok()  { echo "  ✓ $1"; P=$((P+1)); }
bad() { echo "  ✗ $1"; F=$((F+1)); }

S1=$(mktemp); S2=$(mktemp)
CCT_NO_PICKER=1 cct -e deep    bash -c 'echo P=${ANTHROPIC_BASE_URL##*:}; sleep 3' > "$S1" 2>&1 &
A=$!
CCT_NO_PICKER=1 cct -e balance bash -c 'echo P=${ANTHROPIC_BASE_URL##*:}; sleep 3' > "$S2" 2>&1 &
B=$!
wait $A $B
p1=$(grep -o 'P=[0-9]*' "$S1" | cut -d= -f2); p2=$(grep -o 'P=[0-9]*' "$S2" | cut -d= -f2)
if [ -n "$p1" ] && [ -n "$p2" ] && [ "$p1" != "$p2" ]; then
  ok "two concurrent sessions have isolated ports ($p1 / $p2)"
else bad "port isolation: p1=$p1 p2=$p2"; fi
n=$(pgrep -f relay_anthropic | wc -l)
if [ "$n" = 0 ]; then ok "zero stray relays after both sessions exit"; else bad "$n strays left"; fi
rm -f "$S1" "$S2"

python3 "$QD/qa_reliab_mock.py" 18778 &
MOCK=$!
sleep 1
R=$(DA_UPSTREAM=http://127.0.0.1:18778 CCT_NO_PICKER=1 cct -e deep \
    python3 "$QD/qa_reliab_probe.py" 2>&1)
kill $MOCK 2>/dev/null
n200=$(echo "$R" | grep -c "200")
if [ "$n200" = 3 ]; then ok "reuse self-heals after 3s idle (upstream already cut): all 3 got 200"
else bad "connection reuse: $(echo "$R" | tr '\n' ' ')"; fi

echo
echo "reliab acceptance: passed $P / failed $F"
exit $F
