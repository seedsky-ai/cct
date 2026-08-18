#!/usr/bin/env python3
"""picker terminal simulation matrix (L4, the root-cause layer). argv[1] = the cct package dir.

Ships its own ~120-line mini VT interpreter (zero dependencies) and simulates rendering of
picker's stderr byte stream over a matrix of width 40-200 × height 5-50 × A1/A2 width × probe
failure × non-UTF8 locale:
  · strict mode (honors ESC[?7l, i.e. autowrap off): asserts **scroll count ≤ the 4 scrolls of
    canvas initialization** — "canvas drift / scroll-spam" under any geometry is an immediate
    red light (the form a narrow 80-column terminal triggers most easily);
  · paranoid mode (ignores ?7l, forces wrap semantics): asserts **wrap count = 0** — a missed
    clamp at the clip choke point is an immediate red light;
  · the final frame contains the confirmation banner / stdout tier name is correct / the
    degraded path must not emit animation sequences.
"""
import fcntl
import json
import os
import pty
import re
import select
import struct
import subprocess
import sys
import termios
import time
import unicodedata

NM = sys.argv[1]
TT = json.load(open(NM + "/tiers.json", encoding="utf-8"))
CD = TT.get("picker_countdown_s") or 0
fails = []

CSI = re.compile(r"\x1b\[([0-9;?]*)([A-Za-z])")


class VT:
    """Mini VT: implements only the subset picker uses + line-wrap/scroll semantics."""

    def __init__(self, w, h, honor_awm, ambig2):
        self.w, self.h = w, h
        self.honor = honor_awm             # honor ?7l/?7h (strict) or ignore them (paranoid)
        self.ambig2 = ambig2
        self.grid = [[" "] * w for _ in range(h)]
        self.r, self.c = h - 1, 0          # cursor at bottom row (worst case: after a shell prompt)
        self.autowrap = True
        self.scrolls = 0
        self.wraps = 0
        self.dsr = 0                       # number of ESC[6n received (harness answers these)
        self.pend = ""

    def cw(self, ch):
        w = unicodedata.east_asian_width(ch)
        return 2 if (w in "WF" or (self.ambig2 and w == "A")) else 1

    def _lf(self):
        if self.r == self.h - 1:
            self.grid.pop(0)
            self.grid.append([" "] * self.w)
            self.scrolls += 1
        else:
            self.r += 1

    def feed(self, text):
        self.pend += text
        i, n = 0, len(self.pend)
        while i < n:
            m = CSI.match(self.pend, i)
            if m:
                ps, fin = m.group(1), m.group(2)
                if fin == "A":
                    self.r = max(0, self.r - int(ps or "1"))
                elif fin == "G":
                    self.c = max(0, min(self.w - 1, int(ps or "1") - 1))
                elif fin == "K":
                    for x in range(self.c, self.w):
                        self.grid[self.r][x] = " "
                elif fin == "J":
                    for x in range(self.c, self.w):
                        self.grid[self.r][x] = " "
                    for y in range(self.r + 1, self.h):
                        self.grid[y] = [" "] * self.w
                elif fin == "n" and ps == "6":
                    self.dsr += 1
                elif fin in "lh" and ps == "?7":
                    if self.honor:
                        self.autowrap = fin == "h"
                # ?25l/h and SGR(m) are ignored
                i = m.end()
                continue
            ch = self.pend[i]
            if ch == "\x1b":
                if n - i < 4:              # sequence may be cut short, wait for the next chunk
                    break
                i += 1                     # lone non-CSI ESC, discard
                continue
            i += 1
            if ch == "\r":
                self.c = 0
            elif ch == "\n":
                self._lf()
            elif ch >= " ":
                wch = self.cw(ch)
                if self.c + wch > self.w:
                    if self.autowrap:
                        self.wraps += 1
                        self.c = 0
                        self._lf()
                    else:
                        continue           # DECAWM off: truncate
                self.grid[self.r][self.c] = ch
                for k in range(1, wch):
                    if self.c + k < self.w:
                        self.grid[self.r][self.c + k] = ""
                self.c += wch
        self.pend = self.pend[i:]

    def screen(self):
        return "\n".join("".join(row).rstrip() for row in self.grid)


