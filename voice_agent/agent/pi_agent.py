# -*- coding: utf-8 -*-
"""PiAgent：把 pi CLI 当 LLM 后端的正式 Agent 实现。

思路：`pi -p --mode json --session-id <uuid>` 非交互执行，prompt 经 stdin
传入（跨平台，避免命令行转义），stdout 是 JSONL 事件流——其中
assistantMessageEvent.type == "text_delta" 的 delta 即流式正文 token。
本实现逐行解析并 yield 这些 delta，框架的打断/位置记账/状态切换原生生效。

- 历史连续：--session-id 固定一个 UUID，多轮自动落在同一 pi 会话，
  框架不传 history（符合契约，Agent 层自管记忆）。
- 思考阶段：pi 的 thinking 事件不 yield，内部丢弃（不出 Agent）。
- 打断：think_stream 任务被取消时 kill 子进程，pi 立即终止。
- 提示词：build_prompt 的结果（打断现场前提 + 本轮输入）作为一条
  用户消息传给 pi；行为人设经 --append-system-prompt 注入。

依赖：机器上已安装 pi CLI（npm 全局）。
"""
from __future__ import annotations

import asyncio
import json
import uuid

from .base import Agent

DEFAULT_SYSTEM_PROMPT = (
    "你是语音助手的回答内核：回答必须是口语化短句，禁止 markdown、列表、代码块等无法朗读的格式，默认中文。"
    "用户消息若含【打断现场】字样，表示上一轮回复被打断，请自然衔接，可简短确认被打断的位置再回应本轮输入。"
)


class PiAgent(Agent):
    def __init__(
        self,
        pi_bin: str = "pi",
        system_prompt: str = DEFAULT_SYSTEM_PROMPT,
        session_id: str = "",
        extra_args: list | None = None,
        show_prompt: bool = False,
    ) -> None:
        self._pi_bin = pi_bin
        self._system_prompt = system_prompt
        # 每个实例一个稳定会话：多轮历史由 pi 会话文件自己维护
        self._session_id = session_id or f"voice-agent-{uuid.uuid4().hex[:12]}"
        self._extra_args = list(extra_args or [])
        self._show_prompt = show_prompt

    def think_stream(self, user_text, interrupt_premise):
        return self._stream(user_text, interrupt_premise)

    def _build_cmd(self) -> str:
        args = [
            self._pi_bin, "-p",
            "--mode", "json",
            "--session-id", self._session_id,
            "--no-tools",
            "--no-extensions", "--no-skills", "--no-mcp",
            "--no-prompt-templates", "--no-themes",
            "--no-context-files",
            "--append-system-prompt", self._system_prompt,
        ] + self._extra_args
        return " ".join(args)

    async def _stream(self, user_text, interrupt_premise):
        prompt = self.build_prompt(user_text, interrupt_premise)
        if self._show_prompt:
            print(f"\n[PiAgent] 收到提示词:\n-----\n{prompt}\n-----\n", flush=True)

        proc = await asyncio.create_subprocess_shell(
            self._build_cmd(),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        assert proc.stdin is not None and proc.stdout is not None
        proc.stdin.write((prompt + "\n").encode("utf-8"))
        await proc.stdin.drain()
        proc.stdin.close()

        try:
            while True:
                line = await proc.stdout.readline()
                if not line:
                    break
                delta = self._extract_delta(line.decode("utf-8", errors="replace"))
                if delta:
                    yield delta
            await proc.wait()
        finally:
            # 被打断（任务取消/生成器关闭）时立即杀掉 pi 进程
            if proc.returncode is None:
                try:
                    proc.kill()
                except ProcessLookupError:
                    pass

    @staticmethod
    def _extract_delta(line: str) -> str:
        """从一行 JSONL 里提取 assistant 的流式正文增量；其余事件一律忽略。"""
        line = line.strip()
        if not line.startswith("{"):
            return ""
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            return ""
        if ev.get("type") != "message_update":
            return ""
        sub = ev.get("assistantMessageEvent") or {}
        if sub.get("type") == "text_delta":
            return sub.get("delta", "")
        return ""
