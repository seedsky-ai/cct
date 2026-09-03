#!/usr/bin/env python3
"""Anthropic-format rewriting relay — for "Claude Code as the harness × deepseek-v4-flash".

Why ANTHROPIC_BASE_URL cannot simply point at DeepSeek (three reasons, each a hard requirement):

  ① **You can see which model is actually used.** Official docs: names starting with
     `claude-opus` are mapped by DeepSeek to **deepseek-v4-pro**, and Claude Code sends opus by
     default ⇒ a direct connection **silently ends up on v4-pro**. This relay **forwards
     verbatim** and records the name the client asked for in the ledger, call by call — a
     transparent proxy must not tamper with the request, otherwise the ledger drifts from
     reality and nothing can be attributed after the fact. The model is decided by the caller
     via `--model` / `ANTHROPIC_MODEL`; the relay only **observes and warns**
     (see `DA_PIN`, off by default). Two explicit opt-ins rewrite the name instead of observing
     it: `DA_PIN`, and a tier that declares `force_model` in tiers.json (single-model tiers —
     the arm behind them was only measured on that one model). Both keep the client's original
     name in the ledger under `asked`, so nothing about the rewrite is hidden.
  ② **Ledger**: a direct connection has no token/cost record at all. An agent loop makes 8-20
     calls per step; without a ledger there is no way to control the budget. The official docs
     also state that `cache_control` is **ignored** ⇒ no cache discount, so it must all be
     tracked at full price.
  ③ **Leak audit**: a sandbox can only block "what is in the directory", it cannot stop the
     agent from using the shell to read somewhere else. The relay **captures every request and
     response byte for byte**, so afterwards you can scan for sensitive strings / traces of
     out-of-scope reads — a second line of evidence, stronger than the session log.

⚠ **Never export ANTHROPIC_BASE_URL globally** — that hijacks **the current Claude Code session
   itself** onto DeepSeek. The environment variables are passed only to the `claude -p`
   subprocess.

Lessons carried over: immune to proxy env vars (http.client inherently never reads
HTTP(S)_PROXY, so the semantics of the old requests trust_env=False are kept for free) ·
bind 0.0.0.0 for containers · generous read timeout · the key never reaches the command line.
Upstream HTTP uses the **standard library only** (installing the package must not involve a pip
step) — requests was only used shallowly here (POST/stream read/timeout), http.client covers all
of it, and it does not quietly add Accept-Encoding: gzip for transparent decompression, which
makes the passthrough convention cleaner instead.

env:
  DA_PORT 8301 · DA_KEY_FILE · DA_LEDGER · DA_UPSTREAM · DA_READ_TIMEOUT 3600
  DA_PIN / DA_DENY            model handling (both off by default = pure passthrough)
  DA_TIER_TABLE               tier table json (used by the cct launcher): only deepseek-v4* is
                              governed by the session tier, every other model name passes
                              through; mutually exclusive with the single-tier env mode
  DA_EFFORT                   if non-empty, inject output_config.effort
  DA_PREAMBLE_FILE            if non-empty, append this file's content to the end of system
                              (tier injection, off by default)
  DA_CAPTURE                  capture directory; empty = **off** (default)
  DA_CAPTURE_WHAT  req|resp|both (default both)
  DA_CAPTURE_MAX   per-file byte cap, 0=unlimited (default 2000000)
  DA_CAPTURE_REDACT 1=redact keys (default 1)
Usage: python3 relay_anthropic.py
"""
import http.client
import json
import os
import re
import select
import sys
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# On Chinese Windows, stdout redirected into a log file defaults to GBK and symbols such as ⚠✓
# blow up → force utf-8 everywhere
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:                                              # noqa: BLE001
        pass

PORT = int(os.environ.get("DA_PORT", "8301"))
# Bind address: 0.0.0.0 by default for containers (the existing README convention); the cct
# launcher passes DA_BIND=127.0.0.1 — a per-session private relay should not be reachable from
# other machines, and binding 0.0.0.0 on Windows/macOS pops up a firewall authorization dialog.
BIND = os.environ.get("DA_BIND", "0.0.0.0")
# ── Auth: by default **pass through** the client's own x-api-key / authorization ──
# The relay holds no key of its own and injects nothing.
# (By design: the key is not something cct/relay supplies; forwarding only rewrites the effort
# part.)
# Only an explicit DA_KEY_FILE / DA_KEY_ENC loads a key and injects it over the top (legacy
# experimental mode; the ledger records the fingerprint).
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
KEY = ""
KEY_FP = None
if os.environ.get("DA_KEY_FILE") or os.environ.get("DA_KEY_ENC"):
    from keystore import fingerprint, load_key                     # noqa: E402
    KEY = load_key()
    KEY_FP = fingerprint(KEY)
UPSTREAM = os.environ.get("DA_UPSTREAM", "https://api.deepseek.com/anthropic")
# Official-upstream detection: tiers / injection / mapping / pricing are all calibrated against
# api.deepseek.com, so pointing at a different upstream must fall back to pure passthrough with
# zero rewriting (forcing the calibration onto it does more harm than good); loopback addresses
# are exempt (local gateway / tests).
_UP_HOST = urllib.parse.urlsplit(UPSTREAM).hostname or ""
DS_OFFICIAL = _UP_HOST == "api.deepseek.com" or _UP_HOST in ("127.0.0.1", "localhost", "::1")
# The ledger goes into the user's home directory — never hard-code an absolute path: on macOS's
# read-only root volume even makedirs would not get through. The cct launcher always passes
# DA_LEDGER (one ledger per session); this default only comes into play for a standalone relay.
LEDGER = os.environ.get("DA_LEDGER") or os.path.join(
    os.path.expanduser("~"), ".cct", "usage_relay.jsonl")
try:
    os.makedirs(os.path.dirname(os.path.abspath(LEDGER)), exist_ok=True)
