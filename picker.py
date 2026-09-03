#!/usr/bin/env python3
"""cct tier picker "Gilded Shuttle" — stdout emits a single line, the machine-readable tier
name; animation/banner all go to stderr.

Skeleton: "Gilded Shuttle" + chrome header line and channel separation.
Tier data is read from tiers.json (single source of truth), not hard-coded.
Usage: python3 picker.py <tiers.json>   → stdout: tier name (e.g. balance)

Four terminal-adaptation layers (0.1.3; structural cure for the line wrap / canvas drift /
scroll-spam at 80 columns):
  L1 render choke point: every line goes through clip(), clamped to display width ≤ tw-1
     (over-wide line wrap is structurally impossible) + DECAWM off during the animation
     (ESC[?7l, a hardware-level second belt: even a missed clamp only truncates instead of
     wrapping, restored on exit)
  L2 geometry lifecycle: height <6 / width <40 gates; shrinking mid-animation → fall back to
     the list immediately; width re-read live on every frame
  L3 probe instead of assumption: a 250ms silent probe before the animation (\\r★ + DSR
     cursor-position query) nails down both a-priori unknowns at once — ① whether the
     terminal renders Ambiguous wide characters (★◆·←→) as 1 cell or 2 (2 cells → switch to
     the A=2 width table and re-lay out) ② whether the terminal understands ANSI at all
     (no DSR reply → fall back to the list).
     There is also a locale gate: on a non-UTF-8 locale the terminal's multi-byte layout
     math is necessarily wrong → list
  L4 tests: tests/qa_picker_vt.py ships its own mini VT simulator and renders in simulation
     over a matrix of width 40-200 × height 5-50 × A1/A2 × probe failure × locale,
     asserting zero canvas drift and zero line wrap
Fallback ladder: a failure in any layer only degrades (numbered list → silent default tier),
it never blocks the main flow.
"""
import json
import math
import os
import re
import select
import sys
import time
import unicodedata

ERR = sys.stderr
AMBIG = False                  # L3-probe measured: East-Asian Ambiguous rendered as 2 cells?
PENDING = bytearray()          # user keys mis-swallowed by probe window; getkey consumes first


def cw(c):
    w = unicodedata.east_asian_width(c)
    return 2 if (w in "WF" or (AMBIG and w == "A")) else 1


def cells(s):
    return sum(map(cw, s))


TT = json.load(open(sys.argv[1], encoding="utf-8"))
_by = {t["name"]: t for t in TT["tiers"]}
ORDER = [n for n in (TT.get("picker_order") or _by) if n in _by]
# default-tier mark (a terminal that renders it oddly can configure it back to ★)
MARK = TT.get("picker_default_mark") or "★"

def _badge(t: dict) -> str:
    """Display badge: the same yardstick as the exit receipt — the cost/depth delta against
    official max. Promised at the entrance, delivered at the exit, and the ordering matches
    intuition (a money-saving tier talks money, a deep-thinking tier talks depth).
    passthrough (Flex) has no fixed cost — it takes no numeric slot, it only tells a story."""
    _b = TT.get("official_bucket_out_per_turn") or {}
    if t.get("passthrough"):
        # Flex's "numeric slot" = tier-count expansion (official bucket count → number of
        # mapping-table entries, computed from the data, not hard-coded)
        _n5 = len(TT.get("cc_effort_map") or {})
        return f"{len(_b)}→{_n5} efforts" if _b and _n5 > len(_b) else ""
    mx, o = _b.get("max"), t.get("out_per_turn")
    if not mx or not o:
        return ""
    pct = (mx - o) / mx * 100
    return f"−{pct:.0f}% cost" if pct >= 0 else f"+{-pct:.0f}% depth"


ITEMS = []                                # (key, display label, info line)
for _n in ORDER:
    _t = _by[_n]
    _lbl = _t.get("label", _n)
    if _n == TT["default"]:
        _lbl = MARK + _lbl
    _bg = _badge(_t)
    ITEMS.append((_n, _lbl, f"{_bg} · {_t.get('desc', '')}" if _bg else _t.get("desc", "")))
