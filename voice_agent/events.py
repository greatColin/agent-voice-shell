# -*- coding: utf-8 -*-
"""会话事件钩子：状态流转的事件通知（预留实时状态展示用）。

关键约束：思考内容不出 Agent，事件里也不带任何正文/思考文本——
只带"阶段 + 打断现场（位置类事实）"。UI 拿它显示"思考中/输出中"即可。
监听器为同步回调，在管线线程的事件循环内被调用 —— **必须非阻塞、线程安全**
（如 GUI 请在回调里只投递自己的队列，重型处理交给 UI 线程；回调阻塞会
顺带阻塞会话状态机与打断响应）。
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Callable

from .interrupt import InterruptContext


class EventType(Enum):
    ROUND_START = "round_start"          # payload: gen
    CORRECTING = "correcting"            # payload: gen, 用户原文
    THINKING = "thinking"                # payload: gen
    SPEAKING = "speaking"                # payload: gen（首个正文 token 已到达）
    INTERRUPTED = "interrupted"          # payload: InterruptContext（位置类事实）
    ROUND_END = "round_end"              # payload: gen, interrupted: bool


@dataclass
class SessionEvent:
    type: EventType
    data: dict


Listener = Callable[[SessionEvent], None]


class EventHub:
    """简单同步事件分发：注册/移除/广播。异常相互隔离，不打断主流程。"""

    def __init__(self) -> None:
        self._listeners: list[Listener] = []

    def subscribe(self, listener: Listener) -> None:
        self._listeners.append(listener)

    def unsubscribe(self, listener: Listener) -> None:
        try:
            self._listeners.remove(listener)
        except ValueError:
            pass

    def emit(self, etype: EventType, data: dict) -> None:
        event = SessionEvent(etype, data)
        for l in tuple(self._listeners):
            try:
                l(event)
            except Exception:
                # 监听器异常绝不影响会话主流程
                pass
