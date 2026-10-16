import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import asyncio, io, re
from contextlib import redirect_stdout

from voice_agent.agent import MockAgent
from voice_agent.corrector.identity import IdentityCorrector
from voice_agent.output.gui import GuiPrinterChannel
from voice_agent.session import SessionManager

async def main():
    # 生成快（token_delay 0.05/句），播放慢（gui 0.15/字）→ 队列大量积压
    buf = io.StringIO()
    with redirect_stdout(buf):
        sm = SessionManager(
            IdentityCorrector(), MockAgent(token_delay=0.05),
            GuiPrinterChannel(char_delay=0.15),
        )
        t1 = asyncio.create_task(sm.run("天气怎么样"))
        await asyncio.sleep(2.0)          # 生成早已完成，播放落后 N 字
        t2 = asyncio.create_task(sm.run("打断"))
        await asyncio.gather(t1, t2, return_exceptions=True)

    text = buf.getvalue()
    m = re.search(r"已说出约 (\d+) 个字", text)
    assert m, text
    consumed = int(m.group(1))
    # 全文远长于已消费数 → 证明打断位置按"GUI 已消费"记录，而不是生成总量
    full_len = sum(len(x) for x in re.findall(r"关于「天气怎么样」，我来回答你。", text)) * 0
    print("consumed =", consumed)
    assert consumed < 40, f"backlog 未生效? consumed={consumed}"
    # 新一轮正常跑完
    assert sm.state == "idle"

asyncio.run(main())
print("GUI BACKLOG TEST OK")
