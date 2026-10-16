# -*- coding: utf-8 -*-
"""GUI 输出通道：Tkinter 窗口流式显示输出，终端不再被打断内容污染。

线程模型：
- Tk 主循环跑在独立线程（支持安全 stop / 退出）；
- asyncio 协程只往队列塞字符，Tk 侧用 after 轮询消费——跨线程.Send 安全。
"""
from __future__ import annotations

import asyncio
import queue
import threading

from .base import OutputChannel

# 塞入队列的特殊对象：表示一次打断
STOP_MARK = object()


class GuiPrinterChannel(OutputChannel):
    """注意：不做内部节流——节奏（token/播放速度）由 Agent 生成速度决定；
    真实测试环境里模拟 LLM 已有 token_delay，GUI 直接即收即显。"""

    def __init__(
        self,
        title: str = "Voice Agent 输出",
        width: int = 80,
        height: int = 20,
        font_size: int = 14,
        char_delay: float = 0.0,
    ) -> None:
        """char_delay: 每消费一个字符之后的 sleep。默认 0（即收即显）；
        测试时设为大于 Agent token_delay 的值，可模拟"生成远快于播放，
        大量内容积压在队列中"，打断时的位置应反映已消费进度而非生成量。"""
        self._title = title
        self._width = width
        self._height = height
        self._font_size = font_size
        self._char_delay = char_delay
        self._q: queue.Queue = queue.Queue()
        self._ready = threading.Event()
        self._root = None
        self._text = None
        self._started = threading.Event()
        self._thread = threading.Thread(target=self._run_tk, daemon=True)
        self._thread.start()
        self._ready.wait(timeout=5)

    # ============================================================== Tk 线程
    def _run_tk(self) -> None:
        import tkinter as tk
        from tkinter.scrolledtext import ScrolledText

        root = tk.Tk()
        root.title(self._title)
        root.geometry("700x450")
        text = ScrolledText(
            root, wrap=tk.WORD, font=("Microsoft YaHei", self._font_size),
            state=tk.DISABLED, width=self._width, height=self._height,
        )
        text.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)
        # 打断标记的样式
        text.tag_config("interrupt", foreground="#c0392b")

        poll_ms = 16

        def poll():
            dirty = False
            while True:
                try:
                    item = self._q.get_nowait()
                except queue.Empty:
                    break
                dirty = True
                if item is STOP_MARK:
                    text.configure(state=tk.NORMAL)
                    text.insert(tk.END, "\n[输出通道被打断]\n", "interrupt")
                    text.see(tk.END)
                    text.configure(state=tk.DISABLED)
                else:
                    text.configure(state=tk.NORMAL)
                    text.insert(tk.END, item)
                    text.see(tk.END)
                    text.configure(state=tk.DISABLED)
            if dirty or True:
                root.after(poll_ms, poll)

        root.after(50, poll)
        self._root = root
        self._text = text
        self._ready.set()
        root.mainloop()

    # ====================================================== OutputChannel
    async def write(self, ch: str) -> None:
        self._q.put(ch)
        if self._char_delay > 0:
            await asyncio.sleep(self._char_delay)

    async def stop(self) -> None:
        self._q.put(STOP_MARK)

    def close(self) -> None:
        """应用退出时调用（可选钩子）。"""
        if self._root is not None:
            try:
                self._root.after(0, self._root.destroy)
            except Exception:
                pass