except OSError as _e:                          # warn loudly; do not die at the first ledger write
    print(f"[relay-anthropic] WARN: cannot create ledger dir ({_e}); ledger writes will fail. "
          f"Set DA_LEDGER to change the path",
          file=sys.stderr)
# ── Capture switches (configurable) ──────────────────────────────────────
# DA_CAPTURE   capture directory; empty = off (default)
# DA_CAPTURE_WHAT  what to store: req / resp / both (default both)
# DA_CAPTURE_MAX   max bytes per file; anything beyond is truncated and marked
#                  (default 2_000_000; 0 = unlimited)
# DA_CAPTURE_REDACT 1 = redact x-api-key/authorization-shaped strings before writing (default 1)
# Why capture is off by default: one agent batch run can write tens of thousands of full SSE
# dumps (a single one can reach MB size). It should only be switched on **when a leak audit is
# needed** — that is its one irreplaceable use.
CAPTURE = os.environ.get("DA_CAPTURE", "")
CAPTURE_WHAT = os.environ.get("DA_CAPTURE_WHAT", "both").lower()
CAPTURE_MAX = int(os.environ.get("DA_CAPTURE_MAX", "2000000"))
CAPTURE_REDACT = os.environ.get("DA_CAPTURE_REDACT", "1") != "0"
EFFORT = os.environ.get("DA_EFFORT", "")            # if non-empty, inject output_config.effort

# ── Preamble injection (DA_PREAMBLE_FILE, off by default) ───────────────────
# Why this sits on the relay side and not in the client: tiers have to be kept separate per
# session and run several at a time, and Claude Code offers no entry point for sending an
# arbitrary string into the system slot. One tier, one port.
#
# ★ No cache_control on the injected block: it sits after every cache breakpoint of the client,
#   so a few hundred prompt tokens are resent every turn; in exchange **the client's cache
#   structure is left untouched** — the prompt side is a small share of total cost, so it pays.
# ★ DA_BASE_EFFORT: when a preamble is injected the official base effort **must** be cleared,
#   otherwise it is addition rather than replacement (not setting effort is not the same as
#   having no base effort). Only clearing it first and then injecting actually "replaces that
#   official tier".
BASE_EFFORT = os.environ.get("DA_BASE_EFFORT", "")
PREAMBLE_FILE = os.environ.get("DA_PREAMBLE_FILE", "")
PREAMBLE = ""
PREAMBLE_TAG = ""
if PREAMBLE_FILE:
    import pathlib as _pl
    PREAMBLE = _pl.Path(PREAMBLE_FILE).read_text(encoding="utf-8")
    PREAMBLE_TAG = _pl.Path(PREAMBLE_FILE).stem
    # ⚠ An empty preamble must stay the empty string — the preamble of official low is defined
    #   as **exactly the empty string**; appending two newlines breaks that equivalence.
    if PREAMBLE.strip() and not PREAMBLE.endswith("\n\n"):   # house rule: 2 newlines end paragraphs
        print(f"[relay-anthropic] WARN: preamble {PREAMBLE_TAG} did not end with a blank line; appended",
              file=sys.stderr)
        PREAMBLE = PREAMBLE.rstrip("\n") + "\n\n"
    elif not PREAMBLE.strip():
        PREAMBLE = ""                                  # empty file = no injection (= official low)


def _inject_preamble(body: dict) -> None:
    """Splice the preamble **in front of the text of the first system block** (not a new block,
    not appended at the end).

    ⚠ These two points are nailed down by measurement, they are not design choices — changing
    them departs from the calibrated construction:
      ★ Position: it must be spliced in front of the text of system[0]. Opening a new block, or
        splicing onto the end of system, is not equivalent even with exactly the same token
        count, and it destroys the server-side prefix cache hit.
      ★ Base effort: DA_BASE_EFFORT=low must be set at the same time to clear the official base
        effort, otherwise the two pieces add up instead of replacing.

    Cache cost: splicing in front changes the whole system prefix ⇒ the client's existing cache
    misses once and is then rebuilt on the new prefix. Since the same block is injected on every
    request, the steady-state hit rate is unaffected; it is in fact cheaper than "append at the
    end, uncached" (the append variant has to resend those uncached tokens every turn).
    """
    if BASE_EFFORT:                       # clear the base effort first, then inject — order matters
        oc = body.get("output_config")
        # the client may send a non-dict (attack test measured: a string crashes the handler)
        oc = dict(oc) if isinstance(oc, dict) else {}
        oc["effort"] = BASE_EFFORT
        body["output_config"] = oc
        _thinking_on(body)                # same convention as the tier-table mode
    _splice_system(body, PREAMBLE)


def _reminder(text: str) -> dict:
    """The official wire form of a mid-conversation system message.

    Established by two independent checks rather than guessed: asking the upstream to quote back
    what preceded its turn returns "<system-reminder>\\n…\\n</system-reminder>", and the prefix
    cache behaves as an exact-match oracle — re-sending a warm request carrying
    {"role":"system","content":TXT} hits every cached token, as does sending this wrapper as its
    own user message, while gluing it onto the previous user turn stalls. So the upstream turns a
    system turn into this wrapper and renders it on the user side.
    """
    return {"role": "user",
            "content": f"<system-reminder>\n{text.rstrip()}\n</system-reminder>"}


def _insert_tier_reminder(body: dict, text: str) -> None:
    """Per-turn reminder mounted by the session tier (tiers.json `msg_system_file`).

    It lands right after the first user message — the slot Claude Code uses for its agent-type
    roster — and never touches the top-level system field, so it composes with the preamble
    splice. The index is fixed, so the block sits at the same place on every request and the
    prefix cache is unaffected; re-sending it on a retry is a no-op because an identical block
    already occupying the slot is left alone.
    """
    if not text:
        return
    ms = body.get("messages")
    if not isinstance(ms, list) or not ms:
        return
    blk = _reminder(text)
    at = 1 if ms[0].get("role") == "user" else 0
    if not (len(ms) > at and ms[at] == blk):
        ms.insert(at, blk)


