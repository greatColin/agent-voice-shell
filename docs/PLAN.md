# Agent Voice Shell — 开发计划

> **本文档只描述"怎么做、节点、每个节点如何验收"。** 需求放在 [`REQUIREMENTS.md`](REQUIREMENTS.md)。
> 任何修改先确认它不破坏 `REQUIREMENTS.md` 的不变量。

---

## 0. Document Control

| 项 | 值 |
| --- | --- |
| 项目名 | `agent-voice-shell` |
| 版本 | v1.0 |
| 关联需求文档 | [`REQUIREMENTS.md`](REQUIREMENTS.md) |
| 主语言 | Python 3.10+ |
| 当前优先级 | **V1** 优先；V2-V4 概要 |

---

## 1. 技术栈决策

### 1.1 主语言

**Python**。理由：

- voice pipeline 主流实现（ASR / VAD / TTS / Audio）全是 Python 包
- Pi 有 `pi-py-sdk` 同语言接入
- FastAPI + WebSocket 生态成熟
- 满足 `REQUIREMENTS.md` 第 4.2 节的"少语言原则"

### 1.2 模块选型

| 模块 | 选型 | 备注 |
| --- | --- | --- |
| 后端 | FastAPI + uvicorn | WebSocket 一等公民 |
| 前端 | 单 HTML + 原生 JS | 无构建链；served by FastAPI |
| WebSocket | FastAPI native | 不需要 Socket.IO |
| Agent Adapter | `pi-py-sdk`（`PiAgent`） | 内部走 `pi --mode rpc` |
| LLM 配置 | Pi 全局配置 | voice 代码零感知 |
| 日志 | Python `logging` | 写文件 + stdout |
| 依赖管理 | `requirements.txt` 钉版本 | |

### 1.3 Pi 接入细节

用 `pi-py-sdk` 的 `PiAgent` 客户端。需要 Pi CLI binary 在 PATH：

```bash
# 安装 Pi（一次性）
npm i -g @earendil-works/pi-coding-agent
pi --help  # 验证
```

如果 `pi-py-sdk` 版本滞后/出问题，fallback 是直接用 `pi --mode rpc` + 自写 JSONL 客户端（`AgentClient` 抽象层保证切换无成本）。

---

## 2. 架构设计

### 2.1 顶层图

```
   ┌────── Browser (单 HTML) ─────────────────┐
   │   输入框 │ 文本流区域 │ 开始按钮             │
   └──────────────┬────────────────────────────┘
                  │ WebSocket
   ┌──────────────▼────────────────────────────┐
   │           FastAPI Backend (Python)         │
   │                                            │
   │   ┌─ state machine ────────────────────┐   │
   │   │ IDLE ⇄ GENERATING ⇄ INTERRUPTING  │   │
   │   └────────────────┬───────────────────┘   │
   │                    ↓                        │
   │   ┌─ Interruption Handler (V1-V4 共用) ─┐   │
   │   │ 三步取消 + 切换 trigger 类型        │   │
   │   └────────────────┬───────────────────┘   │
   │                    ↓                        │
   │   session → agent adapter (Pi) → router    │
   └──────────────┬────────────────────────────┘
                  │ pi-py-sdk
                  ▼
             [Pi (Node, LLM 配置归 Pi)]
```

### 2.2 借鉴依据：全双工 LLM 业界做法

| 流派 | 代表 | 我们的选择 |
| --- | --- | --- |
| Pipeline + 主动 cancel | GPT-4o Realtime | ✅ V1 选这条 |
| 端到端自学习 | Moshi / Seeduplex | ❌ V1 不选（要重新训模型） |

### 2.3 关键设计原则

#### 2.3.1 三步取消（来自 GPT-4o Realtime）

每次 interruption **必须**完整执行三步：

1. **停 LLM 生成**：`agent.cancel()`
2. **停 output**：`state.flush_output()`
3. **回滚 state**：`session.discard_assistant_partial()`（V1 简化版）

#### 2.3.2 Interruption Handler 单一实现（V1-V4 共用）

