# -*- coding: utf-8 -*-
"""打断现场定义：打断时由 SessionManager 快照，渲染成一段提示词前提。"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class InterruptState(Enum):
    THINKING = "thinking"   # 正在思考回答
    SPEAKING = "speaking"   # 正在语音/文字输出


@dataclass
class Position:
    """已消费（已说出）位置的快照。"""

    statement_idx: int = -1        # 当前说到第几句（0 基）
    char_idx_in_statement: int = 0  # 本句第几个字（0 基）
    total_chars: int = 0           # 整段已消费总字数
    last_char: str = ""            # 最后消费的字符
    consumed_text: str = ""        # 已说出的全部原文
    current_statement: str = ""    # 当前正在说的这一句（含未消费完的句子）


@dataclass
class InterruptContext:
    """一次打断的完整现场（只含位置类事实，思考内容不出 Agent）。"""

    state: InterruptState
    position: Position | None = None  # SPEAKING 时必有
    epoch: int = 0                 # 第几次打断（从 1 开始）

    def render(self) -> str:
        """渲染成提示词前提。渲染逻辑在框架侧，因为只有框架知道现场。

        原则：不复述上一轮的完整内容——Agent 自己有历史记录，
        框架只提供"被打断的是哪一段文字、位于什么位置"的定位信息。
        """
        s = f"【打断现场】"
        if self.state is InterruptState.THINKING:
            s += "上一轮你正在【思考回答】的过程中被用户打断，你之前想的内容尚未输出。"
        else:
            pos: Position = self.position  # type: ignore[assignment]
            # 流式事实：打断时只知道"已说出多少"，全段总长不可知（生成未完）。
            # 定位信息量在打断点附近：现场 = 精确坐标（第几说、第几字）
            # + 尾部锚点（几字重复词/重句时消歧义，文字-designed，定位信息在尾部非开头）。
            if pos.current_statement:
                stmt = pos.current_statement
                tail = stmt[-20:]              # 打断处最后说出的 ≤20 字
                head_ellipsis = "…" if len(stmt) > 20 else ""
                loc = (
                    f"打断时你已说出约 {pos.total_chars} 个字，"
                    f"停在第 {pos.statement_idx + 1} 句、该句第 {pos.char_idx_in_statement} 个字上。"
                    f"最后说到的是什么：「{head_ellipsis}{tail}」。"
                )
            elif pos.total_chars > 0:
                # 恰好落在句末标点收尾：当前片段已清零，但顶多说了完整句子
                loc = (
                    f"打断时你已说出约 {pos.total_chars} 个字，"
                    f"恰好刚完整说完第 {pos.statement_idx} 句的句尾，"
                    f"下一句一个字都还没说。"
                )
            else:
                loc = "打断时你上一轮的回答一个字都还没说出。"
            s += (
                f"你上一轮正在【语音输出】时被用户打断。"
                f"{loc}"
                f"未说出的剩余内容将不会再说。"
                f"请基于你自己的历史记录自行决定如何衔接。"
            )
        return s
