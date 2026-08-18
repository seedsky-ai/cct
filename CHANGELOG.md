# CHANGELOG

This file records **user-visible changes** only: what capability was added, what problem that affects usage was fixed, and what to watch out for when upgrading.

## Upgrade notes

- Upgrading from **0.1.3 or earlier** (local tgz install, package name `cct`): first `npm uninstall -g cct`, then `npm i -g @seedsky/cct` — the two packages provide the same `cct` command and cannot coexist.
- Upgrading from **0.1.0**: you must re-run `npm i -g` (the entry point changed from a bash script to a Node shim).
- If your `~/.claude/settings.json` sets `ANTHROPIC_BASE_URL`: on 0.1.4 and earlier the session bypasses the relay (tiers have no effect, no ledger, no receipt); upgrading to 0.1.5+ fixes it.
- Runtime dependencies: Node ≥16 + system Python ≥3.8, **zero pip packages**.

---

## 0.1.7 — 2026-08-17 · Non-official upstream: warn only, do not degrade

- **Semantics inverted**: when `DA_UPSTREAM` points at a third-party proxy / self-hosted gateway, the tier table, the `/effort` mapping, and the preamble and base-effort rewrites **still take effect as usual** (previously: warn + force pure passthrough, with all tiers disabled). The warning now states the facts: tiers and pricing are calibrated against `api.deepseek.com`, so on another upstream the effect and the bill can differ.
- The warning **shows the hostname only** and does not print the full upstream URL — that URL can look like `https://user:token@gw/…`, and putting the whole thing on screen leaks the embedded credentials.
- Fixed: with credentials embedded in the upstream URL, connection setup parsed it wrong, which made **every single request fail** with no visible reason. The connection is now made to `hostname:port` (IPv6 gets brackets added automatically), and a note says the credentials in the URL are ignored (authentication goes through the request headers).
- Reverted the 0.1.6 context-window injection: `CLAUDE_CODE_MAX_CONTEXT_TOKENS` is no longer injected into the child process, and `model_context_tokens` is removed from `tiers.json` along with it. If you want the full window, set that environment variable yourself.
- The receipt gained a catch-all line: when a pinned-tier session contains requests that are not governed by the tier, it reports them as `◆ N request(s) bypassed Deeper — model '…' is not governed by tiers`.
- **Known limitation**: if an external tool rewrites `ANTHROPIC_MODEL` to a model name other than `deepseek-v4*`, the tier has no effect in that session (the relay is pure passthrough) while the startup banner still shows the tier you picked — the receipt's bypassed line is the authoritative one.

---

## 0.1.6 — 2026-08-17 · Pinned-tier hardening

