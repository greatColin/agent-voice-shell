import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import asyncio, json, uuid

# 用 printer 通道跑真实 LLM 打断链路
cfg = json.load(open("config.json", encoding="utf-8"))
cfg["output"] = {"impl": "printer", "params": {"char_delay": 0.06}}
cfg["agent"]["params"]["session_id"] = f"voice-agent-e2e-{uuid.uuid4().hex[:8]}"
with open("test_pi_config.json", "w", encoding="utf-8") as f:
    json.dump(cfg, f, ensure_ascii=False)

from voice_agent.engine import PipelineEngine

def main():
    engine = PipelineEngine(config_path="test_pi_config.json").start()
    engine.submit("给我详细介绍一下长城，多说几句")   # 引导长回答，留出打断窗口
    import time; time.sleep(6)                        # 大概率已进入输出中
    st = engine._session.state
    print("\n[TEST] interrupt at state =", st)
    engine.submit("好了好了别说了，聊点别的：今天天气如何")
    time.sleep(15)
    engine.submit("")
    engine.join(timeout=30)
    os.remove("test_pi_config.json")
    print("PI INTERRUPT E2E TEST OK (state at interrupt =", st, ")")

if __name__ == "__main__":
    main()