DEFAULT = ORDER.index(TT["default"])
# header topic word (model_label is only used in the session banner)
TITLE = TT.get("picker_title") or "Reasoning Tier"
# >0: after N seconds with no key press, auto-confirm the default (any key cancels)
CD = TT.get("picker_countdown_s") or 0

TRUE = os.environ.get("COLORTERM", "") in ("truecolor", "24bit")
PAL = {"base": ((138, 109, 59), 94), "peak": ((255, 233, 168), 229),
       "brk": ((168, 134, 60), 136), "banner": ((216, 180, 90), 179),
       "gray": ((107, 107, 107), 242), "info": ((154, 143, 122), 246),
       "dim": ((78, 78, 78), 239)}
RAMP = [94, 136, 179, 221, 229]           # 256-color gold ramp (shimmer fallback)


def fgn(name):
    rgb, c256 = PAL[name]
    return "\x1b[38;2;%d;%d;%dm" % rgb if TRUE else "\x1b[38;5;%dm" % c256


def col(sel, g):
    """Selection degree×sheen → foreground color. The cross-fade gradient and shimmer share
    one and the same coloring pipeline."""
    if sel <= 0.02:
        return fgn("gray")
    if TRUE:
        def mix(a, b, t):
            return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))
        gold = mix(PAL["base"][0], PAL["peak"][0], g ** 1.4)
        return "\x1b[38;2;%d;%d;%dm" % mix(PAL["gray"][0], gold, sel)
    return "\x1b[38;5;%dm" % (RAMP[min(4, int(g * 4.999))] if sel > 0.5 else 242)


GAP, H = 6, 4
POS, OCC = [], set()                      # pre-layout: start cell + text occupancy table
ROW_W = 0
BRACKETS = True


def _build_layout():
    """Recompute the layout against the current width table (A=1/A=2). Contract kept:
    gate ③ changing GAP does not trigger a recompute."""
    global ROW_W
    POS.clear()
    OCC.clear()
    x = 0
    for _, _s, _ in ITEMS:
        POS.append(x)
        OCC.update(range(x, x + cells(_s)))
        x += cells(_s) + GAP
    ROW_W = x - GAP


_build_layout()

_ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")


def clip(line, tw):
    """L1 render choke point: clamp the display width to ≤ tw-1 (the -1 dodges the "last
    column pending-wrap" that terminals handle inconsistently); ANSI sequences pass through
    with zero width; \\x1b[0m is appended at the cut to prevent style bleed. No line that
    leaves through this exit can wrap."""
    out, w, i, n = [], 0, 0, len(line)
    while i < n:
        m = _ANSI.match(line, i)
        if m:
            out.append(m.group(0))
            i = m.end()
            continue
        ch = line[i]
        if w + cw(ch) > tw - 1:
            out.append("\x1b[0m")
            break
        out.append(ch)
        w += cw(ch)
        i += 1
    return "".join(out)


def label_str(s, x0, sel, ph, bw=4.0):
    hi = ph * (cells(s) + 2 * bw) - bw     # highlight center: off-canvas in→off-canvas out
    out, cx = [], x0
    for c in s:
        d = abs(cx + cw(c) * 0.5 - x0 - hi)
        g = max(0.0, math.cos(math.pi * min(d, bw) / (2 * bw))) ** 2
        out.append(col(sel, g) + ("\x1b[1m" if sel * g > 0.75 else "") + c + "\x1b[22m")
        cx += cw(c)
    return "".join(out)


def brk(colx, pad, ch):
    """If the bracket column hits a text cell, it dodges for this frame and is not drawn
    (grazing a glyph leaves ghosting)."""
    c = int(round(colx))
    if c in OCC or c < -2 or c > ROW_W + 2:
        return ""
    return "\x1b[%dG%s%s\x1b[0m" % (pad + c + 1, fgn("brk"), ch)


