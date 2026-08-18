<div align="center">

<a href="https://seedsky.ai"><img src="assets/seedsky-mark.png" width="86" alt="SeedSky"></a>

<a href="https://seedsky.ai"><picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/seedsky-tagline-dark.png">
  <img src="assets/seedsky-tagline-light.png" width="342" alt="Seek within. Evolve beyond.">
</picture></a>

# cct

**让你的 AI agent 想得刚刚好 —— 同样的结果，账单减半。**

[![seedsky.ai](https://img.shields.io/badge/seedsky.ai-6C7AD7?logo=data:image/svg%2Bxml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCA2NCA2NCI%2BPHBhdGggZD0iTTMxIDUyYzAtMTQgNC0yNSAxOC0zOE0zMSA1MmMwLTExLTQtMjAtMTUtMjciIGZpbGw9Im5vbmUiIHN0cm9rZT0iI2ZmZiIgc3Ryb2tlLXdpZHRoPSIzLjQiIHN0cm9rZS1saW5lY2FwPSJyb3VuZCIvPjxwYXRoIGQ9Ik00OSAxNGMtMTEgMC0xNiA0LTE5IDEyIDEwIDIgMTctMiAxOS0xMlpNMTYgMjVjOSAwIDE0IDQgMTYgMTEtOSAwLTE0LTQtMTYtMTFaIiBmaWxsPSIjZmZmIi8%2BPGNpcmNsZSBjeD0iNTIiIGN5PSIxMCIgcj0iNC4yIiBmaWxsPSIjZmZmIi8%2BPC9zdmc%2B)](https://seedsky.ai)
[![npm](https://img.shields.io/npm/v/@seedsky/cct?color=cb3837&logo=npm)](https://www.npmjs.com/package/@seedsky/cct)
[![python](https://img.shields.io/badge/python-%E2%89%A53.8-3776AB?logo=python&logoColor=white)](https://www.python.org)
[![platform](https://img.shields.io/badge/platform-Linux%20%7C%20macOS%20%7C%20Windows-666)](#环境要求)
[![license](https://img.shields.io/badge/license-see%20LICENSE-blue)](LICENSE)
[![WeChat](https://img.shields.io/badge/WeChat-join-07C160?logo=wechat&logoColor=white)](#交流群)

[English](README.md) · **简体中文**

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/fig-value-hero-dark.png">
  <img src="assets/fig-value-hero.png" width="820" alt="Value 档：每题 55k 输出 token 解出 60.7% 的任务 —— 比官方 High 少 32% token，比官方曲线高 5.3 个百分点。Terminal-Bench 2.1，89 题，deepseek-v4-flash，每档每题跑一次。">
</picture>

</div>

---

官方只给三档思考：low / high / max（见 [DeepSeek 思考模式文档](https://api-docs.deepseek.com/zh-cn/guides/thinking_mode)）。high 烧掉的 token 是 low 的 **1.5 倍**，max 是 **2.2 倍** —— 而在我们跑的 89 道题上，max 并没有因此多解出一道。**大多数活儿，不需要模型想那么深。**

**Value 档：和官方 high 同等表现，token 少 32%。**

它不是手调出来的。我们从**神经元级机理**去看模型"想"的过程，再用**自进化高通量搜索**批量生成**思考锚点**、逐个上真实基准打分 —— 方法见 [seedsky.ai](https://seedsky.ai)。cct 就是靠控制这些锚点，在官方 low / high / max 之外补上 **medium**（low↔high 之间）与 **xhigh**（high↔max 之间），再开出两个全新的思考区域：**Value** 与 **Deeper**。各档具体落在哪，见 [该选哪个档](#该选哪个档)。

用法就是在你原来的命令前加一个 `cct`：启动时选档，退出时给你一张花费回执。**它只动一样东西：模型想得多深** —— 不修改、不压缩、不留存你的对话内容。

**目前只支持 Claude Code**，Codex、DSH、OpenCode 正在内测；**模型侧目前支持 DeepSeek 系列**，
GLM、Kimi 等其他模型正在路上 —— 见 [路线图](#路线图)。

## 长什么样

启动时选档（3 秒无按键自动确认默认档）：

```text
  1. Flex       3→5 efforts · official low/high/max + our medium & xhigh
  2. Value      −49% cost · same result, less cost (beta) ★default
  3. Deeper     +7% depth · deeper than max (beta)
Choose 1-3 (Enter=default):
```

照常干活，退出时看回执：

```text
◆ Value · technical preview 0.1.7
  /effort locked for end-to-end tuning — same result, less cost · for free /effort choice, use Flex

  ... 你的 Claude Code 会话 ...

✓ Saved ≈48.6% cost · ≈12s faster
◆ Value ×14 · in 241,806 tok(cache hit 73.1%) · out 9,118 tok · paid ¥0.28(off-peak rate)
```

---

## 目录

[环境要求](#环境要求) · [快速上手](#快速上手) · [该选哪个档](#该选哪个档) ·
[用法](#用法) · [三种会话模式](#三种会话模式) · [回执怎么读](#回执怎么读) ·
[环境变量](#环境变量) · [故障排查](#故障排查) · [路线图](#路线图) · [常见问题](#常见问题) ·
[交流群](#交流群) · [许可](#许可)

---

## 环境要求

| | 为什么需要 | 怎么检查 | 缺了去哪装 |
|---|---|---|---|
| **Node.js ≥ 16** | 用 npm 安装 | `node -v` | [nodejs.org](https://nodejs.org) |
| **Python ≥ 3.8** | 启动壳与中继是纯标准库 —— **零 pip 依赖** | `python3 --version` | Windows：[python.org](https://www.python.org/downloads/)（勾选 *Add python.exe to PATH*）· macOS：`xcode-select --install` · Linux：包管理器 |
| **Claude Code** | cct 是它的外壳，不打包它 | `claude --version` | `npm install -g @anthropic-ai/claude-code` 或 `curl -fsSL https://claude.ai/install.sh \| bash` |
| **DeepSeek API 密钥** | 你直接付给 DeepSeek；cct 从不持有你的密钥 | — | [platform.deepseek.com](https://platform.deepseek.com/api_keys) |

Linux / macOS / Windows 同一条代码路径。Windows 上选择器没有动画，降级为编号列表，其余完全一致。

---

## 快速上手

**1 —— 安装**

```bash
npm install -g @seedsky/cct
```

<details>
<summary>从旧包名 <code>cct</code> 升级？</summary>

这个包早期以裸名 `cct` 发布。两者提供同一个 `cct` 命令，所以旧的不卸载，npm 会拒绝链接新的：

```bash
npm uninstall -g cct
npm install -g @seedsky/cct
```
</details>

> **支持的渠道：只有 DeepSeek 官方 API** —— `https://api.deepseek.com/anthropic`。
> 所有档位都是针对它标定的，回执里的价格也按它的价表算。第三方中转、代理商、自建网关
> 大概率也能跑，但**兼容性不作保证**，档位效力与花费数字都不迁移。
> DeepSeek 官方关于 Claude Code 接入的说明见：[接入 Claude Code](https://api-docs.deepseek.com/zh-cn/quick_start/agent_integrations/claude_code)。

**2 —— 装好 DeepSeek 官方配置**

cct 只对接 **DeepSeek 官方 API**。下面 ② 的两段按官方文档来，只有两处模型名不同（差异见块下说明），
出处：[DeepSeek 文档 · 接入 Claude Code](https://api-docs.deepseek.com/zh-cn/quick_start/agent_integrations/claude_code)。

**① 申请 API Key** —— [platform.deepseek.com/api_keys](https://platform.deepseek.com/api_keys)，
建一个，形如 `sk-…`。新账号需要先充值，API 不送额度。

**② 把 Claude Code 指向 DeepSeek**

Linux / Mac 用户，直接在终端中执行：

```bash
export ANTHROPIC_BASE_URL=https://api.deepseek.com/anthropic
export ANTHROPIC_AUTH_TOKEN=<你的 DeepSeek API Key>
export ANTHROPIC_MODEL=deepseek-v4-flash
export ANTHROPIC_DEFAULT_OPUS_MODEL=deepseek-v4-pro[1m]
export ANTHROPIC_DEFAULT_SONNET_MODEL=deepseek-v4-flash
export ANTHROPIC_DEFAULT_HAIKU_MODEL=deepseek-v4-flash
export CLAUDE_CODE_SUBAGENT_MODEL=deepseek-v4-flash
export CLAUDE_CODE_EFFORT_LEVEL=max
export CLAUDE_CODE_AUTO_COMPACT_WINDOW=786432
```

Windows 用户，在 Powershell 中执行：

```powershell
$env:ANTHROPIC_BASE_URL="https://api.deepseek.com/anthropic"
$env:ANTHROPIC_AUTH_TOKEN="<你的 DeepSeek API Key>"
$env:ANTHROPIC_MODEL="deepseek-v4-flash"
$env:ANTHROPIC_DEFAULT_OPUS_MODEL="deepseek-v4-pro[1m]"
$env:ANTHROPIC_DEFAULT_SONNET_MODEL="deepseek-v4-flash"
$env:ANTHROPIC_DEFAULT_HAIKU_MODEL="deepseek-v4-flash"
$env:CLAUDE_CODE_SUBAGENT_MODEL="deepseek-v4-flash"
$env:CLAUDE_CODE_EFFORT_LEVEL="max"
$env:CLAUDE_CODE_AUTO_COMPACT_WINDOW="786432"
```

这样执行只在**当前终端**有效。想长期生效：Linux / Mac 写进 `~/.bashrc` 或 `~/.zshrc`，
Windows 用 `setx` 或写进 PowerShell 配置文件（`$PROFILE`）。

> **和 DeepSeek 官方那段的差别只有两处**（这个搭配更适合配 cct 用）：`ANTHROPIC_MODEL` 与
> `ANTHROPIC_DEFAULT_SONNET_MODEL` 官方给的是 `deepseek-v4-pro[1m]`，这里是 `deepseek-v4-flash`
> —— **价格约为 pro 的三分之一**，也是 cct 全部档位的标定基准、回执价表所依据的模型。
> `ANTHROPIC_DEFAULT_OPUS_MODEL` 保持 pro，这样你显式点名 opus 时拿到的仍是重模型；
> haiku 与 subagent 两个槽位官方本来就是 flash。想完全照官方来，把那两处换回
> `deepseek-v4-pro[1m]` 即可 —— 档位规则完全一样，只是贵约 3 倍。

**③ 先验证官方链路通了**（这一步还没 cct，就是裸 Claude Code 打 DeepSeek）：

```bash
claude -p "1+1=? 只回数字"
```

回了个 `2` 就说明 DeepSeek 侧配好了，可以往下走第 3 步。

**只用 cct 的话，这一堆里 cct 真正需要的只有 `ANTHROPIC_AUTH_TOKEN` 一个** —— 其余的 cct
会在自己会话里自行接管（`ANTHROPIC_BASE_URL` 钉到中继、模型钉到 flash、`/effort` 按档管）。
如果你本来就通过 `~/.claude/settings.json` 或环境变量让 Claude Code 连着 DeepSeek，那
**什么都不用改** —— cct 照用你现有的配置，并把流量钉回自己的中继。见
[settings.json 抢管](#会话里发生了什么)。


**3 —— 跑起来**

```bash
cct claude
```

先出选择器，然后是正常的 Claude Code 会话，退出时打回执。

**4 —— 验证安装（30 秒）**

```bash
cct list                                       # 档位表 —— 不打 API，不需要密钥
cct claude -p "17*23=? 只回数字"                 # 一次完整的真实调用
```

一次健康的运行长这样：

```text
◆ Value · technical preview 0.1.7
  /effort locked for end-to-end tuning — same result, less cost · for free /effort choice, use Flex
391
✓ Saved ≈48.6% cost · ≈0s faster
◆ Value ×1 · in 19,621 tok(cache hit 0.0%) · out 2 tok · paid ¥0.03(off-peak rate)
```

那两行 `◆` 说明中继确实在链路上、档位确实生效了。如果你看到的是 `◆ No successful API calls this session`，直接去 [故障排查](#故障排查)。

---

## 该选哪个档

<img src="assets/fig-tier-landscape.png" width="820" alt="七个档位并排：官方 Low/High/Max 三档与 SeedSky CCT 补的 Value/Classic/Extra/Deeper 四档，横轴为每题输出 token 的对数轴分布。Terminal-Bench 2.1，89 题，deepseek-v4-flash。">

七档并排：官方三档（灰）+ 我们补的四档（蓝），横轴是每题输出 token（对数轴）。要看的是
**Value 落在 Low 的花费位置上**——`Classic` 与 `Extra` 填住官方相邻档之间的空档，`Deeper` 顶到 Max 之外。

| 档位 | 什么时候用 | 代价 |
|---|---|---|
| **Value**（默认） | 日常写码、改 bug、批量小活 | 同样的活，实测更省 |
| **Flex** | 想自己逐条决定深度，或想要原生官方行为 | 由你用 `/effort` 逐请求控制 |
| **Deeper** | 一道值得花钱的难题 —— 长链推理、棘手 bug | 更多 token、更慢 |

**默认用 Value 就好，别多想**；遇到真正值得的那道题再上 **Deeper**。`Classic` 与 `Extra` 位于中间，用 `-e` 直达（见 [用法](#用法)）。

---

## 用法

```bash
cct                       # 等价于 cct claude
cct claude                # 启动时三选一（3 秒无按键 = 默认档）
cct -e deeper claude      # 直接指定档位，跳过选择器
cct claude -p "..."       # 其余参数原样透传给 claude
cct list                  # 档位表（vs 官方 max 徽标 + 说明）
```

选档**只发生在启动时**（选择器或 `-e`）。会话中途不能换档；想换就退出重开。

| `-e` 可写 | 界面名 | 含义 |
|---|---|---|
| `flex` `official` `high` | **Flex** | 不注入，把控制权交还给 Claude Code 自己的 `/effort` |
| `value` `balance` `best` | **Value**（默认） | 同样的活更省 —— 日常主力档 |
| `classic` `medium` `med` | **Classic** | 中间的注入档 |
| `extra` `xhigh` | **Extra** | 比官方 high 更深 |
| `deeper` `deep` | **Deeper** | 比官方 max 更深 —— 更贵更慢 |

选择器只摆三个（Flex · Value · Deeper）；五档全量随时可用 `-e` 直达。

---

## 三种会话模式

### 钉档会话（Value / Classic / Extra / Deeper）

**本会话全部请求走该档。** Claude Code 里的 `/effort` 不再生效，但**不是静默的**：启动横幅会写明 `/effort locked`，退出回执会统计它被覆盖了多少次。

档位施加在中继层：先清空上游自带的思考底座，再把该档的前导注入到 system 首部。为防止客户端把深度压浅，注入档下 `thinking.type` 会被强制为 `enabled` —— **只翻这一个开关**；`budget_tokens` / `display` 与 `output_config` 的其余键原样不动，客户端没发的字段也绝不新增。

### Flex 会话（= 交给 Claude Code 原生 `/effort` 管辖）

逐请求按 `/effort` 查 `tiers.json` 里的 `cc_effort_map`（可改）：

- `low` / `high` / `max` → **官方直通**（转发你的原始 effort 值，落到上游对应的桶）；
- `medium` / `xhigh` → 落到我们标定的注入档（Classic / Extra）。

Claude Code 的默认值（`cc_effort_default`）直通官方 high 桶，即原生体验。Flex 会话还会清除环境里遗留的 `CLAUDE_CODE_EFFORT_LEVEL`（它会压过 `/effort` 菜单把等级锁死），让 `/effort` 真的能用。

⚠ 脚枪：`cc_effort_map` 的值必须是档位表里存在的档名；`official` 直通的语义是"只换通道不改值"—— 把 `medium → official` 会落到上游的 medium 桶，而不是 high 桶。

### 怎么选

- 日常写码、改 bug、跑批量小任务 → **Value**（默认）；
- 想逐条自己决定深度、或要原生官方行为 → **Flex**；
- 难题、长链推理、值得多花钱的一次性攻坚 → **Deeper**。

Value 与 Deeper 目前标 `(beta)`。

---

## 模型通道规则（就两条，没有第三条）

1. `deepseek-v4*` → 受会话档管辖，**模型原名透传**（含 pro）；
2. **其余一切模型名**（`claude-*` / `gpt-*` / 乱名 / 空）→ **原样转发，零干预零拒绝**；对错由上游裁决并原话透传 —— 中继不会有任何策略性 400。

推论：如果外部工具把 `ANTHROPIC_MODEL` 改成了非 `deepseek-v4*` 的名字，这些请求会被原样转发，**档位不参与**。但这不是静默发生的：退出回执会点名有多少请求绕过了你选的档。

---

## 回执怎么读

```
✓ Saved ≈38.2% cost(≈¥0.21) · ≈47s faster
◆ Value ×12 · in 214,880 tok(cache hit 71.3%) · out 13,004 tok · paid ¥0.34(peak 0.21 + off-peak 0.13)
```

- **第一行 = 对标**：基准是"同样的活全程跑**官方 max 思考等级**"，按随包标定的每轮输出量折算。Deeper 会话不会硬凑省钱，而是如实写成正向的深度表述 `◆ Thinking ≈7% deeper than official max`；折算金额 < ¥0.01 时不显示。
- **第二行 = 构成与实付**：各档命中次数（Flex 会话按你按下的 `/effort` 词聚合）、输入/输出 token、缓存命中率，以及按 DeepSeek 分时价逐请求估算的实付（北京时间 9:00–12:00 与 14:00–18:00 为高峰，其余时段半价；pro 按 pro 价；价表是 `tiers.json` 里的 `deepseek_price_cny_per_M`，可改）。
- 可能出现的附加行：
  - `◆ /effort mapped: medium→Classic ×3` —— Flex 会话里你按的 `/effort` 落到了哪个档；
  - `◆ /effort locked by Value ×4 — for free /effort choice, use Flex` —— 钉档会话里 `/effort` 被覆盖了几次；
  - `◆ N request(s) bypassed Deeper — model '...' is not governed by tiers` —— 这些请求的模型名不在 `deepseek-v4*` 通道内，档位没参与；
  - `◆ No successful API calls this session` —— 本会话没有一次成功调用落账（见[故障排查](#故障排查)）。

回执上的金额是**按台账估算**，不是账单；以 DeepSeek 的实际账单为准。

---

## 会话里发生了什么

- **每会话私有中继**：临时端口起、退出即杀（按 PID 精确终止），多个会话互不干扰。中继绑 `127.0.0.1`，不弹防火墙授权框，外机连不上。
- **环境变量只进子进程**：`ANTHROPIC_BASE_URL` 只注入被包裹的那个进程，**绝不全局 export**（那会把你外层正在跑的 Claude Code 会话也劫持走）。
- **零密钥逻辑**：cct 与中继都不持钥。请求自带的 `x-api-key` / `authorization` **原样透传**，改写只发生在 effort 部分。密钥按你平常的方式提供即可。
- **台账**：`~/.cct/sessions/<时间>_p<端口>.jsonl`，每行只有记账字段（模型名、token 数、缓存、耗时、状态码）—— **没有对话内容，没有密钥**。中继自身日志在同目录的 `.relay.log`。
- **settings.json 钉回**：Claude Code 启动时会把 `settings.json` 的 `env` 块写回进程环境，可能顶掉 cct 注入的 `ANTHROPIC_BASE_URL`（症状：会话看起来一切正常，但流量绕过中继 —— 无档位、无台账、无计价）。cct 给 claude 会话追加 `--settings <本会话钉回文件>`，**只钉 `ANTHROPIC_BASE_URL` 这一个键**：你的 settings 文件磁盘零改动，`ANTHROPIC_AUTH_TOKEN` 等原样透传。钉回成功**全静默**；唯一发声点是"钉回失败且 settings 确在抢管"—— 那种情况必然绕过，会响亮告警。
- **不动你的配置**：cct 不写你的 `~/.claude/settings.json`，也不改 `~/.claude.json`。

---

## 边界与注意事项

- **标定只对 `api.deepseek.com` 成立。** 档位效力、每轮输出量、峰谷价表都是在官网上游上标定的。把 `DA_UPSTREAM` 指向第三方中转或自建网关时，cct **只提醒不降级**（档位照常施加），但结果与账单可能有出入 —— 要不要用由你判断。
- **凭据不要写在上游 URL 里。** `https://user:token@host/...` 这种写法虽然能连，但完整 URL 会出现在中继日志与 `/health` 响应里（都在本机 `~/.cct/sessions/` 下）。优先用请求头传凭据。
- **上下文窗口。** cct 不碰 Claude Code 的上下文设置。Claude Code 不认识 DeepSeek 的模型名，
  会按 200k 窗口假设并提前触发自动压缩。想开满窗口，DeepSeek 官方文档建议设
  `CLAUDE_CODE_AUTO_COMPACT_WINDOW=786432`（并用 `[1m]` 后缀的模型名）——见
  [官方 Claude Code 接入说明](https://api-docs.deepseek.com/zh-cn/quick_start/agent_integrations/claude_code)。需要就自己设，cct 有意把这个决定留给你。
- **预览期。** 版本号 `0.1.x`，启动横幅标 `technical preview`，部分档位标 `(beta)`；行为与档位表都可能变。
- **不承担账单。** 中继把请求转发给你自己配置、自己付费的第三方 API，计费以对方为准。
- **Windows 差异**：选择器无动画，降级为编号列表（无 termios），功能等价。
- **macOS**：TLS 用系统信任库。若用 python.org 官网安装包装的 Python，需要跑一次安装目录里的 `Install Certificates.command`，否则连上游会报 `CERTIFICATE_VERIFY_FAILED`（Homebrew / Command Line Tools 的 python3 无此问题）。

---

## 环境变量

**启动壳（`CCT_*`）**

| 变量 | 作用 |
|---|---|
| `CCT_PYTHON` | 指定 Python 解释器路径（默认按 python3 / python / `py -3` 探测） |
| `CCT_NO_PICKER` | 跳过选择器，直接用 `-e` 或默认档 |
| `CCT_TIERS` | 换一份档位表 json |
| `CCT_SESS_DIR` | 换会话台账目录（默认 `~/.cct/sessions`） |
| `CCT_NO_UPDATE_CHECK` / `CCT_REGISTRY` / `CCT_UPDATE_TAG` / `CCT_FORCE_ACK` | 更新检查开关 / 私有源 / 通道 / CI 逃生 |

**中继（`DA_*`）** —— cct 会话下 `DA_PORT` / `DA_TIER` / `DA_TIER_TABLE` / `DA_LEDGER` / `DA_BIND` 由 cct 自己设定；下面这些你可以在 shell 里预先设好，会被继承。

| 变量 | 作用 |
|---|---|
| `DA_UPSTREAM` | 上游地址（默认 `https://api.deepseek.com/anthropic`） |
| `DA_READ_TIMEOUT` | 上游读超时秒数（默认 3600） |
| `DA_LEDGER` | 台账文件路径（独立跑时默认 `~/.cct/usage_relay.jsonl`） |
| `DA_CAPTURE` | 逐请求逐响应留档目录；空 = 关闭（默认）。配套 `DA_CAPTURE_WHAT`（req/resp/both）、`DA_CAPTURE_MAX`（单文件字节上限）、`DA_CAPTURE_REDACT`（默认 1，落盘前抹密钥形态串） |
| `DA_PIN` / `DA_DENY` | 模型处理：默认都关 = 纯透传；`DA_PIN=<模型名>` 才改写，`DA_DENY=1` 遇到非 flash 直接 400 拒绝 |
| `DA_BIND` / `DA_PORT` | 独立跑中继时的绑定地址与端口 |
| `DA_EFFORT` / `DA_BASE_EFFORT` / `DA_PREAMBLE_FILE` | 单档模式的手动注入（与档位表模式互斥）；改动注入构造会偏离标定，不保证与官方档等价 |
| `DA_KEY_FILE` / `DA_KEY_ENC` | 旧模式：由中继代注入密钥（默认不启用，台账只记不可逆指纹） |

留档（`DA_CAPTURE`）默认关是有原因的：一次 agent 跑批能写出上万份 SSE 全文，单份可达 MB 级。它只在需要做泄漏审计时才该开。

---

## 故障排查

| 现象 | 处理 |
|---|---|
| **`✗ command not found: claude`** | cct 是 Claude Code 的外壳，不打包它。先装：`npm install -g @anthropic-ai/claude-code`（或 `curl -fsSL https://claude.ai/install.sh \| bash`），再用 `claude --version` 确认 |
| **`Not logged in · Please run /login`** | **别跑 `/login`** —— 那是登录 Anthropic 账号，另一家服务。这条提示的真实含义是没有密钥到达 API：`export ANTHROPIC_AUTH_TOKEN=sk-你的DeepSeek密钥`（或写进 `~/.claude/settings.json` 的 `env` 块）后重开 |
| 提示找不到 Python | Windows 从官网装并勾 Add to PATH；macOS `xcode-select --install`；Linux 用包管理器。或用 `CCT_PYTHON` 指定路径 |
| `✗ relay failed to start` | 看 `~/.cct/sessions/<时间>_p<端口>.relay.log` 的尾部，真实原因在那里 |
| 会话正常，但回执说 `No successful API calls` | 多半是流量绕过了中继：检查 `~/.claude/settings.json` 与项目 `.claude/settings.json` / `settings.local.json` 的 `env` 里有没有 `ANTHROPIC_BASE_URL` |
| 回执出现 `bypassed <档名> — model ... is not governed by tiers` | 这些请求的模型名不是 `deepseek-v4*`（常见于外部工具改写了 `ANTHROPIC_MODEL`），它们被原样转发，档位没参与 |
| 钉档会话里 `/effort` 没反应 | 设计如此：钉档会话由中继统一施加一个档。想逐请求决定深度，请用 Flex |
| `CERTIFICATE_VERIFY_FAILED`（macOS） | 跑一次 Python 安装目录里的 `Install Certificates.command` |
| 本机全局代理导致请求失败 | cct 已为子进程加 `NO_PROXY=127.0.0.1,localhost`，并从中继环境剥掉代理变量；若你的代理工具用别的机制拦截本地流量，需要你自己放行 `127.0.0.1` |
| `cct` 命令指向了别的东西 | 旧包名残留：`npm uninstall -g cct` 后重装 |

---

## 路线图

| Agent CLI | 状态 |
|---|---|
| **Claude Code** | ✅ 已支持 —— 档位、台账、回执、settings 钉回，全部端到端验证过 |
| **Codex** | 🔬 内测中 |
| **DSH** | 🔬 内测中 |
| **OpenCode** | 🔬 内测中 |
| 其他常见 agent CLI | 🚧 评估中 |

中继说的是 Anthropic 消息格式，所以任何讲这个格式的客户端**现在就能手工接上**（见[独立跑中继](#独立跑中继进阶)）。每个新 agent 要补的是**启动壳那一半**：找到它的可执行文件、在不打扰用户自身配置的前提下注入本会话端点、读懂它对应的"思考等级"设置。这部分是逐个 agent 的活，所以只能一个一个来。

| 模型 | 状态 |
|---|---|
| **DeepSeek 系列**（`deepseek-v4-flash` / `deepseek-v4-pro`） | ✅ 已支持 —— 档位在 flash 上标定，价表按官方峰谷分时计价 |
| **GLM** | 🚧 计划中 |
| **Kimi** | 🚧 计划中 |
| 其他模型 | 🚧 评估中 |

---

## 常见问题

**cct 会看到我的对话内容或密钥吗？**
不会。中继把你客户端本来就带的 `x-api-key` / `authorization` 头原样转发，cct 自己从不存密钥。`~/.cct/sessions/` 下的台账只有记账字段 —— token 数、缓存命中、耗时、状态码 —— 从不含对话内容。中继**会**改写的只有请求体里与思考深度相关的部分，别的一概不动。

**回执上的金额就是我的账单吗？**
不是，那是按台账和 `tiers.json` 里的价表算出来的**估算**，以 DeepSeek 的实际账单为准。省钱百分比同样是估算：它拿你的实际消耗，去比"同样的活全程跑官方 max 思考等级"会花多少，用的是标定的每轮输出量。

**能不能接第三方网关，而不是直连 DeepSeek？**
可以，把 `DA_UPSTREAM` 指过去即可。cct 会提醒一次"标定只对 `api.deepseek.com` 成立"，然后照常施加档位。凭据请走请求头而不是 URL：`https://user:token@host/...` 这种上游能连，但完整 URL 会出现在本机的中继日志里。

**会和 CC Switch 之类的 Claude Code 管理工具冲突吗？**
不会。那类工具是通过写 `~/.claude/settings.json` 的 `env` 块来配置 Claude Code 的；cct 用优先级更高的 CLI 参数，把本会话的 `ANTHROPIC_BASE_URL` 钉回自己的中继，**不改你的文件**。会话中途切换供应商、项目级 settings、`settings.local.json` 三种情况都实测过，都夺不走流量。

**为什么 `/effort` 没反应？**
因为你在钉档会话里（Value / Classic / Extra / Deeper），它的意义就是"一个档管住每一个请求"。想逐请求控制就用 **Flex** —— 那里 `/effort` 完全可用，cct 还会顺手清掉会锁死菜单的遗留 `CLAUDE_CODE_EFFORT_LEVEL`。

**回执说有些请求绕过了我的档，为什么？**
档位只管辖 `deepseek-v4*` 这类模型名，其余一律原样转发。如果某个工具把 `ANTHROPIC_MODEL` 改成了 `claude-sonnet-4-5` 之类，这些请求照样能跑（DeepSeek 会映射这个名字），但档位不参与。把模型名改回 `deepseek-v4-flash` 就能重新纳入管辖。

**我能跑测试套件吗？**
可以，但先读 `tests/README.md`：其中一部分会打**真实的、计费的 API 调用**，并且会临时改写 `~/.claude/settings.json`（退出时还原，Ctrl-C 也会）。mock 上游与纯离线的那些测试不花钱。

---

## 独立跑中继（进阶）

不经启动壳，从别的客户端或容器里用：

```bash
DA_PORT=8301 python3 relay_anthropic.py

# 客户端指过来（只传给子进程，绝不全局 export！）
ANTHROPIC_BASE_URL=http://127.0.0.1:8301 ANTHROPIC_MODEL=deepseek-v4-flash \
  ANTHROPIC_API_KEY=<你的DeepSeek密钥> claude -p "..."
```

这种模式下没有档位表，默认是纯透传 + 观测，认证同样透传。`/health` 会如实报告这个进程开启了哪些改写。

⚠ 独立模式下 `DA_BIND` 默认是 `0.0.0.0`（为容器场景保留）。在共享机器上请显式设 `DA_BIND=127.0.0.1`，否则同网段的任何人都能连到你的中继，并从 `/health` 读到上游地址。

---

## 文件

| 文件 | 作用 |
|---|---|
| `cct.js` / `cct.py` | npm bin 跨平台跳板（只负责找 Python）/ 启动壳的唯一实现，三平台同一条代码路径 |
| `cct` | 仓库内直跑 `./cct` 用的薄壳 |
| `picker.py` | 启动时的档位选择器（非 TTY / 窄终端 / Windows 下自动降级） |
| `relay_anthropic.py` | Anthropic 格式透明改写中继：chunked 请求体 + SSE 流式透传 + 从流尾抠 usage |
| `keystore.py` | 可选的密钥加密留存（PBKDF2 + Fernet）；台账里只出现不可逆指纹 |
| `tiers.json` | 档位表：档位定义、`/effort` 映射、标定值、价表 |
| `preambles/` | 各档的前导文本 |
| `tests/` | 验收脚本，见 [tests/README.md](tests/README.md)。⚠ 其中部分会消耗真实 API 额度、需要可用的 claude CLI，并会临时改写本机的 Claude Code 配置 —— 跑之前先读脚本顶部的警示，最好只在一次性容器里跑 |

---

## 交流群

<div align="center">

<img src="assets/wechat_group.jpg" width="250" alt="cct 用户交流群微信二维码">

<sub>微信扫码进 <b>cct 用户交流群</b></sub>

</div>

微信群码七天一换 —— 当前这张 **2026-08-25 前有效**。过期了发邮件到 <hello@seedsky.ai>，我们贴新的。

---

## 许可

见 [LICENSE](LICENSE)。

---

<div align="center">

<sub>由 <a href="https://seedsky.ai"><b>SeedSky</b></a> 打造 · <a href="https://seedsky.ai">seedsky.ai</a> · <i>Seek within. Evolve beyond.</i></sub>

</div>
