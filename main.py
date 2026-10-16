# -*- coding: utf-8 -*-
"""应用入口：两线程运行时。

- 后台线程（PipelineEngine）：纠错之后的一切——矫正/思考/输出状态机、
  队列消费、输出通道、组件 initialize/shutdown，跑在独立 asyncio loop。
- 主线程：调用触发源 start()，唤醒方式由触发实现完全自定义（终端阻塞
  循环 / Tk mainloop / HTTP 服务……），事件通过 engine.submit() 提交。

用法：python main.py [config路径]
"""
from __future__ import annotations

import sys

from voice_agent.engine import PipelineEngine


def main() -> None:
    engine = PipelineEngine(
        config_path=sys.argv[1] if len(sys.argv) > 1 else None
    ).start()

    def on_trigger(text: str) -> None:
        # 空文本 = 退出；否则提交进管线（线程安全）
        engine.submit(text)

    # 主线程交给触发源；本轮 demo 配置为终端阻塞循环
    trigger = engine.components["trigger"]
    trigger.start(lambda ev: on_trigger(ev.text))
    engine.join()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[app] 退出")