def frame(fx, bl, br, ph, tw, bw=4.0, cd=None):
    pad = max(2, (tw - ROW_W) // 2)
    parts, info, ic = [], "", 0
    for i, (_, s, d) in enumerate(ITEMS):
        sel = max(0.0, 1.0 - abs(fx - i))
        if sel >= 0.5:
            info, ic = d, pad + POS[i] + cells(s) // 2
        parts.append(label_str(s, POS[i], sel, ph if sel > 0.02 else 0.0, bw))
    l1 = " " * pad + (" " * GAP).join(parts)
    if BRACKETS:
        l1 += brk(bl, pad, "❮") + brk(br, pad, "❯")
    # The header keeps the title only: the model name does not affect the three-way choice
    # on this screen = noise; "only supports" is even more of a fake constraint (rule ③ zero
    # rejection). The home of model info is the session banner and the receipt, where the
    # timing is right.
    l0 = fgn("dim") + "◆ cct · " + TITLE
    l2 = " " * max(0, ic - cells(info) // 2) + fgn("info") + info
    # The hint line shrinks intelligently (segments are dropped one by one when they do not
    # fit, keeping Enter/Esc and the countdown digits), clip is the final guarantee
    # Number quick-select (1-N) is kept as a hidden shortcut, not shown in the hint line
    # (one fewer cognitive item)
    l3t = "←/→ move · Enter confirm · Esc default"
    if cd is not None:
        l3t += " · default in %ds" % cd
    if cells(l3t) > tw - 1:
        l3t = ("" if cd is None else "default in %ds · " % cd) + "Enter confirm · Esc default"
    l3 = " " * min(pad, max(0, tw - 1 - cells(l3t))) + fgn("dim") + l3t
    return "\x1b[%dA\r" % H + "".join(
        "\x1b[K%s\x1b[0m\n" % clip(ln, tw) for ln in (l0, l1, l2, l3))


def term_size():
    """Geometry must be queried on stderr — under $(...) capture stdout is a pipe and the
    ioctl blows up (measured, we hit this in practice)."""
    try:
        ts = os.get_terminal_size(ERR.fileno())
        return (ts.columns if ts.columns > 0 else 80,
                ts.lines if ts.lines > 0 else 24)
    except OSError:
        return 80, 24


def term_w():
    return term_size()[0]


def _read_pending_or_fd(fd, n):
    if PENDING:
        b = bytes(PENDING[:n])
        del PENDING[:n]
        return b
    return os.read(fd, n)


def getkey(fd, timeout):
    if not PENDING and not select.select([fd], [], [], timeout)[0]:
        return None
    c = _read_pending_or_fd(fd, 1).decode(errors="ignore")
    # bare-Esc disambiguation: a 30ms window (10ms misjudges under SSH)
    if c == "\x1b":
        if not PENDING and not select.select([fd], [], [], 0.03)[0]:
            return "esc"
        seq = _read_pending_or_fd(fd, 2).decode(errors="ignore")
        if len(seq) < 2 and select.select([fd], [], [], 0)[0]:
            seq += os.read(fd, 2 - len(seq)).decode(errors="ignore")
        return {"[C": "right", "[D": "left", "OC": "right", "OD": "left"}.get(seq, "esc")
    if c in "123456789" and int(c) <= len(ITEMS):
        return ("go", int(c) - 1)
    return {"h": "left", "l": "right", "\r": "ok", "\n": "ok",
            "q": "esc", "\x03": "esc"}.get(c)


def fallback_list():
    """Animation-free fallback: plain-text numbered list (TERM=dumb / NO_COLOR / non-UTF8 /
    narrow or short screen / probe failure)."""
    for i, (_, lbl, info) in enumerate(ITEMS):
        mark = " ★default" if i == DEFAULT else ""
        ERR.write("  %d. %-10s %s%s\n" % (i + 1, lbl.lstrip("★" + MARK), info, mark))
    ERR.write("Choose 1-%d (Enter=default): " % len(ITEMS))
    ERR.flush()
    try:
        s = input().strip()
    except (EOFError, KeyboardInterrupt):
        s = ""
    # last decontamination pass: strip a late DSR reply when it mixed into the input line
    s = _ANSI.sub("", s).strip()
    return int(s) - 1 if s.isdigit() and 1 <= int(s) <= len(ITEMS) else DEFAULT


def _probe(fd):
    """L3 probe: \\r★ + DSR (ESC[6n). A reply within 1s → the cursor column decides the
    Ambiguous width (col≥3 = A rendered as 2 cells); no reply → the terminal ignores even
    DSR, its ANSI capability is in doubt → degrade.
    The 1s window: with a 250ms SSH round trip we measured replies arriving late and being
    misjudged (the late bytes also get echoed as ^[[43;2R); it returns the moment the reply
    arrives, so fast terminals notice nothing and only a truly dumb terminal pays the full 1s.
    User key presses that slipped into the probe window are handed back to PENDING, so fast
    typing is not swallowed."""
    ERR.write("\r★\x1b[6n")
    ERR.flush()
    resp = b""
    end = time.time() + 1.0
    while time.time() < end and b"R" not in resp:
        if select.select([fd], [], [], max(0.0, end - time.time()))[0]:
            resp += os.read(fd, 64)
    ERR.write("\r\x1b[K")
    ERR.flush()
    m = re.search(rb"\x1b\[(\d+);(\d+)R", resp)
    if not m:
        # Timeout: discard the fragments that did arrive and flush the input queue — so that
        # an even later reply is not taken as user input and echoed as garbage once termios
        # is restored (echo back on)
        import termios as _t
        try:
            _t.tcflush(fd, _t.TCIFLUSH)
        except OSError:
            pass
        return None
    PENDING.extend(resp[:m.start()] + resp[m.end():])
    return int(m.group(2))


def _animate():
    """Animation core. Returns ("ok", idx) / ("noansi",) / ("narrow",); the termios/canvas
    lifecycle is self-contained."""
    global AMBIG
    import termios
    import tty
    fd, cur = sys.stdin.fileno(), DEFAULT
    old = termios.tcgetattr(fd)
    canvas = False
    try:
        tty.setcbreak(fd)
        pcol = _probe(fd)
        if pcol is None:
            return ("noansi",)
        if pcol >= 3 and not AMBIG:
            # this terminal draws ★ as 2 cells → recompute the whole layout with A=2
            AMBIG = True
            _build_layout()
        ERR.write("\x1b[?7l\x1b[?25l" + "\n" * H)   # L1: auto-wrap off + hide cursor + canvas
        ERR.flush()
        canvas = True
        edge = lambda i: (POS[i] - 2.0, POS[i] + cells(ITEMS[i][1]) + 1.0)
        fx, ph = float(cur), 0.0
        bl, br = edge(cur)
        deadline = time.time() + CD if CD > 0 else None
        while True:
            tw = term_w()
            if tw < 40:                    # L2: shrank mid-animation → clear canvas, go list
                return ("narrow",)
            tl, tr = edge(cur)
            going_r = tr > br
            bl += (tl - bl) * (0.42 if going_r else 0.62)  # two-edge asymmetry: capsule stretch
            br += (tr - br) * (0.62 if going_r else 0.42)
            fx += (float(cur) - fx) * 0.55
            moving = abs(bl - tl) + abs(br - tr) > 0.6
            cd = None if deadline is None else max(0, int(math.ceil(deadline - time.time())))
            ERR.write(frame(fx, bl, br, ph, tw, cd=cd))
            ERR.flush()
            k = getkey(fd, 0.033 if moving else 0.1)
            if k is not None:
                deadline = None            # a key was pressed → countdown cancelled
            elif deadline is not None and time.time() >= deadline:
                return ("ok", DEFAULT)     # timeout = default tier (same as the Esc path)
            if not moving:
                ph = (ph + 0.045) % 1.0    # the sheen freezes while sliding
            if k == "left":
                cur = max(0, cur - 1)
            elif k == "right":
                cur = min(len(ITEMS) - 1, cur + 1)
            elif k == "esc":
                return ("ok", DEFAULT)
            elif k == "ok":
                break
            elif isinstance(k, tuple):
                cur = k[1]
                fx = float(cur)
                bl, br = edge(cur)
                ERR.write(frame(fx, bl, br, ph, term_w()))
                ERR.flush()
                time.sleep(0.12)           # freeze-frame on quick select
                break
        for j in range(4):                 # Enter seal: wide light band sweeps at 3× speed
            ERR.write(frame(float(cur), bl, br, (ph + 0.25 * (j + 1)) % 1.0,
                            term_w(), bw=8.0))
            ERR.flush()
            time.sleep(0.033)
        return ("ok", cur)
    except KeyboardInterrupt:              # ISIG is on, the \x03 mapping cannot cover it
        return ("ok", DEFAULT)
    finally:
        # Canvas cleanup split: ok→main erases + banner; narrow→pick() erases then degrades;
        # noansi has no canvas
        ERR.write("\x1b[?7h")              # L1: restore auto-wrap (every exit path)
        ERR.flush()
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


def pick():
    global GAP, BRACKETS
    if not (sys.stdin.isatty() and ERR.isatty()):          # gate ① non-TTY: silent default
        return DEFAULT, False
    if os.environ.get("TERM") == "dumb" or os.environ.get("NO_COLOR"):
        return fallback_list(), False                      # gate ② animation-free fallback
    loc = (os.environ.get("LC_ALL") or os.environ.get("LC_CTYPE")
           or os.environ.get("LANG") or "")
    if loc and "utf" not in loc.lower():                   # gate ②¼ non-UTF8: layout math
        return fallback_list(), False                      # is necessarily wrong
    if os.name == "nt":                                    # gate ②½ Windows: no termios/tty,
        return fallback_list(), False                      # select rejects stdin → list
    tw, th = term_size()
    if th < 6:                                             # gate ②¾ too short: no room for
        return fallback_list(), False                      # the canvas + banner
    # gate ③ the row does not fit: tighten the gaps, drop the brackets, rebuild.
    # The trigger is the measured row width, not a fixed column count. The old constant 55 was
    # tuned when the table held four short labels and the row was 40 cells wide at the default
    # gap — comfortably inside 55. Six labels make it 61, so 55-63 tightened nothing and clip()
    # cut the last label off the right edge: a 60-column split pane drew five tiers out of six
    # while the arrow key still walked into the one that was not there.
    # frame() lays the row out at pad = max(2, …) and clip() trims at tw-1, so a fully visible
    # row needs ROW_W + 3 columns.
    if tw < ROW_W + 3:
        GAP, BRACKETS = 2, False
        _build_layout()
    if tw < 40:                                            # gate ④ extremely narrow: list
        return fallback_list(), False
    # Below 40 the numbered list takes over; between 40 and the tightened row width the row is
    # still clipped, which is the degradation this picker has always accepted — clip() guarantees
    # no line ever wraps, and a truncated label beats a canvas that scrolls.
    res = _animate()
    if res[0] == "ok":
        return res[1], True
    if res[0] == "narrow":                                 # shrank mid-animation: erase the
        ERR.write("\x1b[%dA\r\x1b[J\x1b[?25h" % H)         # canvas, then degrade
        ERR.flush()
    return fallback_list(), False


def main():
    cur, drew = pick()
    key, lbl, info = ITEMS[cur]
    if drew:                                               # erase canvas + one-line
        ERR.write("\x1b[%dA\r\x1b[J\x1b[?25h" % H)         # confirmation banner
        # Display label up front: users know Value/Flex/Deeper, not the internal names
        banner = ("%s◆ %s ✓\x1b[0m %s%s\x1b[0m"
                  % (fgn("banner"), lbl.lstrip("★" + MARK), fgn("info"), info))
        # the banner goes through the L1 choke point too (the matrix caught a miss here)
        ERR.write(clip(banner, term_w()) + "\n")
        ERR.flush()
    # stdout: machine-readable tier name, zero ANSI
    print(key)


if __name__ == "__main__":
    main()
