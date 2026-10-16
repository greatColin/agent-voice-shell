import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import asyncio, io
from contextlib import redirect_stdout

from voice_agent.agent import MockAgent
from voice_agent.corrector.identity import IdentityCorrector
from voice_agent.output.printer import PrinterChannel
from voice_agent.session import SessionManager

async def main():
    buf = io.StringIO()
    with redirect_stdout(buf):
        sm = SessionManager(IdentityCorrector(), MockAgent(), PrinterChannel(0.02))
        t1 = asyncio.create_task(sm.run("天气怎么样"))
        await asyncio.sleep(0.4)              # 此刻尚在【思考】阶段
        assert sm.state == "thinking", sm.state
        t2 = asyncio.create_task(sm.run("打断"))
        await asyncio.gather(t1, t2, return_exceptions=True)
    text = buf.getvalue()
    assert "你之前想的内容尚未输出" in text, text[-400:]
    assert "我在【思考】时被打断" in text, text[-400:]
    assert sm.state == "idle"
    print("THINKING INTERRUPT TEST OK")

asyncio.run(main())