def _thinking_on(body: dict) -> None:
    """Reclaim the "thinking switch" on injection tiers (0.1.6).

    DeepSeek's Anthropic compatibility table: `thinking` is **Supported** (only budget_tokens is
    ignored) — a client sending {"type":"disabled"} really does turn thinking mode off, and
    splicing our preamble in anyway cannot bring it back, which breaks the pinned-tier promise
    ("however you change it, you land on that tier").

    Only this one switch, type, is flipped: budget_tokens and the remaining keys inside thinking
    are kept as they are, and the other output_config keys are left alone too — the smaller the
    change surface, the lower the chance of collateral damage.
    If the client did not send thinking, **nothing is added**: adding a field out of thin air
    changes the shape of the request and departs from the calibrated construction.
    """
    th = body.get("thinking")
    if isinstance(th, dict) and th.get("type") != "enabled":
        th = dict(th)
        th["type"] = "enabled"
        body["thinking"] = th


def _splice_system(body: dict, pre: str, skip_billing: bool = False) -> None:
    """Shared implementation of front-splicing (construction B).

    skip_billing decides where the preamble lands when the client's system field is a block
    list. Claude Code's system[0] is an "x-anthropic-billing-header" line the upstream drops
    via a startswith() check, so splicing in front of it defeats that check and leaks the
    billing line (~28 tokens) into the model's context; skipping it lands the preamble on the
    first real text block instead.

    ⚠ Do NOT "clean this up" by picking one behaviour for every tier. The two tier families
    were calibrated at different positions and their published numbers are only valid at the
    position they were measured at:
      · the tuned tiers (Value / Classic / Extra / Deeper) were measured with the preamble
        BEFORE the billing header — system[0] = preamble + billing header. Verified against
        2687 archived requests.
      · the pro register tiers (Proven / Swift / Peak) were measured with it AFTER — system[0]
        stays the bare billing header. Verified against their own archives.
    Unifying the two would silently invalidate one family's numbers. The per-tier flag
    (tiers.json "splice_skip_billing") is what keeps both honest; the env single-tier mode
    keeps the pre-existing behaviour, so nothing already published changes underneath.
    """
    if not pre:
        return
    s = body.get("system")
    if s is None:
        body["system"] = [{"type": "text", "text": pre}]
    elif isinstance(s, str):
        body["system"] = pre + s
    elif isinstance(s, list) and s:
        tgt = None
        if skip_billing:
            for blk in s:
                if isinstance(blk, dict) and blk.get("type") == "text" and \
                        not (blk.get("text") or "").startswith("x-anthropic-billing-header"):
                    tgt = blk
                    break
        else:
            first = s[0]
            if isinstance(first, dict) and first.get("type") == "text":
                tgt = first
        if tgt is not None:
            tgt["text"] = pre + tgt.get("text", "")
        else:                             # no usable text block: insert a fresh one up front
            s.insert(0, {"type": "text", "text": pre})
    elif isinstance(s, list):
        s.append({"type": "text", "text": pre})