V1 的"用户输入"等价 V2/V3 的"VAD 触发"——handler 内部逻辑稳定，仅 trigger 类型变化。

#### 2.3.3 V1 简化策略：discard partial

`discard_assistant_partial()` 直接丢弃 partial。`truncate`（保留已播放部分）留作 V1.x 增强项，不影响 V1 落地。

#### 2.3.4 Agent 抽象（Adapter）

```python
class AgentClient(ABC):
    async def stream(self, messages: list[dict]) -> AsyncIterator[VoiceEvent]: ...
    async def cancel(self) -> None: ...
    async def __aenter__(self): ...
    async def __aexit__(self, *a): ...
```

V1 实例：`PiAdapter`。切换 agent 不重写 voice。

---

## 3. 接口契约

### 3.1 WebSocket 协议

**浏览器 → 服务端**：

```json
{ "type": "start" }
{ "type": "user_input", "text": "..." }
{ "type": "interrupt" }
```

**服务端 → 浏览器**：

```json
{ "type": "assistant_text_delta", "delta": "..." }
{ "type": "tool_call",         "name": "...", "args": {...} }
{ "type": "tool_result",       "name": "...", "result": "..." }
{ "type": "generation_complete" }
{ "type": "error",             "message": "..." }
```

**为什么 thinking 不入 ws**：按 `REQUIREMENTS.md` 第 3.1，thinking 仅入日志，不应展示给用户。

### 3.2 VoiceEvent 归一化

```python
@dataclass
class TextChunk:        delta: str
@dataclass
class ThinkingChunk:    delta: str
@dataclass
class ToolCall:         name: str; args: dict
@dataclass
class ToolResult:       name: str; result: str
@dataclass
class Complete:         final_text: str
```

`PiAdapter` 把 Pi 内部事件翻译成这 5 类。

---

## 4. 文件结构（最终态）

```
agent-voice-shell/
├── README.md
├── docs/
│   ├── REQUIREMENTS.md          # 需求（要什么）
│   └── PLAN.md                  # 本文（怎么做）
├── requirements.txt             # 钉死版本
├── pyproject.toml (optional)
├── .gitignore
├── app/
│   ├── __init__.py
│   ├── main.py                  # FastAPI 入口
│   ├── cli.py                   # CLI 自测口
│   ├── events/
│   │   ├── events.py            # VoiceEvent 数据类
│   │   └── router.py            # event_type → callback
│   ├── session/
│   │   └── session.py           # Session
│   ├── agent/
│   │   ├── base.py              # AgentClient 抽象
│   │   └── pi_adapter.py        # Pi 实现
│   ├── controller/
│   │   ├── state_machine.py
│   │   └── interruption.py      # V1-V4 共用
│   └── web/
│       ├── protocol.py          # ws 消息类型
│       ├── ws_endpoint.py       # FastAPI ws handler
│       └── static/
│           └── index.html       # 单 HTML 前端
├── tests/
│   ├── unit/
│   ├── integration/
│   └── fixtures/
└── scripts/
    ├── start.sh
    └── check_pi.sh              # 验证 Pi CLI 在 PATH
```

---

## 5. 节点计划

**推进原则**：每个节点**必须先通过验收，再进下一个**。自测清单见第 7 节。

### 5.1 V1 详细（11 节点）

#### 节点 1.1 — 项目骨架 + 依赖

**任务**：

- 按第 4 节创建目录
- 写 `requirements.txt`（钉版本）
- 写 `.gitignore`（标准 Python）
- 占位 `app/__init__.py`、`tests/__init__.py`、`app/main.py`（空 FastAPI app）

**关键版本基线**（具体号码用 `pip index versions` 查后钉死）：

- `fastapi`, `uvicorn[standard]`, `websockets`
- `pi-py-sdk`（具体版本查 PyPI）
- `pytest`, `pytest-asyncio`

**验收**：

- [ ] `pip install -r requirements.txt` 一次成功
- [ ] `python -c "from app.main import app"` 不报错（占位 main 返回空 app）
- [ ] `tree -L 3` 输出符合第 4 节"文件结构"

**核心**：all-in-one 单仓落地。

---

