#!/bin/bash
# T14 — settings.json env hijack guard (0.1.5): under a hijack, traffic must still enter this
# session's relay.
# Mechanism: CC writes settings.json's env back into the process environment, which can clobber
#            the BASE_URL cct injected; cct pins it back with a single key via claude --settings.
# Asserts: ① the jsonl still grows under a hijack ② the receipt has a paid line ③ a successful
#          pin-back is completely silent (no ⚠ hijack line at all) ④ the pin file holds the URL
#          as its only key.
#
# ⚠ Warning: requires a real ANTHROPIC_AUTH_TOKEN and a **logged-in claude CLI**, spends real API
#   credit, and **temporarily overwrites ~/.claude/settings.json** (the script restores it with a
#   trap on any exit path, including Ctrl-C). Run it only in a throwaway container.
set -u
S="$HOME/.claude/settings.json"
SESS="$HOME/.cct/sessions"
# Back up into a 0700 temporary directory, with a trap covering every exit path (including
# Ctrl-C / timeout) — never leave a copy of the user's settings.json under ~/.claude/ waiting to
# be casually packaged up or scanned.
BK=$(mktemp -d); chmod 700 "$BK"
restore() { if [ -f "$BK/settings.json" ]; then mv -f "$BK/settings.json" "$S"; else rm -f "$S"; fi; rm -rf "$BK"; }
trap restore EXIT INT TERM
[ -f "$S" ] && cp "$S" "$BK/settings.json"
mkdir -p "$HOME/.claude"
python3 - <<'PY'
import json, os  # noqa: F401
# Write only the one key under test: auth is still supplied by the outer environment — no need to
# put a real key on disk.
json.dump({"env": {"ANTHROPIC_BASE_URL": "https://api.deepseek.com/anthropic"}},
          open(os.path.expanduser("~/.claude/settings.json"), "w"), indent=1)
PY
before=$(ls "$SESS"/*.jsonl 2>/dev/null | wc -l)
OUT=$(CCT_NO_PICKER=1 cct claude -p '6*7=? digits only' 2>&1)
after=$(ls "$SESS"/*.jsonl 2>/dev/null | wc -l)
# Restore before the assertions, so a failure in a later step cannot strand the user's config in
# the test state.
restore; trap - EXIT INT TERM
R=0
[ "$after" -gt "$before" ] || { echo "✗ no new jsonl under the hijack (still bypassed)"; R=1; }
case "$OUT" in *"paid ¥"*) :;; *) echo "✗ receipt has no paid line: $(echo "$OUT" | tail -3)"; R=1;; esac
# 0.1.5 turned cct's pin-back warnings English ("BASE_URL not pinned" / "cannot write pin file" /
# "pin-back failed"), so the patterns below match nothing today; kept as a permanent negative
# guard that a successful pin-back stays completely silent. Re-arming it against the current
# English wording would be a behaviour change, so it is left for a deliberate follow-up.
case "$OUT" in *"pinned back"*|*"bypass relay"*)
  echo "✗ a successful pin-back must be silent, got: $(echo "$OUT" | grep 'pinned back')"; R=1;; esac
PIN=$(ls -t "$SESS"/*.settings.json 2>/dev/null | head -1)
python3 - "$PIN" <<'PY' || R=1
import json, sys
d = json.load(open(sys.argv[1]))
e = d.get("env") or {}
# Since 0.1.6 a pinned-tier session additionally pins CLAUDE_CODE_EFFORT_LEVEL=max (the CC
# client-side behaviour has to match too); nothing beyond these two keys may be pinned
# (ANTHROPIC_MODEL and the rest are never touched).
assert set(e) == {"ANTHROPIC_BASE_URL", "CLAUDE_CODE_EFFORT_LEVEL"}, \
    f"pin key set mismatch: {sorted(e)}"
assert e["ANTHROPIC_BASE_URL"].startswith("http://127.0.0.1:"), e
assert e["CLAUDE_CODE_EFFORT_LEVEL"] == "max", f"a pinned tier must pin max: {e}"
PY
[ "$R" = 0 ] && echo "T14_PASS" || echo "T14_FAIL"
exit $R