# ── Tier-table mode (DA_TIER_TABLE, used by the cct launcher; off by default) ──
# Resolution rules (two of them; the tier-name channel was cleaned up in 0.1.5): ① deepseek-v4*
# → governed by the session tier (DA_TIER), the model name passes through unchanged (pro
# included) ② everything else (including tier-name variants best/value/…) → forwarded verbatim,
# zero rejection.
# Tier selection happens only at startup (picker / -e); inside an official session there is an
# additional per-request channel through the CC effort mapping.
# Injection tiers are always the virtual-tier construction (effort=low clears the base effort +
# the preamble spliced in front of system[0], same equivalence proof as the single-tier mode).
#
# ── CC effort mapping (cc_effort_map) ──
# When the session tier is passthrough (official), the tier is looked up per request from the
# client's output_config.effort: low/high/max→official (original value forwarded → the matching
# official bucket), medium/xhigh→a calibrated injection tier. Pinned-tier sessions (Value,
# Deeper and the other injection tiers) do not consult the table — the choice of tier belongs to
# the session, and the receipt points out any /effort that was overridden. Observed with
# claude 2.1.219: CC sends effort on every request, default value high, vocabulary
# low/medium/high/xhigh/max (cc_effort_default can be adjusted as CC versions change).
TIER_TABLE_FILE = os.environ.get("DA_TIER_TABLE", "")
TIERS = {}
TIER_DEFAULT = ""
CC_MAP = {}                                    # CC effort word (lower) → tier name (lower)
if TIER_TABLE_FILE:
    import pathlib as _pl2
    _tt = json.loads(_pl2.Path(TIER_TABLE_FILE).read_text(encoding="utf-8"))
    _tbase = _pl2.Path(TIER_TABLE_FILE).resolve().parent
    _TIER_BROKEN = {}                                    # tier name → why it is unusable

    def _tier_block(_rel, _tier):
        """Read a file a tier mounts, with the byte hygiene the whole relay shares.

        An unreadable file disables THAT TIER instead of killing the process. This loop runs at
        import and walks the whole table eagerly, so a missing file used to raise before the
        socket was ever bound — every tier died, including the passthrough one that reads no
        preamble at all, and the user saw only "relay failed to start". A packaging slip is the
        realistic way to get there, and it should cost one tier, not all of them.
        """
        if not _rel:
            return ""
        try:
            _b = (_tbase / _rel).read_text(encoding="utf-8")
        except OSError as _e:
            _TIER_BROKEN[_tier] = f"{_rel}: {_e.__class__.__name__}"
            return None
        if not _b.strip():
            return ""                                    # empty file = official low
        return _b if _b.endswith("\n\n") else _b.rstrip("\n") + "\n\n"

    for _t in _tt["tiers"]:
        _pre = _tier_block(_t.get("file"), _t["name"])
        # A per-turn reminder the tier mounts itself, so a tier can carry the preamble+reminder
        # construction without the operator wiring anything by hand.
        _msg = _tier_block(_t.get("msg_system_file"), _t["name"])
        # force_model: tiers calibrated against a single model. Running one on another model does
        # not fail — it quietly returns an uncalibrated result, which is worse — so the tier pins
        # the model instead of trusting the client.
        _force = str(_t.get("force_model") or "")
        # force_effort: same argument for the thinking level. A register preamble was searched
        # with the official effort held at one value, so the pair (preamble, effort) is the thing
        # that was measured — shipping the preamble at a different effort ships a different arm.
        # Pinned here as well as in the launcher because the environment variable cannot reach
        # every caller (the client's own background requests, a relay run standalone).
        _feff = str(_t.get("force_effort") or "")
        # splice_skip_billing: where this tier's preamble lands relative to Claude Code's
        # billing-header block. Per tier because the two families were measured at different
        # positions — see the warning in _splice_system.
        _skipbh = bool(_t.get("splice_skip_billing"))
        if _pre is None or _msg is None:                  # a mounted file was unreadable
            continue                                      # this tier stays out of the table
        for _n in [_t["name"], *_t.get("aliases", [])]:
            TIERS[_n.lower()] = {"pre": _pre, "tag": _t["name"],
                                 "pt": bool(_t.get("passthrough")),
                                 # keep_effort: tiers calibrated riding the client's own effort
                                 # (Claude Code defaults to high), NOT on the effort=low
                                 # virtual-tier base — they splice their preamble and leave
                                 # effort and thinking exactly as the client sent them.
                                 "keep": bool(_t.get("keep_effort")),
                                 "msg": _msg,
                                 "force": _force,
                                 "feff": _feff,
                                 "skipbh": _skipbh}
    for _bn, _why in _TIER_BROKEN.items():
        print(f"[relay-anthropic] WARN: tier {_bn!r} disabled — {_why}", file=sys.stderr)
    TIER_DEFAULT = str(_tt.get("default", _tt["tiers"][0]["name"])).lower()
    if TIER_DEFAULT in _TIER_BROKEN:
        # The default tier itself lost a mounted file. Falling back to the passthrough tier keeps
        # the session alive on stock upstream behaviour, which is a far better outcome than a
        # relay that will not start; the warning above already named the cause.
        _pt = next((n for n, v in TIERS.items() if v["pt"]), None)
        assert _pt, f"default tier {TIER_DEFAULT!r} is unusable and no passthrough tier exists"
        print(f"[relay-anthropic] WARN: default tier {TIER_DEFAULT!r} disabled, "
              f"falling back to {_pt!r}", file=sys.stderr)
        TIER_DEFAULT = _pt
    assert TIER_DEFAULT in TIERS, f"tiers.json default={TIER_DEFAULT!r} is not in the table"
    # DA_TIER: the session-level default tier (passed in by cct from -e). By design CC is none
    # the wiser: the client sends the real model name and the tier is enforced in the relay
    # layer; tier names/aliases are no longer valid request model names (cleaned up in 0.1.5).
    _env_tier = os.environ.get("DA_TIER", "").lower()
    if _env_tier:
        assert _env_tier in TIERS, f"DA_TIER={_env_tier!r} is not in the tier table"
        TIER_DEFAULT = _env_tier
    for _k, _v in (_tt.get("cc_effort_map") or {}).items():
        _vl = str(_v).lower()
        if _vl in _TIER_BROKEN:
            # The mapping target was disabled above. Dropping the entry means that effort word
            # goes straight through to the official bucket, which is the same thing the table
            # would do for an unmapped word — a degraded mapping, not a dead relay.
            print(f"[relay-anthropic] WARN: cc_effort_map[{_k!r}] drops — tier {_vl!r} disabled",
                  file=sys.stderr)
            continue
        assert _vl in TIERS, f"cc_effort_map[{_k!r}]={_v!r} is not a name in the tier table"
        if str(_k).lower() not in ("low", "medium", "high", "xhigh", "max"):
            print(f"[relay-anthropic] WARN: cc_effort_map has non-CC keyword {_k!r} (applied anyway)",
                  file=sys.stderr)
        CC_MAP[str(_k).lower()] = _vl


# Final model-channel rules (three of them, after the tier-name channel was cleaned up):
#   ① deepseek-v4* → governed by thinking level (session tier DA_TIER), the model name is
#      **forwarded verbatim** (pro included)
#   ② everything else (claude-*/gpt-*/tier-name variants/garbage names/empty) → **forwarded
#      verbatim, zero intervention, zero rejection** — fully transparent
#   ③ EXCEPT when the session tier declares force_model: that tier pins the model for every
#      request, ② included. Single-model tiers exist because the arm behind them was only ever
#      measured on that model — a request escaping to another one does not fail, it silently
#      returns an uncalibrated result, which is worse. The ledger keeps `asked` (what the client
#      sent) beside `forced` (what went upstream), so the rewrite is never invisible.
# From here on the table mode has no policy 400 of any kind; whether a name is right is
# adjudicated by the upstream, whose own wording is relayed verbatim.
READ_TIMEOUT = int(os.environ.get("DA_READ_TIMEOUT", "3600"))

# ── Non-official upstream → warn only, do not degrade ──
# Reason: when users go through a third-party relay / self-hosted gateway, what they expect is
# "the same tier experience as the official API", not to be silently stripped of their tiers.
# The calibration (preamble efficacy / token buckets / peak-off-peak prices) only holds for
# api.deepseek.com, so we honestly point out that "behaviour and billing may differ", but the
# logic treats everyone alike — whether to use it is left to the user's judgement.
if not DS_OFFICIAL and (TIERS or CC_MAP or PREAMBLE or BASE_EFFORT
                        or os.environ.get("DA_PIN") or os.environ.get("DA_EFFORT")
                        or os.environ.get("DA_DENY") == "1"):
    print(f"[relay-anthropic] WARN: upstream '{_UP_HOST}' is not the DeepSeek official API. "
          f"Tiers / effort mapping / pricing are calibrated against api.deepseek.com, so the "
          f"actual behaviour and billing may differ; rewrites are still applied as usual.",
          file=sys.stderr)

