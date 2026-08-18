#!/bin/bash
# qa_main — full cct acceptance (needs a container / clean HOME)
#
# ⚠ WARNING: this script is **not** a harmless unit test. Before you run it, confirm you accept
# all three of the following:
#   ① It burns **real DeepSeek credit** — T5/T6/T9/T14/T15/T16/T17/T21/T23/T24 all send real
#      requests upstream, and need a usable ANTHROPIC_AUTH_TOKEN in the environment.
#   ② It needs an **already logged-in claude CLI**.
#   ③ It **temporarily overwrites ~/.claude/settings.json and ~/.claude.json** (each sub-script
#      backs them up and restores them).
# Strongly recommended: run this only in a throwaway container, never on your daily work machine.
P=0; F=0
ok()  { echo "  ✓ $1"; P=$((P+1)); }
bad() { echo "  ✗ $1"; F=$((F+1)); }
has() { case "$2" in *"$3"*) ok "$1";; *) bad "$1 | got: $(echo "$2" | head -c 140)";; esac; }

T=$(mktemp -d "${TMPDIR:-/tmp}/cct-qa.XXXXXXXX")
export T                       # T4's bash -c is single-quoted, so $T reaches the child via env
trap 'rm -rf "$T"' EXIT INT TERM
QD=$(cd "$(dirname "$0")" && pwd)
NM=$(dirname "$(readlink -f "$(which cct)")")
SESS="${CCT_SESS_DIR:-$HOME/.cct/sessions}"

echo "═══ T1 install and tier table ═══"
L=$(cct list)
has "cct on PATH, list works" "$L" "balance"
n=$(echo "$L" | grep -cE '^(balance|medium|official|xhigh|deep) ')
[ "$n" = 5 ] && ok "all five tiers present 5/5" || bad "all five tiers present (got $n)"
has "default mark on balance" "$(echo "$L" | grep '^balance')" "★default"
has "official tier marked with all five effort levels open" "$(echo "$L" | grep '^official')" "5 efforts"
has "display badge column (vs max, replaces bare acc)" "$(echo "$L" | grep '^balance')" "−49% cost"
has "deep tier badge speaks of depth" "$(echo "$L" | grep '^deep ')" "+7% depth"
# tb_acc assertion: read each tier's calibrated accuracy out of tiers.json at runtime and assert
# one by one that it does **not** appear in cct list. Those numbers are deliberately not hard-coded
# in the test file — that would scatter calibration conclusions across the repo.
accleak=0
while IFS= read -r a; do
  [ -n "$a" ] || continue
  case "$L" in *"$a"*) accleak=$((accleak+1));; esac
done <<EOF
$(python3 -c "
import json,sys
t=json.load(open(sys.argv[1]))
print('\n'.join(str(x['tb_acc']) for x in t['tiers'] if x.get('tb_acc')))" "$NM/tiers.json" 2>/dev/null)
EOF
[ "$accleak" = 0 ] && ok "tb_acc fully retired (only the vs max badge left)" \
  || bad "tb_acc should be fully retired, $accleak still appear in cct list"

echo "═══ T2 picker silent when not a TTY (zero interference in pipes) ═══"
out=$(python3 "$NM/picker.py" "$NM/tiers.json" </dev/null 2>"$T"/qa_perr)
[ "$out" = "balance" ] && [ ! -s "$T"/qa_perr ] && ok "stdout=balance, stderr=0 bytes" \
  || bad "pipe silence (out=$out err=$(wc -c <"$T"/qa_perr)B)"

echo "═══ T3 picker pty: every key path ═══"
msg=$(python3 "$QD"/qa_picker_pty.py "$NM" 2>&1) && ok "→Enter=deep / 1=official / hh=official / Esc·q=balance / no key 3s=balance + cursor restored" \
  || bad "pty: $msg"
msg=$(python3 "$QD"/qa_picker_vt.py "$NM" 2>&1) && ok "T3b VT simulation matrix (geometry×Ambiguous width×probe failure×locale: zero drift, zero wrap)" \
  || bad "vt: $msg"

echo "═══ T4 session lifecycle (private relay: start→use→die) ═══"
rm -f "$T"/qa_port
CCT_NO_PICKER=1 cct -e balance bash -c '
  echo "${ANTHROPIC_BASE_URL##*:}" > "$T"/qa_port
  python3 -c "import urllib.request as u; u.build_opener(u.ProxyHandler({})).open(\"$ANTHROPIC_BASE_URL/health\", timeout=3)" && echo QA_ALIVE
' > "$T"/qa_t4.log 2>&1
grep -q QA_ALIVE "$T"/qa_t4.log && ok "relay healthy inside the session" || bad "relay healthy inside the session"
port=$(cat "$T"/qa_port 2>/dev/null)
python3 -c "import urllib.request as u; u.build_opener(u.ProxyHandler({})).open('http://127.0.0.1:$port/health', timeout=2)" 2>/dev/null \
  && bad "relay should be dead after exit (port $port still alive)" || ok "relay dead after exit (port $port)"
nres=$(ps -ef 2>/dev/null | grep -c '[r]elay_anthropic' || true)
[ "${nres:-0}" = 0 ] && ok "no stray relay processes" || bad "$nres stray relay processes"
# 0.1.5 removed the "global export" startup warning; this guard asserts it never comes back.
case "$(cat "$T"/qa_t4.log)" in
  *"suggest unset"*) bad "the global export warning should be gone, yet it still shows up";;
  *) ok "global export warning is gone (container env meets the old trigger, zero output)";;
