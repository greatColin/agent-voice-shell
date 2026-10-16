import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import asyncio

from voice_agent.agent import MockAgent
from voice_agent.corrector.identity import IdentityCorrector
from voice_agent.events import EventHub, EventType
from voice_agent.output.printer import PrinterChannel
from voice_agent.session import SessionManager

async def main():
    hub = EventHub()
    seq = []
    hub.subscribe(lambda ev: seq.append((ev.type, dict(ev.data))))

    sm = SessionManager(IdentityCorrector(), MockAgent(), PrinterChannel(0.02), events=hub)
    t1 = asyncio.create_task(sm.run("天气怎么样"))
    await asyncio.sleep(0.4)                   # 思考中
    t2 = asyncio.create_task(sm.run("打断"))    # 触发 INTERRUPTED
    await asyncio.gather(t1, t2, return_exceptions=True)
    types = [t for t, _ in seq]
    assert EventType.INTERRUPTED in types, types
    interrupted_ev = dict(seq[types.index(EventType.INTERRUPTED)][1])
    ctx = interrupted_ev["context"]
    assert ctx.state.value == "speaking" or ctx.state.value == "thinking"
    # 正常轮收尾 + 被打断样均应有 ROUND_END
    assert types.count(EventType.ROUND_END) >= 2
    assert types[0] is EventType.ROUND_START
    print("sequence:", [t.value for t in types])
    print("EVENTS TEST OK")

asyncio.run(main())
