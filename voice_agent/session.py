# -*- coding: utf-8 -*-
"""SessionManager：单实例状态机（核心）。

设计要点：
- _handoff 锁只保护"打断 + 轮次交接"这一短临界区，绝不贯穿整轮；
  否则排队中的触发要等上一轮跑完才拿到锁，永远无法打断。
- 用 _generation 代际计数守卫：旧轮的收尾(置 IDLE)只有当前代时才生效，
  防止"新轮已开始、旧轮 finally 却把状态拉回 IDLE"的竞态。
- 打断以"已消费位置"(PositionTracker)为准，未消费队列整体作废。
"""
from __future__ import annotations

import asyncio

from .agent import Agent
from .corrector import TextCorrector
from .events import EventHub, EventType
from .interrupt import InterruptContext, InterruptState
from .output import POISON, OutputChannel
from .tracker import PositionTracker


class ConversationState:
    IDLE = "idle"
    CORRECTING = "correcting"
    THINKING = "thinking"
    SPEAKING = "speaking"


class SessionManager:
    def __init__(
        self,
        corrector: TextCorrector,
        agent: Agent,
        channel: OutputChannel,
        verbose: bool = True,
        events: EventHub | None = None,
    ) -> None:
        self._corrector = corrector
        self._agent = agent
        self._channel = channel
        self._verbose = verbose
        self._events = events or EventHub()

        self.state = ConversationState.IDLE
        self._think_task: asyncio.Task | None = None
        self._consume_task: asyncio.Task | None = None
        self._queue: asyncio.Queue | None = None
        self._tracker = PositionTracker()
        self._interrupt_epoch = 0      # 当前连续打断轮次（第几次打断）
        self._generation = 0           # 轮次代际，防收尾竞态
        self._handoff = asyncio.Lock()

    # ------------------------------------------------------------------ 入口
    async def run(self, raw_text: str) -> None:
        """处理一次触发：忙则先打断；锁只保护交接，不贯穿整轮。"""
        premise: str | None = None
        async with self._handoff:
            if self.state != ConversationState.IDLE:
                premise = await self._stop_current()
            self._generation += 1
            gen = self._generation
            queue: asyncio.Queue = asyncio.Queue()
            self._queue = queue                 # 局部绑定，防旧轮 POISON 漏到新队列
            self._tracker.reset()
            interrupted = premise is not None
            self._events.emit(EventType.ROUND_START, {"gen": gen, "interrupted": interrupted})
            self.state = ConversationState.CORRECTING

        try:
            # 矫正（锁外执行，LLM 矫正器耗时不阻塞后续打断的发现）
            corrected = await self._corrector.correct(raw_text)
            self._events.emit(
                EventType.CORRECTING, {"gen": gen, "raw": raw_text, "fixed": corrected}
            )
            if corrected != raw_text and self._verbose:
                print(f"\n[SessionManager] 原文 {raw_text!r} -> 矫正 {corrected!r}")

            # 【竞态防线】矫正期间可能已被新手打断赶超：代际不匹配则本轮作废，
            # 不再创建任何任务，避免踩进新轮的队列/状态
            async with self._handoff:
                if gen != self._generation:
                    if self._verbose:
                        print(f"\n[SessionManager] 丢弃代际过期轮次(gen={gen})")
                    return
                self.state = ConversationState.THINKING
                self._events.emit(EventType.THINKING, {"gen": gen})
                self._think_task = asyncio.create_task(
                    self._run_agent(corrected, premise, queue, gen)
                )
                self._consume_task = asyncio.create_task(self._consume(queue))
            await asyncio.gather(
                self._think_task, self._consume_task, return_exceptions=True
            )
            # 取消路径不用报错：return_exceptions 收集结果，诊断留给 verbose 日志；
            # 正常结束与被取消都在 finally 统一收尾
        finally:
            # 只有当前代才有资格收尾；旧轮被新轮打断后跳过
            async with self._handoff:
                if gen == self._generation:
                    self.state = ConversationState.IDLE
                    self._interrupt_epoch = 0  # 恢复打断轮次计数
                    ended_interrupted = False
                else:
                    ended_interrupted = True
                self._events.emit(
                    EventType.ROUND_END,
                    {"gen": gen, "interrupted": ended_interrupted},
                )            


    # -------------------------------------------------------------- 打断中枢
    async def _stop_current(self) -> str:
        """打断进行中的流程（持锁调用），返回渲染后的提示词前提。"""
        before_state = self.state

        # 1) 停思考：取消生成任务（未入队的 token 不再产生）
        think_task = self._think_task
        if think_task is not None:
            think_task.cancel()
        # 2) 停输出：通道立即静音，未消费内容物理上不再出现
        #    （仅 SPEAKING 需物理静音；CORRECTING 时什么都还没说，避免无谓打断标记）
        if before_state == ConversationState.SPEAKING:
            await self._channel.stop()

        # 3) 账本快照：以"已消费位置"为准确账
        position = self._tracker.snapshot()

        # 4) 取消消费协程，清空未消费队列
        consume_task = self._consume_task
        if consume_task is not None:
            consume_task.cancel()
        if self._queue is not None:
            queue = self._queue
            self._queue = None
            while not queue.empty():
                queue.get_nowait()

        # 5) 等旧任务彻底退出，杜绝幽灵协程写通道
        pending = [t for t in (think_task, consume_task) if t is not None]
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
        self._think_task = None
        self._consume_task = None


        ctx = InterruptContext(
            state=(
                InterruptState.THINKING
                if before_state in (ConversationState.CORRECTING, ConversationState.THINKING)
                else InterruptState.SPEAKING
            ),
            position=position,
            epoch=self._interrupt_epoch + 1,
        )
        self._interrupt_epoch = ctx.epoch
        self._events.emit(EventType.INTERRUPTED, {"context": ctx})

        premise = ctx.render()
        # 注意：提示词不在框架侧打印——由 Agent 实现（如模拟 LLM 的
        # show_prompt）展示，避免双份输出污染通道
        return premise

    # -------------------------------------------------------------- 轮内协程
    async def _run_agent(
        self, user_text: str, premise: str | None, queue: asyncio.Queue,
        gen_at_creation: int,
    ) -> None:
        """生成路由：yield 的都是发往用户的正文（思考阶段在 Agent 内部消化）。

        契约信号：首个 token 到达 = 正文开始，会话状态 THINKING -> SPEAKING。
        思考期间被取消 -> 无输出位置，打断前提只描述"思考中被打断"。
        token 只进本轮局部 queue，POISON 不越过代际。
        """
        task = asyncio.current_task()
        assert task is not None
        try:
            async for token in self._agent.think_stream(user_text, premise):
                if self.state == ConversationState.THINKING:
                    self.state = ConversationState.SPEAKING
                    self._events.emit(EventType.SPEAKING, {"gen": gen_at_creation})
                await queue.put(token)  # 【竞态防线】只用本轮局部 queue
        finally:
            await queue.put(POISON)

    async def _consume(self, queue: asyncio.Queue) -> None:
        """消费协程：只消费正文（thinking 不会进队列），按通道速度逐字消费并记账。
        注意：state 的 SPEAKING 由生成侧遇到首个正文时切换，这里不再重复设置。"""
        while True:
            item = await queue.get()
            if item is POISON:
                return
            # token 可能是多字 chunk，必须逐字符写/记，打断位置才能精确到字
            for ch in str(item):
                await self._channel.write(ch)  # await 返回才算"说出了"
                self._tracker.on_consumed(ch)

    # -------------------------------------------------------------- 便捷入口
    def start(self, raw_text: str) -> asyncio.Task:
        """外部入口：调度 run() 为后台任务，立即返回。"""
        return asyncio.create_task(self.run(raw_text))

    async def wait_idle(self, loop, timeout: float = 10.0) -> None:
        """停机用：等待当前会话结束（非阻塞轮询在途任务）。"""
        deadline = loop.time() + timeout
        while self.state != ConversationState.IDLE and loop.time() < deadline:
            await asyncio.sleep(0.05)
