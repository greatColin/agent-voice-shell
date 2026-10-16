# -*- coding: utf-8 -*-
"""手动输入触发：终端每回车一次触发一次。读线程阻塞 input()，
事件经线程安全的 on_trigger 交接，与 PipelineEngine 两线程结构天然契合。

内置命令：
- /exit 或空行/EOF/Ctrl+C -> 触发退出（text=""）
- /stop                  -> 作为触发文本透传（可用于测试打断语义）
其它文本 -> 正常触发。
"""
from __future__ import annotations

import threading

from .base import TriggerEvent, TriggerSource


class StdinTrigger(TriggerSource):
    def __init__(self, prompt: str = ">>> ") -> None:
        self._prompt = prompt
        self._enabled = True

    def start(self, on_trigger) -> None:
        """on_trigger: Callable[[TriggerEvent], None]。

        契约：on_trigger 必须线程安全（PipelineEngine.submit 满足），
        触发源可从自身线程直接调用，无需关心事件循环。
        """

        def _reader():
            while self._enabled:
                try:
                    line = input(self._prompt)
                except (EOFError, KeyboardInterrupt):
                    line = ""
                if not self._enabled:
                    return
                text = line.strip()
                if text.lower() in ("/exit", "/quit") or not text:
                    self._enabled = False
                    on_trigger(TriggerEvent(text=""))
                    return
                on_trigger(TriggerEvent(text=text))
                print(self._prompt, end="", flush=True)

        threading.Thread(target=_reader, daemon=True).start()

    def stop(self) -> None:
        self._enabled = False
