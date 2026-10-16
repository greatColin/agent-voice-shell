# -*- coding: utf-8 -*-
"""识别文字矫正抽象层：字符串进、字符串出，内部实现自定义。"""
from __future__ import annotations

from abc import ABC, abstractmethod

from ..lifecycle import Lifecycle


class TextCorrector(ABC, Lifecycle):
    """矫正层抽象。raw 是 ASR 原文（或手打文本），返回矫正后的文本。"""

    @abstractmethod
    async def correct(self, raw: str) -> str:
        raise NotImplementedError