# By design: **do not rewrite unconditionally**. The default is to forward verbatim and observe.
# Only DA_PIN=<model name> enables rewriting (explicit opt-in, and the ledger marks pinned=true).
# DA_DENY=1 rejects anything that is not flash outright with a 400 (failing loudly beats
# silently swapping the model).
PIN = os.environ.get("DA_PIN", "")
DENY_NON_FLASH = os.environ.get("DA_DENY", "") == "1"
FLASH = "deepseek-v4-flash"

_lk = threading.Lock()
_tls = threading.local()
_n = {"i": 0}
_UP = urllib.parse.urlsplit(UPSTREAM)
# The connection target must be hostname:port and not netloc — netloc carries credentials
# embedded in the URL (https://user:tok@gw/…), and resolving that as a host name is bound to
# fail, which shows up as a silent deadlock where every send returns status=-1 (measured in the
# 0.1.7 tests). IPv6 needs square brackets added. Credentials are not forwarded: auth travels in
# the request headers, see up_headers below.
_UP_NET = (f"[{_UP_HOST}]" if ":" in _UP_HOST else _UP_HOST) + (f":{_UP.port}" if _UP.port else "")
if _UP.username:
    print("[relay-anthropic] WARN: credentials embedded in the DA_UPSTREAM URL are ignored "
          "(send auth in request headers)",
          file=sys.stderr)


def _drop_conn() -> None:
    c = getattr(_tls, "c", None)
    _tls.c = None
    if c is not None:
        try:
            c.close()
        except OSError:
            pass


def _post_upstream(path: str, data: bytes, headers: dict):
    """POST once over a thread-local keep-alive connection (the equivalent of the old
    requests.Session connection pool).

    http.client never reads the HTTP(S)_PROXY env vars — the proxy immunity of the old
    trust_env=False is kept for free; it also sends Accept-Encoding: identity by default, so the
    upstream does not gzip and the forwarded bytes are the originals.
    A reused connection may already have been cut off by the peer (keep-alive idle timeout).
    Retry convention: **only** "reused connection + RemoteDisconnected (peer disconnected with
    zero bytes)" is resent once — the upstream returned no bytes at all, so it can be taken as
    established that it did not execute, and resending risks no double billing. Every other
    failure (half-finished response / timeout / network error) is raised → 502, failing loudly,
    so the ledger never drifts from what the upstream actually executed; the client (CC) backs
    off and retries on its own.
    Note: if the upstream explicitly says Connection: close, http.client reconnects transparently
    via auto_open and does not go through this retry.
    """
    for _ in range(2):
        conn = getattr(_tls, "c", None)
        if conn is not None and conn.sock is not None:
            # Liveness pre-check before sending (the same one as urllib3's
            # is_connection_dropped): an idle connection turning readable = the peer has already
            # sent FIN / there are junk bytes → discard it and get a new one. This happens
            # **before** sending, so there is zero risk of double execution; the classic
            # keep-alive expiry is caught here deterministically (the first write after a FIN
            # often triggers RST, and that form is a ConnectionResetError rather than a
            # zero-byte disconnect, which the retry below cannot fully cover on its own).
            if select.select([conn.sock], [], [], 0)[0]:
                _drop_conn()
                conn = None
        fresh = conn is None
        if fresh:
            cls = (http.client.HTTPSConnection if _UP.scheme == "https"
                   else http.client.HTTPConnection)
            conn = _tls.c = cls(_UP_NET, timeout=20)   # connect phase 20s (old (20, read timeout))
        try:
            conn.request("POST", _UP.path + path, body=data, headers=headers)
            conn.sock.settimeout(READ_TIMEOUT)            # switch to the long read-phase timeout
            return conn.getresponse()
        except http.client.RemoteDisconnected:            # ⚠ it inherits from both HTTPException
            _drop_conn()                                  #   and ConnectionResetError, so it
            if fresh:                                     #   must come before the clause below
                raise
        except (http.client.HTTPException, OSError):
            _drop_conn()
            raise
    raise ConnectionError("unreachable")                   # for-loop completeness; never reached


