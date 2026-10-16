# -*- coding: utf-8 -*-
"""恒等矫正：原样返回，用于 demo 调试。"""
from __future__ import annotations

from .base import TextCorrector


class IdentityCorrector(TextCorrector):
    async def correct(self, raw: str) -> str:
        return raw
