import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import asyncio, uuid

from voice_agent.agent.pi_agent import PiAgent
from voice_agent.corrector.identity import IdentityCorrector
from voice_agent.output.printer import PrinterChannel
from voice_agent.session import SessionManager

async def main():
    # 每次测试用全新会话，避免历史污染
    agent = PiAgent(session_id=f"voice-agent-test-{uuid.uuid4().hex[:8]}", show_prompt=False)
    parts = []
    async for t in agent.think_stream("从1数到5，用顿号分隔", None):
        parts.append(t)
    text = "".join(parts)
    print("\n[直接契约] 流式片段数 =", len(parts), "| 全文 =", text)
    assert len(parts) >= 1

    # 同会话第二轮：验证历史连续（pi 自己记忆）
    parts2 = []
    async for t in agent.think_stream("刚才让你数到几？", None):
        parts2.append(t)
    print("[历史连续] =", "".join(parts2))

    # 全链路一轮
    sm = SessionManager(IdentityCorrector(), agent, PrinterChannel(0.03))
    await sm.run("你叫什么名字？用一句话回答")
    print("\n[全链路] final state =", sm.state)

asyncio.run(main())
print("PI AGENT TEST OK")