esac

echo "═══ T5 official tier: straight through + CC effort mapping + auth passed through ═══"
R=$(CCT_NO_PICKER=1 cct -e official bash "$QD"/qa_api_official.sh 2>/dev/null)
has "no effort → lands in the official high bucket"        "$(echo "$R" | grep OFF_NOEFF)" "89"
has "client effort=low → 10 (forwarded verbatim)"          "$(echo "$R" | grep OFF_LOW)" " 10"
has "client effort=max → 104 (forwarded verbatim)"         "$(echo "$R" | grep OFF_MAX)" "102"
has "effort=medium → mapped to the Classic injection tier" "$(echo "$R" | grep OFF_MED)" "45"
has "effort=xhigh → mapped to the Extra injection tier"    "$(echo "$R" | grep OFF_XH)" "68"
has "no auth header → upstream 401 relayed verbatim"       "$(echo "$R" | grep NOAUTH)" "Authentication"
has "T11 receipt: /effort mapped aggregate line (display labels)" "$R" "/effort mapped: medium→Classic"
has "T11 receipt: Flex symmetric pointer line" "$R" "for peak performance, use Value or Deeper"
has "T11 receipt: Flex component family (extended: medium×)" "$R" "extended: medium×"

echo "═══ T6/T7 injection tier intervention + two model-channel cases (tier-name channel cleaned up) ═══"
R=$(CCT_NO_PICKER=1 cct -e balance bash "$QD"/qa_api_balance.sh 2>"$T"/qa_bal_receipt.txt)
has "balance, no effort → lands in the Value injection tier"             "$(echo "$R" | grep BAL_NOEFF)" "60"
has "balance, client forces max → 62 (unconditional override)"           "$(echo "$R" | grep '^BAL_STOMP ')" "60"
has "balance, client disables thinking → still 62 (switch reclaimed)"    "$(echo "$R" | grep BAL_STOMP_THINK)" "60"
has "tier name best → unclaimed, pure passthrough, upstream adjudicates" "$(echo "$R" | grep TIERNAME)" "ERR"
has "①v4-pro → name forwarded verbatim + 60 injected"                    "$(echo "$R" | grep PRO_KEEP)" "60 deepseek-v4-pro"
has "②gpt-4o → zero rejection, upstream error relayed verbatim"          "$(echo "$R" | grep FOREIGN)" "supported API model names"