def _ledger(row: dict) -> None:
    # fingerprint only in inject mode (recognizes the key, but the key cannot be derived from it)
    if KEY_FP:
        row.setdefault("key_fp", KEY_FP)
    with _lk:
        with open(LEDGER, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


_SECRET = re.compile(r'(sk-[A-Za-z0-9]{8,}|"x-api-key"\s*:\s*"[^"]+"|Bearer\s+\S+)')


def _cap(tag: str, obj) -> None:
    """Capture according to the switches. tag looks like req / resp / resp_sse;
    CAPTURE_WHAT decides which of them are stored."""
    if not CAPTURE:
        return
    kind = "req" if tag.startswith("req") else "resp"
    if CAPTURE_WHAT not in ("both", kind):
        return
    # ★ Truncation must be done **field by field**; the serialized string must not be cut —
    #   cutting it yields broken JSON and afterwards not a single one parses. Measured: in the
    #   first l3 run only 2-8 out of 25 samples could be json.load'ed, and the request body grows
    #   with the turn count ⇒ the further along, the less of it parses, i.e. no audit capability
    #   at all over the second half of the run.
    #   Field-wise truncation keeps the structure: the beginning of system[0] (the injection
    #   point) and output_config are both still there.
    truncated = False

    def _shrink(o, lim):
        nonlocal truncated
        if isinstance(o, str):
            if len(o) > lim:
                truncated = True
                return o[:lim] + f"…<+{len(o) - lim} chars>"
            return o
        if isinstance(o, dict):
            return {k: _shrink(v, lim) for k, v in o.items()}
        if isinstance(o, list):
            return [_shrink(v, lim) for v in o]
        return o

    if not isinstance(obj, str) and CAPTURE_MAX:
        # Cap for a single string field: 1/8 of the total budget, at least 4000 (enough to read
        # the full text of the injected preamble)
        obj = _shrink(obj, max(4000, CAPTURE_MAX // 8))
    txt = obj if isinstance(obj, str) else json.dumps(obj, ensure_ascii=False)
    if CAPTURE_REDACT:
        txt = _SECRET.sub("<redacted>", txt)
    if isinstance(obj, str) and CAPTURE_MAX and len(txt) > CAPTURE_MAX:
        txt = txt[:CAPTURE_MAX] + f"\n<truncated at {CAPTURE_MAX} bytes>"
        truncated = True
    with _lk:
        _n["i"] += 1
        i = _n["i"]
    try:
        os.makedirs(CAPTURE, exist_ok=True)
        suffix = ".trunc" if truncated else ""
        with open(os.path.join(CAPTURE, f"{i:06d}_{tag}{suffix}.json"), "w",
                  encoding="utf-8") as f:
            f.write(txt)
    except Exception:                                              # noqa: BLE001
        pass


DEBUG = os.environ.get("DA_DEBUG", "") == "1"


def _dbg(*a) -> None:
    if DEBUG:
        print("[dbg]", *a, flush=True)


class H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    timeout = 3700

    def log_message(self, *a):
        pass

    def handle_expect_100(self):
        """Answer 100-continue explicitly. The default implementation answers too, but if the
        client stalls here the main request never arrives — the shape of the first smoke run
        (188 seconds, zero API calls) matches exactly, so this is made explicit and logged."""
        _dbg("EXPECT-100", self.command, self.path)
        self.send_response_only(100)
        self.end_headers()
        return True

    def _dump_in(self) -> None:
        if not DEBUG:
            return
        hs = {k.lower(): (v[:80] if k.lower() not in
                          ("x-api-key", "authorization") else "<redacted>")
              for k, v in self.headers.items()}
        _dbg("IN", self.command, self.path, "proto", self.request_version, "headers", hs)

    def do_OPTIONS(self):
        self._dump_in()
        self.send_response(200)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_HEAD(self):
        self._dump_in()
        self.send_response(200)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _json(self, code: int, obj: dict) -> None:
        b = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        self._dump_in()
        if self.path.rstrip("/").endswith("/health"):
            self._json(200, {"auth": "inject" if KEY else "passthrough",
                             "key_fp": KEY_FP, "port": PORT, "bind": BIND,
                             "mode": "passthrough" if not PIN else f"pin:{PIN}",
                             "deny_non_flash": DENY_NON_FLASH,
                             "upstream": UPSTREAM, "effort": EFFORT or None,
                             "base_effort": BASE_EFFORT or None,
                             "preamble": {"tag": PREAMBLE_TAG or None,
                                          "chars": len(PREAMBLE) or None,
                                          "file": PREAMBLE_FILE or None},
                             "tiers": ({"default": TIER_DEFAULT,
                                        "names": sorted({v["tag"] for v in TIERS.values()}),
                                        "cc_effort_map": CC_MAP or None}
                                       if TIERS else None),
                             "capture": {"on": bool(CAPTURE), "dir": CAPTURE or None,
                                         "what": CAPTURE_WHAT, "max": CAPTURE_MAX,
                                         "redact": CAPTURE_REDACT}})
        else:
            self._json(404, {"error": "not found"})

    def _read_body(self) -> bytes:
        """Both Content-Length and chunked must be supported — Claude Code sends the request body
        chunked, and reading only Content-Length yields an empty body (this is what bit us on the
        first smoke run: not even a record in the ledger)."""
        if (self.headers.get("Transfer-Encoding") or "").lower() == "chunked":
            buf = []
            while True:
                ln = self.rfile.readline().strip()
                if not ln:
                    break
                try:
                    sz = int(ln.split(b";")[0], 16)
                except ValueError:
                    break
                if sz == 0:
                    self.rfile.readline()
                    break
                buf.append(self.rfile.read(sz))
                self.rfile.readline()
            return b"".join(buf)
        return self.rfile.read(int(self.headers.get("Content-Length") or 0))

    def do_POST(self):
        self._dump_in()
        path = self.path.split("?")[0]
        raw = b""
        try:
            raw = self._read_body()
            _dbg("BODY", len(raw), "bytes")
            body = json.loads(raw)
        except Exception as e:                                     # noqa: BLE001
            # This must be recorded in the ledger — otherwise there is "nothing at all", as on
            # the first smoke run, and it cannot be localized
            _ledger({"ts": round(time.time(), 1), "path": path, "status": 400,
                     "err": f"bad body: {e!r}"[:160], "nbytes": len(raw),
                     "te": self.headers.get("Transfer-Encoding"),
                     "cl": self.headers.get("Content-Length")})
            self._json(400, {"type": "error",
                             "error": {"type": "invalid_request_error",
                                       "message": f"bad body: {e}"}})
            return

        asked = body.get("model")
        # The client's original effort (observation only, always extracted; observed with CC
        # 2.1.219: sent on every request, default high)
        eff_in = None
        _oc_in = body.get("output_config")
        if isinstance(_oc_in, dict):
            _e = _oc_in.get("effort")
            if isinstance(_e, str) and _e.strip():
                eff_in = _e.strip()
        # The client's original thinking switch (observation only, 0.1.6): when investigating
        # "why is the pinned tier weakened", whether the client sent thinking at all used to be
        # completely invisible — that was the most time-consuming step.
        _th_in = body.get("thinking")
        think_in = _th_in.get("type") if isinstance(_th_in, dict) else None
        # ── Drift sentinel (0.1.6): the client's request format drifts (thinking.type was added,
        # for example), and an unrecognized new field leads to a silent degradation. Any key/value
        # we do not know about that shows up in a depth-related container is recorded in the
        # ledger — drift is traced on the spot, no need to wait for a bug report.
        _unknown = []
        if isinstance(_oc_in, dict):
            _unknown += [f"output_config.{k}" for k in _oc_in if k != "effort"]
        if isinstance(_th_in, dict):
            _unknown += [f"thinking.{k}" for k in _th_in
                         if k not in ("type", "display", "budget_tokens")]
            if think_in not in (None, "enabled", "disabled", "adaptive"):
                _unknown.append(f"thinking.type={think_in}")
        # Watch list of top-level depth knobs: today the upstream does not honour
        # reasoning_effort on the Anthropic endpoint (A/B measured, n=3, no detectable effect,
        # and the compatibility table does not list it either), but it is a real knob in the
        # OpenAI format — the day the upstream starts honouring it, the ledger traces it on the
        # spot, with no need to rely on user bug reports any more.
        _unknown += [f"top.{k}" for k in ("reasoning_effort", "reasoning", "thinking_budget",
                                          "max_thinking_tokens", "verbosity") if k in body]
        tier = None
        mapped = False
        forced = None
        eff_forced = None
        tier_msg = ""
        if TIERS:
            name = str(asked or "").lower()
            t = None
            if name.startswith("deepseek-v4"):     # ① thinking level governs, model name verbatim
                t = TIERS[TIER_DEFAULT]
            # ①″ A single-model tier claims the request whatever the client asked for. This is
            # the one exception to rule ② below, and it is deliberate: such a tier was measured
            # on one model only, and Claude Code's own background small-model calls go out under
            # a different name — letting those escape would split one session across two models
            # and quietly void the calibration. `asked` is kept in the ledger beside `forced`, so
            # the rewrite is always visible after the fact.
            elif TIERS[TIER_DEFAULT].get("force"):
                t = TIERS[TIER_DEFAULT]
            # ①′ CC effort mapping: only passthrough-tier (official) sessions consult the table —
            # pinned-tier sessions do not (the choice of tier belongs to the session); the table
            # values are tier names, so hitting an injection tier switches tier, while hitting
            # official itself keeps going straight through (original value forwarded → the
            # matching official bucket), which counts as neither a mapping nor a ledger entry.
            if t is not None and t.get("pt") and CC_MAP and eff_in:
                _tgt = CC_MAP.get(eff_in.lower())
                if _tgt is not None and TIERS[_tgt]["tag"] != t["tag"]:
                    t = TIERS[_tgt]
                    mapped = True
            if t is not None:
                tier = t["tag"]
                # passthrough tier ("official"): the effort channel is forwarded verbatim too,
                # the relay does not intervene at all.
                if not t.get("pt"):                # injection tier: intervene unconditionally
                    if not t.get("keep"):          # keep_effort tiers ride the client's effort
                        oc = body.get("output_config")
                        # the client may send a non-dict (attack test measured: a string crashes
                        # the handler)
                        oc = dict(oc) if isinstance(oc, dict) else {}
                        # clear the official base effort — the virtual-tier construction
                        oc["effort"] = "low"
                        body["output_config"] = oc
                        _thinking_on(body)         # reclaim the thinking switch (see docstring)
                    _splice_system(body, t["pre"], t.get("skipbh", False))
                    tier_msg = t.get("msg") or ""  # per-turn reminder mounted by the tier
                # Pin model and effort last, so they cover passthrough and injection tiers alike
                # and land on top of whatever the branches above wrote.
                # DA_PIN still wins for the model (explicit operator opt-in, applied further down).
                if t.get("force") and body.get("model") != t["force"]:
                    forced = t["force"]
                    body["model"] = forced
                if t.get("feff"):
                    oc = body.get("output_config")
                    oc = dict(oc) if isinstance(oc, dict) else {}
                    if oc.get("effort") != t["feff"]:
                        eff_forced = t["feff"]
                    oc["effort"] = t["feff"]
                    body["output_config"] = oc
            # ② All other models (tier-name variants included): forwarded verbatim, zero
            # intervention, zero rejection (recorded in the ledger with tier=None)
        # **No change** by default. DA_DENY=1 rejects anything that is not flash loudly; only an
        # explicit DA_PIN triggers a rewrite.
        if not TIERS and DENY_NON_FLASH and not str(asked or "").startswith(FLASH):
            self._json(400, {"type": "error", "error": {
                "type": "invalid_request_error",
                "message": f"relay: only {FLASH} allowed, got {asked!r}. "
                           f"Set ANTHROPIC_MODEL={FLASH} or run claude --model {FLASH}."}})
            _ledger({"ts": round(time.time(), 1), "asked": asked,
                     "status": 400, "denied": True})
            return
        if PIN:
            body["model"] = PIN
        if EFFORT:
            oc = body.get("output_config")
            # the client may send a non-dict (attack test measured: a string crashes the handler)
            oc = dict(oc) if isinstance(oc, dict) else {}
            oc["effort"] = EFFORT
            body["output_config"] = oc
        if not TIERS:
            _inject_preamble(body)
        # Independent of the preamble splice: this touches messages, not system, so the two
        # compose. Runs after the splice so a capture shows both.
        _insert_tier_reminder(body, tier_msg)
        stream = bool(body.get("stream"))
        _cap("req", {"path": path, "asked_model": asked, "asked_effort": eff_in,
                     "body": body})

        t0 = time.time()
        try:
            _dbg("UPSTREAM ->", UPSTREAM + path, "stream", stream)
            up_headers = {"Content-Type": "application/json",
                          "anthropic-version": self.headers.get("anthropic-version",
                                                                "2023-06-01")}
            for h in ("x-api-key", "authorization"):   # auth headers forwarded verbatim
                v = self.headers.get(h)
                if v:
                    up_headers[h] = v
            if KEY:                                    # only an explicit DA_KEY_FILE overrides it
                up_headers["x-api-key"] = KEY
                up_headers.pop("authorization", None)
            r = _post_upstream(path, json.dumps(body).encode(), up_headers)
        except Exception as e:                                     # noqa: BLE001
            _ledger({"ts": round(time.time(), 1), "asked": asked, "status": -1,
                     "ms": round((time.time() - t0) * 1000), "err": repr(e)[:200]})
            self._json(502, {"type": "error",
                             "error": {"type": "api_error",
                                       "message": f"relay upstream failed: {e!r}"}})
            return

        _dbg("UPSTREAM <-", r.status, "stream", stream)
        row = {"ts": round(time.time(), 1), "path": path, "asked": asked,
               "used": body.get("model"), "pinned": bool(PIN),
               "status": r.status, "stream": stream,
               "port": PORT, "pre": PREAMBLE_TAG or None, "tier": tier,
               "eff_in": eff_in}
        if forced:
            # the session tier pinned the model; `asked` above keeps what the client really sent
            row["forced"] = forced
        if eff_forced:
            # the session tier pinned the thinking level; `eff_in` above keeps the client's own
            row["eff_forced"] = eff_forced
        if think_in is not None:
            row["think_in"] = think_in             # the client's original thinking.type
        if _unknown:
            row["unknown_fields"] = _unknown       # drift sentinel: the client's format changed
        # recorded only when the mapping really switched tier (going straight through with the
        # original value does not count)
        if mapped:
            row["eff_map"] = True

        if stream:
            # SSE forwarded byte for byte while being accumulated for the ledger and the
            # capture — Claude Code streams by default, stream=False cannot be forced.
            self.send_response(r.status)
            for k in ("Content-Type", "Cache-Control"):
                v = r.getheader(k)
                if v is not None:
                    self.send_header(k, v)
            self.send_header("Transfer-Encoding", "chunked")
            self.end_headers()
            buf = []
            try:
                while True:
                    # read1: hand over whatever arrived (per-chunk low latency) instead of
                    # waiting for a full buffer — the same as iter_content
                    chunk = r.read1(65536)
                    if not chunk:
                        break
                    buf.append(chunk)
                    self.wfile.write(hex(len(chunk))[2:].encode() + b"\r\n"
                                     + chunk + b"\r\n")
                    self.wfile.flush()
                self.wfile.write(b"0\r\n\r\n")
            except Exception as e:                                 # noqa: BLE001
                row["stream_err"] = repr(e)[:120]
                _drop_conn()               # upstream half-read / client gone → discard, no reuse
            txt = b"".join(buf).decode(errors="ignore")
            _cap("resp_sse", txt)
            # dig usage out of the SSE (message_delta carries the final usage)
            for line in reversed(txt.splitlines()):
                if line.startswith("data: ") and '"usage"' in line:
                    try:
                        d = json.loads(line[6:])
                        u = d.get("usage") or (d.get("message") or {}).get("usage") or {}
                        if u:
                            row.update(inp=u.get("input_tokens"),
                                       out=u.get("output_tokens"),
                                       cache_r=u.get("cache_read_input_tokens"))
                            break
                    except Exception:                              # noqa: BLE001
                        pass
        else:
            try:
                b = r.read()
            except Exception as e:                                 # noqa: BLE001
                # The upstream sent response headers and then disconnected mid-response (measured
                # with the mock): this used to raise straight away — that ledger row vanished
                # into thin air (a hole in the audit trail, the receipt undercounting calls) and
                # the client only saw a bare disconnect.
                # At this point no response header has been sent yet, so we can return an
                # explainable 502 and record it honestly (status=-2).
                _drop_conn()               # half-read connection discarded; retry: next request
                row["status"] = -2
                row["err"] = f"upstream closed mid-response: {e!r}"[:200]
                row["ms"] = round((time.time() - t0) * 1000)
                _ledger(row)
                self._json(502, {"type": "error", "error": {
                    "type": "api_error",
                    "message": f"relay: upstream closed mid-response: {e!r}"}})
                return
            _cap("resp", b.decode(errors="ignore"))
            try:
                d = json.loads(b)
                u = d.get("usage") or {}
                row.update(inp=u.get("input_tokens"), out=u.get("output_tokens"),
                           cache_r=u.get("cache_read_input_tokens"),
                           stop=d.get("stop_reason"))
            except Exception:                                      # noqa: BLE001
                row["err"] = b[:200].decode(errors="ignore")
            self.send_response(r.status)
            self.send_header("Content-Type",
                             r.getheader("Content-Type") or "application/json")
            self.send_header("Content-Length", str(len(b)))
            self.end_headers()
            self.wfile.write(b)

        row["ms"] = round((time.time() - t0) * 1000)
        _ledger(row)


if __name__ == "__main__":
    srv = ThreadingHTTPServer((BIND, PORT), H)
    srv.daemon_threads = True
    mode = f"pin={PIN}" if PIN else ("deny-non-flash" if DENY_NON_FLASH else "passthrough")
    print(f"[relay-anthropic] auth={'inject key_fp=' + KEY_FP if KEY else 'passthrough (client supplies its own auth header)'}",
          flush=True)
    print(f"[relay-anthropic] {BIND}:{PORT} → {UPSTREAM}  model={mode} "
          f"effort={EFFORT or '-'} "
          f"capture={'off' if not CAPTURE else f'{CAPTURE_WHAT}@{CAPTURE}'}", flush=True)
    if TIERS:
        print(f"[relay-anthropic] tiers={sorted({v['tag'] for v in TIERS.values()})} "
              f"default={TIER_DEFAULT} (only deepseek-v4* is governed; everything else "
              f"passes through)", flush=True)
    if CC_MAP:
        _mm = " ".join(f"{k}→{CC_MAP[k]}" for k in ("low", "medium", "high", "xhigh", "max")
                       if k in CC_MAP)
        print(f"[relay-anthropic] CC effort map (applies in Flex sessions): {_mm}",
              flush=True)
    if not PIN and not DENY_NON_FLASH and not TIERS:
        print("  WARN: passthrough mode -- a client asking for claude-opus* gets mapped to "
              "v4-pro by DeepSeek. The ledger records the asked model per call so you can audit "
              "it afterwards; set DA_DENY=1 to reject instead.", flush=True)
    srv.serve_forever()
