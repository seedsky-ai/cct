#!/bin/bash
# T23 — compatibility with third-party provider-switching tools (new in 0.1.7).
#
# Tools of this kind (e.g. CC Switch) take over Claude Code by rewriting the env block of
# ~/.claude/settings.json. Measured public behaviour: they write 6 keys —
#   ANTHROPIC_BASE_URL / ANTHROPIC_AUTH_TOKEN (or ANTHROPIC_API_KEY) / ANTHROPIC_MODEL
#   + ANTHROPIC_DEFAULT_{HAIKU,SONNET,OPUS}_MODEL
# Their "local routing" mode points BASE_URL at their own loopback proxy (of the form
# http://127.0.0.1:15721/<prefix>).
#
# This test reproduces those configuration forms (the tool itself is a GUI and cannot run inside
# a container), covers each of its modes, and asserts cct's behaviour: routing priority · whether
# the tier still applies · whether auth passes through · whether the model name affects what is
# governed.
#
# ⚠ Warning: requires a real ANTHROPIC_AUTH_TOKEN and a **logged-in claude CLI**, and spends real
#   API credit. It **temporarily overwrites ~/.claude/settings.json**, and — because the very
#   scenario being reproduced is "the tool writes a real key into settings.json" — that file
#   really does hold a real token briefly during the test. The script restores the original with
#   a trap covering every exit path (including Ctrl-C). Run it only in a throwaway container.
set -u
QD=$(cd "$(dirname "$0")" && pwd)
S="$HOME/.claude/settings.json"
SESS="$HOME/.cct/sessions"
P=0; F=0
ok()  { echo "  ✓ $1"; P=$((P+1)); }
bad() { echo "  ✗ $1"; F=$((F+1)); }
BK=$(mktemp -d); chmod 700 "$BK"
restore() { if [ -f "$BK/settings.json" ]; then mv -f "$BK/settings.json" "$S"; else rm -f "$S"; fi; rm -rf "$BK"; }
trap restore EXIT INT TERM
[ -f "$S" ] && cp "$S" "$BK/settings.json"
mkdir -p "$HOME/.claude"

# settings.json in CC Switch form: $1=BASE_URL $2=auth field name $3=ANTHROPIC_MODEL
mk() {
  python3 - "$1" "$2" "$3" <<'PY'
import json, os, sys
url, authfield, model = sys.argv[1], sys.argv[2], sys.argv[3]
json.dump({"env": {
    "ANTHROPIC_BASE_URL": url,
    authfield: os.environ["ANTHROPIC_AUTH_TOKEN"],
    "ANTHROPIC_MODEL": model,
    "ANTHROPIC_DEFAULT_HAIKU_MODEL": model,
    "ANTHROPIC_DEFAULT_SONNET_MODEL": model,
    "ANTHROPIC_DEFAULT_OPUS_MODEL": model,
}}, open(os.path.expanduser("~/.claude/settings.json"), "w"), indent=1)
PY
}
last() {   # print tier/asked of the first successful row of the newest ledger
  python3 - <<'PY'
import glob, json, os
fs = sorted(glob.glob(os.path.expanduser("~/.cct/sessions/*.jsonl")), key=os.path.getmtime)
rows = [json.loads(x) for x in open(fs[-1])] if fs else []
ok = [r for r in rows if r.get("status") == 200 and (r.get("out") or 0) > 0]
r = ok[-1] if ok else {}
print(f"{r.get('tier')}|{r.get('asked')}|{r.get('inp')}")
PY
}

echo "── ① Direct provider mode (the official DeepSeek API, AUTH_TOKEN)"
mk "https://api.deepseek.com/anthropic" ANTHROPIC_AUTH_TOKEN "deepseek-v4-flash"
OUT=$(CCT_NO_PICKER=1 cct -e deep claude -p '1+1=? digits only' 2>&1)
R=$(last)
case "$R" in deep\|deepseek-v4-flash\|*) ok "① tier applied · model governed ($R)";;
  *) bad "①: $R";; esac