def run_case(tag, w, h, keys, ambig2=False, env_extra=None, answer_dsr=True,
             expect_anim=True, expect_out=None, feed_line=False, dsr_delay=0.0):
    m, s = pty.openpty()
    fcntl.ioctl(s, termios.TIOCSWINSZ, struct.pack("HHHH", h, w, 0, 0))
    env = dict(os.environ)
    env.pop("NO_COLOR", None)
    env.setdefault("TERM", "xterm-256color")
    if env_extra:
        env.update(env_extra)
    p = subprocess.Popen([sys.executable, NM + "/picker.py", NM + "/tiers.json"],
                         stdin=s, stderr=s, stdout=subprocess.PIPE, env=env)
    os.close(s)
    strict = VT(w, h, honor_awm=True, ambig2=ambig2)
    paranoid = VT(w, h, honor_awm=False, ambig2=ambig2)
    raw, replied, sent = b"", 0, False
    t0, hard = time.time(), (CD + 6 if not keys and expect_anim else 10)
    while time.time() - t0 < hard:
        r, _, _ = select.select([m], [], [], 0.05)
        if r:
            try:
                chunk = os.read(m, 65536)
            except OSError:
                break
            raw += chunk
            txt = chunk.decode("utf-8", "ignore")
            strict.feed(txt)
            paranoid.feed(txt)
        if answer_dsr and strict.dsr > replied and time.time() - t0 >= dsr_delay:
            os.write(m, b"\x1b[%d;%dR" % (h, 3 if ambig2 else 2))
            replied = strict.dsr
        if not sent and expect_anim and keys and b"\x1b[K" in raw:
            os.write(m, keys)
            sent = True
        # feed a line once the prompt of the degraded numbered list shows up
        if not sent and feed_line and b":" in raw:
            os.write(m, b"\n")
            sent = True
        if p.poll() is not None:
            # drain once more on the way out
            r, _, _ = select.select([m], [], [], 0.1)
            if r:
                try:
                    txt = os.read(m, 65536).decode("utf-8", "ignore")
                    strict.feed(txt)
                    paranoid.feed(txt)
                except OSError:
                    pass
            break
    got = p.stdout.read().decode().strip()
    os.close(m)
    if p.poll() is None:
        p.kill()
        fails.append(f"{tag}: hung, never exited")
        return
    want = expect_out if expect_out is not None else TT["default"]
    if got != want:
        fails.append(f"{tag}: stdout={got!r} want {want!r}")
    if expect_anim:
        if strict.scrolls > 4:
            fails.append(f"{tag}: drop! scrolled {strict.scrolls} times (>4) — canvas drift")
        if paranoid.wraps:
            fails.append(f"{tag}: {paranoid.wraps} line wraps — clip choke point missed a clamp")
        if b"\x1b[?25l" not in raw:
            fails.append(f"{tag}: no animation entered (animation expected)")
        if "✓" not in strict.screen():
            fails.append(f"{tag}: no confirmation banner in the final frame")
    else:
        if b"\x1b[?25l" in raw:
            fails.append(f"{tag}: must not enter animation (degraded path expected)")


# ── matrix ──
for w, h in [(40, 24), (55, 24), (60, 10), (72, 24), (80, 24), (80, 7),
             (100, 24), (120, 50), (200, 24)]:
    run_case(f"anim {w}x{h}", w, h, b"\r")
run_case("anim 80x24 Esc", 80, 24, b"\x1b")
if CD:
    run_case("countdown 80x24 no keys", 80, 24, b"")            # 3s timeout → default
run_case("A2 width 80x24", 80, 24, b"\r", ambig2=True)          # CJK terminal: ★=2 cells, relayout
_ord = TT.get("picker_order") or [TT["default"]]
_right = _ord[min(len(_ord) - 1, _ord.index(TT["default"]) + 1)]   # right neighbor of default
run_case("A2 width 100x24 →Enter", 100, 24, b"\x1b[C\r", ambig2=True, expect_out=_right)
run_case("height gate 80x5", 80, 5, b"", expect_anim=False, feed_line=True)
run_case("probe failure (no DSR reply)", 80, 24, b"", answer_dsr=False,
         expect_anim=False, feed_line=True)
run_case("late DSR 600ms (high-latency SSH)", 80, 24, b"\r", dsr_delay=0.6)
run_case("non-UTF8 locale", 80, 24, b"", env_extra={"LC_ALL": "C", "LANG": "C"},
         expect_anim=False, feed_line=True)

if fails:
    print("; ".join(fails))
    sys.exit(1)
print(f"OK matrix: all {15 if CD else 14} cases passed")
sys.exit(0)
