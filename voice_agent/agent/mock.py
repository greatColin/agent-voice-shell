# -*- coding: utf-8 -*-
"""模拟 Agent：慢速生成 + 打印收到的完整提示词，便于观察打断现场。

阶段结构在 Agent 内部消化：
- 【思考】阶段：内部打日志 + sleep，思考不 yield、不出 Agent、不经 out ——
  思考中被打断时现场只描述"思考时被打断"，无输出位置；
- 首次 yield 起 = 正文开始，框架状态切 SPEAKING，此后打断才有输出位置。

打断确认行为（模拟 LLM 的"被打断反应"）：
- 语音输出中打断 -> 「好的，我知道上一轮我在说【xxx】时被打断了。」
- 思考中打断   -> 「好的，我知道上一轮我在【思考】时被打断了。」
"""
from __future__ import annotations

import asyncio
import re

from .base import Agent

"""匹配打断点尾部锚点（最后说到的是什么：「…tail」。）"""
_LAST_SPOKEN_RE = re.compile(r"最后说到的是什么：「(.+?)」。")
_AT_BOUNDARY_RE = re.compile(r"恰好刚完整说完第 (\d+) 句")


class MockAgent(Agent):
    def __init__(
        self,
        token_delay: float = 0.25,
        reply_interrupted: str = "",
        show_prompt: bool = True,
        think_duration: float = 1.0,
    ) -> None:
        self._token_delay = token_delay
        self._reply_interrupted = reply_interrupted  # 自定义被打断轮次的回答（可空）
        self._show_prompt = show_prompt
        self._think_duration = think_duration  # 模拟思考耗时，营造"思考中被打断"窗口

    def think_stream(self, user_text, interrupt_premise):
        return self._stream(user_text, interrupt_premise)

    async def _stream(self, user_text, interrupt_premise):
        prompt = self.build_prompt(user_text, interrupt_premise)
        if self._show_prompt:
            print(f"\n[MockAgent] 收到提示词:\n-----\n{prompt}\n-----\n")

        # -------- 思考阶段（内部消化：不打 out，只打自己的日志）--------
        print("[MockAgent] 【思考】正在推理不过 out……", flush=True)
        await asyncio.sleep(self._think_duration)
        print("[MockAgent] 【思考】完成，开始输出正文", flush=True)

        # -------- 正文阶段（yield 起才是"说出口"的开始）--------
        if interrupt_premise:
            reply = self._reply_interrupted or (
                self._acknowledge(interrupt_premise) + f"现在接着聊「{user_text}」。"
            )
        else:
            # 正文间插轮次专属内容：锚点随轮次可辨，方便肉眼分清
            # "过去几轮各自的打断位置"，不误认为记账没重置
            reply = (
                f"关于「{user_text}」，我来回答你。"
                f"围绕「{user_text}」这个主题，我准备分三点展开："
                f"第一，这个主题的第一部分；"
                f"第二，这个主题的第二部分；"
                f"第三，结尾部分。"
                f"如果你现在打断我，我应该能记住我说到哪里。"
            )
        # 按句逐段、字逐个 yield，模拟大部分 LLM 的流式返回
        buf = ""
        for ch in reply:
            buf += ch
            if ch in "。，！？;":
                yield buf
                buf = ""
                await asyncio.sleep(self._token_delay)
        if buf:
            yield buf

    def _acknowledge(self, premise: str) -> str:
        m = _LAST_SPOKEN_RE.search(premise)
        if m:
            return f"好的，我知道上一轮我说到【{m.group(1)}】时被打断了。"
        m = _AT_BOUNDARY_RE.search(premise)
        if m:
            return f"好的，我知道上一轮我刚说完第 {m.group(1)} 句就被打断了。"
        if "【思考】" in premise or "思考回答" in premise or "尚未输出" in premise:
            return "好的，我知道上一轮我在【思考】时被打断了。"
        return "好的，我知道上一轮我被你打断了。"