case "$OUT" in *"Deeper ×"*) ok "① receipt normal (settings did not steal it)";;
  *) bad "① receipt: $(echo "$OUT" | tail -2)";; esac

echo "── ② Auth field is ANTHROPIC_API_KEY (CC Switch's apiKeyField variant)"
mk "https://api.deepseek.com/anthropic" ANTHROPIC_API_KEY "deepseek-v4-flash"
CCT_NO_PICKER=1 cct -e deep claude -p '2+2=? digits only' >/dev/null 2>&1
R=$(last)
case "$R" in deep\|*) ok "② API_KEY variant: auth passes through fine ($R)";; *) bad "②: $R";; esac

echo "── ③ Model slot holds a non-deepseek name (common with aggregators) + receipt fallback"
mk "https://api.deepseek.com/anthropic" ANTHROPIC_AUTH_TOKEN "claude-sonnet-4-5"
OUT=$(CCT_NO_PICKER=1 cct -e deep claude -p '3+3=? digits only' 2>&1)
R=$(last)
case "$R" in None\|*) ok "③ non-deepseek model name → pure passthrough, no tier ($R)";;
  deep\|*) ok "③ still governed ($R)";; *) bad "③: $R";; esac
# 0.1.7 fallback: a bypassed tier must be stated honestly in the receipt
case "$OUT" in *"bypassed Deeper"*) ok "③ receipt fallback: $(echo "$OUT" | grep -o 'bypassed Deeper.*' | head -1)";;
  *) bad "③ receipt did not report the bypassed tier: $(echo "$OUT" | tail -2)";; esac

echo "── ④ Local routing mode (Local Routing: BASE_URL points at a loopback proxy)"
python3 "$QD/qa_fault_mock.py" 15721 &
MOCK=$!
sleep 1
mk "http://127.0.0.1:15721/claude" ANTHROPIC_AUTH_TOKEN "deepseek-v4-flash"
CAP=$(mktemp -d)
OUT=$(DA_UPSTREAM=http://127.0.0.1:15721/claude CCT_NO_PICKER=1 DA_CAPTURE="$CAP" \
      cct -e deep python3 "$QD/qa_fault_probe.py" 2>&1)
kill $MOCK 2>/dev/null
case "$OUT" in *"Non-official upstream"*) bad "④ loopback must not warn (local routing is normal)";;
  *) ok "④ local routing: loopback exempted, no spurious warning";; esac
python3 - "$CAP" <<'PY'
import glob, json, os, sys
fs = sorted(glob.glob(os.path.join(sys.argv[1], "*req*")), key=os.path.getmtime)
b = json.load(open(fs[0])).get("body") or {}
s = b.get("system")
t = s[0].get("text", "") if isinstance(s, list) and s and isinstance(s[0], dict) else ""
assert t.startswith("Reasoning Effort"), \
    f"the preamble must be spliced in as usual under local routing: {t[:40]!r}"
assert (b.get("output_config") or {}).get("effort") == "low", b.get("output_config")
PY
if [ $? = 0 ]; then
  ok "④ tier applied as usual over the local-routing chain (claude→cct→CCSwitch proxy→provider)"
else bad "④ tier had no effect"; fi
rm -rf "$CAP"

echo "── ⑤ Routing priority: the BASE_URL cct injects must win over settings.json"
mk "https://api.deepseek.com/anthropic" ANTHROPIC_AUTH_TOKEN "deepseek-v4-flash"
before=$(ls "$SESS"/*.jsonl 2>/dev/null | wc -l)
CCT_NO_PICKER=1 cct -e balance claude -p '4+4=? digits only' >/dev/null 2>&1
after=$(ls "$SESS"/*.jsonl 2>/dev/null | wc -l)
[ "$after" -gt "$before" ] && ok "⑤ ledger grew (traffic really went through the cct relay)" \
  || bad "⑤ ledger did not grow = traffic never went through the relay"

restore; trap - EXIT INT TERM
echo
echo "ccswitch acceptance: passed $P / failed $F"
exit $F
