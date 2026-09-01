# Agent Voice Shell

> Pseudo-full-duplex voice shell with local LLM backend.

一个运行在浏览器中的伪全双工语音 Agent Shell，基于本地 pi CLI 后端，支持语音输入、离线情感 TTS、数字人动画和自由布局。

---

## 功能状态

| 阶段 | 描述 | 状态 |
|------|------|------|
| V1 | 文字交互（WebSocket + 中断） | ✅ 已实现 |
| V2 | 语音输入（Browser ASR） | ✅ 已实现 |
| V3 | 本地 TTS（sherpa-onnx 情感语音） | ✅ 已实现 |
| V4 | 数字人 + 状态看板 + 自由布局 | ✅ 已实现 |
| V5 | 移动端布局 + 声纹动画 | ✅ 已实现 |

---

## 快速启动

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 首次运行：下载 TTS 模型（可选）
scripts/init_models.sh              # 默认下载 fanchen 情感 TTS（187 情绪说话人）
scripts/init_models.sh --kokoro   # 追加 Kokoro 中英双语模型
scripts/init_models.sh --all      # 两个模型都下

# 3. 启动服务
python -m app.main
# 浏览器打开 http://localhost:8000
```

**TTS 模型说明：**
- `fanchen`（默认）：VITS 情感模型，187 情绪说话人，RTF~0.4（实时 2.5 倍），16kHz
- `kokoro`（可选）：Kokoro int8 多语言模型，103 说话人，中英双语，RTF~2，24kHz

---

## 界面布局

右上角按钮：
- **编辑** — 拖拽调整 widget 位置和大小
- **保存** — 保存当前布局
- **重置** — 恢复桌面端默认布局
- **移动端** — 切换到移动端专用布局

### 桌面端默认布局
- 左上：语音引擎（ASR/TTS provider 选择）
- 右上：状态看板（连接状态、模型信息）
- 中央：数字人 sprite 动画
- 中下：对话气泡
- 底部：文字输入框 + 麦克风按钮 + 语音波形

### 移动端默认布局
- 顶部：移动声纹（thinking 涟漪 / speaking 频谱 / idle 呼吸）
- 底部：64px 大麦克风按钮，录音结束后出现发送/取消按钮

---

## 架构

```
┌─────────── 浏览器（单文件 HTML）─────────────┐
│  WebSocket 文字流 + 语音波形 + 声纹动画      │
│  数字人 sprite（8×9 spritesheet）            │
└──────────────┬──────────────────────────────┘
               │ WebSocket
┌──────────────▼──────────────────────────────┐
│  FastAPI 后端（Python）                     │
│                                             │
│  state machine（IDLE ⇄ GENERATING）          │
│       ↓                                     │
│  interruption handler（打断 → 截断上下文）    │
│       ↓                                     │
│  session manager → event router             │
│       ↓                                     │
│  agent adapter → pi subprocess（本地 CLI）  │
└──────────────┬──────────────────────────────┘
               │ HTTP（OpenAI 兼容格式）
               ▼
         [pi CLI — 本地模型]
```

**TTS 路径（sherpa-onnx）：**
```
后端 TTS 端点（/api/tts/speak）
    → sherpa-onnx OfflineTts（vits-fanchen / kokoro）
    → WAV bytes
    → 前端 HTMLAudioElement 播放
```

---

## 伪全双工原理

与真正的全双工不同（本项目无需服务端取消支持），通过客户端流控实现可打断输出：

1. 用户打断 → `cancel_event.set()`
2. 流循环检测到标志 → `break`（停止接收）
3. 新请求开始 → 截断的输出不进入下一轮上下文

---

## TTS 配置（设置面板）

支持三种 TTS provider，切换实时生效：

| Provider | 说明 | 依赖 |
|----------|------|------|
| Browser TTS | 系统语音合成，无需配置 | 浏览器支持 |
| 本地（sherpa-onnx）| 离线情感 TTS，187 种情绪音色 | `models/` 下 fanchen VITS |
| 自定义 API | OpenAI 兼容接口 | 需配置 baseURL + API Key |

---

## 开发

```bash
# 安装
pip install -r requirements.txt

# 单元测试
pytest tests/

# 启动服务
python -m app.main

# TTS 模型初始化脚本
scripts/init_models.sh --help
```

---

## 目录结构

```
app/
  agent/       pi_adapter.py  — pi subprocess 封装 + _ThinkFilter
  controller/  state_machine.py / interruption.py — 状态机 + 打断
  events/      router.py / events.py — 事件流
  session/     session.py — 消息栈管理
  tts/         service.py — sherpa-onnx 多引擎 TTS 服务
  web/         ws_endpoint.py / protocol.py — WebSocket 端点
               static/index.html — 全量前端单文件
scripts/
  init_models.sh   — TTS 模型下载（断点续传）
  start.sh          — 服务启动脚本
models/             — TTS 模型目录（gitignore，运行时下载）
```

---

## License

MIT
