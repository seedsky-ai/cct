# tests

Acceptance scripts. There is no CI here: every item is "run the real path once, assert one contract".

> ## ⚠ Read this first
>
> **These scripts are not harmless unit tests.** Half of them will:
>
> - burn **real DeepSeek API credit** (a usable `ANTHROPIC_AUTH_TOKEN` must be present in the environment);
> - require a **logged-in `claude` CLI**;
> - **temporarily rewrite your machine's Claude Code configuration** (`~/.claude/settings.json`; a few scripts also touch `~/.claude.json`).
>   These scripts use `trap ... EXIT INT TERM` to restore the original files on every exit path (Ctrl-C included), with backups in a 0700 temporary directory, but **any** script that rewrites your machine's configuration deserves a look before you run it.
>
> **Recommended: run these only in a throwaway container / on a clean HOME.**

---

## Two categories

### A. Purely local — zero network, zero keys, does not touch your configuration

Run them freely.

| Script | What it tests |
|---|---|
| `qa_picker_vt.py` | Brings its own mini VT interpreter and simulates rendering over the matrix of width 40–200 × height 5–50 × Ambiguous width × probe failure × non-UTF-8 locale — "canvas drift scroll-spam" under any geometry is an immediate red light |
| `qa_picker_pty.py` | Runs the picker's full key-press paths inside a pty + the terminal width invariant (every line's display width must be < the terminal width) |
| `qa_price.py` | Synthetic ledger → receipt amounts. Peak/off-peak boundaries, the 3× pro price, old flat-price compatibility, with every amount hand-computed and nailed down |

### B. Mock upstream — zero real network, but a cct session is started

No real key needed (they hit a local mock), but `cct` must be on PATH.

| Script | What it tests |
|---|---|
| `qa_fault.sh` + `qa_fault_mock.py` / `qa_fault_probe.py` | The four upstream states 429 / 500 / bad JSON / mid-response disconnect: the error is relayed in the upstream's own wording · every single request is recorded in the ledger · a disconnect yields an explainable 502 |
| `qa_reliab.sh` + `qa_reliab_mock.py` / `qa_reliab_probe.py` | Port isolation between two concurrent sessions · zero strays left behind on exit · reuse self-heals after the upstream kills an idle connection |
| `qa_update.sh` | The whole auto-update chain (mock registry + fake npm + isolated HOME): probe / notice / skip / soft and hard forced-update floor / ACK escape hatch / interactive menu |
| `qa_upstream.sh` | Non-official upstream: warn only, do not degrade · the warning shows the hostname only and does not print the full URL |

### C. Real money — real API requests

**Read the warning block at the top of a script before running it.** Every one of these actually spends money; the ones marked ⚙ also temporarily rewrite your Claude Code configuration.

| Script | What it tests |
|---|---|
| `qa_main.sh` | Master control: chains the items below into one full acceptance run |
| `qa_api_official.sh` / `qa_api_balance.sh` | API semantics probes run inside a cct session (Flex go-straight-through vs injection tiers, auth pass-through, the two model-channel cases) |
| `qa_attack.sh` + `qa_attack_probe.py` | 20 client-side variants trying to defeat the pinned tier: inp is always identical to that tier's baseline · zero crashes on malformed input · forged future fields are traced by the sentinel |
| `qa_pin_hard.sh` + `qa_pin_hard_probe.py` | Pinned-tier hardening: reads the **body actually sent upstream** from the `DA_CAPTURE` captures and checks it field by field |
| `qa_tier_matrix.sh` + `qa_tier_matrix_probe.py` | The full tier × client-variant matrix + differential invariants |
| `qa_redline.sh` + `qa_redline_probe.py` | Red-line evidence: the ledger holds zero conversation content and zero key-shaped strings; captures store the body only, never headers |
| ⚙ `qa_settings_pin.sh` | Under a `settings.json` `env` hijack, traffic still goes into this session's relay; a successful pin-back is completely silent |
| ⚙ `qa_flex_unlock.sh` | A Flex session strips the leftover `CLAUDE_CODE_EFFORT_LEVEL` |
| ⚙ `qa_ccswitch.sh` / `qa_ccswitch2.sh` | Compatibility with third-party provider-switching tools: routing priority, switching mid-session, project-level/local-level settings, coexistence with `~/.claude.json` (MCP) |

---

## Assertion conventions

The tests **do not hard-code calibrated token counts**. Every assertion involving `input_tokens` judges relatively, against a baseline taken at run time:

- pinned tier: the various client-side variants of one tier must be **equal to each other** (the baseline = that tier's bare request);
- Flex: the official bucket satisfies the ordering `low == low_disabled < high == bare < max`, and the mapped tiers equal the baseline of the corresponding injection tier;
- passthrough tier < injection tier.

This makes the assertion semantics stronger ("however the client writes it, it lands on the same construction"), and it keeps the tier table's calibration numbers from being scattered across the test files.