- **Fixed: the client could flatten the thinking depth of a pinned-tier session** (you picked Deeper/Value, yet the thinking got noticeably shorter). The `thinking` field that recent Claude Code carries on every request makes depth follow effort, which conflicts with the contract "pinned tier = however the client changes it, the request lands on that tier". Injection tiers now normalize `thinking.type` to `enabled` and leave every other key (`budget_tokens` / `display`, etc.) alone; if the client sent no `thinking`, none is added. **Flex (the passthrough tier) is untouched**: official effort and the native thinking experience are fully preserved.
- Fixed: when a non-streaming request failed midway upstream, the client only got a bare disconnect, and that call never made it into the ledger. It now returns an explainable **502** and is recorded in the ledger.
- Fixed: when the client sent `output_config` / `thinking` as something other than a dict (string/number/list), the relay crashed and the connection was cut bare. Malformed fields are now ignored across the board and the request is processed as usual.
- A pinned-tier session also pins Claude Code's own effort to the maximum (`tiers.json` gained `pinned_effort`; leave it empty = no intervention), so that "picking a deep tier means maximum investment" holds on the API side and the client side alike.
- The ledger gained `think_in` (the client's original `thinking.type`) and `unknown_fields` (unrecognized keys/values among the depth-related fields) — when the client's request format changes it is traced on the spot, instead of having to be discovered through a bug report.
- Added context-window injection `CLAUDE_CODE_MAX_CONTEXT_TOKENS` (default 1000000) — **reverted in 0.1.7**.

---

## 0.1.5 — 2026-08-17 · settings.json hijack guard

- **Fixed: a session could run around the relay entirely**. At startup Claude Code writes `settings.json`'s `env` block back into the process environment, clobbering the `ANTHROPIC_BASE_URL` that cct injected (tutorials for connecting straight to DeepSeek commonly carry this configuration); the result is that tiers have no effect, the ledger is blank and the receipt has no data, while nothing looks wrong on screen. cct now appends `--settings <session file>` to claude and pins the single key `ANTHROPIC_BASE_URL` — **your own settings file is not modified on disk at all**, and your token/permissions/hooks take effect as-is. A `--settings` you pass yourself (file or inline JSON) is merged and preserved; if it cannot be parsed, your argument is left alone and the problem is reported honestly. A successful pin-back is completely silent; only a failed pin-back speaks up.
- **Fixed: `/effort` was locked in Flex sessions**. A leftover `CLAUDE_CODE_EFFORT_LEVEL` (tutorials often set `=max`) overrides the `/effort` menu. Flex sessions now strip it (both forms: the environment variable and settings); pinned-tier sessions still do not strip it (pinned-tier semantics ignore effort anyway).
- **License**: `UNLICENSED` → a proprietary **Preview License** (full English text in the repo). It grants evaluation / personal / internal use of installing and running the **unmodified** version; redistribution, re-hosting, modified derivatives, and extracting the calibration data of `preambles/` and `tiers.json` on its own are prohibited.
- **Receipt rebuilt + the product surface is all English**: the main line is now `✓ Saved ≈X% cost (≈¥Y) · ≈Zs faster`, with the benchmark = doing the same work end to end at the official max thinking level; Deeper's main line talks about depth (`Thinking ≈X% deeper than official max`) rather than cost. All Chinese visible on screen became English, and the currency symbol is uniformly `¥`.
- The picker's and the banner's badges now use the same yardstick as the receipt (`−X% cost` / `+Y% depth`), replacing the unlabeled bare percentage they carried before.
- **Model channel narrowed**: a request body with `model=<tier name/alias>` is no longer claimed and rewritten by the relay; it takes the same pure-passthrough path as any foreign model name, the upstream adjudicates whether it is right or wrong, and its own wording is relayed verbatim. The ability to switch tiers with `/model` inside a session is removed along with it — **tier selection happens at startup only** (the picker or `-e`).
- Removed the startup warning present since 0.1.3 ("`ANTHROPIC_BASE_URL` is already exported globally in the outer shell"): a cct session is unaffected by that variable, so repeating it at every startup is noise (the "never export it globally" advice stays in the README).
- The update probe now follows the package's own release channel (it reads `publishConfig.tag`; `CCT_UPDATE_TAG` can override it), so users on a pre-release channel are no longer left without update prompts forever.

---

## 0.1.4 — 2026-08-17 · Public npm release + auto-update + time-of-day pricing

- **Public npm release**: `npm i -g @seedsky/cct`.
- **Pricing aligned with DeepSeek's new price table**: the official API turned on peak/off-peak time-of-day pricing (peak = Beijing time 9:00–12:00 and 14:00–18:00, half price in the off-peak period) and raised the unit prices, so the old flat price made the receipt's actually-paid amount a clear underestimate, and pro requests were priced as flash on top of that. The receipt is now priced **row by row**: peak vs off-peak is judged by the Beijing time of the ledger row's timestamp (fixed UTC+8 offset, immune to the host timezone) and flash/pro by the actual model, and the actually-paid line notes which periods make it up; custom old-style flat price tables are still compatible.
- **Update prompt at startup**: the probe runs in the background (throttled to 24h; zero wait in the main flow, zero stall when offline) and prompts at the next startup; on a TTY it opens a menu (update now / skip / skip this version), while non-TTY and CI only print a one-line notice and never block; any query failure passes through silently.
- If a version is marked as a mandatory update, there is a 5-day grace period from the first time this machine sees it; once it expires you must update to continue (under CI it warns and exits; `CCT_FORCE_ACK=1` is the escape hatch).
- Switches: `CCT_NO_UPDATE_CHECK=1` turns the check off, `CCT_REGISTRY` points at a private registry; `cct list` is never interrupted at any point.

---

## 0.1.3 — 2026-08-16 · CC native effort mapping + three-way startup choice

- **Claude Code's native `/effort` really works in a Flex session**: `low / high / max` go straight through as their original values to the corresponding official tiers, and `medium / xhigh` map to the injection tiers we calibrated. Previously, under an injection tier, `/effort` and `CLAUDE_CODE_EFFORT_LEVEL` were silently overridden by the relay with zero feedback — two control planes fighting, and the losing side said nothing.
- **Three-way choice at startup**: `Flex · Value (default) · Deeper`, auto-confirmed by a 3-second countdown (any key press cancels it); all five tiers are kept in full, and `-e <tier name>` goes straight to one.
- A pinned-tier session's "`/effort` was overridden" is no longer silent: the banner states plainly that it is already pinned by this tier, and the receipt counts how many times it was overridden (the client's default value is not counted).
- **Terminal hardening**: every rendered line is clamped to within the display width + automatic line wrapping is turned off during the animation, so a narrow terminal no longer produces wrap-induced canvas drift that scrolls the header into history; before entering the animation a silent probe runs (the actual width taken by Ambiguous wide characters, whether the terminal honours ANSI), and anything short of that degrades to the numbered list; a terminal that is too short or a non-UTF-8 locale degrades the same way. A failure at any layer only degrades; it never blocks the main flow.
- **Upstream endpoint guard**: when the `DA_UPSTREAM` host is not `api.deepseek.com`, it warns and forces pure passthrough (tiers disabled); loopback addresses are exempt. (Since 0.1.7 this only warns and no longer disables anything.)
- The receipt no longer shows the ledger path (diagnostic info hurts UX); the ledger is still stored as before, at the location documented in the README (`~/.cct/sessions/`, changeable with `CCT_SESS_DIR`).
- The picker and the session banner are all English, and the five tiers' display labels are fixed as Classic / Value / Flex / Extra / Deeper (aliases work with `-e`).

