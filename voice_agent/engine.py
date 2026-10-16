# -*- coding: utf-8 -*-
"""PipelineEngine：两线程运行时。

- 后台线程：完整的 asyncio 事件循环，承载"纠错之后"的全部流程
  （SessionManager 状态机、队列消费、输出通道、组件 initialize/shutdown）。
- 主线程：随任由 TriggerSource 自定义——终端阻塞循环、Tk mainloop、
  HTTP 服务轮询……只要持有"何时触发"决定权，怎么写都行。

线程安全契约：engine.submit(text) 可从**任何线程**调用（内部走
loop.call_soon_threadsafe）。触发源实现无需关心事件循环。

追加实现类的兼容性示例：HttpTrigger 起一个只转发文字的 HTTP 服务
（语音由其他程序推过来），在 handler 里调 engine.submit 即可；或
TkTrigger 用 GUI 文本框提交——都不影响两线程结构，只改配置。
"""
from __future__ import annotations

import asyncio
import threading

from .config import ConfigError, load_config
from .session import SessionManager


class PipelineEngine:
    def __init__(self, config_path: str | None = None) -> None:
        self._config_path = config_path
        self._loop: asyncio.AbstractEventLoop | None = None
        self._session: SessionManager | None = None
        self._components: dict | None = None
        self._thread: threading.Thread | None = None
        self._ready = threading.Event()
        self._init_error: Exception | None = None

    # ------------------------------------------------------------ 启动
    def start(self) -> "PipelineEngine":
        """启动后台管线线程并阻塞至组件初始化完成（链式调用）。"""
        self._thread = threading.Thread(
            target=self._pipeline_main, name="pipeline", daemon=True
        )
        self._thread.start()
        self._ready.wait(timeout=120)  # 留时间给模型加载等重初始化
        if self._init_error is not None:
            raise ConfigError(
                f"组件初始化失败: {self._init_error}"
            ) from self._init_error
        return self

    def _pipeline_main(self) -> None:
        """后台线程主体：建 loop -> initialize 全部组件 -> run_forever 直至停机。"""
        self._loop = loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        async def _init():
            cfg = load_config(self._config_path)
            from .config import assemble

            return cfg, await assemble(cfg)

        try:
            cfg, components = loop.run_until_complete(_init())
        except Exception as e:  # noqa: BLE001 - 初始化失败必须穿透到主线程
            self._init_error = e
            self._ready.set()
            loop.close()
            return

        session_params = cfg.get("session", {}).get("params", {}) or {}
        self._session = SessionManager(
            corrector=components["corrector"],
            agent=components["agent"],
            channel=components["output"],
            **session_params,
        )
        self._components = components
        self._ready.set()
        self._done: asyncio.Event = asyncio.Event()

        loop.run_until_complete(self._server())

    # ------------------------------------------------------------ 事件循环
    async def _server(self) -> None:
        """空转直至停机。"""
        await self._done.wait()

    # ------------------------------------------------------------ 触发入口
    def submit(self, text: str) -> None:
        """线程安全的触发提交（从任何线程调用均可）。空文本 = 请求退出。"""
        if self._session is None:
            raise RuntimeError("engine 未就绪：请先 start()")
        if not text:
            self.request_stop()
            return
        try:
            self._loop.call_soon_threadsafe(self._spawn, text)
        except RuntimeError as e:
            # 停机竞态：loop 已退出时新触发直接丢弃
            raise RuntimeError("engine 已停止，触发被丢弃") from e

    def _spawn(self, text: str) -> None:
        asyncio.ensure_future(self._session.run(text))  # type: ignore[union-attr]

    @property
    def components(self) -> dict:
        """已装配的四层组件（output/corrector/agent/trigger）。"""
        if self._components is None:
            raise RuntimeError("engine 未就绪：请先 start()")
        return self._components

    # ------------------------------------------------------------ 停机
    def request_stop(self) -> None:
        """请求管线退出（任何线程可调）：排干在途会话 -> 组件 shutdown -> loop 退出。"""
        if self._loop is None:
            return

        def _schedule() -> None:
            loop = asyncio.get_running_loop()

            async def _shutdown():
                try:
                    await self._session.wait_idle(loop)  # type: ignore[union-attr]
                    for kind in ("trigger", "agent", "corrector", "output"):
                        try:
                            await self._components[kind].shutdown()  # type: ignore[index]
                        except Exception:
                            pass
                finally:
                    self._done.set()

            loop.create_task(_shutdown())

        self._loop.call_soon_threadsafe(_schedule)

    def join(self, timeout: float | None = None) -> None:
        if self._thread is not None:
            self._thread.join(timeout=timeout)
