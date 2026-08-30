# Agent Voice Shell

> Pseudo-full-duplex text/voice shell that wraps any agent CLI.

A Python shell that gives any agent CLI a **pseudo-full-duplex** interface. Inspired by GPT-4o Realtime style interruption handling (3-step cancel + truncate), Moshi dual-stream semantics, and Doubao Seeduplex full-duplex UX. The voice pipeline is **agent-agnostic** by design — v1 wires up [Pi](https://github.com/earendil-works/pi), but the adapter pattern keeps the door open for OpenCode, Hermes, or any future runtime.

---

## Status

| Version | Description                                | Status          |
| ------- | ------------------------------------------ | --------------- |
| V1      | Text-only pseudo-full-duplex over WebSocket | ✅ implemented  |
| V2      | + 语音输入 (browser → ASR → LLM)            | 🚧 in design   |
| V3      | + TTS + 回声协调                             | 🚧 in design   |
| V4      | + 数字人 + 状态看板                          | 🚧 planned      |

---

## What It Is

Agent Voice Shell sits between **a user (in a browser)** and **an agent CLI (Pi for v1)**. It:

- Streams agent output to a web UI over WebSocket
- Lets the user interrupt at any time — input becomes "barge-in"
- Hides the specific agent runtime behind an `AgentClient` adapter
- Uses a single session message stack; one session, many turns
- Provides a CLI mode for development without a browser

The full design and acceptance criteria are pinned in [`docs/REQUIREMENTS.md`](docs/REQUIREMENTS.md) (what) and [`docs/PLAN.md`](docs/PLAN.md) (how).

---

## Quick Start

```bash
# 1. Install
pip install -r requirements.txt

# 2. CLI self-test (no browser needed)
python -m app.cli

# 3. Or start the web server
python -m app.main
# then open http://localhost:8000
```

Requires Python 3.10+.

---

## Architecture (V1)

```
   ┌────────── Browser (single HTML) ──────────┐
   │   [Input] [Start] [Interrupt] [Streaming] │
   └──────────────┬────────────────────────────┘
                   │ WebSocket
   ┌──────────────▼────────────────────────────┐
   │          FastAPI backend (Python)         │
   │                                            │
   │   state machine (IDLE ⇄ GENERATING)      │
   │        ↓                                   │
   │   interruption handler  (V1–V4 共用)      │
   │        ↓                                   │
   │   session manager → event router          │
   │        ↓                                   │
   │   agent adapter (BigModel GLM-4-Flash)    │
   └──────────────┬────────────────────────────┘
                   │ HTTP stream (OpenAI compatible)
                   ▼
              [BigModel API — GLM-4-Flash]
```

---

## How Pseudo-Full-Duplex Works

Unlike true full-duplex (which requires server-side cancellation support), this implementation achieves interruptible output through client-side flow control:

**Mechanism:**
1. User sends interrupt → sets `cancel_requested = True`
2. Next stream iteration detects flag → breaks (stops receiving)
3. New request starts fresh → discarded partial output not included in next context

**Trade-offs:**
| | Pseudo-Full-Duplex | True Full-Duplex |
|---|---|---|
| User can interrupt immediately | ✅ | ✅ |
| Real-time streaming output | ✅ | ✅ |
| Next round continues normally | ✅ | ✅ |
| Server resource efficiency | Slight waste | ✅ Optimal |
| Implementation complexity | Low | High (requires server support) |

**Result:** User experience is nearly identical to true full-duplex, with minimal server-side overhead. Works with any LLM provider via OpenAI-compatible API.

---

## Development

For full node-by-node development tasks and acceptance criteria, see [`docs/PLAN.md`](docs/PLAN.md) §5.

| Command                          | What it does                       |
| -------------------------------- | ---------------------------------- |
| `pip install -r requirements.txt` | install deps                       |
| `python -m app.cli`              | CLI self-test (no browser)         |
| `python -m app.main`             | start FastAPI server               |
| `pytest tests/`                  | run unit + integration tests       |

---

## Why This Project Exists

Most agent CLIs are turn-based: ask, wait, answer. Real conversation is **half-duplex**, with awkward pauses. Full-duplex voice agents (GPT-4o Realtime, Moshi, Doubao Seeduplex) have shown how natural it feels — but they are large systems, locked to specific runtimes, and not open in the way that lets you own your stack.

Agent Voice Shell is a pragmatic middle ground: **pseudo-full-duplex** built on top of open CLIs, with an adapter layer that doesn't tie you to one vendor.

---

## License

MIT
