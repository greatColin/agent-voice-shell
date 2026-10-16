# -*- coding: utf-8 -*-
"""Agent 抽象层：文字进 + 流式文字出。

框架对 Agent 的唯一契约：
  think_stream(user_text, interrupt_premise) -> AsyncIterator[str]

- user_text          : 矫正后的本轮用户输入
- interrupt_premise  : 上一次打断现场的提示词（渲染好的字符串），无则 None
- yield 的是发往用户的正文 token

结构化（思考/正文等阶段）属于 Agent 内部实现细节，不进入本契约：
思考阶段在 Agent 内部自行消化（内部维护、内部展示），不出 Agent、
不经过输出通道；首个 yield 即视为正文开始，框架据此切换状态。
历史记录、行为模式等也一概由 Agent 实现自行管理，框架不传 history。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import AsyncIterator

from ..lifecycle import Lifecycle


class Agent(ABC, Lifecycle):
    """思考层抽象。"""

    @abstractmethod
    def think_stream(
        self, user_text: str, interrupt_premise: str | None
    ) -> AsyncIterator[str]:
        """流式 yield 正文 token；取消任务即视为思考中断。

        思考过程（如有）在实现内部完成，不 yield——
        思考被打断时框架只知道"还在思考、无输出位置"。
        """
        raise NotImplementedError

    def build_prompt(self, user_text: str, interrupt_premise: str | None) -> str:
        """默认提示词组装：打断前提 + 本轮输入。实现可覆盖。"""
        parts = []
        if interrupt_premise:
            parts.append(interrupt_premise)
        parts.append(f"本轮用户输入: {user_text}")
        return "\n".join(parts)