#### 节点 1.2 — VoiceEvent 数据类

**任务**：5 类 dataclass + 类型判定方法。

**输出**：`app/events/events.py`, `tests/unit/test_events.py`

**验收**：

- [ ] 5 类 dataclass 可创建、可序列化（`dataclasses.asdict`）
- [ ] 单测：equal、hash、`type` 字段
- [ ] 与 `REQUIREMENTS.md` 第 4.2 节"5 类事件"约束一致

**核心**：

```python
@dataclass
class TextChunk:        type: str = "text";        delta: str = ""
@dataclass
class ThinkingChunk:    type: str = "thinking";    delta: str = ""
@dataclass
class ToolCall:         type: str = "tool_call";   name: str = ""; args: dict = field(default_factory=dict)
@dataclass
class ToolResult:       type: str = "tool_result"; name: str = ""; result: str = ""
@dataclass
class Complete:         type: str = "complete";    final_text: str = ""
```

---

#### 节点 1.3 — Session（消息栈）

**任务**：消息栈 + partial buffer。

**输出**：`app/session/session.py`, `tests/unit/test_session.py`

**验收**：

- [ ] `add_user_turn(text)` → `messages` 追加 user
- [ ] `append_assistant_partial(chunk)` → partial 累加
- [ ] `finalize_assistant()` → messages 追加完整 assistant、partial 清空
- [ ] `discard_assistant_partial()` → partial 直接清空
- [ ] `get_messages()` → 返回 `messages + 当前 partial`（partial 非空时）
- [ ] 单测覆盖 5 个方法

**核心**：

```python
class Session:
    def __init__(self):
        self.messages: list[dict] = []
        self.assistant_partial: str = ""

    def add_user_turn(self, text: str) -> None: ...
    def append_assistant_partial(self, chunk: str) -> None: ...
    def finalize_assistant(self) -> None: ...
    def discard_assistant_partial(self) -> None: ...
    def get_messages(self) -> list[dict]: ...
```

---

#### 节点 1.4 — Event Router

**任务**：5 类 event 按 type 路由到 callback 字典。

**输出**：`app/events/router.py`, `tests/unit/test_router.py`

**验收**：

- [ ] 注册 callback：`on_text(cb)`, `on_thinking(cb)`, `on_tool_call(cb)`, `on_tool_result(cb)`, `on_complete(cb)`
- [ ] `dispatch(event)` 路由到正确 callback
- [ ] 单测覆盖每种 type 路由一次

**核心**：

```python
class EventRouter:
    def __init__(self):
        self._callbacks: dict[type, Callable] = {}

    def on(self, event_cls, cb): ...
    async def dispatch(self, event): ...
```

---

#### 节点 1.5 — Agent 抽象 + Pi Adapter

**任务**：定义 `AgentClient` 接口 + 实现 `PiAdapter`。

**输出**：`app/agent/base.py`, `app/agent/pi_adapter.py`

**验收**：

- [ ] `AgentClient` 4 方法签名清晰：`stream / cancel / __aenter__`
- [ ] `PiAdapter` 用 `pi-py-sdk.PiAgent` 跑通 hello
- [ ] `python -m app.cli` 能输出第一句 hello
- [ ] 单测：mock fake `AgentClient`，验证 `EventRouter` 收到正确事件
- [ ] **不出现** LLM 模型名 / Provider 地址在 voice 代码中

**核心**：

```python
class AgentClient(ABC):
    @abstractmethod
    async def stream(self, messages): ...

    @abstractmethod
    async def cancel(self): ...


class PiAdapter(AgentClient):
    def __init__(self):
        self._agent = PiAgent(...)  # 实际 API 按 pi-py-sdk

    async def stream(self, messages):
        async for raw in self._agent.stream(messages):
            yield self._translate(raw)  # Pi 内部事件 → VoiceEvent
```

---

#### 节点 1.6 — Interruption Handler

**任务**：实现"三步取消"统一函数。

**输出**：`app/controller/interruption.py`, `tests/unit/test_interruption.py`

**验收**：

