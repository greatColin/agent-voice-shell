# -*- coding: utf-8 -*-
"""触发抽象层：所有触发方式统一收敛为一个 TriggerEvent(text)。"""
from __future__ import annotations

import time
from abc import ABC, abstractmethod

from ..lifecycle import Lifecycle
from dataclasses import dataclass, field


@dataclass
class TriggerEvent:
    """一次触发。所有触发源（语音/按键/手动）最终都产出它。"""

    text: str
    ts: float = field(default_factory=time.time)


class TriggerSource(ABC, Lifecycle):
    """触发源抽象。start() 后自行开始上报事件，不做任何打断判断。"""

    @abstractmethod
    def start(self, on_trigger) -> None:
        """on_trigger: Callable[[TriggerEvent], None]，由 SessionManager 提供。"""
        raise NotImplementedError

    def stop(self) -> None:  # 可选钩子：应用退出时调用
        pass
