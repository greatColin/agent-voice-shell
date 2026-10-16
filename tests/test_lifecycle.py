import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import asyncio
from voice_agent.lifecycle import Lifecycle
from voice_agent.config import load_config, assemble

# 验证：1) 默认组件不需要 initialize 也能跑  2) 自定义初始化会被调到
calls = []

class Probe(Lifecycle):
    async def initialize(self):
        calls.append("probe.init")

cfg = load_config()
components = asyncio.get_event_loop().run_until_complete(assemble(cfg))
probe = Probe()
probe.initialize is not None
asyncio.new_event_loop().run_until_complete(probe.initialize())
print("calls =", calls, "| components =", sorted(components))
print("LIFECYCLE TEST OK")
