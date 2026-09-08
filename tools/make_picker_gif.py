#!/usr/bin/env python3
"""Record the real six-tier picker into an animated GIF.

Runs picker.py under a pty exactly the way tests/qa_picker_pty.py does (including answering the
DSR probe), feeds it real key presses, snapshots the emulated screen after each one and renders the
frames with PIL. Nothing is mocked and no frame is hand-drawn: what the GIF shows is what the
terminal shows.

Usage: tools/make_picker_gif.py [out.gif] [cols] [rows]
"""
import fcntl
import os
import pty
import select
import struct
import subprocess
import sys
import termios
import time

import pyte
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "assets", "picker-six-tiers.gif")
COLS = int(sys.argv[2]) if len(sys.argv) > 2 else 100
ROWS = int(sys.argv[3]) if len(sys.argv) > 3 else 6

FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"
FONT_B = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"
SIZE = 15
PAD = 14
BG = (24, 24, 27)
FG = (228, 228, 231)
PALETTE = {  # pyte colour names -> RGB, tuned for a dark terminal
    "black": (60, 60, 66), "red": (248, 113, 113), "green": (134, 239, 172),
    "brown": (250, 204, 21), "yellow": (250, 204, 21), "blue": (125, 211, 252),
    "magenta": (216, 180, 254), "cyan": (103, 232, 249), "white": (228, 228, 231),
    "default": FG,
}


def colour(name, default):
    if not name or name == "default":
        return default
    if name in PALETTE:
        return PALETTE[name]
    if len(name) == 6:                       # pyte gives raw hex for 256/true colour
        try:
            return tuple(int(name[i:i + 2], 16) for i in (0, 2, 4))
        except ValueError:
            pass
    return default


def render(screen, font, font_b):
    w = font.getbbox("M")[2] - font.getbbox("M")[0]
    h = SIZE + 6
    img = Image.new("RGB", (COLS * w + 2 * PAD, ROWS * h + 2 * PAD), BG)
    d = ImageDraw.Draw(img)
    for y in range(ROWS):
        line = screen.buffer[y]
        for x in range(COLS):
            ch = line[x]
            if ch.data in ("", " ") and ch.bg in ("default",):
                continue
            px, py = PAD + x * w, PAD + y * h
            fg = colour(ch.fg, FG)
            bg = colour(ch.bg, BG)
            if ch.reverse:
                fg, bg = bg, fg
            if bg != BG:
                d.rectangle([px, py, px + w, py + h], fill=bg)
            if ch.data.strip():
                d.text((px, py + 2), ch.data, font=font_b if ch.bold else font, fill=fg)
    return img


def main():
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    font, font_b = ImageFont.truetype(FONT, SIZE), ImageFont.truetype(FONT_B, SIZE)
    screen = pyte.Screen(COLS, ROWS)
    stream = pyte.Stream(screen)

    m, s = pty.openpty()
    fcntl.ioctl(s, termios.TIOCSWINSZ, struct.pack("HHHH", ROWS, COLS, 0, 0))
    p = subprocess.Popen([sys.executable, os.path.join(HERE, "picker.py"),
                          os.path.join(HERE, "tiers.json")],
                         stdin=s, stderr=s, stdout=subprocess.PIPE,
                         env={**os.environ, "TERM": "xterm-256color"})
    os.close(s)

    replied = [0]

    def pump(seconds):
        """Drain the pty for `seconds`, feeding the emulator and answering the DSR probe."""
        end = time.time() + seconds
        while time.time() < end:
            r, _, _ = select.select([m], [], [], 0.03)
            if not r:
                continue
            try:
                chunk = os.read(m, 65536)
            except OSError:
                return
            stream.feed(chunk.decode("utf-8", "replace"))
            need = chunk.count(b"\x1b[6n")
            for _ in range(need):
                os.write(m, b"\x1b[%d;2R" % ROWS)
                replied[0] += 1

    frames, durations = [], []

    def shoot(hold_ms):
        frames.append(render(screen, font, font_b))
        durations.append(hold_ms)

    pump(1.2)                       # first paint
    shoot(1100)
    # walk right through all six labels, then come back to the default and confirm
    for _ in range(5):
        os.write(m, b"\x1b[C")
        pump(0.45)
        shoot(650)
    for _ in range(4):
        os.write(m, b"\x1b[D")
        pump(0.35)
        shoot(430)
    os.write(m, b"\r")
    pump(0.8)
    shoot(1500)

    try:
        p.wait(timeout=5)
    except subprocess.TimeoutExpired:
        p.kill()
    chosen = (p.stdout.read() or b"").decode().strip()
    os.close(m)

    frames[0].save(OUT, save_all=True, append_images=frames[1:], duration=durations,
                   loop=0, optimize=True)
    print(f"wrote {OUT}  frames={len(frames)}  size={os.path.getsize(OUT)}B  chosen={chosen!r}")


if __name__ == "__main__":
    main()