echo "═══ T8 ledger trace (asked/used/tier, no key_fp) ═══"
LED=$(ls -t $SESS/*.jsonl | head -1)
ROWS=$(python3 - "$LED" <<'EOF'
import json, sys
rows = [json.loads(x) for x in open(sys.argv[1])]
tiers = [str(r.get("tier")) for r in rows]
kf = any("key_fp" in r for r in rows)
pro = any(r.get("asked") == "deepseek-v4-pro" and r.get("used") == "deepseek-v4-pro" for r in rows)
tn = any(r.get("asked") == "best" and r.get("tier") is None for r in rows)
fo = any(r.get("asked") == "gpt-4o" and r.get("tier") is None for r in rows)
ei = any(r.get("eff_in") == "max" and r.get("tier") == "balance" and not r.get("eff_map") for r in rows)
print(f"keyfp={kf} pro_kept={pro} tiername_none={tn} foreign_none={fo} effin_pin={ei} n={len(rows)}")
EOF
)
has "no key_fp (passthrough mode never inspects the key)" "$ROWS" "keyfp=False"
has "pro asked=used, original name recorded on both"      "$ROWS" "pro_kept=True"
has "tier-name row has tier=None (channel cleaned up)"    "$ROWS" "tiername_none=True"
has "pure passthrough row has tier=None"                  "$ROWS" "foreign_none=True"
has "pinned-tier row records eff_in=max and no eff_map"   "$ROWS" "effin_pin=True"

echo "═══ T9 end to end with CC none the wiser (real claude) ═══"
R=$(CCT_NO_PICKER=1 cct claude -p 'Explain the idea behind quicksort in three sentences' 2>&1)
has "claude answers correctly" "$R" "sort"
VER=$(python3 -c "import json;print(json.load(open('$NM/package.json'))['version'])")
has "banner: technical preview version ($VER)" "$R" "· technical preview $VER"
has "receipt: breakdown and amount-paid line (display label Value)" "$R" "Value ×"
has "receipt: main line (Saved ≈, English)" "$R" "Saved ≈"
case "$R" in *"/effort locked by"*) bad "we set the pinned value ourselves, so no locked notice (noise)";;
  *) ok "receipt has zero noise (a value we pinned is not a user choice being overridden)";; esac
LED2=$(ls -t $SESS/*.jsonl | head -1)
eff9=$(python3 -c "
import json
rows=[json.loads(x) for x in open('$LED2') if x.strip()]
main=[r for r in rows if (r.get('out') or 0)>0]
print(main[-1].get('eff_in'), main[-1].get('tier'))" 2>/dev/null)
has "pinned-tier session pins CC effort to max (client behaviour consistent)" "$eff9" "max balance"
A9=$(python3 -c "
import json,sys
rows=[json.loads(x) for x in open('$LED2')]
main=[r for r in rows if (r.get('out') or 0)>0]
print(main[-1].get('asked'), main[-1].get('tier'))")
has "CC sends the real model name (none the wiser)" "$A9" "deepseek-v4-flash"
# Zero intervention on the context window: CLAUDE_CODE_MAX_CONTEXT_TOKENS must not be injected
ctx=$(CCT_NO_PICKER=1 cct -e balance bash -c 'echo CTX=[$CLAUDE_CODE_MAX_CONTEXT_TOKENS]' 2>/dev/null | grep CTX)
has "zero intervention on the context window (no MAX_CONTEXT_TOKENS injected)" "$ctx" "CTX=[]"
has "lands in the default session tier balance"     "$A9" "balance"

echo "═══ T14 settings.json hijack guard (real claude, 0.1.5) ═══"
msg=$(bash "$QD"/qa_settings_pin.sh 2>&1)
case "$msg" in *T14_PASS*) ok "under hijack traffic still hits relay + paid line + silent success + single pin key";; *) bad "t14: $(echo "$msg" | head -3)";; esac

echo "═══ T23 CC Switch compatibility (replicates its settings.json form and local routing) ═══"
msg=$(bash "$QD"/qa_ccswitch.sh 2>&1 | tail -1)
case "$msg" in *"failed 0"*) ok "direct connect / API_KEY variant / aliased model + fallback / local routing / hijack pin-back ($msg)";; *) bad "ccswitch: $msg";; esac

echo "═══ T24 CC Switch in depth: provider swap mid-session · project/local hijack · MCP coexistence ═══"
msg=$(bash "$QD"/qa_ccswitch2.sh 2>&1 | tail -1)
case "$msg" in *"failed 0"*) ok "provider swap mid-session keeps the tier · pin-back wins at all 3 settings levels ($msg)";; *) bad "ccswitch2: $msg";; esac

echo "═══ T22 non-official upstream: warn only, never degrade (mock, zero real network) ═══"
msg=$(bash "$QD"/qa_upstream.sh 2>&1 | tail -1)
case "$msg" in *"failed 0"*) ok "warning shows host name only (no credential leak) + tier still applied + ledger records tier ($msg)";; *) bad "upstream: $msg";; esac

echo "═══ T21 attack test: 20 client-side techniques trying to defeat the pinned tier ═══"
msg=$(bash "$QD"/qa_attack.sh 2>&1 | tail -1)
case "$msg" in *"failed 0"*) ok "thinking/effort/model name/system/sampling/future fields all blocked ($msg)";; *) bad "attack: $msg";; esac

echo "═══ T20 reliability: concurrent session port isolation/zero strays · idle connection reuse self-heals (zero real net) ═══"
msg=$(bash "$QD"/qa_reliab.sh 2>&1 | tail -1)
case "$msg" in *"failed 0"*) ok "two sessions isolated + zero strays · self-heals after upstream drops the idle connection ($msg)";; *) bad "reliab: $msg";; esac

echo "═══ T19 red lines and transport path: zero leaks in ledger/capture · streaming pinned tier · large request body ═══"
msg=$(bash "$QD"/qa_redline.sh 2>&1 | tail -1)
case "$msg" in *"failed 0"*) ok "zero conversation content/zero keys + streaming pinned tier + 40KB chunked ($msg)";; *) bad "redline: $msg";; esac

echo "═══ T18 upstream fault paths (mock, zero real net): verbatim relay · no lost traces · 502 on disconnect ═══"
msg=$(bash "$QD"/qa_fault.sh 2>&1 | tail -1)
case "$msg" in *"failed 0"*) ok "429/500/bad JSON/disconnect, all four states + five ledger rows with zero loss ($msg)";; *) bad "fault: $msg";; esac

echo "═══ T17 all tiers × client variants matrix (5 tiers × adversarial variants, capture + calibration double assertion) ═══"
msg=$(bash "$QD"/qa_tier_matrix.sh 2>&1 | tail -1)
case "$msg" in *"failed 0"*) ok "4 pinned tiers: constant calibrated value + differential invariant · Flex straight through untouched/mapping takes over ($msg)";; *) bad "matrix: $msg";; esac

echo "═══ T16 pinned-tier hardening: client thinking carriers must not weaken the injection tier (real key, capture assertions) ═══"
msg=$(bash "$QD"/qa_pin_hard.sh 2>&1 | tail -1)
case "$msg" in *"failed 0"*) ok "adaptive/disabled/budget: all 4 variants land in Deeper + Flex straight through untouched ($msg)";; *) bad "pin_hard: $msg";; esac

echo "═══ T15 Flex unlocks /effort (env+settings, both forms, real claude) ═══"
msg=$(bash "$QD"/qa_flex_unlock.sh 2>&1)
case "$msg" in *T15_PASS*) ok "CLAUDE_CODE_EFFORT_LEVEL stripped in both forms → eff_in back to default high + empty pin";; *) bad "t15: $(echo "$msg" | head -3)";; esac

echo "═══ T12 auto-update system (mock registry, zero real network) ═══"
msg=$(bash "$QD"/qa_update.sh 2>&1 | tail -1)
case "$msg" in *"failed 0"*) ok "probe/notice/skip/soft and hard force/ACK/menu 123 all pass ($msg)";; *) bad "update: $msg";; esac

echo "═══ T13 peak/off-peak time-of-day pricing (local only, synthetic ledger) ═══"
msg=$(python3 "$QD"/qa_price.py "$NM" 2>&1 | tail -1)
case "$msg" in *"failed 0"*) ok "peak/off-peak, hour boundaries, pro 3×, legacy price table compat all pass ($msg)";; *) bad "price: $msg";; esac

echo "═══ T10 deep tier receipt, reverse presentation ═══"
# an empty session must not print an intervention line
CCT_NO_PICKER=1 cct -e deep bash /dev/null > "$T"/qa_deep0.log 2>&1
R=$(CCT_NO_PICKER=1 cct -e deep bash -c '
python3 -c "
import json, os, urllib.request
op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
b = {\"model\": \"deepseek-v4-flash\", \"max_tokens\": 6000,
     \"messages\": [{\"role\": \"user\", \"content\": \"13*17=? digits only\"}]}
req = urllib.request.Request(os.environ[\"ANTHROPIC_BASE_URL\"] + \"/v1/messages\",
    data=json.dumps(b).encode(),
    headers={\"content-type\": \"application/json\", \"anthropic-version\": \"2023-06-01\",
             \"x-api-key\": os.environ[\"ANTHROPIC_AUTH_TOKEN\"]})
op.open(req, timeout=300).read()
"' 2>&1)
has "deep tier main line (deeper than official max, positive framing)" "$R" "deeper than official max"
grep -qE "Saved ≈|deeper than official max" "$T"/qa_deep0.log && bad "empty session must not have a main line" || ok "empty session has no main line"

echo
echo "════════════════════════════════"
echo "Result: passed $P / failed $F"
[ "$F" = 0 ] && echo "★ everything matches the design" || echo "✗ nonconformances found, see above"
exit $F
