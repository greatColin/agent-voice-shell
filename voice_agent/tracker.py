# -*- coding: utf-8 -*-
"""消费位置记账：每真实消费一个字符调用一次，打断时快照。

语义约定（流式场景的关键事实）：
- 本 tracker 只知道"已说出口"的部分；打断发生在流式过程中时，
  整段总字数不可知（生成还在进行），所以 Position.total_chars 是
  "打断时已消费的字数"，不是"全段总长"。
- 提示词渲染应基于该事实表述，避免声称"全段共 M 字"这类不可知数字。
"""
from __future__ import annotations

from .interrupt import Position

# 句子边界字符：用于统计"说到第几句"
_SENTENCE_ENDS = "。！？；!?\n"


class PositionTracker:
    """由消费协程驱动，维护"已说出口"的精确位置。每轮会话开始 reset 一次。"""

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        # 每轮重置：statement_idx 0 基下标从 0（第 1 句）开始
        self.statement_idx = 0       # 当前句下标（0 基）
        self.char_idx = 0            # 当前句内已消费字符数
        self.total_chars = 0         # 已消费总数（≠全段总长，流式不可知）
        self.last_char = ""
        self.consumed_text = ""      # 已说出口的全部原文（逐字累加）
        self.current_statement = ""  # 当前句已消费片段（开下一句时清零）

    def feed_statement(self, statement: str) -> None:
        """生成侧知道完整句子边界时调用（可选），让 current_statement 更准。"""
        self.current_statement = statement

    def on_consumed(self, ch: str) -> None:
        """流式累加：消费协程每真实消费一个字符调用一次。"""
        self.char_idx += 1
        self.total_chars += 1
        self.last_char = ch
        self.consumed_text += ch
        self.current_statement += ch
        if ch in _SENTENCE_ENDS:
            # 句子结束，切下一句，各句内计数清零
            self.statement_idx += 1
            self.char_idx = 0
            self.current_statement = ""

    def snapshot(self) -> Position:
        return Position(
            statement_idx=self.statement_idx,
            char_idx_in_statement=self.char_idx,
            total_chars=self.total_chars,
            last_char=self.last_char,
            consumed_text=self.consumed_text,
            current_statement=self.current_statement,
        )
