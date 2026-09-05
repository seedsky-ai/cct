#!/usr/bin/env python3
"""cct — Claude Code thinking-tier launcher (the single cross-platform implementation;
Windows/macOS/Linux share one code path).

Entry chain: npm bin → cct.js (Node shim, its only job is finding Python) → this file;
running ./cct straight from the repo → this file.
The behaviour of the original bash version is preserved item by item; only three platform
differences remain:
  · Shielding the child from Ctrl+C: POSIX uses start_new_session (the bash version relied on
    "a & background job of a non-interactive shell ignores SIGINT by default"), Windows uses
    CREATE_NEW_PROCESS_GROUP — otherwise a Ctrl+C typed by the user inside claude also kills
    the relay, and every later request 502s
  · claude command resolution: on Windows npm installs claude.cmd, which must be started via
    `cmd /d /s /c "..."`
  · picker: Windows has no termios → numbered-list fallback (see gate ②½ in picker.py)
Deliberate fixes relative to the bash version:
  · Ctrl+C inside the health-check window → silent 130 (the original wrongly reported
    "relay failed to start" with exit 1)
  · bad ledger rows (killed mid-write / disk full) are skipped row by row, without swallowing
    claude's exit code
  · tiers.json missing / bad JSON: list reports the error with exit 1 (the original exited 0
    by accident), the tier-selection path still exits 2

Usage:
  cct [command...]              wrapped launch; command defaults to claude
  cct -e <tier> [command...]    pick a tier, e.g.: cct -e deep claude
  cct list                      tier table

Tier selection happens only at launch (picker / -e; since 0.1.5 tier names are no longer valid
model names, the /model tier-name channel has been removed); inside an official session CC's
per-request /effort mapping stays fully live.
On exit a spend receipt is printed automatically: actually paid (DeepSeek time-of-day price)
vs the benchmark official Claude price = how much was saved.

Mechanism: every session starts a private relay (ephemeral port + its own ledger); environment
variables are handed to the child process only, and ANTHROPIC_BASE_URL is never exported
globally (that would hijack the CC session running outside).
Auth: cct has zero key logic — claude's requests carry their own auth header, the relay
forwards it verbatim, and only the effort part of a forwarded request is modified.
"""
import collections
import json
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.parse

# On Chinese Windows, redirected stdio defaults to GBK and ✓★◆ raise UnicodeEncodeError →
# force utf-8 everywhere.
# line_buffering=True matches the immediate flush of bash echo (otherwise, behind a pipe, the
# banner lands after the child process's output).
# Do not inject PYTHONUTF8 into the environment: it would leak into the wrapped claude and its
# descendants (changing the default encoding of the user's python scripts); picker/relay each
# reconfigure themselves and all file IO is explicitly utf-8, so it is not needed.
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
    except Exception:                                              # noqa: BLE001
        pass

DIR = os.path.dirname(os.path.abspath(__file__))
TIERS_JSON = os.environ.get("CCT_TIERS") or os.path.join(DIR, "tiers.json")
SESS_DIR = (os.environ.get("CCT_SESS_DIR")
            or os.path.join(os.path.expanduser("~"), ".cct", "sessions"))
FLASH = "deepseek-v4-flash"

# ═══ Auto-update (0.1.4): background probe + cache read up front (zero startup latency) ·
#     fail-open · forceBefore forced-update floor pre-wired (5-day grace from the first
#     sighting on this machine) · CI escape hatch CCT_FORCE_ACK ═══
UPD_CACHE = os.path.join(os.path.expanduser("~"), ".cct", "update-check.json")
GRACE_S = 5 * 86400                            # forced-update grace: 5 days


def _pkg_info():
    """Read the package name/version from our own package.json — switching scope changes one
    field and every message follows automatically."""
    try:
        with open(os.path.join(DIR, "package.json"), encoding="utf-8") as f:
            p = json.load(f)
        return p.get("name") or "cct", p.get("version") or "0"
    except Exception:                                              # noqa: BLE001
        return "cct", "0"


def _upd_channel():
    """Update channel = the dist-tag this copy was published from (publishConfig.tag, default
    latest). If a pre-release is ever published on a channel like `npm publish --tag beta`,
    this function guarantees the probe queries /beta — a hard-coded /latest would 404, and the
    silent fail-open means that batch of users would never receive an update prompt.
    CCT_UPDATE_TAG overrides it."""
    t = os.environ.get("CCT_UPDATE_TAG")
    if t:
        return t
    try:
        with open(os.path.join(DIR, "package.json"), encoding="utf-8") as f:
            return str((json.load(f).get("publishConfig") or {}).get("tag") or "latest")
    except Exception:                                              # noqa: BLE001
        return "latest"


def _ver_t(v):
    out = []
    for part in str(v).split("-")[0].split("."):
        try:
            out.append(int(part))
        except ValueError:
            out.append(0)
    return tuple(out)


