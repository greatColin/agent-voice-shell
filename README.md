# Agent Voice Shell

伪全双工语音交互 Agent 引擎——打断是一等公民。

> 本仓库 `master` 分支是重构后的新架构（引擎骨架见下文）；
> 旧版本代码保留在 `legacy-main` 分支，仅作历史参考，不再维护。


伪全双工语音交互 Agent 引擎骨架。核心特点：**打断是一等公民**。上一个流程（思考中/输出中）未结束时，新的触发会打断当前流程，并按"现场快照"生成一段提示词前提，连同本轮输入一起交给 Agent。

> 作者 colin.cheng.ai · Python 3.9+（经 conda base 实测）· 纯标准库，无第三方依赖
> · 两线程运行时：主线程=触发，后台线程=管线
> · Agent 可接 pi CLI（真流式 LLM，多轮记忆）

---

## 1. 管线与边界

```
触发(主线程，实现自定义)          管线线程(PipelineEngine 的 asyncio loop)
──► engine.submit(text) ──► 矫正 ──► Agent 思考 ──► 输出队列消费 ──► 输出通道
       (线程安全)              └──── 打断：取消思考/静音通道/队列作废 ────┘
```

- **主线程留给触发源**：终端阻塞循环、Tk mainloop、HTTP 服务、MQ 消费……
  只要能调到 `engine.submit(text)`，环形、线程、进程都不限。
- **后台线程**承载矫正之后的一切：SessionManager 状态机、队列消费、
  组件 initialize/shutdown（由 engine 启动时统一调用）。
- `engine.submit()` 从任何线程调用均安全（call_soon_threadsafe 中转）。

各阶段均为抽象接口（可多实现），层间只传字符串：

| 层 | 抽象 | 职责 | 实现 |
|---|---|---|---|
| 触发 | `TriggerSource` | 各类唤醒方式统一收敛为 `TriggerEvent(text)` | `StdinTrigger`（终端回车提交，含 /exit 命令） |
| 识别 | （并入触发层，后续可拆） | 提供原始文字 | 手动文本 / 真实 ASR |
| 矫正 | `TextCorrector` | 字符串→字符串 | `IdentityCorrector`（直通） |
| Agent | `Agent` | `think_stream(user_text, interrupt_premise) -> AsyncIterator[str]` | `MockAgent`（慢速模拟，测试用） / `PiAgent`（pi CLI 真 LLM） |
| 输出 | `OutputChannel` | 逐字符 `write(char)`，速度即播放速度；`stop()` 立即静音 | `PrinterChannel`（终端，char_delay 模拟语速） / `GuiPrinterChannel`（Tk 窗口，默认即收即显） |

## 2. 职责边界（关键设计决定）

- **框架只负责**：单实例状态机、打断现场快照与渲染、流式产出的队列化与消费进度记账、状态事件广播。
- **Agent 全权负责**：对话历史、思考阶段（含内部展示）、行为模式（要不要先说"好，你说"）、如何利用打断前提——框架不传 history。
- **思考不出 Agent**：思考阶段在 Agent 内部消化（内部维护/展示），不 yield、不经输出通道。契约信号：**首个 yield = 正文开始**，框架据此切 THINKING→SPEAKING；思考中被打断时现场只描述"思考时被打断"，无输出位置。
- 打断现场 = **精确坐标**（第几句/句内第几字/总字数）+ **尾部锚点**（被打断处最后 ≤20 字，防重复词句歧义）。不复述整段——Agent 的历史里本来就有。流式下"全段总长"不可知，现场只报已消费量。
- 框架对 Agent 的唯一契约：两入参（本轮文本 + 上次打断的提示词前提）+ 流式正文产出。

## 3. 打断语义

新触发到达时：

1. 若正在 THINKING/CORRECTING → 取消生成任务（CORRECTING 时可能无任务，代际复核后直接作废本轮）
2. 若正在 SPEAKING → 调用 `channel.stop()`，未消费队列整体作废
3. 以 `PositionTracker` 记录的**已消费位置**为准快照现场
4. 现场渲染成前提（`InterruptContext.render()`），下一轮与用户输入一起传给 Agent
5. 立刻进入下一轮（generation 代际计数 + 队列局部绑定，保证旧轮收尾/POISON 不污染新轮）

进度以 `write()` 真正完成（await 返回）为准，而非入队时间——保证"用户耳朵听到的位置"。生成快于播放时（队列积压），打断位置只算已消费部分（`tests/test_gui_backlog.py` 验证）。

## 4. 配置驱动

装配由根目录 `config.json` 决定，每个抽象层一个 `impl`（注册表中的名字）+ 自定义 `params`（作为构造参数展开）：

```json
{
  "trigger":   {"impl": "stdin",    "params": {"prompt": ">>> "}},
  "corrector": {"impl": "identity", "params": {}},
  "agent":     {"impl": "pi",       "params": {"show_prompt": false}},
  "output":    {"impl": "gui",      "params": {"title": "Voice Agent 输出"}},
  "session":   {"params": {"verbose": true}}
}
```

