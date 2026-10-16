import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import asyncio
from voice_agent.agent import MockAgent
from voice_agent.corrector.identity import IdentityCorrector
from voice_agent.output.gui import GuiPrinterChannel
from voice_agent.session import SessionManager

async def main():
    sm = SessionManager(IdentityCorrector(), MockAgent(), GuiPrinterChannel())
    t1 = asyncio.create_task(sm.run("天气怎么样"))
    await asyncio.sleep(2.0)
    print("[TEST] state =", sm.state)
    t2 = asyncio.create_task(sm.run("打断你了，聊点别的"))
    await asyncio.gather(t1, t2)
    print("[TEST] final =", sm.state)

asyncio.run(main())
print("TEST OK")
