#!/bin/bash
# qa_update — acceptance for the auto-update system (mock registry, never touches the real
# npm/registry).
# Covers: probe writes the cache · one-line notice on non-TTY · skip_version suppression ·
#       forced-update floor soft/hard/ACK escape hatch · interactive menu 1 (run the update
#       command) / 2 (skip) / 3 (skip this version).
set -u
QD=$(cd "$(dirname "$0")" && pwd)
# Locating cct.py: prefer the installed package directory (container case), fall back to the
# repo root (local case)
NM=$(dirname "$(readlink -f "$(which cct 2>/dev/null)" 2>/dev/null)" 2>/dev/null || true)
RP=$(dirname "$QD")
[ -n "$NM" ] && [ -f "$NM/cct.py" ] && RP="$NM"
W=$(mktemp -d)
# no fixed /tmp/… name: on a shared box that is a predictable path surface
export UPD_PATHS="$W/upd_paths.txt"
trap 'rm -rf "$W"' EXIT INT TERM
P=0; F=0
ok()  { echo "  ✓ $1"; P=$((P+1)); }
bad() { echo "  ✗ $1"; F=$((F+1)); }
has() { case "$2" in *"$3"*) ok "$1";; *) bad "$1 | got: $(echo "$2" | head -c 160)";; esac; }

cat > "$W/reg.py" <<'PY'
import json, os, sys
from http.server import BaseHTTPRequestHandler, HTTPServer
MAN = json.loads(sys.argv[2])
class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_GET(self):
        # record the actual request path (used by the channel assertion)
        with open(os.environ["UPD_PATHS"], "a") as f:
            f.write(self.path + "\n")
        b = json.dumps(MAN).encode()
        self.send_response(200); self.send_header("Content-Length", str(len(b))); self.end_headers()
        self.wfile.write(b)
HTTPServer(("127.0.0.1", int(sys.argv[1])), H).serve_forever()
PY
python3 "$W/reg.py" 18511 '{"version":"9.9.9"}' >/dev/null 2>&1 &
RPID=$!
sleep 0.4
export HOME="$W/home"; mkdir -p "$HOME"
export no_proxy=127.0.0.1 NO_PROXY=127.0.0.1

echo "═══ U1 probe → cache ═══"
rm -f "$UPD_PATHS"
CCT_REGISTRY=http://127.0.0.1:18511 python3 "$RP/cct.py" __update_probe__
# Channel assertion (0.1.5 pre-release): the probe must query the dist-tag named by its own
# publishConfig.tag, never a hard-coded latest
TAG=$(python3 -c "import json;print((json.load(open('$RP/package.json')).get('publishConfig') or {}).get('tag') or 'latest')")
has "probe queries channel /$TAG (not hard-coded latest)" "$(cat "$UPD_PATHS" 2>/dev/null)" "/$TAG"
rm -f "$UPD_PATHS"
CCT_UPDATE_TAG=beta CCT_REGISTRY=http://127.0.0.1:18511 python3 "$RP/cct.py" __update_probe__
has "CCT_UPDATE_TAG overrides the channel" "$(cat "$UPD_PATHS" 2>/dev/null)" "/beta"
python3 -c "
import json, os
c = json.load(open(os.path.expanduser('~/.cct/update-check.json')))
assert c['latest'] == '9.9.9', c" && ok "latest lands in the cache" || bad "cache"

echo "═══ U2 non-TTY notice / skip suppression ═══"
GATE="import sys; sys.path.insert(0, '$RP'); import cct; cct._upd_gate(); print('GATE_PASS')"
R=$(CCT_NO_PICKER=1 python3 -c "$GATE" 2>&1)
has "one-line notice (stderr) + session continues" "$R" "✨ cct 9.9.9 available"
has "execution continues" "$R" "GATE_PASS"
python3 -c "
import json, os
p = os.path.expanduser('~/.cct/update-check.json'); c = json.load(open(p))
c['skip_version'] = '9.9.9'; json.dump(c, open(p, 'w'))"
R=$(CCT_NO_PICKER=1 python3 -c "$GATE" 2>&1)
[ "$R" = "GATE_PASS" ] && ok "zero interruption after skip_version" || bad "skip: $R"