def _upd_read():
    try:
        with open(UPD_CACHE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:                                              # noqa: BLE001
        return {}


def _upd_write(d):
    try:
        os.makedirs(os.path.dirname(UPD_CACHE), exist_ok=True)
        tmp = UPD_CACHE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(d, f)
        os.replace(tmp, UPD_CACHE)
    except OSError:
        pass


def _upd_probe():
    """Hidden entry point (background child process): query the registry for the latest version
    and write the cache. Silent throughout; any failure = fail-open."""
    name, _cur = _pkg_info()
    cache = _upd_read()
    cache["checked_at"] = time.time()
    try:
        import urllib.request
        reg = (os.environ.get("CCT_REGISTRY") or "https://registry.npmjs.org").rstrip("/")
        url = reg + "/" + urllib.parse.quote(name, safe="@") + "/" + _upd_channel()
        # honour the system proxy (the registry is remote)
        with urllib.request.urlopen(url, timeout=4) as r:
            man = json.load(r)
        latest = str(man.get("version") or "")
        fb = str((man.get("cct") or {}).get("forceBefore") or "") or None
        if latest:
            cache["latest"] = latest
        # the forced-update floor version changed → the grace period restarts from zero
        if fb != cache.get("force_before"):
            cache["force_before"] = fb
            cache["force_first_seen"] = time.time() if fb else None
    except Exception:                                              # noqa: BLE001
        pass
    _upd_write(cache)


def _upd_spawn():
    """Spawn a background probe on every launch (throttled to 24h); the main flow never waits."""
    if os.environ.get("CCT_NO_UPDATE_CHECK"):
        return
    if time.time() - (_upd_read().get("checked_at") or 0) < 86400:
        return
    try:
        kw = (dict(creationflags=subprocess.CREATE_NEW_PROCESS_GROUP) if os.name == "nt"
              else dict(start_new_session=True))
        subprocess.Popen([sys.executable, os.path.abspath(__file__), "__update_probe__"],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **kw)
    except Exception:                                              # noqa: BLE001
        pass


def _upd_gate():
    """Startup gate (reads the cache, no network): pop a menu when a human is present, print a
    one-line notice when not; forceBefore hit → strong reminder inside the grace period, hard
    block once it expires (CI: exit code 1 + the CCT_FORCE_ACK escape hatch)."""
    if os.environ.get("CCT_NO_UPDATE_CHECK"):
        return
    name, cur = _pkg_info()
    c = _upd_read()
    latest = c.get("latest")
    if not latest or not _ver_t(latest) > _ver_t(cur):
        return
    fb = c.get("force_before")
    forced = bool(fb) and _ver_t(fb) > _ver_t(cur)
    hard, left = False, 0
    if forced:
        first = c.get("force_first_seen")
        if not first:                                              # first seen here → grace starts
            first = c["force_first_seen"] = time.time()
            _upd_write(c)
        hard = time.time() > first + GRACE_S
        left = max(1, int((first + GRACE_S - time.time()) // 86400) + 1)
    cmd = f"npm install -g {name}"
    interactive = (sys.stdin.isatty() and sys.stderr.isatty()
                   and not os.environ.get("CCT_NO_PICKER"))
    if not interactive:
        if forced and hard:
            if os.environ.get("CCT_FORCE_ACK"):
                print(f"⛔ cct {cur} disabled (needs ≥{fb}) — CCT_FORCE_ACK set, proceeding",
                      file=sys.stderr)
                return
            print(f"⛔ cct {cur} disabled (needs ≥{fb}) — run: {cmd}"
                  f"  (emergency bypass: CCT_FORCE_ACK=1)", file=sys.stderr)
            sys.exit(1)
        if c.get("skip_version") == latest and not forced:
            return
        print(f"✨ cct {latest} available (now {cur}) — {cmd}", file=sys.stderr)
        return
    if c.get("skip_version") == latest and not forced:
        return
    if forced and hard:
        print(f"⛔ Update required! {cur} → {latest} (versions < {fb} are disabled)",
              file=sys.stderr)
        print(f"› 1. Update now (runs {cmd})\n  2. Exit", file=sys.stderr)
    elif forced:
        print(f"✨ Update required soon! {cur} → {latest} ({left} day(s) left)", file=sys.stderr)
        print(f"› 1. Update now (runs {cmd})\n  2. Skip\n  3. Skip this version",
              file=sys.stderr)
    else:
        print(f"✨ Update available! {cur} → {latest}", file=sys.stderr)
        print(f"› 1. Update now (runs {cmd})\n  2. Skip\n  3. Skip this version",
              file=sys.stderr)
    sys.stderr.write("Select [1]: ")
    sys.stderr.flush()
    try:
        choice = input().strip()
    except (EOFError, KeyboardInterrupt):
        choice = "2"
    if choice in ("", "1"):
        rc = subprocess.call(cmd, shell=True)      # shell=True: also works for win32 npm.cmd
        if rc == 0:
            print("✓ Updated — takes effect next launch", file=sys.stderr)
            return
        print(f"✗ update failed (rc={rc}) — run manually: {cmd}", file=sys.stderr)
        if forced and hard:
            print("  emergency bypass this run: CCT_FORCE_ACK=1", file=sys.stderr)
            sys.exit(1)
        return
    if forced and hard:
        sys.exit(1)                                # a hard block offers only update / exit
    if choice == "3":
        c["skip_version"] = latest
        _upd_write(c)


def _tiers(exit_code: int) -> dict:
    try:
        with open(TIERS_JSON, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError) as e:
        print(f"✗ cannot read tier table {TIERS_JSON}: {e}", file=sys.stderr)
        sys.exit(exit_code)


def cmd_list() -> None:
    """Tier detail table. tb_acc is never put on screen; badges all use the cost/depth
    convention vs official max (the same yardstick as the exit receipt) + the description."""
    tt = _tiers(1)
    _mx = (tt.get("official_bucket_out_per_turn") or {}).get("max")
    print(f"{'tier':<10s}{'vs max':<13s}notes")
    for t in tt["tiers"]:
        star = "  ★default" if t["name"] == tt["default"] else ""
        lab = f"({t['label']})" if t.get("label") and t["label"] != t["name"] else ""
        o = t.get("out_per_turn")
        if t.get("passthrough"):
            _nb, _n5 = len(tt.get("official_bucket_out_per_turn") or {}), len(tt.get("cc_effort_map") or {})
            bg = f"{_nb}→{_n5} efforts" if _nb and _n5 > _nb else ""
        elif not _mx or not o:
            bg = ""
        else:
            _p = (_mx - o) / _mx * 100
            bg = f"−{_p:.0f}% cost" if _p >= 0 else f"+{-_p:.0f}% depth"
        print(f"{t['name']:<10s}{bg:<13s}{t.get('desc', '')}{lab}{star}")


def _price_row(p: dict, r: dict):
    """Price one row (DeepSeek 2026-08 time-of-day price table): peak/off-peak is decided from
    the Beijing time of the ledger row's ts (fixed UTC+8 offset, immune to the host timezone),
    peak = Beijing 9-12/14-18 (half-open intervals: 12:00 and 18:00 sharp already count as
    off-peak); pro passthrough rows use the pro price (= 3× flash). Returns (CNY, segment,
    is pro, output unit price CNY/M); segment None = compatibility with the old flat price
    table (custom tiers.json): a single price, no time-of-day split."""
    pro = False
    if "input_miss" in p:
        u, seg = {"hit": p["cache_hit"], "miss": p["input_miss"], "out": p["output"]}, None
    else:
        h = time.gmtime((r.get("ts") or time.time()) + 8 * 3600).tm_hour
        peak = any(a <= h < z for a, z in p.get("peak_hours_beijing") or [[9, 12], [14, 18]])
        pro = str(r.get("used") or "").startswith("deepseek-v4-pro")
        u = p["deepseek-v4-pro" if pro else "deepseek-v4-flash"]["peak" if peak else "off"]
        seg = "peak" if peak else "off"
    cny = ((r.get("inp") or 0) * u["miss"] + (r.get("cache_r") or 0) * u["hit"]
           + (r.get("out") or 0) * u["out"]) / 1e6
    return cny, seg, pro, u["out"]


def receipt(ledger: str, sess_label: str = "") -> None:
    """Exit receipt: actually paid (time-of-day pricing, row by row) vs the benchmark official
    price + the gain from intervening on the thinking level (ported from the bash version's
    heredoc)."""
    tj = _tiers(1)
    inp = out = cr = calls = 0
    ds = ds_peak = ds_off = ds_pro = out_cost = 0.0    # row-by-row time-of-day totals (CNY)
    tiers, touts = collections.Counter(), collections.Counter()
    effmaps = collections.Counter()            # (eff_in, tier) mapping hits
    # times /effort was overridden by the pinned tier (the default value is not counted: noise)
    pinned_ign = 0
    _pts = {t["name"] for t in tj["tiers"] if t.get("passthrough")}
    _ccdef = str(tj.get("cc_effort_default", "high")).lower()
    # In a pinned-tier session CC's effort is the one we pinned ourselves (pinned_effort) — that
    # does not count as "the user's choice was overridden", otherwise every session would print
    # one locked line = noise. Only some other value means it was genuinely overridden.
    _pin_eff = str(tj.get("pinned_effort") or "").lower()
    _ccm_on = bool(tj.get("cc_effort_map"))
    p = tj["deepseek_price_cny_per_M"]
    rows = []
    try:
        with open(ledger, encoding="utf-8") as f:
            for x in f:
                try:
                    rows.append(json.loads(x))
                except ValueError:
                    pass                       # skip truncated / bad rows (relay killed mid-write)
    except FileNotFoundError:
        pass
    for r in rows:
        if r.get("status") == 200 and r.get("out"):
            calls += 1
            inp += r.get("inp") or 0
            out += r.get("out") or 0
            cr += r.get("cache_r") or 0
            _c, _seg, _pro, _uo = _price_row(p, r)
            ds += _c
            if _seg == "peak":
                ds_peak += _c
            elif _seg == "off":
                ds_off += _c
            if _pro:
                ds_pro += _c
            out_cost += (r.get("out") or 0) * _uo / 1e6
            if r.get("tier"):
                tiers[r["tier"]] += 1
                touts[r["tier"]] += r.get("out") or 0
            _ei = r.get("eff_in")
            if r.get("eff_map") and _ei and r.get("tier"):
                effmaps[(_ei, r["tier"])] += 1
            elif (_ccm_on and _ei and r.get("tier") and r["tier"] not in _pts
                  and str(_ei).lower() not in (_ccdef, _pin_eff)):
                pinned_ign += 1
    if not calls:
        # the ledger path is not put on screen (diagnostic info; it lives in ~/.cct/sessions/,
        # and the README gives the address)
        print("◆ No successful API calls this session")
        return
    hit = cr / (cr + inp) * 100 if (cr + inp) else 0.0
    # ── Display vocabulary: internal tier names are never put on screen, always the label;
    #    Flex (the official tier) is aggregated by /effort word — that is the word the user
    #    pressed themselves ──
    labels = {t["name"]: t.get("label") or t["name"] for t in tj["tiers"]}
    pts = {t["name"] for t in tj["tiers"] if t.get("passthrough")}
    feffs = {t["name"]: str(t["force_effort"]) for t in tj["tiers"] if t.get("force_effort")}
    ok_rows = [r for r in rows if r.get("status") == 200 and r.get("out")]
    # The Flex group is aggregated by the /effort word the user pressed — including mapped rows
    # (the user pressed medium/xhigh, so they should not see the Classic/Extra display labels in
    # the breakdown line; where the mechanism sent them is explained by the mapped line)
    # Two families inside the group (continuing the banner's extended narrative): official =
    # the official native buckets (passthrough rows), extended = the tiers we calibrated
    # (mapped rows)
    parts = []
    ew_off = collections.Counter(str(r.get("eff_in") or _ccdef).lower()
                                 for r in ok_rows if r.get("tier") in pts)
    ew_ext = collections.Counter(str(r.get("eff_in") or _ccdef).lower()
                                 for r in ok_rows if r.get("eff_map"))
    if ew_off or ew_ext:
        _ptl0 = next((labels.get(n, n) for n in pts if n in labels), "Flex")
        segs = []
        if ew_off:
            segs.append("official: " + " · ".join(f"{w}×{c}" for w, c in ew_off.most_common()))
        if ew_ext:
            segs.append("extended: " + " · ".join(f"{w}×{c}" for w, c in ew_ext.most_common()))
        parts.append(f"{_ptl0}({' | '.join(segs)})")
    solo = collections.Counter(r["tier"] for r in ok_rows
                               if r.get("tier") and r["tier"] not in pts and not r.get("eff_map"))
    for k, v in solo.most_common():
        parts.append(f"{labels.get(k, k)} ×{v}")
    seg = ""
    if ds_peak > 0 and ds_off > 0:
        seg = f"(peak {ds_peak:.2f} + off-peak {ds_off:.2f})"
    elif ds_peak > 0:
        seg = "(peak-hour rate)"
    elif ds_off > 0:
        seg = "(off-peak rate)"
    if ds_pro > 0:
        seg += f" · incl. pro ¥{ds_pro:.2f}"
    # ── Main line: the benchmark = running the same work at "official max thinking level"
    #    throughout (normalized from each tier's internally calibrated output tokens per turn
    #    vs max 2226; same ratio for flash and pro).
    #    Say plainly what percentage of cost was saved + how much faster; the normalized money
    #    is not shown below ¥0.01; Deeper honestly reports "spent more". ──
    buck = tj.get("official_bucket_out_per_turn") or {}
    opt = {t["name"]: t.get("out_per_turn") for t in tj["tiers"]}
    bo_max = buck.get("max")
    est = act = 0.0
    if bo_max:
        for r in ok_rows:
            k = r.get("tier")
            if not k:
                continue                       # foreign-model rows have no calibration, skipped
            bo = (buck.get(str(r.get("eff_in") or _ccdef).lower()) if k in pts
                  else opt.get(k))
            if bo:
                est += r["out"] * bo_max / bo
                act += r["out"]
    saved = est - act
    ms = tj.get("ms_per_token", 10.2)
    if est > 0 and saved >= 1:
        money = saved * (out_cost / out) if out else 0.0
        m = f"(≈¥{money:.2f})" if money >= 0.01 else ""
        print(f"✓ Saved ≈{saved / est * 100:.1f}% cost{m}"
              f" · ≈{saved * ms / 1000:.0f}s faster")
    elif est > 0 and saved <= -1:
        print(f"◆ Thinking ≈{-saved / est * 100:.1f}% deeper than official max")
    print(f"◆ {' · '.join(parts)} · in {inp + cr:,} tok(cache hit {hit:.1f}%)"
          f" · out {out:,} tok · paid ¥{ds:.2f}{seg}")
    # ── CC effort feedback (kills "silently ineffective"; zero hits = zero output) ──
    if effmaps:
        s = " · ".join(f"{k}→{labels.get(t, t)} ×{n}" for (k, t), n in effmaps.most_common())
        print(f"◆ /effort mapped: {s}")
    # ── Tier-bypass fallback (0.1.7): when the model name is not deepseek-v4*, the relay treats
    # it as a "foreign model" and passes it through untouched (tier=None), so the tier does not
    # apply — reported honestly here. External tools that rewrite ANTHROPIC_MODEL take this
    # path. Zero behaviour change, it only makes it visible; covers every unknown model name to
    # come.
    _byp = [r for r in ok_rows if not r.get("tier")]
    if _byp and sess_label:
        _bm = collections.Counter(str(r.get("asked")) for r in _byp)
        _top, _more = _bm.most_common(1)[0][0], len(_bm) - 1
        print(f"◆ {len(_byp)} request(s) bypassed {sess_label} — model {_top!r}"
              f"{f' (+{_more} more)' if _more else ''} is not governed by tiers")
    # ── Single-model tier, wrong client name: multi-turn requests that arrived under another
    # model name were rewritten to the pin (fine, audited) — but Claude Code ≤2.1.219 replays no
    # thinking in that state (relay _warn_model_mismatch), so the session ran without its own
    # reasoning. Name the offender so the launch can be fixed (a settings.json env block, a
    # --model, a /model switch). One-shot background rewrites are not in this count.
    _fm = [r for r in ok_rows if r.get("forced_multi")]
    if _fm:
        _fn = collections.Counter(str(r.get("asked")) for r in _fm)
        _top, _more = _fn.most_common(1)[0][0], len(_fn) - 1
        _ft = next((labels.get(r["tier"], r["tier"]) for r in _fm if r.get("tier")),
                   sess_label or "this tier")
        print(f"◆ {len(_fm)} multi-turn request(s) arrived as {_top!r}"
              f"{f' (+{_more} more)' if _more else ''} under {_ft}, pinned to "
              f"{_fm[0].get('forced')} — Claude Code ≤2.1.219 replays no thinking in that "
              f"state; launch it under the pinned name and do not switch /model")
    if pinned_ign:
        # the third line uses the same opening as the banner + all English
        _lk = next((k for k, _ in tiers.most_common() if k not in pts), None)
        lock = labels.get(_lk, _lk) if _lk else "this tier"
        ptl = next((labels.get(n, n) for n in pts if n in labels), "Flex")
        if _lk in feffs:
            # A force_effort tier does pin the level, so "locked" is true — but say which level
            # and why, otherwise it reads as the generic virtual-tier lock and the user cannot
            # tell that the value is the one the tier was measured at.
            print(f"◆ /effort pinned to {feffs[_lk]} by {lock} ×{pinned_ign} — the level it was "
                  f"calibrated at; for a free /effort choice, use {ptl}")
        else:
            print(f"◆ /effort locked by {lock} ×{pinned_ign} — for free /effort choice, "
                  f"use {ptl}")
    if any(k in pts for k in tiers):
        # symmetric signpost for Flex sessions: the same reverse hint as the banner
        _pins = [str(labels.get(n, n)) for n in (tj.get("picker_order") or [])
                 if n in labels and n not in pts]
        if _pins:
            print(f"◆ /effort live — for peak performance, use {' or '.join(_pins)}")


def _safe_receipt(ledger: str, sess_label: str = "") -> None:
    """The receipt is only a bonus; no accident may swallow claude's real exit code."""
    try:
        receipt(ledger, sess_label)
    except SystemExit:
        raise
    except Exception as e:                                         # noqa: BLE001
        print(f"⚠ receipt failed: {e!r}", file=sys.stderr)


def _settings_env(path: str) -> dict:
    """Read the env block of one settings.json (tolerant: missing file / bad JSON / not a
    dict → {})."""
    try:
        with open(path, encoding="utf-8") as f:
            e = (json.load(f) or {}).get("env") or {}
            return e if isinstance(e, dict) else {}
    except (OSError, ValueError):
        return {}


def _inject_settings(cmd: list, pin: str, penv: dict):
    """Inject --settings <pin> into claude's arguments, pinning penv back key by key. Returns
    (new cmd, whether the pin succeeded).
    When the user brings their own --settings (file / inline JSON): read it → merge penv on top
    → write the pin file in place of the original value, keeping everything else verbatim; if it
    cannot be parsed, leave the original argument alone and honestly report "not pinned"."""
    base, idx = {}, None
    for i, a in enumerate(cmd[1:], 1):
        if a == "--settings" and i + 1 < len(cmd):
            idx = i + 1
            break
        if a.startswith("--settings="):
            idx = i
            break
    if idx is not None:
        v = cmd[idx].split("=", 1)[1] if cmd[idx].startswith("--settings=") else cmd[idx]
        try:
            if os.path.isfile(v):
                with open(v, encoding="utf-8") as f:
                    base = json.load(f)
            elif v.lstrip().startswith("{"):
                base = json.loads(v)
            else:
                raise ValueError("not a file nor inline JSON")
        except (OSError, ValueError) as e:
            print(f"⚠ your --settings is unreadable({e}), left as-is — BASE_URL not "
                  f"pinned; a settings.json override may bypass the relay", file=sys.stderr)
            return cmd, False
    if not isinstance(base, dict):
        base = {}
    env = base.get("env")
    env = dict(env) if isinstance(env, dict) else {}
    env.update(penv)
    base["env"] = env
    try:
        with open(pin, "w", encoding="utf-8") as f:
            json.dump(base, f, ensure_ascii=False, indent=1)
        try:
            os.chmod(pin, 0o600)           # the merged file may hold user-supplied sensitive keys
        except OSError:
            pass
    except OSError as e:
        print(f"⚠ cannot write pin file({e}) — env injection only; a settings.json "
              f"override would bypass the relay", file=sys.stderr)
        return cmd, False
    if idx is None:
        return [cmd[0], "--settings", pin, *cmd[1:]], True
    out = list(cmd)
    out[idx] = "--settings=" + pin if out[idx].startswith("--settings=") else pin
    return out, True


def _pin_model(cmd: list, model: str, label: str = "") -> list:
    """Single-model tier: put --model <pin> on claude's command line — the top rung of Claude
    Code's model-name precedence (measured on 2.1.219 and 2.1.258: it outranks a settings env
    block, the process environment and a settings "model"). Placed right after the executable,
    before any subcommand: `claude --model X mcp list` is accepted, `claude mcp list --model X`
    is rejected (measured). A --model the user passed is dropped and said so — with two flags
    the last one wins anyway (measured), but overriding silently would hide the fact."""
    out, skip, theirs = [cmd[0]], False, []
    for a in cmd[1:]:
        if skip:
            theirs.append(a)
            skip = False
            continue
        if a == "--model":
            skip = True
            continue
        if a.startswith("--model="):
            theirs.append(a.split("=", 1)[1])
            continue
        out.append(a)
    if any(t != model for t in theirs):
        print(f"⚠ --model {theirs[-1]} overridden — {label or 'this tier'} answers on {model} only")
    return [out[0], "--model", model, *out[1:]]


def _pick_tier(argv: list) -> tuple:
    """Returns (tier, remaining argv). Same order as the bash version: parse -e → picker →
    default → validate."""
    tier = ""
    if argv[:1] in (["-e"], ["--effort"]):
        # an empty string counts as a missing argument (bash ${2:?} fires on null just the same)
        if len(argv) < 2 or not argv[1]:
            print("usage: cct -e <tier> [command...]", file=sys.stderr)
            sys.exit(1)
        tier, argv = argv[1], argv[2:]
    # No -e → the "gilded shuttle" tier-selection animation (the animation goes to stderr,
    # stdout returns only the machine-readable tier name; non-TTY / dumb / narrow terminal /
    # Windows degrade automatically, CCT_NO_PICKER=1 skips it outright)
    if not tier and not os.environ.get("CCT_NO_PICKER"):
        try:
            r = subprocess.run([sys.executable, os.path.join(DIR, "picker.py"), TIERS_JSON],
                               stdout=subprocess.PIPE)
            if r.returncode == 0:
                tier = r.stdout.decode("utf-8", "replace").strip()
        except OSError:
            tier = ""                          # picker won't start = silent default (bash: || true)
    tt = _tiers(2)
    if not tier:
        tier = tt["default"]
    names = {n.lower() for t in tt["tiers"] for n in [t["name"], *t.get("aliases", [])]}
    if tier.lower() not in names:
        print(f"✗ unknown tier {tier!r}; available: {', '.join(t['name'] for t in tt['tiers'])}(see cct list)")
        sys.exit(2)
    return tier, argv, tt


def _resolve_cmd(name: str):
    """PATH resolution + Windows fixups. Returns (exe, None) or (None, exit code)."""
    exe = shutil.which(name)
    if exe and os.name == "nt" and not os.path.splitext(exe)[1]:
        # Python 3.12.0's which ranks the extension-less POSIX sh shim that npm writes ahead of
        # the .cmd (gh-109590, fixed in 3.12.1) — CreateProcess on the bare name is
        # WinError 193, so put the extension back
        for ext in (".exe", ".cmd", ".bat"):
            if os.path.exists(exe + ext):
                exe += ext
                break
    if exe is None:
        # on PATH but not executable → 126 (bash's convention)
        found = shutil.which(name, mode=os.F_OK)
        print(f"✗ not executable: {found}" if found else f"✗ command not found: {name}", file=sys.stderr)
        return None, (126 if found else 127)
    return exe, None


def main(argv: list) -> int:
    _upd_spawn()                               # background probe (throttled to 24h), zero wait
    if argv[:1] == ["list"]:
        cmd_list()
        return 0
    _upd_gate()                                # session path only prompts/blocks (list: zero noise)
    tier, argv, tt = _pick_tier(argv)
    # Display label of the session tier: the receipt's "bypassed tier" fallback line needs it to
    # name the tier (when every request is bypassed the ledger holds no tier at all and it cannot
    # be inferred — and that is exactly the most common shape when an external tool rewrites the
    # model name).
    _sess_lbl = next((str(t.get("label") or t["name"]) for t in tt["tiers"]
                      if tier.lower() in {str(n).lower()
                                          for n in [t["name"], *t.get("aliases", [])]}), tier)
    # force_model (2026-09-02): tiers calibrated against a single model pin it on both sides —
    # here for the model name CC believes it is talking to, and again in the relay when the
    # request goes upstream. Two layers on purpose: the env var keeps /model and the CC UI
    # honest, the relay rewrite catches anything the env var cannot reach (CC's background
    # small-model calls, or a user who overrides ANTHROPIC_MODEL themselves).
    _sess_model = next((str(t["force_model"]) for t in tt["tiers"]
                        if t.get("force_model") and tier.lower() in
                        {str(n).lower() for n in [t["name"], *t.get("aliases", [])]}), FLASH)

    # The global-export footgun warning has been removed: connecting directly through an
    # environment variable is a deliberate user configuration, and repeating the warning is
    # noise; the cct session itself is unaffected by that variable (cenv injection + --settings
    # pin-back take over in two layers).
    # The "never export globally" red line still stands at the README documentation layer.

    cmd = argv or ["claude"]

    # Zero third-party Python dependencies at runtime (installing the package must not involve a
    # pip step): the relay's upstream HTTP now uses pure-stdlib http.client, and python itself is
    # vetted by cct.js / ./cct.
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    ts = time.strftime("%Y%m%d_%H%M%S")
    os.makedirs(SESS_DIR, exist_ok=True)
    ledger = os.path.join(SESS_DIR, f"{ts}_p{port}.jsonl")
    rlog = os.path.join(SESS_DIR, f"{ts}_p{port}.relay.log")

    renv = {k: v for k, v in os.environ.items()
            if k not in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy",
                         "ALL_PROXY", "all_proxy")}
    # DA_BIND=127.0.0.1: cct's relay is private to each session and only serves the local claude;
    # binding 0.0.0.0 pops a firewall authorization dialog on Windows/macOS. For container
    # scenarios, run relay_anthropic.py directly (it defaults to 0.0.0.0).
    renv.update(DA_PORT=str(port), DA_TIER_TABLE=TIERS_JSON, DA_TIER=tier,
                DA_LEDGER=ledger, DA_BIND="127.0.0.1")
    kw = (dict(creationflags=subprocess.CREATE_NEW_PROCESS_GROUP) if os.name == "nt"
          else dict(start_new_session=True))
    with open(rlog, "wb") as lf:
        relay = subprocess.Popen([sys.executable, os.path.join(DIR, "relay_anthropic.py")],
                                 stdout=lf, stderr=lf, env=renv, **kw)
    try:
        # The health check uses http.client rather than curl/urllib: minimal container images
        # often have no curl; urllib's build_opener unconditionally builds an HTTPS context,
        # which blows up outright on a python without ssl / with broken crypto (stripped-down
        # builds, wine) — plain HTTP to 127.0.0.1 should not drag ssl in.
        # http.client also natively ignores proxy env vars (the equivalent upgrade of the old
        # "empty ProxyHandler for proxy immunity").
        import http.client
        ok = False
        for _ in range(40):
            try:
                hc = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
                hc.request("GET", "/health")
                ok = hc.getresponse().status == 200
                hc.close()
                if ok:
                    break
            except Exception:                                      # noqa: BLE001
                pass
            if relay.poll() is not None:
                break
            time.sleep(0.25)
        if not ok:
            print("✗ relay failed to start, log tail:")
            try:
                with open(rlog, encoding="utf-8", errors="replace") as f:
                    sys.stdout.write("".join(f.readlines()[-5:]))
            except OSError:
                pass
            return 1

        # Session banner (all English): display label first + a per-mode "why" —
        # locked tiers such as Value/Deeper explain the benefit of locking (taken from desc),
        # Flex tells the 3→5 extension story; an old tiers.json (no cc_effort_map) keeps the
        # original 0.1.2 banner = compatibility contract.
        # Non-official upstream: the calibration only holds for the official API, so it is
        # reported honestly here (loopback exempt).
        _up = os.environ.get("DA_UPSTREAM", "https://api.deepseek.com/anthropic")
        _uh = urllib.parse.urlsplit(_up).hostname or ""
        _ds_ok = _uh == "api.deepseek.com" or _uh in ("127.0.0.1", "localhost", "::1")
        _ent = next((x for x in tt["tiers"] if tier.lower() in
                     {str(n).lower() for n in [x["name"], *x.get("aliases", [])]}), None)
        _ccm = tt.get("cc_effort_map") or {}
        if not _ds_ok:
            # Warn only, do not degrade: the tier is applied as usual, but state honestly that
            # the calibration is not guaranteed.
            # Show only the hostname, never the full URL — DA_UPSTREAM may carry credentials
            # embedded in the URL.
            print(f"⚠ Non-official upstream ({_uh}) — tiers & pricing are calibrated for "
                  f"api.deepseek.com, so results and billing may differ")
        if _ccm and _ent:
            # The head line keeps only the display label: the model face / relay port are
            # diagnostic-layer info that live in the ledger file name ({ts}_p{port}.jsonl),
            # relay.log and /health, and must not take up the user's field of view.
            # A locked tier points at exactly one way out: Flex is the free choice (since 0.1.5
            # /model switching is no longer mentioned)
            _lbl = _ent.get("label") or _ent["name"]
            _by2 = {e["name"]: e for e in tt["tiers"]}
            # Version identity: hangs off the display-label line — that is the one line every
            # path (picker / -e / the Windows numbered-list fallback / CCT_NO_PICKER) prints,
            # and it never enters the picker canvas, so no terminal-width machinery affects it.
            print(f"◆ {_lbl} · technical preview {_pkg_info()[1]}")
            if _ent.get("passthrough"):
                # Flex reverse signpost: peak performance is over on the locked-tier side
                _pins = [str(_by2[n2].get("label") or n2)
                         for n2 in (tt.get("picker_order") or [])
                         if n2 in _by2 and not _by2[n2].get("passthrough")]
                _hint = f" · for peak performance, use {' or '.join(_pins)}" if _pins else ""
                print(f"  /effort live — official low/high/max extended with medium & xhigh{_hint}")
            else:
                # Reason for locking = end-to-end tuning ("deeper tuning" collided with the mode
                # name Deeper, dropped)
                # Strip the display markers (parentheticals such as locked/beta) — this banner
                # sentence already says locked itself, and carrying the parenthetical a second
                # time would produce the odd sentence "…less cost (beta) · for free /effort…".
                _why = re.sub(r"\s*\([^)]*\)\s*$", "", str(_ent.get("desc", ""))).strip(" ·")
                _pt = next((str(e.get("label") or e["name"]) for e in tt["tiers"]
                            if e.get("passthrough")), None)
                _hint = f" · for free /effort choice, use {_pt}" if _pt else ""
                if _ent.get("force_effort"):
                    # These tiers do not clear the base effort the way the tuned tiers do; they
                    # hold it at the value they were measured with. Naming the value matters —
                    # "locked" alone reads as the generic virtual-tier lock and hides which
                    # level the session is actually running.
                    print(f"  /effort held at {_ent['force_effort']} — {_why or 'this tier'}"
                          f"{_hint}")
                else:
                    print(f"  /effort locked for end-to-end tuning — {_why or 'this tier'}{_hint}")
            if _ent.get("force_model") or _ent.get("force_effort"):
                # Say it out loud: this tier answers on one model at one thinking level whatever
                # /model and /effort show, because that pair is what it was measured on.
                _pins = " / ".join(x for x in (_ent.get("force_model"),
                                               _ent.get("force_effort")) if x)
                print(f"  pinned to {_pins} — the combination this tier is calibrated on")
        else:
            print(f"◆ tier={tier} · model={_sess_model} · relay=127.0.0.1:{port}")

        # NO_PROXY must include localhost: a machine-wide HTTP(S)_PROXY sends API traffic aimed
        # at 127.0.0.1 through the proxy and it 502s (curl ignores upper-case HTTP_PROXY so the
        # smoke test passed, Node's claude honours it so real runs broke).
        # By design CC is none the wiser: CC sees the real model name, and the tier is applied by
        # the relay layer from the session config (DA_TIER).
        cenv = dict(os.environ)
        cenv.update(ANTHROPIC_BASE_URL=f"http://127.0.0.1:{port}", ANTHROPIC_MODEL=_sess_model)
        # Zero intervention on the context window (0.1.6 injected 1M, 0.1.7 reverted it): CC
        # does its own auto-compact against the 200k assumption; users who want the full 1M set
        # CLAUDE_CODE_MAX_CONTEXT_TOKENS themselves.
        for k in ("NO_PROXY", "no_proxy"):
            cenv[k] = "127.0.0.1,localhost" + ("," + cenv[k] if cenv.get(k) else "")
        # The model-slot overrides are commented out (deliberately not overridden) — the outer
        # DEFAULT_OPUS/SONNET/HAIKU/SMALL_FAST/SUBAGENT mappings (e.g. opus→deepseek-v4-pro[1m])
        # are passed through to CC verbatim and are visible in /model; deepseek* names are
        # relayed under their own name, and other names such as claude-* are forwarded with zero
        # intervention.
        # To restore the suppression, just uncomment the following:
        #   cenv.update(ANTHROPIC_DEFAULT_OPUS_MODEL=FLASH, ANTHROPIC_DEFAULT_SONNET_MODEL=FLASH,
        #               ANTHROPIC_DEFAULT_HAIKU_MODEL=FLASH, ANTHROPIC_SMALL_FAST_MODEL=FLASH,
        #               CLAUDE_CODE_SUBAGENT_MODEL=FLASH)
        #
        # ── Single-model tiers (tiers.json force_model) are the one exception, and only they ──
        # The name Claude Code runs under must equal the model the relay answers with: up to
        # 2.1.219 it drops every thinking block from the replayed history the moment the two
        # differ (measured against a stub with that binary — asked flash / answered pro → 0 of 1
        # replayed, asked pro → 1 of 1; 2.1.258 no longer does), and a session in that state
        # runs without its own reasoning while nothing errors. The env export above only holds
        # the lowest rung of CC's model-name precedence (measured, both versions):
        #     --model flag  >  settings env.ANTHROPIC_MODEL (--settings > ~/.claude)  >
        #     process env  >  settings "model"
        # so a force_model tier takes the rungs it can reach: every model slot resolves to the
        # pin here (a /model pick of opus/sonnet/haiku then stays on the pin, and sub-agents /
        # background calls go out under it — the relay would rewrite them anyway), the pin file
        # below carries ANTHROPIC_MODEL, and the claude branch adds --model. Passthrough and
        # depth-tuned tiers are untouched: nothing here runs for them.
        _force = str(_ent.get("force_model") or "") if _ent else ""
        if _force:
            cenv.update(ANTHROPIC_MODEL=_force,
                        ANTHROPIC_DEFAULT_OPUS_MODEL=_force, ANTHROPIC_DEFAULT_SONNET_MODEL=_force,
                        ANTHROPIC_DEFAULT_HAIKU_MODEL=_force, ANTHROPIC_SMALL_FAST_MODEL=_force,
                        CLAUDE_CODE_SUBAGENT_MODEL=_force)

        # ── settings.json hijack guard (0.1.5): at startup CC writes settings.json's env back
        # into the process environment, clobbering the BASE_URL injected via cenv above
        # (measured: zero relay traffic, the tier idling).
        # The CLI --settings layer outranks user/project settings and env is merged key by key
        # across layers (measured: with a single-key file, settings' AUTH_TOKEN survives as
        # usual) → pin the single key ANTHROPIC_BASE_URL (MODEL joins it only under a
        # single-model tier, see below), with zero changes to the user's settings on disk.
        # The effort environment layer: it takes effect for **any** wrapped command (not just
        # claude) — writing it inside the claude-only branch would make behaviour inconsistent
        # when wrapping bash/python, which is extremely easy to misjudge while debugging.
        _penv = {"ANTHROPIC_BASE_URL": f"http://127.0.0.1:{port}"}
        if _force:
            # Single-model tier: the pin file carries the model name too. The --settings layer
            # outranks a ~/.claude/settings.json env block — the one thing that clobbers the
            # cenv export (measured) — and Claude Code writes settings env back into its own
            # environment, so its hooks and Bash children inherit the pin as well.
            _penv["ANTHROPIC_MODEL"] = _force
        if _ent and _ent.get("passthrough"):
            # Flex unlocks /effort: a leftover CLAUDE_CODE_EFFORT_LEVEL outranks the /effort
            # menu inside CC and would silently lock down the "/effort live" promise. Strip both
            # forms at once: the shell env one is removed outright; the settings.json form is
            # pinned to an empty string via the pin file (measured: pinning "" with --settings ≡
            # clearing it, CC falls back to the default high). Zero output on success.
            cenv.pop("CLAUDE_CODE_EFFORT_LEVEL", None)
            _penv["CLAUDE_CODE_EFFORT_LEVEL"] = ""
        elif _ent and _ent.get("force_effort"):
            # A tier that names its own effort pins CC to exactly that, not to pinned_effort.
            # These tiers were calibrated as a (preamble, effort) pair with the relay leaving
            # effort alone, so pinning the usual max here would send a level the tier was never
            # measured at — the relay, honouring keep_effort, would forward it untouched and the
            # session would silently run a different arm. The relay pins the same value again on
            # the way upstream; this half only keeps CC's own client-side behaviour consistent
            # with it.
            _pe = str(_ent["force_effort"])
            cenv["CLAUDE_CODE_EFFORT_LEVEL"] = _pe
            _penv["CLAUDE_CODE_EFFORT_LEVEL"] = _pe
        elif _ent and tt.get("pinned_effort"):
            # A pinned-tier session pins the CC side to max as well. The API side is already
            # taken over by the relay (effort is always rewritten to low to clear the base
            # effort, matching the calibrated construction); what is pinned here is **CC's own
            # client-side behaviour** (status bar / internal heuristics), so that "choosing
            # Deeper means the highest investment" holds on both sides and is no longer at the
            # mercy of effortLevel in the user's settings. env outranks settings.effortLevel
            # (measured), and writing it into the pin file outranks even settings.env.
            _pe = str(tt["pinned_effort"])
            cenv["CLAUDE_CODE_EFFORT_LEVEL"] = _pe
            _penv["CLAUDE_CODE_EFFORT_LEVEL"] = _pe
        if os.path.basename(cmd[0]).lower().split(".")[0] == "claude":
            _pin = os.path.join(SESS_DIR, f"{ts}_p{port}.settings.json")
            cmd, _pin_ok = _inject_settings(cmd, _pin, _penv)
            if _force:
                # Single-model tier: the top rung as well. Env + pin file + --model together
                # leave only an in-session /model switch to a typed name, which the relay
                # reports (relay.log) and the receipt counts.
                cmd = _pin_model(cmd, _force, _sess_lbl)
            # When to speak up: a successful pin-back is completely silent (the success path
            # does not even read settings); ANTHROPIC_MODEL is pinned only by a single-model
            # tier and never checked here (the relay warns when a multi-turn request arrives
            # under another name). The only place we speak up = the pin-back failed AND
            # settings really is hijacking — that is a guaranteed bypass (no tier / no ledger /
            # no pricing), so it must be loud.
            if not _pin_ok:
                for _sp in (os.path.join(os.path.expanduser("~"), ".claude", "settings.json"),
                            os.path.join(os.getcwd(), ".claude", "settings.json"),
                            os.path.join(os.getcwd(), ".claude", "settings.local.json")):
                    _se = _settings_env(_sp)
                    if "ANTHROPIC_BASE_URL" in _se:
                        _sh = urllib.parse.urlsplit(str(_se["ANTHROPIC_BASE_URL"])).hostname or "?"
                        print(f"⚠ {_sp} env sets ANTHROPIC_BASE_URL({_sh}) and pin-back "
                              f"failed — this session will bypass the relay"
                              f"(no tiers/ledger/pricing)")

        exe, err_rc = _resolve_cmd(cmd[0])
        if exe is None:
            # bash's convention: still print the receipt after the env error
            _safe_receipt(ledger, _sess_lbl)
            return err_rc
        if os.name == "nt" and exe.lower().endswith((".cmd", ".bat")):
            # A .cmd must be started through cmd.exe, and quoting must be taken over explicitly
            # with a string + /s: Popen(list)'s list2cmdline follows MSVCRT's convention, which
            # cmd.exe does not accept — an install path containing spaces
            # (C:\Users\Jane Smith\...) combined with arguments containing spaces puts more than
            # 2 quotes after /c, which triggers cmd's old "strip the first and last quote" rule
            # and the command is split at C:\Users\Jane (audit confirmed: blows up every time).
            # /d skips AutoRun.
            inner = subprocess.list2cmdline([exe, *cmd[1:]])
            run = 'cmd /d /s /c "' + inner + '"'
        else:
            run = [exe, *cmd[1:]]
        # Ctrl+C/SIGTERM belong to the claude inside; the wrapper plays dead and stays alive
        # until the receipt has been printed (a bash trap is deferred until the foreground
        # command finishes, so the observed behaviour = ignored). Python-level handlers are not
        # inherited by the child process (they are reset at exec), so claude receives the
        # signals as usual.
        signal.signal(signal.SIGINT, lambda *_: None)
        if os.name != "nt":
            signal.signal(signal.SIGTERM, lambda *_: None)
        try:
            child = subprocess.Popen(run, env=cenv)
        except OSError as e:
            print(f"✗ failed to launch: {cmd[0]}: {e}", file=sys.stderr)
            _safe_receipt(ledger, _sess_lbl)
            return 126
        while True:
            try:
                rc = child.wait()
                break
            except KeyboardInterrupt:
                continue
        signal.signal(signal.SIGINT, signal.default_int_handler)
        if os.name != "nt":
            signal.signal(signal.SIGTERM, lambda *_: sys.exit(143))
        if rc < 0:                             # POSIX: died by signal → 128+n, bash's convention
            rc = 128 - rc
        _safe_receipt(ledger, _sess_lbl)
        return rc
    finally:
        try:                                   # bash: trap 'kill $RELAY_PID' EXIT INT TERM
            relay.terminate()
            relay.wait(3)
        except Exception:                                          # noqa: BLE001
            try:
                relay.kill()
            except Exception:                                      # noqa: BLE001
                pass


if __name__ == "__main__":
    if sys.argv[1:2] == ["__update_probe__"]:  # hidden entry of the background probe child
        _upd_probe()
        sys.exit(0)
    if os.name != "nt":
        # TERM/HUP → SystemExit → the finally block reaps the relay. HUP must be registered: the
        # relay sits in its own session and never receives the terminal hangup signal, so
        # without reaping, every dropped SSH connection leaks a permanent relay (audit
        # confirmed).
        signal.signal(signal.SIGTERM, lambda *_: sys.exit(143))
        signal.signal(signal.SIGHUP, lambda *_: sys.exit(129))
    try:
        sys.exit(main(sys.argv[1:]))
    except BrokenPipeError:                    # a downstream early exit (cct list | head) is normal
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        sys.exit(141)                          # 128+SIGPIPE, the shell pipeline convention
    except KeyboardInterrupt:
        sys.exit(130)
