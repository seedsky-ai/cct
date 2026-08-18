#!/usr/bin/env python3
"""picker pty key-press full-path acceptance (runs in the container). argv[1] = cct package dir."""
import fcntl
import os
import pty
import select
import struct
import subprocess
import sys
import termios
import time

NM = sys.argv[1]
fails = []


def pump(m, buf, replied):
    """Read one chunk + answer the DSR probe (like a real terminal: ESC[6n → ESC[row;colR,
    col=2 i.e. A=1)."""
    r, _, _ = select.select([m], [], [], 0.05)
    if r:
        buf += os.read(m, 65536)
    need = buf.count(b"\x1b[6n")
    while replied[0] < need:
        os.write(m, b"\x1b[24;2R")
        replied[0] += 1
    return buf


def run(keys, expect):
    m, s = pty.openpty()
    fcntl.ioctl(s, termios.TIOCSWINSZ, struct.pack("HHHH", 24, 100, 0, 0))
    p = subprocess.Popen([sys.executable, NM + "/picker.py", NM + "/tiers.json"],
                         stdin=s, stderr=s, stdout=subprocess.PIPE)
    os.close(s)
    buf, t0, replied = b"", time.time(), [0]
    while time.time() - t0 < 4:
        try:
            buf = pump(m, buf, replied)
        except OSError:
            break
        if b"\x1b[K" in buf:
            break
    os.write(m, keys)
    while p.poll() is None and time.time() - t0 < 10:
        try:
            buf = pump(m, buf, replied)
        except OSError:
            break
    got = p.stdout.read().decode().strip()
    os.close(m)
    if got != expect:
        fails.append(f"{keys!r}: got {got!r} want {expect}")
    if b"\x1b[?25h" not in buf:
        fails.append(f"{keys!r}: cursor not restored")
    if b"\x1b[?7l" in buf and b"\x1b[?7h" not in buf:
        fails.append(f"{keys!r}: DECAWM not restored")


# 0.1.3 final picker_order = [official(Flex), balance★(Value) as centered default, deep(Deeper)]
run(b"\x1b[C\r", "deep")       # centered default → right = Deeper
run(b"1", "official")          # quick-select 1 = Flex
run(b"3", "deep")
run(b"\x1b", "balance")
run(b"hh\r", "official")       # all the way left = Flex
run(b"q", "balance")

# Countdown case (when picker_countdown_s>0): no key press → timeout auto-confirms the default
import json
_tt = json.load(open(NM + "/tiers.json", encoding="utf-8"))
_cd = _tt.get("picker_countdown_s") or 0
if _cd:
    m, s = pty.openpty()
    fcntl.ioctl(s, termios.TIOCSWINSZ, struct.pack("HHHH", 24, 100, 0, 0))
    p = subprocess.Popen([sys.executable, NM + "/picker.py", NM + "/tiers.json"],
                         stdin=s, stderr=s, stdout=subprocess.PIPE)
    os.close(s)
    buf, t0, replied = b"", time.time(), [0]
    while p.poll() is None and time.time() - t0 < _cd + 5:
        try:
            buf = pump(m, buf, replied)
        except OSError:
            break
    got = p.stdout.read().decode().strip()
    os.close(m)
    if got != _tt["default"]:
        fails.append(f"countdown: got {got!r} want {_tt['default']}")
    elif time.time() - t0 < _cd - 0.5:
        fails.append("countdown: exited early (did not wait out the timer)")

# Width invariant: at any terminal width, the display width of every frame line must be < tw
# (otherwise it wraps → canvas drift / scroll-spam). Pure-function check, no pty needed.
_w = subprocess.run([sys.executable, "-c", """
import re, sys
sys.argv = [None, sys.argv[1]]
import picker
bad = []
for tw in (55, 60, 72, 80, 100, 120):
    for cd in (None, 3):
        for fx in (0.0, 1.0, 2.4):
            fr = picker.frame(fx, 5.0, 12.0, 0.4, tw, cd=cd)
            for i, ln in enumerate(fr.split("\\n")[:-1]):
                vis = re.sub("\\x1b\\\\[[0-9;]*[A-Za-z]", "", ln).replace("\\r", "")
                w = picker.cells(vis)
                if w > tw - 1:
                    bad.append(f"tw={tw} cd={cd} line {i} width {w}")
print("; ".join(bad) if bad else "OK")
""", NM + "/tiers.json"], capture_output=True, text=True, cwd=NM)
if _w.stdout.strip() != "OK":
    fails.append(f"width invariant: {_w.stdout.strip()[:200]}{_w.stderr.strip()[:200]}")

if fails:
    print("; ".join(fails))
    sys.exit(1)
sys.exit(0)
