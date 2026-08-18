#!/bin/bash
# T24 — deep compatibility with third-party provider-switching tools (0.1.7): the four real
# scenarios the previous round did not cover.
# The core use of these tools is **switching providers** (rewriting ~/.claude/settings.json), and
# the CC docs state that when settings change the env block is written back into the process
# environment — a direct test of the --settings pin-back.
# Also tests the routing priority of project-level / local-level settings, and coexistence with
# ~/.claude.json (the MCP configuration).
#
# ⚠ Warning: requires a real ANTHROPIC_AUTH_TOKEN and a **logged-in claude CLI**, and spends real
#   API credit. It temporarily rewrites ~/.claude/settings.json **and ~/.claude.json** (Claude
#   Code's main configuration, which holds project history and MCP definitions). Both are
#   restored by a trap on every exit path (including Ctrl-C), with the backups in a 0700
#   temporary directory. Running it only in a throwaway container is still strongly advised.
set -u
QD=$(cd "$(dirname "$0")" && pwd)
S="$HOME/.claude/settings.json"
CJ="$HOME/.claude.json"
SESS="$HOME/.cct/sessions"
P=0; F=0
ok()  { echo "  ✓ $1"; P=$((P+1)); }
bad() { echo "  ✗ $1"; F=$((F+1)); }
WORK=$(mktemp -d)
# The backup directory is kept apart from $WORK: $WORK is rm -rf'd at the end, and the user's
# real configuration must not be lying inside it.
BK=$(mktemp -d); chmod 700 "$BK"
restore() {
  if [ -f "$BK/settings.json" ]; then mv -f "$BK/settings.json" "$S"; else rm -f "$S"; fi
  if [ -f "$BK/claude.json" ];   then mv -f "$BK/claude.json" "$CJ"; fi
  rm -rf "$BK"
}
trap 'restore; rm -rf "$WORK"' EXIT INT TERM
[ -f "$S" ]  && cp "$S" "$BK/settings.json"
[ -f "$CJ" ] && cp "$CJ" "$BK/claude.json"
mkdir -p "$HOME/.claude"

mkset() {  # $1=target file $2=BASE_URL
  mkdir -p "$(dirname "$1")"
  python3 - "$1" "$2" <<'PY'
import json, sys
# Do not write a real key to disk: what this test asserts is routing priority and tiers, auth is
# still supplied by the outer environment.
json.dump({"env": {"ANTHROPIC_BASE_URL": sys.argv[2],
                   "ANTHROPIC_MODEL": "deepseek-v4-flash"}}, open(sys.argv[1], "w"), indent=1)
PY
}
grew() {   # successful calls in the newest ledger (traffic really entered the cct relay)
  python3 - <<'PY'
import glob, json, os
fs = sorted(glob.glob(os.path.expanduser("~/.cct/sessions/*.jsonl")), key=os.path.getmtime)
rows = [json.loads(x) for x in open(fs[-1])] if fs else []
ok = [r for r in rows if r.get("status") == 200 and (r.get("out") or 0) > 0]
print(len(ok))
PY
}

echo "── ⑥ Switching providers while a session runs (third-party tool rewrites settings.json)"
mkset "$S" "https://api.deepseek.com/anthropic"
CCT_NO_PICKER=1 cct -e deep claude -p 'Count .sh files in /tmp/qa2, then say how you counted them' \
  > "$WORK/mid.log" 2>&1 &
CPID=$!
sleep 6
# Simulate the user clicking "switch to another provider" in the switching tool
mkset "$S" "https://switched-provider.example.com/anthropic"
wait $CPID 2>/dev/null
N=$(grew)
if [ "${N:-0}" -ge 1 ]; then
  ok "⑥ provider switch mid-session: traffic stays on the cct relay throughout ($N calls logged)"
else bad "⑥ traffic did not go through the relay after the mid-session switch ($N ledger rows)"; fi
case "$(cat "$WORK/mid.log")" in *"Deeper ×"*) ok "⑥ receipt normal, tier did not lapse";;
  *) bad "⑥ receipt abnormal: $(tail -2 "$WORK/mid.log")";; esac

echo "── ⑦ Routing priority of a project-level .claude/settings.json (the CLI pin-back must win)"
mkset "$S" "https://api.deepseek.com/anthropic"
cd "$WORK"
mkset "$WORK/.claude/settings.json" "https://project-level.example.com/anthropic"
before=$(grew)
CCT_NO_PICKER=1 cct -e balance claude -p '5+5=? digits only' >/dev/null 2>&1
after=$(grew)
cd - >/dev/null
# Note: this must be written as an explicit if — the precedence of `A || B && ok || bad` would
# make the assertion always true.
if [ "$after" != "$before" ] && [ "${after:-0}" -ge 1 ]; then
  ok "⑦ project-level settings: the pin-back still wins ($after ledger rows)"
else
  bad "⑦ project-level settings clobbered the pin-back (before=$before after=$after)"
fi

echo "── ⑧ Routing priority of settings.local.json"
cd "$WORK"
mkset "$WORK/.claude/settings.local.json" "https://local-level.example.com/anthropic"
CCT_NO_PICKER=1 cct -e balance claude -p '6+6=? digits only' >/dev/null 2>&1
N=$(grew)
cd - >/dev/null
[ "${N:-0}" -ge 1 ] && ok "⑧ local-level settings: the pin-back still wins ($N calls logged)" \
  || bad "⑧ local-level settings clobbered the pin-back"

echo "── ⑨ Coexistence with ~/.claude.json (MCP / project configuration)"
# The backup was already taken at the top of the file (into $BK, restored by the trap) — so we
# can just edit it here.
python3 - <<'PY'
import json, os
p = os.path.expanduser("~/.claude.json")
try:
    d = json.load(open(p))
except Exception:
    d = {}
d.setdefault("mcpServers", {})["ccswitch-demo"] = {"command": "echo", "args": ["hi"]}
json.dump(d, open(p, "w"), indent=1)
PY
CCT_NO_PICKER=1 cct -e deep claude -p '7+7=? digits only' >/dev/null 2>&1
N=$(grew)
[ "${N:-0}" -ge 1 ] && ok "⑨ coexists with ~/.claude.json (MCP): session fine ($N calls logged)" \
  || bad "⑨ session broken when an MCP configuration is present"
restore; trap - EXIT INT TERM; rm -rf "$WORK"
echo
echo "ccswitch2 acceptance: passed $P / failed $F"
exit $F
