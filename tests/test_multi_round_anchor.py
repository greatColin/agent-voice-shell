import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import asyncio, io, re
from contextlib import redirect_stdout

from voice_agent.agent import MockAgent
from voice_agent.corrector.identity import IdentityCorrector
from voice_agent.output.printer import PrinterChannel
from voice_agent.session import SessionManager

async def main():
    hub_text = io.StringIO()
    sm = SessionManager(IdentityCorrector(), MockAgent(token_delay=0.05, think_duration=0.2), PrinterChannel(0.02))
    import voice_agent.session as mod
    # 捕获框架流的输出：用 events Hook而非 stdout（框架不打印提示词）
    from voice_agent.events import EventHub, EventType
    hub = EventHub()
    caught = []
    hub.subscribe(lambda ev: caught.append(ev.data["context"].render())
                   if ev.type is EventType.INTERRUPTED else None)
    sm._events = hub

    async def round(text, delay):
        await asyncio.sleep(delay)
        await sm.run(text)

    # 轮1: 在第3句（第一/二部分之间）打断；轮2: 换新输入再打断
    t1 = asyncio.create_task(round("苹果", 0))
    await asyncio.sleep(0.45)
    t2 = asyncio.create_task(round("香蕉", 0))
    await asyncio.gather(t1, t2, return_exceptions=True)

    assert len(caught) >= 1, caught
    premise = caught[0]           # 轮1 被打断时生成的现场
    m = re.search(r"最后说到的是什么：「(.+?)。」?", premise)
    anchor = m.group(1) if m else ""
    assert "苹果" in premise, premise
    assert anchor == "" or "香蕉" not in anchor, premise  # 轮1现场不包含轮2内容
    print("anchor =", anchor[:40])
    print("MULTI-ROUND ANCHOR TEST OK")

asyncio.run(main())