换形态零代码：`agent` 换 `mock`/`pi`，`output` 换 `printer`/`gui`，直接改配置。新增实现：在对应包里加类，并在该包 `__init__.py` 的 `*_IMPLS` 注册表登记（`trigger`/`corrector`/`agent`/`output` 四个注册表见 `voice_agent/config.py: REGISTRIES`）。

## 5. 快速运行

```bash
conda activate base                 # Python >= 3.9（已装 pi CLI 则 agent 用 pi）

python main.py                      # 产品入口，默认读 ./config.json
python main.py config.pi.json      # 指定配置（终端输出版）
python tests/test_exit_cmd.py      # 全套件见 tests/
```

产品入口交互：输入文字回车触发一轮；输出中再次输入即打断；`/exit`（或 `/quit`）优雅退出（排干在途会话 → 组件 shutdown），空行/Ctrl+C 同效。打断现场提示词由 Agent 展示（`show_prompt: true` 时打印收到的完整 prompt）。

## 6. 目录结构

```
voice-agent/
├── README.md
├── config.json                 # 当前装配（pi + gui）；config.pi.json 为终端输出版
├── voice_agent/
│   ├── engine.py               # PipelineEngine 两线程运行时（submit 线程安全/优雅停机）
│   ├── config.py               # 配置装载 + 注册表工厂 + assemble（统一 initialize）
│   ├── session.py              # SessionManager 状态机（核心：短临界区 handoff + generation）
│   ├── interrupt.py            # InterruptContext / Position + 提示词渲染（坐标+尾锚）
│   ├── tracker.py              # PositionTracker 消费记账（句边界统计，每轮 reset）
│   ├── events.py               # EventHub 状态事件（round_start/thinking/speaking/…）
│   ├── lifecycle.py            # 组件可选 initialize/shutdown 钩子
│   ├── trigger/   base.py（TriggerSource/TriggerEvent）+ stdin_trigger.py
│   ├── corrector/ base.py（TextCorrector）+ identity.py
│   ├── agent/     base.py（契约见 docstring）+ mock.py + pi_agent.py
│   └── output/    base.py（OutputChannel + POISON）+ printer.py / gui.py
├── main.py                     # 产品入口
└── tests/                      # 全部可独立运行（python tests/xxx.py）
    ├── test_int.py             # 打断链路（printer，含句尾边界）
    ├── test_int_gui.py         # 打断链路（GUI 窗口）
    ├── test_engine.py          # 两线程引擎端到端（跨线程打断+优雅停机）
    ├── test_race.py            # 竞态回归（慢速矫正器 + 三连抢占/代际丢弃）
    ├── test_events.py          # 事件序列断言
    ├── test_thinking_interrupt.py  # 思考中打断（无位置信息分支）
    ├── test_gui_backlog.py     # 队列积压下打断只记已消费位置
    ├── test_tracker_reset.py   # 记账逐字段重置/累加/边界
    ├── test_multi_round_anchor.py  # 多轮打断锚点带各自轮次内容
    ├── test_exit_cmd.py        # /exit 优雅退出
    ├── test_lifecycle.py       # initialize/shutdown 钩子
    └── test_pi_agent.py / test_pi_interrupt.py  # pi 真流式 + 真实 LLM 打断 E2E
```

## 7. 模拟件 vs 正式件

- **模拟件（仅测试用途）**：`MockAgent`（token_delay 模拟慢生成 + think_duration 模拟思考窗口，show_prompt 打印收到提示词）、`PrinterChannel`（char_delay 模拟语速/竞态节奏器）。
- **亦正亦测试的件**：`StdinTrigger`、`IdentityCorrector`、`GuiPrinterChannel`、**`PiAgent`**——正式环境可直接用。
- **PiAgent 细节**：以 `pi -p --mode json --session-id <uuid>` 为后端，stdin 传 prompt，解析 JSONL 的 `text_delta` 实现真流式；同 session-id 多轮共享历史（pi 自管记忆）；打断时 kill 子进程立即终止；换模型/加参数用 `extra_args` 透传（如 `["--model", "anthropic/*sonnet*"]`）。

## 8. 已知边界与扩展点

- **已验证**：speaking/thinking/correcting 三种状态打断；代际竞态（矫正窗口被赶超时静默丢弃过期轮）；队列积压记账；多轮锚点各自独立；pi 真实 LLM 全链路打断。
- **排队语义**：新触发恰在上一轮结束时到达（间隙撞线），走正常新轮次，不打断（符合业务语义）。
- **状态事件钩子**：`hub.subscribe(listener)` 获取 round_start / correcting / thinking / speaking / interrupted / round_end，用于实时显示"思考中/输出中/被打断"。注意：监听器在管线线程事件循环内**同步**执行，必须非阻塞（GUI 只投队列）；事件不带任何文本，只带阶段与打断的位置类事实。
- **待接真实实现**：
  - TriggerSource 接 ASR/VAD（注意 300~500ms 静音窗合并尾音）；
  - TextCorrector 接 LLM（构造函数参数自由扩展）；
  - OutputChannel 接 TTS——重点：`stop()` 必须物理静音，`write()` 内音频播放完成才返回，位置记账才与听感一致。
  - 字符粒度记账在含英文/数字的输出下可能偏粗，需要时在 tracker 加 token 粒度。
