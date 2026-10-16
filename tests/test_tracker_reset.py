import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from voice_agent.tracker import PositionTracker

t = PositionTracker()
for ch in "你好。再见！":
    t.on_consumed(ch)
s = t.snapshot()
assert (s.statement_idx, s.char_idx_in_statement, s.total_chars) == (2, 0, 6), s
assert s.consumed_text == "你好。再见！", s
assert s.current_statement == "", s
t2 = PositionTracker()
for ch in "第二轮话。":
    t2.on_consumed(ch)
s2 = t2.snapshot()
assert (s2.statement_idx, s2.char_idx_in_statement, s2.total_chars) == (1, 0, 5), s2
assert s2.consumed_text == "第二轮话。", s2
print("TRACKER RESET/ACC TEST OK")

# 语境边界：句末标点处打断 → 已说完完整句、下一句未说
t3 = PositionTracker()
for ch in "开头一句。":
    t3.on_consumed(ch)
s3 = t3.snapshot()
assert (s3.statement_idx, s3.char_idx_in_statement, s3.total_chars) == (1, 0, 5), s3
assert s3.current_statement == "", s3
print("TRACKER RESET/ACC TEST OK (incl boundary)")
