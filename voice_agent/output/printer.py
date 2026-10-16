# -*- coding: utf-8 -*-
"""终端流式打印通道。为模拟语速，每个字符之后小睡一下。"""
from __future__ import annotations

import asyncio

from .base import OutputChannel


class PrinterChannel(OutputChannel):
    def __init__(self, char_delay: float = 0.03) -> None:
        self._char_delay = char_delay

    async def write(self, ch: str) -> None:
        print(ch, end="", flush=True)
        await asyncio.sleep(self._char_delay)

    async def stop(self) -> None:
        # 终端没有物理静音能力：换行并标记即可，真实语义留给 TTS 实现
        print("\n[输出通道被打断]")