---

## 0.1.2 — 2026-08-16 · Zero pip dependencies + tightened upstream connection semantics

- **Zero pip dependencies**: the relay's upstream HTTP moved from `requests` to the standard library's `http.client`, so installing takes a single `npm i -g` from now on (the only prerequisite left is system Python ≥3.8).
- Connection reuse gained a **liveness pre-check before sending**: before reusing a connection, a zero-timeout probe checks whether the peer already hung up, and a dead connection is swapped for a fresh one — the decision happens **before** anything is sent, so there is zero risk of double execution.
- **Retry convention tightened**: only "a reused connection + the peer closed with zero bytes (proof that it was not executed)" is resent, once; a half response, a timeout, or a network error all produce a loud 502 — never risking the double-billing case of "the upstream already executed it and we resent it", so the ledger matches reality exactly.
- The relay inherently no longer reads `HTTP(S)_PROXY`; it declares `Accept-Encoding: identity` when forwarding, so the forwarded bytes are the original text.
- **Known differences (kept on purpose)**: CAs now come from the system trust store — on macOS with the python.org build of Python, run `Install Certificates.command` once first (enterprise self-signed CAs on Windows work better instead); no User-Agent is sent any more; the form of the exception string in the ledger's `err` field changed, so scripts that grep the ledger for the old wording need to watch out.

---

## 0.1.1 — 2026-08-16 · Windows / macOS install support

- **Windows and macOS are supported** (0.1.0 was linux/darwin only; installing the package on Windows reported `EBADPLATFORM` outright). The entry chain was rebuilt as `npm bin → cct.js` (a Node shim whose only job is to find Python 3) `→ cct.py` (one code path across all three platforms); the `./cct` you run directly inside the repo is an equivalent thin wrapper.
- On Windows the picker has no animation and degrades to a functionally equivalent numbered list.
- All text IO is explicitly UTF-8 (Chinese Windows defaults to GBK, which is guaranteed to blow up without this); `PYTHONUTF8` is not injected into the wrapped command, so your own Python scripts' behaviour is not changed as a side effect.
- The ledger goes to `~/.cct/` by default; the relay gained `DA_BIND` (default `0.0.0.0` for container scenarios, while a cct session always binds `127.0.0.1` — a private relay should not be connected to from other machines, and this also avoids the firewall popup).
- Fixed: on Windows a username or an argument containing spaces made startup fail; on macOS without Command Line Tools installed, `/usr/bin/python3` is a stub that pops up a GUI and picking it broke with zero warning (a probe was added); an immediate exit on SIGTERM abandoned the running claude and printed no receipt; the relay process leaked after an SSH drop (SIGHUP).
- **Upgrade note**: upgrading from 0.1.0 requires re-running `npm i -g` (the bin changed from bash to `cct.js`).

---

## 0.1.0 — 2026-08-15 · First frozen version (Linux / macOS only)

- A bash launcher + a tier-table transparent relay: pick a tier at startup, the relay rewrites requests according to the tier, and a spend receipt is printed on exit.
- The five-tier table ships with the package (`tiers.json` + `preambles/`), and the ledger and the receipt use the same convention from the same source.
