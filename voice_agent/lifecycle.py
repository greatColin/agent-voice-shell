# -*- coding: utf-8 -*-
"""组件生命周期钩子。

约定：四个抽象层（触发/矫正/Agent/输出）的抽象基类都混入 Lifecycle。
任何实现如果需要初始化资源（加载模型、打开设备、等待窗口就绪、预热连接），
就覆盖 `initialize()`；不需要的组件完全不实现，走基类空实现。

start() 由主入口/配置装配器在应用启动时对**所有已配置组件**按序调用一次，
用时可长可短（如 ASR 模型加载），失败即终止装配，配置错误尽早暴露。
"""
from __future__ import annotations


class Lifecycle:
    """可选初始化协议：不需要初始化的实现不必继承覆盖。"""

    async def initialize(self) -> None:
        """应用启动时调用一次。默认空实现（无需初始化的组件直接继承即可）。"""
        return None

    async def shutdown(self) -> None:
        """应用退出时调用一次。默认空实现。"""
        return None