echo "═══ U3 forced-update floor: soft/hard/ACK ═══"
python3 -c "
import json, os, time
p = os.path.expanduser('~/.cct/update-check.json'); c = json.load(open(p))
c.pop('skip_version', None); c['force_before'] = '9.0.0'; c['force_first_seen'] = time.time()
json.dump(c, open(p, 'w'))"
R=$(CCT_NO_PICKER=1 python3 -c "$GATE" 2>&1)
has "soft force (within grace), non-TTY: notify + continue" "$R" "GATE_PASS"
python3 -c "
import json, os, time
p = os.path.expanduser('~/.cct/update-check.json'); c = json.load(open(p))
c['force_first_seen'] = time.time() - 6 * 86400; json.dump(c, open(p, 'w'))"
CCT_NO_PICKER=1 python3 -c "$GATE" >/dev/null 2>&1; rc=$?
[ "$rc" = 1 ] && ok "hard block (grace expired), non-TTY: exit 1" || bad "hard block rc=$rc"
R=$(CCT_NO_PICKER=1 CCT_FORCE_ACK=1 python3 -c "$GATE" 2>&1)
has "ACK escape hatch: let through" "$R" "GATE_PASS"

echo "═══ U4 interactive menu (pty): 1 run / 2 skip / 3 remember skip ═══"
mkdir -p "$W/bin"
printf '#!/bin/sh\necho FAKE_NPM "$@" > "%s/npm_ran"\nexit 0\n' "$W" > "$W/bin/npm"
chmod +x "$W/bin/npm"
python3 -c "
import json, os
p = os.path.expanduser('~/.cct/update-check.json'); c = json.load(open(p))
c.pop('force_before', None); c.pop('force_first_seen', None); json.dump(c, open(p, 'w'))"
menu() {  # $1=key press
  python3 - "$1" "$RP" "$W" <<'PY'
import os, pty, select, subprocess, sys, time
key, rp, w = sys.argv[1], sys.argv[2], sys.argv[3]
m, s = pty.openpty()
env = dict(os.environ)
env["PATH"] = w + "/bin:" + env["PATH"]
env.pop("CCT_NO_PICKER", None)
p = subprocess.Popen([sys.executable, "-c",
    f"import sys; sys.path.insert(0, '{rp}'); import cct; cct._upd_gate(); print('GATE_PASS')"],
    stdin=s, stderr=s, stdout=subprocess.PIPE, env=env)
os.close(s)
buf, t0, sent = b"", time.time(), False
while p.poll() is None and time.time() - t0 < 8:
    r, _, _ = select.select([m], [], [], 0.05)
    if r:
        try: buf += os.read(m, 65536)
        except OSError: break
    if not sent and b"Select" in buf:
        os.write(m, key.encode() + b"\n"); sent = True
print(p.stdout.read().decode().strip(), "|", "MENU" if b"Update available" in buf else "NOMENU")
PY
}
R=$(menu 2); has "choice 2: skip and continue" "$R" "GATE_PASS | MENU"
R=$(menu 3); has "choice 3: remember the skip" "$R" "GATE_PASS | MENU"
python3 -c "
import json, os
c = json.load(open(os.path.expanduser('~/.cct/update-check.json')))
assert c.get('skip_version') == '9.9.9', c" \
  && ok "skip_version written to the cache" || bad "skip not written"
python3 -c "
import json, os
p = os.path.expanduser('~/.cct/update-check.json'); c = json.load(open(p))
c.pop('skip_version', None); json.dump(c, open(p, 'w'))"
R=$(menu 1); has "choice 1: run the update command" "$R" "GATE_PASS | MENU"
PKGN=$(python3 -c "import json;print(json.load(open('$RP/package.json'))['name'])")
grep -q "FAKE_NPM install -g $PKGN" "$W/npm_ran" 2>/dev/null \
  && ok "npm install -g $PKGN actually invoked (fake)" || bad "npm not invoked / name mismatch"

kill $RPID 2>/dev/null
echo; echo "update acceptance: passed $P / failed $F"
rm -rf "$W"
exit $F
