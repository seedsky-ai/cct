<div align="center">

<a href="https://seedsky.ai"><img src="assets/seedsky-mark.png" width="86" alt="SeedSky"></a>

<a href="https://seedsky.ai"><picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/seedsky-tagline-dark.png">
  <img src="assets/seedsky-tagline-light.png" width="342" alt="Seek within. Evolve beyond.">
</picture></a>

# cct

**Make your AI agent think just enough — same result, half the bill.**

[![seedsky.ai](https://img.shields.io/badge/seedsky.ai-6C7AD7?logo=data:image/svg%2Bxml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCA2NCA2NCI%2BPHBhdGggZD0iTTMxIDUyYzAtMTQgNC0yNSAxOC0zOE0zMSA1MmMwLTExLTQtMjAtMTUtMjciIGZpbGw9Im5vbmUiIHN0cm9rZT0iI2ZmZiIgc3Ryb2tlLXdpZHRoPSIzLjQiIHN0cm9rZS1saW5lY2FwPSJyb3VuZCIvPjxwYXRoIGQ9Ik00OSAxNGMtMTEgMC0xNiA0LTE5IDEyIDEwIDIgMTctMiAxOS0xMlpNMTYgMjVjOSAwIDE0IDQgMTYgMTEtOSAwLTE0LTQtMTYtMTFaIiBmaWxsPSIjZmZmIi8%2BPGNpcmNsZSBjeD0iNTIiIGN5PSIxMCIgcj0iNC4yIiBmaWxsPSIjZmZmIi8%2BPC9zdmc%2B)](https://seedsky.ai)
[![npm](https://img.shields.io/npm/v/@seedsky/cct?color=cb3837&logo=npm)](https://www.npmjs.com/package/@seedsky/cct)
[![python](https://img.shields.io/badge/python-%E2%89%A53.8-3776AB?logo=python&logoColor=white)](https://www.python.org)
[![platform](https://img.shields.io/badge/platform-Linux%20%7C%20macOS%20%7C%20Windows-666)](#requirements)
[![license](https://img.shields.io/badge/license-see%20LICENSE-blue)](LICENSE)
[![WeChat](https://img.shields.io/badge/WeChat-join-07C160?logo=wechat&logoColor=white)](#community)
[![QQ](https://img.shields.io/badge/QQ-1019231337-12B7F5?logo=tencentqq&logoColor=white)](#community)

**English** · [简体中文](README_ZH.md)

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/fig-value-hero-dark.png">
  <img src="assets/fig-value-hero.png" width="820" alt="Value tier: 60.7% of tasks solved at 55k output tokens per task — 32% fewer tokens than official High, 5.3 pp above the official curve. Terminal-Bench 2.1, 89 tasks, deepseek-v4-flash, one run per task per tier.">
</picture>

</div>

---

> ### 0.2.0-beta.0 — we read the model's own mechanism, and wrote the harness it wants
>
> **12 / 30 → 20 / 30.** Same model, same tasks, same day. The only thing that changed is the text
> Claude Code shows it — and that text was not written by a human with good instincts. It was
> **searched out of the model's own neuron-level mechanism.**
>
> | 30 discriminative DeepSWE tasks · official API · `deepseek-v4-pro` · one run per task | Solved |
> |---|---|
> | Claude Code alone | **12 / 30** |
> | Claude Code + `cct` | **20 / 30** |
>
> **Why there was 8 tasks of room to take.** DeepSeek's own agent `dsh` — 46 bytes of system prompt,
> two tools — solves markedly more than the *identical* `deepseek-v4-pro` does inside Claude Code's
> ~12 KB prompt and 24 tools. The model was never the bottleneck. **The harness was.**
>
> **How we took it.** Not by taste, and not by guessing. We watch the running model from the
> inside — which internal circuits light up as it reasons, and how strongly — and turn that into a
> ruler: a measurable distance between thinking inside Claude Code's harness and thinking inside
> the small one at max effort. A **self-evolving search** then walks that distance down, generation
> after generation, each one proposed from what the last one ruled out. **The prefix that shipped is
> the one the model's own internals voted for.**
>
> Two pieces of prior work make this possible. [**JAR — Jacobian Axis Readout**](https://cckfdu.com/jar/)
> ([arXiv:2608.17638](https://arxiv.org/abs/2608.17638)) couples an interpretable reasoning-state
> readout to a model's own internals: it is the instrument. [**RAD — Routing Agreement
> Decoding**](https://cckfdu.com/rad/) ([arXiv:2606.22798](https://arxiv.org/abs/2606.22798)) is
> where the idea comes from — it shows that the same token can stand for different internal states,
> and that the difference is a usable control signal for reasoning rather than noise. Both read a
> single model answering a single prompt. **What is new here is carrying them into the agent
> setting** — a whole session rather than one answer, a harness rather than a question — and closing
> the loop, so the readout does not only explain a prefix, it selects the next one.
>
> **What we did not do — and this is the part that matters.** The proxies that put DeepSeek behind
> Claude Code ([UniClaudeProxy](https://github.com/vibheksoni/UniClaudeProxy),
> [claude-code-proxy](https://github.com/empero-org/claude-code-proxy),
> [deepclaude](https://github.com/aattaran/deepclaude),
> [deep-claude](https://github.com/dennisonbertram/deep-claude),
> [permafrost](https://github.com/jianzhichun/permafrost)) built the plumbing we stand on: wire
> translation, cache-stable prefixes, state isolation. Where several of them go next is to **build a
> Truman Show around the model** — rewrite or compress the harness prompt, strip the identity
> strings, swap native tool-calling for a ReAct/XML imitation so a foreign model will play along.
> It works, and it costs you the model's own tool-calling instincts.
>
> **We build no set. We change no model.** Nothing is deleted from Claude Code's prompt, no tool is
> removed, no emulation is introduced — the agent loop, the tool schemas and the streaming stay
> Claude Code's own. No fine-tune, no LoRA, no distillation. Just bytes in a prompt, chosen by
> measuring the model instead of imagining it. **Self-evolving search against a model's own
> internals, designing the harness it actually wants to think in.**
>
> ![Harness alignment, measured in what the model writes and does](assets/fig-harness-alignment.png)
>
> <sub>Every number above is counted from reasoning the agents actually wrote, on official-API
> sessions over DeepSWE repositories. <b>A</b> — six style axes, with Claude Code and
> dsh-minimal@max as the two anchors. <b>B</b> — the same six axes collapsed into one distance:
> the tiers close roughly 70 % of the gap between how Claude Code writes and how the small
> harness writes.</sub>
>
> This release ships three beta tiers — **Proven**, **Swift**, **Peak** — plus a hidden fourth,
> **Aligned** (`cct -e aligned`), carrying the newest prefix the search produced.
>
> Details: [the three pro-only tiers](#the-three-pro-only-tiers) · [CHANGELOG](CHANGELOG.md)

---

Official gives you three thinking levels: low / high / max ([DeepSeek docs](https://api-docs.deepseek.com/zh-cn/guides/thinking_mode)). High burns **1.5×** the tokens of low, max
**2.2×** — and across the 89 tasks we ran, max did not solve a single one more. **Most work does not
need the model to think that hard.**

**The Value tier: matches official high, on 32% fewer tokens.**

It was not hand-tuned. We look at the **neuron-level mechanism** of how a model thinks, then run
**self-evolving, high-throughput search** to generate **thinking anchors**, scoring every one on a
real benchmark — method at [seedsky.ai](https://seedsky.ai). Steering those anchors is how cct goes past
the official low / high / max: **medium** and **xhigh** fill the gaps (low↔high, high↔max), and two
entirely new regions open up — **Value** and **Deeper**. Where each one lands is in
[Which tier should I use?](#which-tier-should-i-use).

Usage is putting `cct` in front of your usual command: pick a tier at startup, get a cost receipt on
exit. On the tuned tiers it changes exactly one thing: **how hard the model thinks**. The three pro-only
tiers additionally prepend a fixed preamble, and one of them (`Peak`) adds a fixed reminder each
turn — spelled out under [the three pro-only tiers](#the-three-pro-only-tiers). Nothing you write is
ever rewritten, compressed or stored.

**Supported today: Claude Code** as the harness and **the DeepSeek family** as the model behind it.
Codex, DSH and OpenCode are in closed beta; models like GLM and Kimi are on the way — see
[Roadmap](#roadmap).

## What it looks like

Pick a tier at startup (3 seconds of silence takes the default):

```text
  1. Flex     3→5 efforts · official low/high/max + our medium & xhigh
  2. Value    −49% cost · same result, less cost (beta) ★default
  3. Deeper   +7% depth · deeper than max (beta)
  4. Proven   pro only · steady agentic coding (beta)
  5. Swift    pro only · shell + editor focus (beta)
  6. Peak     pro only · stated twice up front (beta)
Choose 1-6 (Enter=default):
```

![The six-tier picker, recorded from a real terminal](assets/picker-six-tiers.gif)

<sub>Recorded by `tools/make_picker_gif.py`: it runs `picker.py` under a pty the way the acceptance
test does, sends real arrow keys and screenshots the emulated terminal. No frame is hand-drawn.</sub>

Work as usual, then read the receipt on exit:

```text
◆ Value · technical preview 0.1.10
  /effort locked for end-to-end tuning — same result, less cost · for free /effort choice, use Flex

  ... your Claude Code session ...

✓ Saved ≈48.6% cost · ≈12s faster
◆ Value ×14 · in 241,806 tok(cache hit 73.1%) · out 9,118 tok · paid ¥0.28(off-peak rate)
```

---

## Contents

[Requirements](#requirements) · [Quick start](#quick-start) · [Which tier](#which-tier-should-i-use) ·
[Usage](#usage) · [Session modes](#three-session-modes) · [Exit receipt](#how-to-read-the-exit-receipt) ·
[Environment variables](#environment-variables) · [Troubleshooting](#troubleshooting) · [Roadmap](#roadmap) · [FAQ](#faq) ·
[Community](#community) · [Citation](#citation) · [License](#license)

---

## Requirements

| | Needed | How to check | If missing |
|---|---|---|---|
| **Node.js ≥ 16** | to install from npm | `node -v` | [nodejs.org](https://nodejs.org) |
| **Python ≥ 3.8** | the launcher and relay are pure standard library — **zero pip installs** | `python3 --version` | Windows: [python.org](https://www.python.org/downloads/) (tick *Add python.exe to PATH*) · macOS: `xcode-select --install` · Linux: your package manager |
| **Claude Code** | cct wraps it; it is not bundled | `claude --version` | `npm install -g @anthropic-ai/claude-code` or `curl -fsSL https://claude.ai/install.sh \| bash` |
| **A DeepSeek API key** | you pay DeepSeek directly; cct never holds your key | — | [platform.deepseek.com](https://platform.deepseek.com/api_keys) |

Works on Linux, macOS and Windows from the same code path. On Windows the picker has no animation and
falls back to a numbered list; everything else is identical.

---

## Quick start

**1 — Install**

```bash
npm install -g @seedsky/cct
```

<details>
<summary>Upgrading from the old package name <code>cct</code>?</summary>

The package used to be published as plain `cct`. Both provide the same `cct` command, so npm refuses
to link the new one until the old one is gone:

```bash
npm uninstall -g cct
npm install -g @seedsky/cct
```
</details>

> **Supported channel:** the official DeepSeek API only — `https://api.deepseek.com/anthropic`.
> That is what every tier is calibrated against and what the receipt prices assume. Third-party
> proxies, resellers and self-hosted gateways may well work, but **compatibility is not guaranteed**
> and neither the tier strength nor the cost figures carry over. DeepSeek's own guide for running
> Claude Code against their API is here: [Claude Code integration](https://api-docs.deepseek.com/zh-cn/quick_start/agent_integrations/claude_code).

**2 — Set up the official DeepSeek API**

cct talks to the **official DeepSeek API** only. The two blocks in ② follow DeepSeek's own guide with
two model names changed (spelled out under the blocks); source:
[DeepSeek docs · Claude Code integration](https://api-docs.deepseek.com/zh-cn/quick_start/agent_integrations/claude_code).

**① Create an API key** — at [platform.deepseek.com/api_keys](https://platform.deepseek.com/api_keys).
It looks like `sk-…`. A new account has to top up first; the API ships no free credit.

**② Point Claude Code at DeepSeek**

Linux / Mac — run this in your terminal:

```bash
export ANTHROPIC_BASE_URL=https://api.deepseek.com/anthropic
export ANTHROPIC_AUTH_TOKEN=<your DeepSeek API Key>
export ANTHROPIC_MODEL=deepseek-v4-flash
export ANTHROPIC_DEFAULT_OPUS_MODEL=deepseek-v4-pro[1m]
export ANTHROPIC_DEFAULT_SONNET_MODEL=deepseek-v4-flash
export ANTHROPIC_DEFAULT_HAIKU_MODEL=deepseek-v4-flash
export CLAUDE_CODE_SUBAGENT_MODEL=deepseek-v4-flash
export CLAUDE_CODE_EFFORT_LEVEL=max
export CLAUDE_CODE_AUTO_COMPACT_WINDOW=786432
```

Windows — run this in PowerShell:

```powershell
$env:ANTHROPIC_BASE_URL="https://api.deepseek.com/anthropic"
$env:ANTHROPIC_AUTH_TOKEN="<your DeepSeek API Key>"
$env:ANTHROPIC_MODEL="deepseek-v4-flash"
$env:ANTHROPIC_DEFAULT_OPUS_MODEL="deepseek-v4-pro[1m]"
$env:ANTHROPIC_DEFAULT_SONNET_MODEL="deepseek-v4-flash"
$env:ANTHROPIC_DEFAULT_HAIKU_MODEL="deepseek-v4-flash"
$env:CLAUDE_CODE_SUBAGENT_MODEL="deepseek-v4-flash"
$env:CLAUDE_CODE_EFFORT_LEVEL="max"
$env:CLAUDE_CODE_AUTO_COMPACT_WINDOW="786432"
```

Run like that and it only lasts for **the current terminal**. To persist: on Linux / Mac put it in
`~/.bashrc` or `~/.zshrc`; on Windows use `setx` or your PowerShell profile (`$PROFILE`).

> **Two lines differ from DeepSeek's own block** (this pairing suits cct better): `ANTHROPIC_MODEL` and
> `ANTHROPIC_DEFAULT_SONNET_MODEL` are `deepseek-v4-flash` here where their guide says
> `deepseek-v4-pro[1m]` — **about a third of the price**, and the model every cct tier is calibrated
> against and every receipt price assumes. `ANTHROPIC_DEFAULT_OPUS_MODEL` stays on pro, so explicitly
> asking for opus still gets you the heavy model; the haiku and subagent slots are flash in their block
> already. Want DeepSeek's exact values? Put `deepseek-v4-pro[1m]` back in those two lines — same tier
> rules, roughly 3× the cost.

**③ Check the official path works** — no cct yet, this is bare Claude Code against DeepSeek:

```bash
claude -p "What is 1+1? Number only."
```

A `2` means the DeepSeek side is configured and you can move on to step 3.

**If you only ever use cct, the one variable it actually needs is `ANTHROPIC_AUTH_TOKEN`** — it takes
over the rest inside its own session (`ANTHROPIC_BASE_URL` pinned to the relay, model pinned to flash,
`/effort` governed by the tier). And if you already run Claude Code against DeepSeek through
`~/.claude/settings.json` or exported environment variables, you do not have to change anything —
cct reads that setup as-is and pins the traffic back to its own relay. See
[settings.json takeover](#what-happens-during-a-session).


**3 — Run it**

```bash
cct claude
```

You get the picker, then a normal Claude Code session, then a receipt on exit.

**4 — Verify the install (30 seconds)**

```bash
cct list                                       # the tier table — no API call, no key needed
cct claude -p "What is 17*23? Number only."    # one real call end to end
```

A healthy run looks like this:

```text
◆ Value · technical preview 0.1.10
  /effort locked for end-to-end tuning — same result, less cost · for free /effort choice, use Flex
391
✓ Saved ≈48.6% cost · ≈0s faster
◆ Value ×1 · in 19,621 tok(cache hit 0.0%) · out 2 tok · paid ¥0.03(off-peak rate)
```

The two `◆` lines mean the relay is in the path and the tier is being applied. If instead you see
`◆ No successful API calls this session`, jump to [Troubleshooting](#troubleshooting).

---

## Which tier should I use?

<img src="assets/fig-tier-landscape.png" width="820" alt="Seven tiers side by side: the official Low/High/Max and the Value/Classic/Extra/Deeper tiers added by SeedSky CCT, plotted as output-token distributions per task on a log axis. Terminal-Bench 2.1, 89 tasks, deepseek-v4-flash.">

Seven tiers side by side: DeepSeek's three (grey) and the four we added (blue), on a log axis of output
tokens per task. The thing to notice is that **Value sits at Low's spend** — `Classic` and `Extra` fill
the gaps between adjacent official steps, and `Deeper` reaches past Max.

| Tier | Use it when | Trade-off |
|---|---|---|
| **Value** (default) | day-to-day coding, bug fixing, batch chores | same job, measurably less spend |
| **Flex** | you want to steer depth yourself, or want stock upstream behaviour | you drive `/effort` per request |
| **Deeper** | one hard problem worth paying for — long reasoning, tricky bug | more tokens, more time |

Start on **Value** and forget about it. Reach for **Deeper** on the one problem that deserves it.
`Classic` and `Extra` sit in between and are reachable with `-e` (see [Usage](#usage)).

### The three pro-only tiers

**What they are for, in one line:** Claude Code is a large harness — a ~12 KB system prompt and two
dozen tools — and DeepSeek's own agent (`dsh`) is a small one: a 46-byte system prompt and two
tools, run at `max` effort. On identical repositories the small harness solves more. These three
tiers put a short prefix in front of Claude Code's own prompt so that the model **behaves as if it
were reading the smaller harness**, while Claude Code itself is left exactly as it is.

| | Claude Code, as shipped | `dsh` minimal, the target | What the tiers change |
|---|---|---|---|
| system prompt | ~12 KB of agent policy | 46 bytes | nothing is deleted; a prefix is prepended |
| tools | 24 schemas | 2 (bash, file editor) | nothing is removed; `Swift` only *says* two are enough |
| effort | your `/effort` | `max` | forwarded untouched on these three tiers |
| tool-calling | native | native | **untouched — this is the point** |

**Measured, one run per task, official API, `deepseek-v4-pro`, 30 DeepSWE tasks chosen for
discrimination** (repos where the arms actually disagree, not a soft panel):

| Arm | Solved |
|---|---|
| Claude Code alone | **12 / 30** |
| Claude Code + `cct` | **20 / 30** |

The 20 was reached twice, by two different prefixes from the same search line: `Proven` in the
2026-09 panel and the newer search-derived prefix on 2026-09-07.

#### How this differs from the other ways of pointing Claude Code at DeepSeek

There is a good and growing set of projects that put DeepSeek behind Claude Code — translation
proxies such as [UniClaudeProxy](https://github.com/vibheksoni/UniClaudeProxy),
[claude-code-proxy](https://github.com/empero-org/claude-code-proxy),
[deepclaude](https://github.com/aattaran/deepclaude) and
[deep-claude](https://github.com/dennisonbertram/deep-claude), and cache-alignment work such as
[permafrost](https://github.com/jianzhichun/permafrost). Their common shape is *plumbing*: translate
the wire format, keep the harness byte-stable, sometimes rewrite or compress the system prompt so a
smaller model is not overwhelmed, sometimes strip the Claude identity so a model will not refuse to
role-play. Several of them note the side effect that the model, having read Claude Code's prompt,
will tell you it is Claude — a persona the harness hands over for free.

`cct` is not doing that. The prefix here was not written by hand from intuition and it is not a
persona: it was **searched for against the model's own internals**. Every candidate sentence was
scored against the running model's **neuron-level activation mechanism** — which internal circuits
each layer engages for the first tokens of its reasoning, and how much energy each of them draws —
and by measuring the distance between "Claude Code's harness" and "the small harness at max effort"
in that space.
Hundreds of hand-written candidates were fielded across generations, each one isolating a single
variable, each with its acceptance threshold written down before the first sample, and each judged
on paired per-task contrasts rather than on a single number. What survived is a prefix that moves
the model's internal activation along the axis that separates the two harnesses, and only along it —
the off-axis component, the part that would mean "doing something else entirely", stays flat.

Three consequences worth stating plainly:

- **We modify the harness, not the model.** No fine-tune, no LoRA, no distillation. The change is
  bytes in the prompt, chosen by measurement rather than by taste.
- **We do not break native tool-calling.** Nothing is deleted from the tool array and no ReAct/XML
  emulation is introduced; tool schemas, streaming and the agent loop are Claude Code's own. The
  one exception is opt-in and labelled: `Swift` *tells* the model to use only two tools, and the
  README says so where you pick it.
- **It self-evolves against a ruler, not against a story.** The search reads its own mechanism
  measurements, proposes the next generation from what the last one refuted, and closes an axis when
  the data says it is closed. A dozen plausible ideas died that way — including several of ours that read
  well and measured worse.


#### The three tiers themselves

`Proven` / `Swift` / `Peak` all carry a **register prefix** — short clipped clauses in the voice the
small harness reasons in — measured against agentic SWE tasks (SWE-bench-style repos, run to
completion with a verifier). They differ only in what the prefix says and how often:

| Tier | Pick it with | The prefix | Size |
|---|---|---|---|
| **Proven** | `cct -e proven` | three escalating paragraphs (inspect → branch, implement, test → the full checklist), then three persona lines and one line fixing the first words of the reasoning | 629 B |
| **Swift** | `cct -e swift` | the same clauses flattened into one paragraph, **plus** "you have exactly two tools… ignore every other tool… no sub-agents, no skills, no task lists" | 738 B |
| **Peak** | `cct -e peak` | `Proven`'s text verbatim, said **twice**: once in the system prompt and once as a reminder after your first message | 629 B ×2 |
| *(hidden)* **Aligned** | `cct -e aligned` | the newest prefix the mechanism search produced: same skeleton as `Proven`, but the plan line states only things literally true of every task, and `/effort` is held at `low` so the prefix is the only depth instruction the model sees. Not in the picker; this is the one that scored 20 / 30 on 2026-09-07 | 1.1 KB |

Three properties set all of them apart from the tiers above:

- **They pin the model.** Each one answers on `deepseek-v4-pro` whatever `/model` says, because
  that is the only model they were ever measured on. Both `ANTHROPIC_MODEL` and the relay's
  model-forwarding enforce it; the ledger keeps what the client asked for beside what was sent.
  **Keep the two in agreement**: if Claude Code runs under any other name (a `settings.json`
  `env.ANTHROPIC_MODEL`, a `--model`, a `/model` switch mid-session) the relay still answers on
  pro, but Claude Code up to 2.1.219 then drops its own thinking from the replayed history — the
  session runs without its reasoning and the numbers below no longer apply. Under these three
  tiers `cct` therefore pins the name everywhere it can reach — `--model` on the command line,
  `ANTHROPIC_MODEL` in the environment and in the `--settings` pin file, and every model slot
  (so a `/model` pick of opus/sonnet/haiku stays on pro); a `--model` of your own is overridden
  and said so. The relay warns in `relay.log` the moment a multi-turn request still arrives
  under another name, and the receipt counts those requests.
- **They leave `/effort` alone.** Unlike the tuned tiers, these splice their prefix and forward
  your effort untouched — that is the construction they were calibrated in.
- **They cost pro rates.** Pro is ~3× flash per token. The receipt prices it correctly.

| Tier | What the prefix does | Measured, official API, `deepseek-v4-pro` |
|---|---|---|
| **Proven** | telegraph-register preamble | **20 of 29 tasks** |
| **Swift** | same register, plus it tells the model it has only a shell and a file editor | **7 of 8 tasks** on the disagreement panel |
| **Peak** | Proven's text, repeated as a per-turn reminder | **18–21 of 30** |

**`Swift` narrows the tool surface by instruction.** Its prefix says "you have exactly two tools…
ignore every other tool… there are no sub-agents, no skills, no task lists". Every tool stays wired
up — Claude Code is unchanged — so sub-agents, skills and task lists simply go unused in that tier.

---

## Usage

```bash
cct                       # equivalent to cct claude
cct claude                # pick one of six at startup (3s without a key press = default tier)
cct -e deeper claude      # go straight to a tier, skipping the picker
cct claude -p "..."       # all other arguments are forwarded verbatim to claude
cct list                  # tier table (vs official max badge + description)
```

Tier selection **only happens at startup** (picker or `-e`). You cannot switch tiers mid-session; quit and restart if you want another one.

| `-e` accepts | Display label | Meaning |
|---|---|---|
| `flex` `official` `high` | **Flex** | no injection, hands control back to Claude Code's own `/effort` |
| `value` `balance` `best` | **Value** (default) | same job, less cost — the everyday workhorse tier |
| `classic` `medium` `med` | **Classic** | the middle injection tier |
| `extra` `xhigh` | **Extra** | deeper than official high |
| `deeper` `deep` | **Deeper** | deeper than official max — more expensive, slower |
| `proven` `tm03` `tripara` | **Proven** | register preamble, pro only — see [the three pro-only tiers](#the-three-pro-only-tiers) |
| `swift` `qt05` | **Swift** | same, with the tool surface narrowed to a shell and an editor |
| `peak` `tm03x5` | **Peak** | same preamble, also as a reminder after the first message |

The picker shows six (Flex · Value · Deeper · Proven · Swift · Peak); `Classic` and `Extra` sit
between the tuned tiers and are reachable with `-e` only. All eight are always reachable directly
with `-e`.

---

## Three session modes

### Pinned-tier sessions (Value / Classic / Extra / Deeper)

**Every request in this session runs on that tier.** `/effort` inside Claude Code no longer takes effect, but this is **not silent**: the startup banner states `/effort locked`, and the exit receipt counts how many times it was overridden.

The tier is applied at the relay layer: it clears the upstream's built-in thinking base effort, then injects that tier's preamble at the head of system. To keep the client from flattening the depth, injection tiers force `thinking.type` to `enabled` — **this is the only switch we flip**; `budget_tokens` / `display` and the other keys of `output_config` are left exactly as they are, and nothing the client did not send gets added.

### Flex sessions (= governed by Claude Code's native `/effort`)

Per request, `/effort` is looked up in `cc_effort_map` in `tiers.json` (editable):

- `low` / `high` / `max` → **straight through to official** (your original effort value is forwarded and lands in the corresponding upstream bucket);
- `medium` / `xhigh` → land on our calibrated injection tiers (Classic / Extra).

Claude Code's default (`cc_effort_default`) goes straight through to the official high bucket, i.e. the native experience. A Flex session also strips any leftover `CLAUDE_CODE_EFFORT_LEVEL` from the environment (it overrides the `/effort` menu and locks the level), so that `/effort` really works.

⚠ Footgun: the values in `cc_effort_map` must be tier names that exist in the tier table; `official` passthrough means "change the channel, not the value" — mapping `medium → official` lands in the upstream medium bucket, not the high bucket.

### How to choose

- Everyday coding, bug fixing, batches of small tasks → **Value** (default);
- You want to decide the depth request by request, or want the native official behaviour → **Flex**;
- Hard problems, long reasoning chains, a one-off push worth paying more for → **Deeper**.

Value and Deeper are currently marked `(beta)`.

---

## Model channel rules (three of them, there is no fourth)

1. `deepseek-v4*` → governed by the session tier, **the original model name is passed through** (pro included);
2. **every other model name** (`claude-*` / `gpt-*` / garbage / empty) → **forwarded verbatim, zero intervention, zero rejection**; right or wrong is adjudicated by the upstream and its own wording is relayed verbatim — the relay never issues a policy 400.
3. **except in a single-model tier** (`Proven` / `Swift` / `Peak`, i.e. any tier declaring `force_model` in `tiers.json`): that tier rewrites the model to its own, for every request, rule 2 included.

Corollary: if an external tool changes `ANTHROPIC_MODEL` to a name that is not `deepseek-v4*`, those requests are forwarded verbatim and **the tier does not participate**. This does not happen silently: the exit receipt names how many requests bypassed the tier you picked.

Why rule 3 exists: the arms behind those tiers were only ever measured on `deepseek-v4-pro`.
A request escaping to another model does not fail loudly — it comes back looking fine while being
uncalibrated, which is worse than an error. So the tier claims the request instead of trusting the
client. Nothing about this is hidden: every ledger row keeps `asked` (what the client sent) next to
`forced` (what went upstream), and the session banner states the pin on startup.

What rule 3 cannot do is fix the client. Claude Code decides what to replay from its own
transcript, and up to 2.1.219 it drops every `thinking` block of the history when the model name
it runs under differs from the `model` in the responses (2.1.258 no longer does). Under a
single-model tier that means: **the name Claude Code is launched with must equal the tier's
`force_model`**. `cct` sets `ANTHROPIC_MODEL` accordingly; anything that overrides it — a
`settings.json` `env` block, a `--model`, a `/model` switch — puts the session in a state where the
relay's rewrite still lands on pro while the model works without its earlier reasoning. The relay
prints one `WARN` line per offending name to `relay.log` as soon as a multi-turn request shows it.

---

## How to read the exit receipt

```
✓ Saved ≈38.2% cost(≈¥0.21) · ≈47s faster
◆ Value ×12 · in 214,880 tok(cache hit 71.3%) · out 13,004 tok · paid ¥0.34(peak 0.21 + off-peak 0.13)
```

- **Line 1 = the benchmark**: the baseline is "the same job run end to end at the **official max thinking level**", normalized by the output tokens per turn calibrated in the package. A Deeper session does not manufacture a saving; it states the truth as a positive depth line, `◆ Thinking ≈7% deeper than official max`; normalized amounts < ¥0.01 are not shown.
- **Line 2 = composition and what you actually paid**: hit count per tier (in a Flex session aggregated by the `/effort` word you pressed), input/output tokens, cache hit rate, and the actual spend estimated request by request from DeepSeek's time-of-day prices (Beijing 9:00–12:00 and 14:00–18:00 are peak, all other hours are half price; pro is charged at the pro price; the price table is `deepseek_price_cny_per_M` in `tiers.json` and is editable).
- Additional lines that may appear:
  - `◆ /effort mapped: medium→Classic ×3` — which tier the `/effort` you pressed landed on in a Flex session;
  - `◆ /effort locked by Value ×4 — for free /effort choice, use Flex` — how many times `/effort` was overridden in a pinned-tier session;
  - `◆ N request(s) bypassed Deeper — model '...' is not governed by tiers` — the model names of these requests are outside the `deepseek-v4*` channel, so the tier did not participate;
  - `◆ No successful API calls this session` — not one successful call was recorded in the ledger this session (see [Troubleshooting](#troubleshooting)).

The amounts on the receipt are **estimated from the ledger**, not a bill; DeepSeek's actual bill is authoritative.

---

## What happens during a session

- **Per-session private relay**: brought up on a temporary port, killed on exit (terminated precisely by PID), so multiple sessions do not interfere with each other. The relay binds `127.0.0.1`, raises no firewall authorization dialog, and cannot be reached from another machine.
- **Environment variables only go into the child process**: `ANTHROPIC_BASE_URL` is injected only into the wrapped process, **never exported globally** (that would hijack the Claude Code session you are already running in the outer shell).
- **Zero key logic**: neither cct nor the relay holds a key. The `x-api-key` / `authorization` the request carries are **forwarded verbatim**; rewriting only happens in the effort part. Supply your key the way you normally do.
- **Ledger**: `~/.cct/sessions/<time>_p<port>.jsonl`, where each line holds accounting fields only (model name, token counts, cache, latency, status code) — **no conversation content, no keys**. The relay's own log sits in the same directory as `.relay.log`.
- **settings.json pin-back**: at startup Claude Code writes the `env` block of `settings.json` back into the process environment, which can clobber the `ANTHROPIC_BASE_URL` cct injected (symptom: the session looks completely normal, but the traffic bypasses the relay — no tier, no ledger, no pricing). cct appends `--settings <this session's pin file>` to the claude session and **pins this one key only, `ANTHROPIC_BASE_URL`**: your settings file is not modified on disk at all, and `ANTHROPIC_AUTH_TOKEN` and the rest pass through unchanged. A successful pin-back is **completely silent**; the only place it speaks up is "the pin-back failed and settings really is hijacking" — that case is guaranteed to bypass, so it warns loudly.
- **It does not touch your configuration**: cct does not write your `~/.claude/settings.json`, and does not modify `~/.claude.json`.

---

## Boundaries and caveats

- **The calibration only holds for `api.deepseek.com`.** Tier strength, output tokens per turn and the peak/off-peak price table were all calibrated against the official upstream. When you point `DA_UPSTREAM` at a third-party proxy or a self-hosted gateway, cct **only warns, it does not degrade** (the tier is applied as usual), but results and billing may deviate — whether to use it is your call.
- **Do not put credentials in the upstream URL.** `https://user:token@host/...` does connect, but the full URL shows up in the relay log and in the `/health` response (both under `~/.cct/sessions/` on this machine). Prefer passing credentials in request headers.
- **Context window.** cct does not touch Claude Code's context settings. Claude Code does not
  recognise the DeepSeek model names, so it assumes a 200k window and auto-compacts early. DeepSeek's
  own guide recommends setting `CLAUDE_CODE_AUTO_COMPACT_WINDOW=786432` (and using the `[1m]` model
  suffix) if you want the full window — see [their Claude Code guide](https://api-docs.deepseek.com/zh-cn/quick_start/agent_integrations/claude_code). Set it yourself if you
  need it; cct deliberately leaves that decision to you.
- **Preview period.** Version `0.1.x`, the startup banner says `technical preview`, some tiers are marked `(beta)`; both the behaviour and the tier table can change.
- **No liability for your bill.** The relay forwards requests to a third-party API that you configure and pay for yourself; billing is whatever that party says it is.
- **Windows differences**: the picker has no animation and degrades to a numbered list (no termios); functionally equivalent.
- **macOS**: TLS uses the system trust store. If you use a Python from the python.org installer, you need to run `Install Certificates.command` from its install directory once, otherwise connecting to the upstream reports `CERTIFICATE_VERIFY_FAILED` (the Homebrew / Command Line Tools python3 does not have this problem).

---

## Environment variables

**Launcher (`CCT_*`)**

| Variable | Effect |
|---|---|
| `CCT_PYTHON` | Path to the Python interpreter (by default probed as python3 / python / `py -3`) |
| `CCT_NO_PICKER` | Skip the picker, go directly with `-e` or the default tier |
| `CCT_TIERS` | Use a different tier table json |
| `CCT_SESS_DIR` | Use a different session ledger directory (default `~/.cct/sessions`) |
| `CCT_NO_UPDATE_CHECK` / `CCT_REGISTRY` / `CCT_UPDATE_TAG` / `CCT_FORCE_ACK` | Update-check switch / private registry / channel / CI escape hatch |

**Relay (`DA_*`)** — in a cct session `DA_PORT` / `DA_TIER` / `DA_TIER_TABLE` / `DA_LEDGER` / `DA_BIND` are set by cct itself; the ones below you can set up front in your shell and they will be inherited.

| Variable | Effect |
|---|---|
| `DA_UPSTREAM` | Upstream address (default `https://api.deepseek.com/anthropic`) |
| `DA_READ_TIMEOUT` | Upstream read timeout in seconds (default 3600) |
| `DA_LEDGER` | Ledger file path (default `~/.cct/usage_relay.jsonl` when run standalone) |
| `DA_CAPTURE` | Capture directory, one file per request and per response; empty = off (default). Goes with `DA_CAPTURE_WHAT` (req/resp/both), `DA_CAPTURE_MAX` (byte cap per file), `DA_CAPTURE_REDACT` (default 1, scrubs key-shaped strings before writing to disk) |
| `DA_PIN` / `DA_DENY` | Model handling: both off by default = pure passthrough; only `DA_PIN=<model name>` rewrites, `DA_DENY=1` rejects anything that is not flash outright with a 400 |
| `DA_BIND` / `DA_PORT` | Bind address and port when running the relay standalone |
| `DA_EFFORT` / `DA_BASE_EFFORT` / `DA_PREAMBLE_FILE` | Manual injection for single-tier mode (mutually exclusive with tier-table mode); changing the injection construction departs from the calibration and is not guaranteed to be equivalent to the official tiers |
| `DA_KEY_FILE` / `DA_KEY_ENC` | Legacy mode: the relay injects the key on your behalf (off by default; the ledger only records an irreversible fingerprint) |

Capture (`DA_CAPTURE`) is off by default for a reason: one agent batch run can write tens of thousands of full SSE transcripts, and a single one can reach MB size. It should only be turned on when you need to run a leak audit.

---

## Troubleshooting

| Symptom | What to do |
|---|---|
| **`✗ command not found: claude`** | cct wraps Claude Code but does not bundle it. Install it first: `npm install -g @anthropic-ai/claude-code` (or `curl -fsSL https://claude.ai/install.sh | bash`), then `claude --version` to confirm |
| **`Not logged in · Please run /login`** | **Do not run `/login`** — that signs you into an Anthropic account, a different service. It means no key reached the API: `export ANTHROPIC_AUTH_TOKEN=sk-your-deepseek-key` (or put it in the `env` block of `~/.claude/settings.json`) and start again |
| It reports that Python cannot be found | On Windows install from the official site and tick Add to PATH; on macOS `xcode-select --install`; on Linux use your package manager. Or point `CCT_PYTHON` at the path |
| `✗ relay failed to start` | Look at the tail of `~/.cct/sessions/<time>_p<port>.relay.log`; the real reason is in there |
| The session is fine, but the receipt says `No successful API calls` | Most likely the traffic bypassed the relay: check whether `ANTHROPIC_BASE_URL` is in the `env` block of `~/.claude/settings.json` or of the project's `.claude/settings.json` / `settings.local.json` |
| The receipt shows `bypassed <tier name> — model ... is not governed by tiers` | The model names of these requests are not `deepseek-v4*` (commonly because an external tool rewrote `ANTHROPIC_MODEL`); they were forwarded verbatim and the tier did not participate |
| `/effort` does nothing in a pinned-tier session | By design: in a pinned-tier session the relay applies one tier uniformly. To pick the depth request by request, use Flex |
| `CERTIFICATE_VERIFY_FAILED` (macOS) | Run `Install Certificates.command` from the Python install directory once |
| A global proxy on this machine breaks requests | cct already adds `NO_PROXY=127.0.0.1,localhost` for the child process and strips the proxy variables from the relay's environment; if your proxy tool intercepts local traffic by some other mechanism, you have to allow `127.0.0.1` yourself |
| The `cct` command points at something else | Leftover from the old package name: `npm uninstall -g cct`, then reinstall |

---

## Roadmap

| Agent CLI | Status |
|---|---|
| **Claude Code** | ✅ supported — tiers, ledger, receipt, settings pin-back, all tested end to end |
| **Codex** | 🔬 in closed beta |
| **DSH** | 🔬 in closed beta |
| **OpenCode** | 🔬 in closed beta |
| other common agent CLIs | 🚧 under evaluation |

The relay speaks the Anthropic message format, so any client that talks that format can already be
pointed at it manually (see [Running the relay standalone](#running-the-relay-standalone-advanced)).
What each new agent needs on top of that is the launcher half: locating its binary, injecting the
per-session endpoint without disturbing the user's own configuration, and reading its equivalent of a
thinking-effort setting. That work is per-agent, which is why they land one at a time.

| Model | Status |
|---|---|
| **DeepSeek family** (`deepseek-v4-flash` / `deepseek-v4-pro`) | ✅ supported — tiers calibrated on flash, priced on the official peak/off-peak table |
| **GLM** | 🚧 planned |
| **Kimi** | 🚧 planned |
| other models | 🚧 under evaluation |

## FAQ

**Does cct see my prompts or my API key?**
No. The relay forwards the `x-api-key` / `authorization` header your client already sends, untouched;
cct itself never stores a key. The ledger under `~/.cct/sessions/` holds accounting fields only —
token counts, cache hits, latency, status codes — never conversation content.

What the relay *does* change, and nothing beyond it: the thinking-depth part of the request body on
every injection tier; on the three pro-only tiers also the model name and the effort value, both
pinned to what that tier was calibrated on, and for `Peak` one added reminder message per request.
Your own messages are passed through untouched in every case; the ledger records what was pinned
(`forced`, `eff_forced`) beside what your client originally asked for.

**Is the receipt my actual bill?**
No — it is an estimate computed from the ledger and the price table in `tiers.json`. DeepSeek's own
invoice is authoritative. The savings percentage is likewise an estimate: it compares what you spent
against what the same work would have cost at the official max thinking level, using calibrated
per-turn output figures.

**Can I use it with a third-party gateway instead of DeepSeek directly?**
Yes — point `DA_UPSTREAM` at it. cct will warn once that the calibration only holds for
`api.deepseek.com`, then apply tiers exactly as it would otherwise. Put credentials in headers, not in
the URL: a `https://user:token@host/...` upstream works, but the full URL then appears in the local
relay log.

**Does it interfere with CC Switch / other Claude Code managers?**
No. Those tools configure Claude Code by writing the `env` block of `~/.claude/settings.json`; cct
pins `ANTHROPIC_BASE_URL` back to its own relay for the session with a higher-precedence CLI flag,
without editing your files. Switching providers mid-session, project-level settings and
`settings.local.json` were all verified not to steal the traffic.

**Why does `/effort` do nothing?**
Because you are in a pinned tier (Value / Classic / Extra / Deeper), where the whole point is that one
tier governs every request. Use **Flex** if you want per-request control — there `/effort` is fully
live, and cct even clears a stale `CLAUDE_CODE_EFFORT_LEVEL` that would otherwise lock the menu.

**The receipt says some requests bypassed my tier. Why?**
Tiers only govern `deepseek-v4*` model names; anything else is forwarded verbatim. If a tool rewrote
`ANTHROPIC_MODEL` to something like `claude-sonnet-4-5`, those requests still work (DeepSeek maps the
name) but the tier does not participate. Set the model back to `deepseek-v4-flash` to bring them under
the tier.

**Can I run the test suite?**
Yes, but read `tests/README.md` first: part of the suite makes **real, billed API calls** and
temporarily rewrites `~/.claude/settings.json` (restored on exit, including on Ctrl-C). The
mock-upstream and offline tests cost nothing.

## Running the relay standalone (advanced)

To reproduce exactly what a tier sends, point the relay at the shipped tier table rather than
at `DA_PREAMBLE_FILE`:

```bash
DA_TIER_TABLE=$(npm root -g)/@seedsky/cct/tiers.json DA_TIER=proven \
DA_CAPTURE=/tmp/cap DA_CAPTURE_WHAT=req python3 relay_anthropic.py
```

The tier is what carries the model pin, the effort pin and the splice position, so a preamble
mounted by hand through `DA_PREAMBLE_FILE` is a different construction from the tier of the same
name — deliberately: `DA_PREAMBLE_FILE` keeps the behaviour it has always had.

For use without the launcher, from another client or a container:

```bash
DA_PORT=8301 python3 relay_anthropic.py

# point the client here (child process only, never export globally!)
ANTHROPIC_BASE_URL=http://127.0.0.1:8301 ANTHROPIC_MODEL=deepseek-v4-flash \
  ANTHROPIC_API_KEY=<your DeepSeek key> claude -p "..."
```

In this mode there is no tier table; the default is pure passthrough + observation, and authentication is passed through as well. `/health` reports honestly which rewrites this process has enabled.

⚠ In standalone mode `DA_BIND` defaults to `0.0.0.0` (kept for container scenarios). On a shared machine set `DA_BIND=127.0.0.1` explicitly, otherwise anyone on the same subnet can reach your relay and read the upstream address from `/health`.

---

## Files

| File | Purpose |
|---|---|
| `cct.js` / `cct.py` | Cross-platform npm bin shim (responsible for finding Python) / the one implementation of the launcher, the same code path on all three platforms |
| `cct` | Thin wrapper for running `./cct` directly inside the repository |
| `picker.py` | The tier picker shown at startup (degrades automatically on non-TTY / narrow terminals / Windows) |
| `relay_anthropic.py` | Transparent rewriting relay in Anthropic format: chunked request body + SSE streaming passthrough + usage scraped from the tail of the stream |
| `keystore.py` | Optional encrypted key storage (PBKDF2 + Fernet); only an irreversible fingerprint appears in the ledger |
| `tiers.json` | Tier table: tier definitions, `/effort` mapping, calibrated values, price table |
| `preambles/` | The preamble text of each tier |
| `tests/` | Acceptance scripts, see [tests/README.md](tests/README.md). ⚠ Some of them consume real API credit, need a logged-in claude CLI, and temporarily rewrite this machine's Claude Code configuration — read the warnings at the top of the scripts before running them, and preferably run them in a disposable container only |

---

## Community

<div align="center">

<table>
<tr>
<td align="center"><img src="assets/wechat-group.jpg" width="240" alt="WeChat QR code for the cct user group"></td>
<td align="center"><img src="assets/qq-group.jpg" width="240" alt="QQ QR code for the cct user group, group number 1019231337"></td>
</tr>
<tr>
<td align="center"><sub>Scan with <b>WeChat</b> — cct user group 1</sub></td>
<td align="center"><sub>Scan with <b>QQ</b> — cct user group 1 · <code>1019231337</code></sub></td>
</tr>
</table>

</div>

The WeChat code rotates every seven days — this one is **valid until 2026-09-15**. Once it expires,
join over QQ instead, or email <hello@seedsky.ai> and we will post a fresh one.

---

## Citation

This work builds on two papers — an interpretable reasoning-state readout, and the finding that a
model's internal state carries a usable control signal for reasoning:

```bibtex
@misc{chen2026jar,
  title  = {Beyond the Trace: Coupling an Interpretable Reasoning-State
            Readout to Native MoE Routing},
  author = {Chen, Kang and Zhao, Sihan and Cao, Yixin and Jiang, Yu-Gang},
  year   = {2026},
  eprint = {2608.17638},
  archivePrefix = {arXiv},
  primaryClass = {cs.AI},
  note   = {JAR --- Jacobian Axis Readout},
  url    = {https://arxiv.org/abs/2608.17638},
}
```

```bibtex
@article{chen2026rad,
  title   = {Does the Same Token Mean the Same State?
             MoE Routing as Signal for Reasoning Control},
  author  = {Chen, Kang and Yu, Mingshen and Nian, Junjie and
             Wang, Yaoning and Cao, Yixin and Jiang, Yugang},
  year    = {2026},
  eprint  = {2606.22798},
  archivePrefix = {arXiv},
  primaryClass = {cs.CL},
  note    = {Routing Agreement Decoding (RAD)},
  url     = {https://arxiv.org/abs/2606.22798},
}
```

Project pages: <https://cckfdu.com/jar/> · <https://cckfdu.com/rad/>

---

## License

See [LICENSE](LICENSE).

---

<div align="center">

<sub>Built by <a href="https://seedsky.ai"><b>SeedSky</b></a> · <a href="https://seedsky.ai">seedsky.ai</a> · <i>Seek within. Evolve beyond.</i></sub>

</div>
