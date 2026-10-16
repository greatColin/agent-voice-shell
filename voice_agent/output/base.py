# -*- coding: utf-8 -*-
"""输出通道抽象层：逐字符消费，速度即播放速度；stop() 立即静音。"""
from __future__ import annotations

from abc import ABC, abstractmethod

from ..lifecycle import Lifecycle


# 队列毒丸：放入后消费协程退出，不再产出任何内容
POISON = object()


class OutputChannel(ABC, Lifecycle):
    """输出通道抽象。

    write() 必须真实代表"该字符播放完毕"——例如 TTS 实现里要等音频播完
    这一个字才返回。消费进度因此等价于用户耳朵听到的进度，打断记账以此为准。
    """

    @abstractmethod
    async def write(self, ch: str) -> None:
        raise NotImplementedError

    @abstractmethod
    async def stop(self) -> None:
        """无侵入打断：立即静音/清缓冲，不依赖消费完当前字符。"""
        raise NotImplementedError
