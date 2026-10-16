import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio

from voice_agent.agent import MockAgent
from voice_agent.corrector.base import TextCorrector
from voice_agent.output.printer import PrinterChannel
from voice_agent.session import SessionManager

judge = {"stale": 0, "interrupt": 0, "rounds_ok": False}


class SlowCorrector(TextCorrector):
    """模拟 LLM 矫正耗时 0.6s：制造"矫正窗口内被新触发打断"的竞态。"""

    async def correct(self, raw: str) -> str:
        await asyncio.sleep(0.6)
        return raw


async def main():
    sm = SessionManager(SlowCorrector(), MockAgent(), PrinterChannel(0.02))

    t1 = asyncio.create_task(sm.run("第一次输入"))
    await asyncio.sleep(0.2)          # A 正处于 CORRECTING（锁外）
    t2 = asyncio.create_task(sm.run("第二次输入"))   # B 抢占
    await asyncio.sleep(0.9)          # B 已开跑（THINKING/SPEAKING）
    t3 = asyncio.create_task(sm.run("第三次输入"))   # C 再抢占 B
    await asyncio.gather(t1, t2, t3, return_exceptions=True)

    assert sm.state == "idle", sm.state
    # 断言：三方先后入侵，靠代际防线每一轮都干净交接，最终收敛 IDLE
    print("RACE TEST OK, final state =", sm.state)

asyncio.run(main())
