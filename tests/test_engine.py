import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json, os, threading, time

# 用 printer 通道避免测试弹 GUI 窗口；其余与生产配置一致
cfg = json.load(open("config.json", encoding="utf-8"))
cfg["output"] = {"impl": "printer", "params": {"char_delay": 0.02}}
cfg["agent"]["params"]["show_prompt"] = True
cfg["session"] = {"params": {"verbose": True}}
with open("test_config.json", "w", encoding="utf-8") as f:
    json.dump(cfg, f, ensure_ascii=False)

from voice_agent.engine import PipelineEngine

def main():
    engine = PipelineEngine(config_path="test_config.json").start()

    # 【场景1】后台轮次进行中，由主线程（跨线程）触发打断
    engine.submit("天气怎么样")
    time.sleep(1.0)                       # 此时输出中
    assert engine._session.state != "idle", engine._session.state
    engine.submit("打断你了，聊点别的")     # 主线程直接 submit，call_soon_threadsafe 中转
    time.sleep(3.0)
    assert engine._session.state == "idle"

    # 【场景2】空文本请求停机：排干会话 -> 组件 shutdown -> 管线线程退出
    engine.submit("")
    engine.join(timeout=10)
    assert not (engine._thread and engine._thread.is_alive()), "管线线程未退出"
    os.remove("test_config.json")
    print("ENGINE TEST OK")

asyncio_done = None
if __name__ == "__main__":
    main()