- [ ] `handle(trigger, payload, agent, session, state)` 三步全执行
- [ ] 单测：mock agent 和 session，验证调用顺序
  - ① `agent.cancel()`
  - ② `state.flush_output()`
  - ③ `session.discard_assistant_partial()`
  - ④ `session.add_user_turn(payload["text"])`
  - ⑤ `state.restart_generation()`
- [ ] 单测：trigger 类型分支正确（V1 仅 `"user_input"`）

**核心**：

```python
async def handle(trigger, payload, agent, session, state):
    await agent.cancel()                  # 1) 停 LLM
    await state.flush_output()            # 2) 停 output
    session.discard_assistant_partial()   # 3) 回滚
    if trigger == "user_input":
        session.add_user_turn(payload["text"])
        await state.restart_generation()
```

---

#### 节点 1.7 — State Machine

**任务**：实现状态机。

**输出**：`app/controller/state_machine.py`, `tests/unit/test_state_machine.py`

**验收**：

- [ ] `IDLE → GENERATING → INTERRUPTING → GENERATING` 转换合法
- [ ] 非法转换被拒绝（抛异常或日志告警）
- [ ] `flush_output()` 与 `restart_generation()` 方法实现
- [ ] 单测覆盖所有合法/非法转换

**核心**：

```python
class State(Enum):
    IDLE = "idle"
    GENERATING = "generating"
    INTERRUPTING = "interrupting"


class StateMachine:
    def __init__(self):
        self.state = State.IDLE
        self._event = asyncio.Event()

    async def on_input_received(self): ...   # IDLE→GENERATING 或 GENERATING→INTERRUPTING
    async def on_generation_complete(self): ...
    async def flush_output(self): ...
    async def restart_generation(self): ...
```

---

#### 节点 1.8 — WebSocket 端点

**任务**：FastAPI + WebSocket + 协议消息定义。

**输出**：`app/web/protocol.py`, `app/web/ws_endpoint.py`

**验收**：

- [ ] 浏览器连上（用 `websocat` 或简单 Python client）能收到 first hello
- [ ] 浏览器发 `user_input` 触发 interruption handler
- [ ] 浏览器发 `interrupt` 取消当前 generation
- [ ] server → client 消息覆盖：`assistant_text_delta / tool_call / tool_result / generation_complete / error`
- [ ] **不**发送 `thinking` 到 ws（按 `REQUIREMENTS.md` 第 3.1）

**核心**：

```python
@app.websocket("/ws")
async def ws_endpoint(websocket):
    session = Session()
    agent = PiAdapter()
    state = StateMachine()
    handler = InterruptionHandler()
    router = EventRouter()
    # 启动时 dispatch hello
    while True:
        msg = await websocket.receive_json()
        if msg["type"] == "start": ...
        elif msg["type"] == "user_input":
            await handler.handle("user_input", msg, agent, session, state)
        elif msg["type"] == "interrupt":
            await handler.handle("interrupt", msg, agent, session, state)
```

---

#### 节点 1.9 — 单 HTML 前端

**任务**：最小可用 UI。

**输出**：`app/web/static/index.html`

**验收**：

- [ ] 浏览器打开 `http://localhost:8000` 看到 hello
- [ ] 输入框输入 + Enter 触发 `user_input`
- [ ] 文本流区域滚动显示 agent 输出
- [ ] **移动端 viewport 自适应**（`meta viewport` 标签 + CSS）
- [ ] **不**展示 `thinking` / `tool_call` 给用户（按需求）

**核心结构**：

```html
<div id="app">
  <button id="start">开始</button>
  <div id="stream"></div>
  <input id="input" placeholder="输入回车提交">
</div>
<script>
const ws = new WebSocket("ws://" + location.host + "/ws");
ws.onmessage = (e) => {
  const msg = JSON.parse(e.data);
  if (msg.type === "assistant_text_delta") append(msg.delta);
  // 忽略其他 type（按需求 3.1）
};
document.getElementById("input").addEventListener("keydown", (e) => {
  if (e.key === "Enter") ws.send(JSON.stringify({type: "user_input", text: e.target.value}));
});
</script>
```

---

