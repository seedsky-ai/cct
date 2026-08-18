#!/bin/bash
# T15 — a Flex session unlocks /effort automatically (0.1.5): a leftover
# CLAUDE_CODE_EFFORT_LEVEL (worst case: both forms, shell env and settings.json, present at
# once) is stripped in a Flex session → CC falls back to its default (ledger eff_in=high) and
# /effort goes live; the pin file must contain the empty-string pin slot.
# (Value/Deeper pinned-tier sessions do not strip it — the locked ×N assertion in T9 is the
# regression test for that.)
#
# ⚠ Warning: requires a real ANTHROPIC_AUTH_TOKEN and a **logged-in claude CLI**, spends real API
#   credit, and **temporarily overwrites ~/.claude/settings.json** (the script restores it with a
#   trap on any exit path, including Ctrl-C). Run it only in a throwaway container.
set -u
S="$HOME/.claude/settings.json"
SESS="$HOME/.cct/sessions"
BK=$(mktemp -d); chmod 700 "$BK"
restore() { if [ -f "$BK/settings.json" ]; then mv -f "$BK/settings.json" "$S"; else rm -f "$S"; fi; rm -rf "$BK"; }
trap restore EXIT INT TERM
[ -f "$S" ] && cp "$S" "$BK/settings.json"
mkdir -p "$HOME/.claude"
python3 - <<'PY'
import json, os
# Write only the two keys under test: auth is still supplied by the outer environment, no real
# key is put on disk.
json.dump({"env": {"ANTHROPIC_BASE_URL": "https://api.deepseek.com/anthropic",
                   "CLAUDE_CODE_EFFORT_LEVEL": "max"}},
          open(os.path.expanduser("~/.claude/settings.json"), "w"), indent=1)
PY
OUT=$(CCT_NO_PICKER=1 cct -e official claude -p '3+4=? digits only' 2>&1)
restore; trap - EXIT INT TERM
R=0
LED=$(ls -t "$SESS"/*.jsonl 2>/dev/null | head -1)
python3 - "$LED" <<'PY' || R=1
import json, sys
rows = [json.loads(x) for x in open(sys.argv[1])]
main = [r for r in rows if r.get("status") == 200 and (r.get("out") or 0) > 0]
assert main, "no successful call"
r = main[-1]
assert r.get("tier") == "official", f"should land on official, got {r.get('tier')!r}"
assert r.get("eff_in") == "high", \
    f"should fall back to the default high (unlock succeeded), got {r.get('eff_in')!r}"
PY
PIN=$(ls -t "$SESS"/*.settings.json 2>/dev/null | head -1)
python3 - "$PIN" <<'PY' || R=1
import json, sys
e = json.load(open(sys.argv[1])).get("env") or {}
assert e.get("ANTHROPIC_BASE_URL", "").startswith("http://127.0.0.1:"), e
assert e.get("CLAUDE_CODE_EFFORT_LEVEL") == "", f"the pin must pin an empty string: {e}"
PY
[ "$R" = 0 ] && echo "T15_PASS" || { echo "tail: $(echo "$OUT" | tail -2)"; echo "T15_FAIL"; }
exit $R
