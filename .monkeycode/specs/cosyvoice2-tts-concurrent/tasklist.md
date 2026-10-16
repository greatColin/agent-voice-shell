# CosyVoice2 + TTS 并发架构实施计划

## 目标
1. 集成 CosyVoice2 作为第三引擎，支持文字情感标签（`[happy]` `[sad]` 等）
2. TTS 改造成线程池并发合成 + 有序结果队列，实现无缝语音输出

## 任务列表

- [ ] 1. 安装 CosyVoice2 及依赖
  - [ ] 1.1 调研 GitHub 克隆 + pip 安装方式（torch CPU 版依赖）
  - [ ] 1.2 编写 `scripts/init_cosyvoice.sh`，下载 CosyVoice2-0.5B 模型到 `models/cosyvoice2/`
  - [ ] 1.3 验证 CosyVoice2 可导入：`from cosyvoice.cli.cosyvoice import CosyVoice2`
  - [ ] 1.4 更新 `requirements.txt` 加入 cosyvoice2-eu 或相关依赖

- [ ] 2. CosyVoice2 引擎封装进 TtsService
  - [ ] 2.1 在 `TtsService` 增加 `_create_cosyvoice()` 引擎工厂方法
  - [ ] 2.2 CosyVoice2 支持情感前缀：`[happy]` `[sad]` `[angry]` `[surprised]` `[fear]` `[neutral]`
  - [ ] 2.3 更新 `_discover_model()` 识别 `cosyvoice*/CosyVoice*` 目录
  - [ ] 2.4 CosyVoice2 优先级：`cosyvoice > vits(fanchen) > kokoro`
  - [ ] 2.5 更新 `status()` 返回 engine 字段

- [ ] 3. TTS 并发架构改造
  - [ ] 3.1 `TtsService` 内部维护 `ThreadPoolExecutor`（默认 2 workers）
  - [ ] 3.2 `asyncio.Queue` 有序结果队列，每项包含 `(text, voice, speed, wav_bytes)`
  - [ ] 3.3 `synthesize()` 改为提交任务到线程池，结果入队，返回 queue 引用给 WS handler
  - [ ] 3.4 `ResultQueue` 类封装队列操作，提供 `async get()` 和完成回调机制
  - [ ] 3.5 线程安全：每个合成任务独立，不阻塞其他合成

- [ ] 4. WS 端串行 pull 机制
  - [ ] 4.1 `ws_endpoint.py` 新增 TTS 队列消费协程 `consume_tts_queue(queue)`
  - [ ] 4.2 `run_agent_stream()` 中的 `pump()` 触发 TTS 合成后，WS 端从队列串行取结果并发送
  - [ ] 4.3 WS 消息类型新增 `TTS_AUDIO` 推送 `{audio: base64, text: str, chunk_index: int}`
  - [ ] 4.4 前端收到 `TTS_AUDIO` 后直接播放，不等待完整句子

- [ ] 5. 前端 TTS 音频流处理
  - [ ] 5.1 WebSocket 收到 `TTS_AUDIO` 消息时，base64 解码为 ArrayBuffer
  - [ ] 5.2 使用 `AudioContext.decodeAudioData()` 解码后 `SourceNode.start()` 播放
  - [ ] 5.3 维护 chunk_index 确保按序播放（乱序时 buffer 等候）
  - [ ] 5.4 `mobile-voice` widget 在 speaking 状态时直接播放 WS 音频流

- [ ] 6. 更新初始化和启动脚本
  - [ ] 6.1 更新 `scripts/init_models.sh` 加入 CosyVoice2 模型下载
  - [ ] 6.2 更新 `scripts/start.sh` 在启动前确认 TTS 模型就绪
  - [ ] 6.3 更新 `README.md` 加入 CosyVoice2 说明和情感标签示例

- [ ] 7. 回归测试
  - [ ] 7.1 `pytest tests/ -x -q` 确保现有功能不受影响
  - [ ] 7.2 手动测试：单句 TTS、多句并发合成、WS 音频流播放
  - [ ] 7.3 检查 RTF 性能变化（CosyVoice2 CPU int8 预期 RTF ~1.0）