#### 节点 1.10 — CLI 自测口

**任务**：不依赖浏览器的端到端 CLI 模式。

**输出**：`app/cli.py`

**验收**：

- [ ] `python -m app.cli` 启动
- [ ] 终端输入文本，stdout 看 agent 流式输出
- [ ] Ctrl+C 退出
- [ ] **不走** ws、**不走** interruption handler（单 turn 模式即可）

**核心**：argparse + `Session` + `PiAdapter` 直连。

---

#### 节点 1.11 — 集成 + 文档

**任务**：端到端集成测试 + 完善 README。

**输出**：`tests/integration/test_v1_e2e.py`, `README.md`

**验收**：

- [ ] 集成测试覆盖：CLI hello、ws hello、ws `user_input` 触发 interruption
- [ ] `pytest tests/` 全通过
- [ ] 新 clone 仓 5 分钟内能起来（按 README）
- [ ] README 含：Quick Start、Architecture、Status、Development 章节（参见 `README.md`）

**核心**：把 11 个节点拼成可发布版本。

---

### 5.2 V2 概要

| 节点 | 任务 | 验收 |
| --- | --- | --- |
| 2.1 | ASR 模块（sherpa-onnx + Paraformer-zh） | 给定 wav 转写正确 |
| 2.2 | 浏览器录音（MediaRecorder） | 推流到后端 |
| 2.3 | 流式 ASR → InterruptionHandler | trigger 改 `"vad"`，**handler 内部零改动** |
| 2.4 | 文字 + 语音多模态 | UI 切换按钮 |

### 5.3 V3 概要

| 节点 | 任务 | 验收 |
| --- | --- | --- |
| 3.1 | TTS 引擎封装（Edge TTS 首选 / 系统 API 兜底） | text → audio |
| 3.2 | 浏览器发声（`MediaTrackConstraints` 设 `echoCancellation`） | 用户听到 AI 说话 |
| 3.3 | **回声协调**（VAD → TTS mute → unmute） | 用户说话时 TTS 必停 |
| 3.4 | State Machine 加 `SPEAKING / MUTED` | 状态转换覆盖 |

### 5.4 V4 概要

| 节点 | 任务 | 验收 |
| --- | --- | --- |
| 4.1 | 状态看板 | thinking / tool_call / tool_result 可视化 |
| 4.2 | 数字人形象模块 | 与本项目解耦，复用 V3 voice 后端 |

---

## 6. 风险 & 依赖

| 风险 | 触发条件 | 应对 |
| --- | --- | --- |
| `pi-py-sdk` 与 Pi 主仓版本滞后 | 接口变更 | fallback = `pi --mode rpc` + 自写 JSONL client（`AgentClient` 抽象保证） |
| Pi CLI 不在 PATH | 启动失败 | README 明确安装步骤；`scripts/check_pi.sh` 检测 |
| 上下文累积超限 | 长会话触发 KV 抖动 | V1 不做；V2 加 `Session.compact()` 摘要旧消息 |
| WebSocket 跨域 | 浏览器连接拒绝 | FastAPI 配置 CORSMiddleware；V1 同源起步 |
| thinking 一时手滑进了 ws 流 | ws 消息类型混了 | 节点 1.8 单测覆盖；lint/类型检查 |

---

## 7. 关键工程原则（开发自检清单）

每次完成一个节点时自查：

- [ ] 没破坏 `REQUIREMENTS.md` 第 4.2 节的不变量
- [ ] VoiceEvent 仍为 5 类（没新增）
- [ ] interruption handler 仍是单一实现（没复制）
- [ ] `AgentClient` 抽象还在（没硬编 Pi API）
- [ ] LLM 配置没进 voice 代码
- [ ] 单测覆盖核心方法
- [ ] **CLI 模式还能跑**（不打 ws 也能验证核心）

---

## 8. 变更记录

| 日期 | 版本 | 变更 |
| --- | --- | --- |
| 2026-08-XX | v1.0 | 锁定基线，与 `REQUIREMENTS.md` 配套 |
| 2026-08-XX | v0.1 技术方案 | 初稿（已并入本文档） |
